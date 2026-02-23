"""Tests for CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimize_anything.cli import main


class TestCLI:
    def test_optimize_help(self, capsys):
        """Verify optimize subcommand help works."""
        try:
            main(["optimize", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "seed_file" in captured.out
        assert "--intake-json" in captured.out
        assert "--intake-file" in captured.out
        assert "--evaluator-cwd" in captured.out

    def test_explain(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        result = main(["explain", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        assert "11 chars" in captured.out

    def test_explain_with_objective(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        result = main(["explain", str(seed_file), "--objective", "Make formal"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Make formal" in captured.out

    def test_budget_short(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hi")
        result = main(["budget", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recommended_budget"] == 50

    def test_budget_medium(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("x" * 300)
        result = main(["budget", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recommended_budget"] == 100

    def test_optimize_missing_evaluator(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main(["optimize", str(seed_file)])
        assert result == 1

    def test_optimize_rejects_both_evaluator_inputs(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--evaluator-url",
                "http://localhost:8000/eval",
            ]
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "not both" in captured.err

    def test_missing_seed_file(self, capsys):
        result = main(["explain", "/nonexistent/file.txt"])
        assert result == 1
        captured = capsys.readouterr()
        assert "file not found" in captured.err

    def test_optimize_accepts_valid_intake_json(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        calls: dict[str, object] = {}

        def fake_command_evaluator(command: list[str], cwd: str | None = None):
            calls["command"] = command
            calls["cwd"] = cwd
            return "fake-command-evaluator"

        def fake_http_evaluator(url: str):
            calls["http_url"] = url
            return "fake-http-evaluator"

        class DummyResult:
            best_candidate = "best candidate"
            total_metric_calls = 7

        def fake_optimize_anything(*args, **kwargs):
            calls["evaluator"] = kwargs["evaluator"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            fake_command_evaluator,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            fake_http_evaluator,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize_anything,
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        intake_json = json.dumps(
            {"execution_mode": "http", "evaluator_cwd": " /tmp/from-intake "}
        )
        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--intake-json",
                intake_json,
            ]
        )
        assert result == 0

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["best_artifact"] == "best candidate"
        assert "score_summary" in payload
        assert "top_diagnostics" in payload
        assert calls["command"] == ["bash", "eval.sh"]
        assert calls["cwd"] == "/tmp/from-intake"
        assert "http_url" not in calls

    def test_optimize_outputs_canonical_summary(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "candidate v2"
            total_metric_calls = 5
            val_aggregate_scores = [0.2, 0.27, 0.33]
            val_aggregate_subscores = [
                {"clarity": 0.2, "safety": 0.1},
                {"clarity": 0.25, "safety": 0.2},
                {"clarity": 0.3, "safety": 0.24},
            ]
            best_idx = 2

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: "fake-evaluator",
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
            ]
        )
        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["best_artifact"] == "candidate v2"
        assert payload["score_summary"]["best"] == pytest.approx(0.33)
        assert payload["top_diagnostics"][0]["name"] == "clarity"
        assert "plateau_guidance" in payload

    def test_optimize_rejects_invalid_intake_json(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--intake-json",
                "{not-json",
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "invalid JSON for --intake-json" in captured.err

    def test_optimize_loads_intake_file(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        intake_file = tmp_path / "intake.json"
        intake_file.write_text(json.dumps({"execution_mode": "http"}))

        result = main(["optimize", str(seed_file), "--intake-file", str(intake_file)])
        assert result == 1

        captured = capsys.readouterr()
        assert "requires --evaluator-url" in captured.err

    def test_optimize_rejects_invalid_intake_spec(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        result = main(
            [
                "optimize",
                str(seed_file),
                "--intake-json",
                '{"execution_mode": "grpc"}',
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "invalid intake spec" in captured.err
        assert "execution_mode must be one of" in captured.err

    def test_optimize_rejects_output_directory_path(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        output_dir = tmp_path / "artifacts"
        output_dir.mkdir()

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-url",
                "http://localhost:8000/eval",
                "--output",
                str(output_dir),
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "--output must be a file path" in captured.err
        assert str(output_dir) in captured.err

    def test_optimize_preflight_rejects_missing_script_path(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--evaluator-cwd",
                str(tmp_path),
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "evaluator preflight failed" in captured.err
        assert "script path not found" in captured.err

    def test_optimize_preflight_rejects_bad_cwd(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        missing_cwd = tmp_path / "does-not-exist"

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--evaluator-cwd",
                str(missing_cwd),
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "evaluator preflight failed" in captured.err
        assert "cwd does not exist" in captured.err

    def test_optimize_preflight_rejects_invalid_json_response(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        script = tmp_path / "eval.sh"
        script.write_text("#!/usr/bin/env bash\necho 'not-json'\n")
        script.chmod(0o755)

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                str(script),
            ]
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "evaluator preflight failed" in captured.err
        assert "stdout is not valid JSON" in captured.err

    def test_optimize_preflight_success_path(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        script = tmp_path / "eval.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 0.25}\'\n')
        script.chmod(0o755)

        class DummyResult:
            best_candidate = "candidate after preflight"
            total_metric_calls = 1
            val_aggregate_scores = [0.25]

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
                "--evaluator-cwd",
                str(tmp_path),
            ]
        )
        assert result == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["best_artifact"] == "candidate after preflight"

    def test_generate_evaluator_basic(self, tmp_path: Path, capsys, monkeypatch):
        """generate-evaluator produces bash script with shebang by default."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            lambda **kwargs: "#!/usr/bin/env bash\n# mock evaluator\n",
        )

        result = main(
            ["generate-evaluator", str(seed_file), "--objective", "maximize clarity"]
        )
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.startswith("#!/usr/bin/env bash")

    def test_generate_evaluator_http_type(self, tmp_path: Path, capsys, monkeypatch):
        """--evaluator-type http produces Python script."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env python3\n# mock http evaluator\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        result = main(
            [
                "generate-evaluator",
                str(seed_file),
                "--objective",
                "maximize clarity",
                "--evaluator-type",
                "http",
            ]
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "python3" in captured.out
        assert calls["evaluator_type"] == "http"

    def test_generate_evaluator_with_intake_json(self, tmp_path: Path, capsys, monkeypatch):
        """intake execution_mode=http infers Python evaluator type."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env python3\n# inferred http\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        intake_json = json.dumps({"execution_mode": "http"})
        result = main(
            [
                "generate-evaluator",
                str(seed_file),
                "--objective",
                "maximize clarity",
                "--intake-json",
                intake_json,
            ]
        )
        assert result == 0
        assert calls["intake"]["execution_mode"] == "http"

    def test_generate_evaluator_explicit_type_overrides_intake(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """--evaluator-type command wins over intake execution_mode=http."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env bash\n# explicit override\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        intake_json = json.dumps({"execution_mode": "http"})
        result = main(
            [
                "generate-evaluator",
                str(seed_file),
                "--objective",
                "maximize clarity",
                "--evaluator-type",
                "command",
                "--intake-json",
                intake_json,
            ]
        )
        assert result == 0
        assert calls["evaluator_type"] == "command"

    def test_generate_evaluator_invalid_intake(self, tmp_path: Path, capsys):
        """Bad intake returns exit 1."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        result = main(
            [
                "generate-evaluator",
                str(seed_file),
                "--objective",
                "maximize clarity",
                "--intake-json",
                '{"execution_mode": "grpc"}',
            ]
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "invalid intake spec" in captured.err

    def test_generate_evaluator_missing_objective(self, capsys):
        """Missing --objective causes argparse error (exit 2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["generate-evaluator", "some-file.txt"])
        assert exc_info.value.code == 2

    def test_intake_defaults(self, capsys):
        """No args returns canonical defaults."""
        result = main(["intake"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["artifact_class"] == "general_text"
        assert data["execution_mode"] == "command"
        assert data["evaluation_pattern"] == "judge"
        assert len(data["quality_dimensions"]) == 3

    def test_intake_with_options(self, capsys):
        """Flag-based options normalize correctly."""
        result = main(
            [
                "intake",
                "--artifact-class",
                "prompt",
                "--execution-mode",
                "http",
                "--evaluation-pattern",
                "verification",
                "--hard-constraint",
                "must be under 500 chars",
            ]
        )
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["artifact_class"] == "prompt"
        assert data["execution_mode"] == "http"
        assert data["evaluation_pattern"] == "verification"
        assert "must be under 500 chars" in data["hard_constraints"]

    def test_intake_from_json(self, capsys):
        """--intake-json parses and normalizes."""
        intake_json = json.dumps(
            {"artifact_class": "config", "execution_mode": "http"}
        )
        result = main(["intake", "--intake-json", intake_json])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["artifact_class"] == "config"
        assert data["execution_mode"] == "http"

    def test_intake_from_file(self, tmp_path: Path, capsys):
        """--intake-file reads and normalizes."""
        intake_file = tmp_path / "intake.json"
        intake_file.write_text(json.dumps({"execution_mode": "http"}))
        result = main(["intake", "--intake-file", str(intake_file)])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["execution_mode"] == "http"

    def test_intake_invalid_execution_mode(self, capsys):
        """Bad execution_mode returns exit 1."""
        result = main(
            ["intake", "--intake-json", '{"execution_mode": "grpc"}']
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "invalid intake spec" in captured.err

    def test_intake_rejects_json_and_flags_together(self, capsys):
        """Mutually exclusive: --intake-json and flags together error."""
        result = main(
            [
                "intake",
                "--intake-json",
                '{"execution_mode": "http"}',
                "--artifact-class",
                "prompt",
            ]
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "not both" in captured.err or "mutually exclusive" in captured.err

    def test_optimize_summary_includes_failure_signal(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "candidate v1"
            total_metric_calls = 5
            val_aggregate_scores = [0.0, 0.0, 0.0]
            best_idx = 0

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: "fake-evaluator",
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main(
            [
                "optimize",
                str(seed_file),
                "--evaluator-command",
                "bash",
                "eval.sh",
            ]
        )
        assert result == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["evaluator_failure_signal"]["kind"] == "repeated_zero_scores"
