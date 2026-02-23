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
