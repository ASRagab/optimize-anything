"""Tests for CLI."""

from __future__ import annotations

import sys
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from optimize_anything.cli import main
from optimize_anything.cli_tools import _parse_validation_provider
from optimize_anything.llm_backends.base import BackendCapabilities, BackendStatus, CompletionResult
from optimize_anything.llm_backends.fallback import FallbackBackend
from optimize_anything.llm_backends.litellm_backend import LiteLLMBackend


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
        assert "openai/gpt-5.6-sol" in captured.out

    def test_generate_evaluator_help(self, capsys):
        """Verify generated evaluator help recommends the current judge model."""
        try:
            main(["generate-evaluator", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "openai/gpt-5.6-luna" in captured.out

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
        assert "only one of" in captured.err

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

    def test_optimize_summary_includes_early_stop_fields_when_stopped_early(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "candidate v2"
            total_metric_calls = 12
            num_full_val_evals = 4
            val_aggregate_scores = [0.2, 0.25]
            best_idx = 1

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
                "--early-stop",
                "--budget",
                "100",
            ]
        )
        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["early_stopped"] is True
        assert payload["stopped_at_iteration"] == 4

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
        """generate-evaluator produces judge script with shebang by default."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            lambda **kwargs: "#!/usr/bin/env python3\n# mock judge evaluator\n",
        )

        result = main(
            ["generate-evaluator", str(seed_file), "--objective", "maximize clarity"]
        )
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.startswith("#!/usr/bin/env python3")

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

    def test_generate_evaluator_default_type_is_judge(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env python3\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        result = main(["generate-evaluator", str(seed_file), "--objective", "maximize clarity"])
        assert result == 0
        assert calls["evaluator_type"] == "judge"

    def test_generate_evaluator_composite_type(self, tmp_path: Path, monkeypatch, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")

        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env python3\n# mock composite evaluator\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        result = main([
            "generate-evaluator",
            str(seed_file),
            "--objective",
            "maximize clarity",
            "--evaluator-type",
            "composite",
        ])
        assert result == 0
        assert calls["evaluator_type"] == "composite"
        assert "python3" in capsys.readouterr().out

    def test_generate_evaluator_dataset_flag_forwarded(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        calls: dict[str, object] = {}

        def fake_generate(**kwargs):
            calls.update(kwargs)
            return "#!/usr/bin/env python3\n"

        monkeypatch.setattr(
            "optimize_anything.evaluator_generator.generate_evaluator_script",
            fake_generate,
        )

        result = main([
            "generate-evaluator",
            str(seed_file),
            "--objective",
            "maximize clarity",
            "--dataset",
        ])
        assert result == 0
        assert calls["dataset"] is True

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

    def test_optimize_rejects_budget_zero(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test artifact")
        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "0",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "--budget must be at least 1" in captured.err

    def test_optimize_rejects_budget_negative(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test artifact")
        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "-5",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "--budget must be at least 1" in captured.err

    def test_optimize_accepts_budget_one(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "1",
        ])
        assert result == 0


    def test_optimize_task_model_is_forwarded_to_command_evaluator(
        self, tmp_path: Path, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured: dict[str, object] = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_command_evaluator(command, cwd=None, task_model=None, **kwargs):
            captured["task_model"] = task_model
            return lambda c, example=None: (0.5, {})

        monkeypatch.setattr("optimize_anything.evaluators.command_evaluator", fake_command_evaluator)
        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", lambda **kwargs: DummyResult())

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--task-model", "openai/gpt-4o-mini",
            "--budget", "1",
        ])
        assert rc == 0
        assert captured["task_model"] == "openai/gpt-4o-mini"

    def test_optimize_model_flag_passes_through_to_gepa(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """R4/R5: the API proposer keeps the chosen model through the completion adapter."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_config = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured_config["config"] = kwargs.get("config")
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize,
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--model", "openai/gpt-4o-mini",
            "--budget", "1",
        ])
        assert result == 0
        cfg = captured_config["config"]
        assert cfg.reflection.reflection_lm.model == "openai/gpt-4o-mini"

    def test_api_proposer_contributes_to_aggregate_run_provenance(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """R4: the API proposer appears in both events and the run aggregate."""
        from optimize_anything.llm_backends.base import CompletionResult
        from optimize_anything.llm_backends.litellm_backend import LiteLLMBackend

        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("seed")

        class DummyResult:
            best_candidate = "improved"
            total_metric_calls = 1

        def fake_complete(self, request):
            assert request.timeout_seconds is None
            return CompletionResult(
                text="improved", structured=None,
                requested_backend="api", actual_backend="api",
                requested_model=request.model, actual_model=request.model,
                auth_class="api", auth_source="openai_api", role=request.role,
            )

        def fake_optimize(**kwargs):
            assert kwargs["config"].reflection.reflection_lm("proposal") == "improved"
            return DummyResult()

        monkeypatch.setattr(LiteLLMBackend, "complete", fake_complete)
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)
        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda candidate: (0.5, {}),
        )

        rc = main([
            "optimize", str(seed_file), "--model", "openai/test", "--budget", "1",
            "--evaluator-command", "bash", "eval.sh",
        ])

        assert rc == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["llm_provenance"][0]["actual_backend"] == "api"
        assert summary["llm_provenance_summary"]["counts"]["role"] == {"proposer": 1}

    def test_optimize_model_env_var_fallback(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_config = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured_config["config"] = kwargs.get("config")
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize,
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setenv("OPTIMIZE_ANYTHING_MODEL", "gemini/gemini-2.0-flash")

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "1",
        ])
        assert result == 0
        cfg = captured_config["config"]
        assert cfg.reflection.reflection_lm.model == "gemini/gemini-2.0-flash"

    def test_optimize_uses_default_proposer_model(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_config = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured_config["config"] = kwargs.get("config")
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize,
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.delenv("OPTIMIZE_ANYTHING_MODEL", raising=False)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "1",
        ])
        assert result == 0
        cfg = captured_config["config"]
        assert cfg.reflection.reflection_lm.model == "openai/gpt-5.6-sol"

    def test_optimize_prints_progress_to_stderr(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "10",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Running optimization" in captured.err
        assert "budget: 10" in captured.err
        assert "bash eval.sh" in captured.err
        assert "Optimization complete." in captured.err
        json.loads(captured.out)

    def test_optimize_progress_shows_url_for_http_evaluator(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            lambda url: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-url", "http://localhost:8080/eval",
            "--budget", "5",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "http://localhost:8080/eval" in captured.err

    def test_optimize_catches_optimize_anything_exception(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        def raise_runtime(**kwargs):
            raise RuntimeError("gepa internal error")

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            raise_runtime,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "optimization failed" in captured.err
        assert "gepa internal error" in captured.err
        assert "Traceback" not in captured.err

    def test_optimize_catches_api_key_error(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        def raise_api_key(**kwargs):
            raise ValueError("Invalid api_key provided")

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            raise_api_key,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "API authentication error" in captured.err

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


    def test_optimize_judge_model_creates_llm_evaluator(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test artifact")
        captured_eval = {}

        class DummyResult:
            best_candidate = "improved"
            total_metric_calls = 3

        def fake_optimize(**kwargs):
            captured_eval["evaluator"] = kwargs.get("evaluator")
            return DummyResult()

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize,
        )

        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--objective", "maximize clarity",
            "--budget", "3",
        ])
        assert result == 0
        # Evaluator was set (the llm_judge_evaluator closure)
        assert captured_eval["evaluator"] is not None
        assert callable(captured_eval["evaluator"])
        # Progress message shows judge label
        captured = capsys.readouterr()
        assert "LLM judge (openai/gpt-4o-mini)" in captured.err

    def test_optimize_judge_model_requires_objective(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "--judge-model requires --objective or --judge-objective" in captured.err

    def test_optimize_judge_objective_overrides_objective(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_args = {}

        def fake_llm_judge(objective, *, model, **kwargs):
            captured_args["objective"] = objective
            captured_args["model"] = model
            return lambda c: (0.8, {"reasoning": "good"})

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.llm_judge.llm_judge_evaluator",
            fake_llm_judge,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--objective", "general objective",
            "--judge-objective", "specific judge objective",
            "--budget", "1",
        ])
        assert result == 0
        assert captured_args["objective"] == "specific judge objective"

    def test_optimize_judge_model_mutual_exclusion_with_command(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--evaluator-command", "bash", "eval.sh",
            "--objective", "test",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "only one of" in captured.err

    def test_optimize_judge_model_mutual_exclusion_with_url(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--evaluator-url", "http://localhost:8000/eval",
            "--objective", "test",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "only one of" in captured.err

    def test_optimize_no_evaluator_error_mentions_judge_model(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main(["optimize", str(seed_file)])
        assert result == 1
        captured = capsys.readouterr()
        assert "--judge-model" in captured.err

    def test_optimize_judge_model_with_intake_dimensions(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_args = {}

        def fake_llm_judge(objective, *, model, quality_dimensions=None, hard_constraints=None, **kwargs):
            captured_args["quality_dimensions"] = quality_dimensions
            captured_args["hard_constraints"] = hard_constraints
            return lambda c: (0.7, {"reasoning": "ok"})

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.llm_judge.llm_judge_evaluator",
            fake_llm_judge,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        intake_json = json.dumps({
            "execution_mode": "command",
            "quality_dimensions": [
                {"name": "clarity", "weight": 0.5},
                {"name": "brevity", "weight": 0.5},
            ],
            "hard_constraints": ["must be under 200 words"],
        })
        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--objective", "maximize quality",
            "--intake-json", intake_json,
            "--budget", "1",
        ])
        assert result == 0
        assert len(captured_args["quality_dimensions"]) == 2
        assert captured_args["hard_constraints"] == ["must be under 200 words"]

    def test_optimize_judge_model_passes_api_base(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured_args = {}

        def fake_llm_judge(objective, *, model, api_base=None, **kwargs):
            captured_args["api_base"] = api_base
            return lambda c: (0.5, {})

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.llm_judge.llm_judge_evaluator",
            fake_llm_judge,
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--judge-model", "openai/gpt-4o-mini",
            "--objective", "test",
            "--api-base", "https://openrouter.ai/api/v1",
            "--budget", "1",
        ])
        assert result == 0
        assert captured_args["api_base"] == "https://openrouter.ai/api/v1"

    def test_optimize_warns_evaluator_cwd_with_url(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """--evaluator-cwd with --evaluator-url should print a warning to stderr."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            lambda url: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-url", "http://localhost:8000/eval",
            "--evaluator-cwd", "/some/path",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "--evaluator-cwd has no effect" in captured.err

    def test_optimize_no_cwd_warning_without_cwd(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """No --evaluator-cwd warning when --evaluator-cwd is not set."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            lambda url: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-url", "http://localhost:8000/eval",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "--evaluator-cwd" not in captured.err

    def test_optimize_diff_flag_prints_diff_to_stderr(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """--diff prints a unified diff to stderr when seed and best differ."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("original content\n")

        class DummyResult:
            best_candidate = "improved content\n"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.7, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--diff",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "--- seed" in captured.err
        assert "+++ optimized" in captured.err
        assert "-original content" in captured.err
        assert "+improved content" in captured.err
        json.loads(captured.out)

    def test_optimize_diff_flag_identical_artifacts(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """--diff reports no diff when seed and best artifact are identical."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("same content\n")

        class DummyResult:
            best_candidate = "same content\n"
            total_metric_calls = 3

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--diff",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "no diff" in captured.err

    def test_optimize_no_diff_output_without_flag(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """Without --diff, no diff markers appear in stderr."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("original\n")

        class DummyResult:
            best_candidate = "improved\n"
            total_metric_calls = 5

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.7, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "--- seed" not in captured.err
        assert "+++ optimized" not in captured.err


class TestSeedlessAndScoreRange:
    def test_seedless_requires_objective_and_model(self, capsys):
        result = main([
            "optimize",
            "--no-seed",
            "--evaluator-command",
            "bash",
            "eval.sh",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert (
            "Error: seedless mode (--no-seed) requires both --objective and --model"
            in captured.err
        )

    def test_seedless_with_objective_and_model_passes_none_seed_candidate(
        self, capsys, monkeypatch
    ):
        captured_kwargs = {}

        class DummyResult:
            best_candidate = "generated"
            total_metric_calls = 1

        def fake_optimize_anything(**kwargs):
            captured_kwargs.update(kwargs)
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c, e=None: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize_anything,
        )

        result = main([
            "optimize",
            "--no-seed",
            "--objective",
            "improve quality",
            "--model",
            "openai/gpt-4o-mini",
            "--evaluator-command",
            "bash",
            "eval.sh",
            "--budget",
            "1",
        ])
        assert result == 0
        assert "seed_candidate" in captured_kwargs
        assert captured_kwargs["seed_candidate"] is None

    def test_seed_file_still_works_normally(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("seed artifact")
        captured_kwargs = {}

        class DummyResult:
            best_candidate = "generated"
            total_metric_calls = 1

        def fake_optimize_anything(**kwargs):
            captured_kwargs.update(kwargs)
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c, e=None: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            fake_optimize_anything,
        )

        result = main([
            "optimize",
            str(seed_file),
            "--evaluator-command",
            "bash",
            "eval.sh",
            "--budget",
            "1",
        ])
        assert result == 0
        assert captured_kwargs["seed_candidate"] == "seed artifact"

    def test_preflight_command_respects_score_range_modes(self, tmp_path: Path):
        from optimize_anything.preflight import _preflight_command_evaluator

        script = tmp_path / "eval.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 1.5}\'\n')
        script.chmod(0o755)

        err_unit = _preflight_command_evaluator([str(script)], cwd=None)
        assert err_unit is not None
        assert "between 0.0 and 1.0" in err_unit

        err_any = _preflight_command_evaluator([str(script)], cwd=None, score_range="any")
        assert err_any is None

    def test_preflight_http_respects_score_range_modes(self, monkeypatch):
        from optimize_anything.preflight import _preflight_http_evaluator

        class FakeResponse:
            status_code = 200
            text = '{"score": 1.5}'

            def raise_for_status(self):
                pass

            def json(self):
                return {"score": 1.5}

        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())

        err_unit = _preflight_http_evaluator("http://localhost:8000/eval")
        assert err_unit is not None
        assert "between 0.0 and 1.0" in err_unit

        err_any = _preflight_http_evaluator("http://localhost:8000/eval", score_range="any")
        assert err_any is None


class TestBudgetPrecedence:
    def test_budget_explicit_100_preserved_over_spec(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """Explicit --budget 100 must not be overridden by spec budget."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test content")
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text(
            '[optimization]\nobjective = "test"\nbudget = 50\n'
        )

        captured_budget = []

        def fake_optimize(**kwargs):
            captured_budget.append(kwargs.get("config"))
            return {"best_candidate": "done", "best_score": 1.0}

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything", fake_optimize
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "echo", '{"score": 1.0}',
            "--spec-file", str(spec_file),
            "--budget", "100",
        ])
        assert result == 0
        assert len(captured_budget) == 1
        config = captured_budget[0]
        assert config.engine.max_metric_calls == 100


class TestEngineConfigWiring:
    def _run_optimize_with_config(self, tmp_path: Path, monkeypatch, *extra_args: str):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "1",
            *extra_args,
        ])
        return result, captured

    def test_default_sets_engine_parallel_without_worker_override(
        self, tmp_path: Path, monkeypatch
    ):
        captured_engine_kwargs = {}

        class FakeEngineConfig:
            def __init__(self, **kwargs):
                captured_engine_kwargs.update(kwargs)
                self.parallel = kwargs["parallel"]
                self.max_workers = kwargs.get("max_workers")
                self.cache_evaluation = kwargs["cache_evaluation"]
                self.run_dir = kwargs["run_dir"]

        class FakeGEPAConfig:
            def __init__(self, **kwargs):
                self.engine = kwargs["engine"]
                self.stop_callbacks = kwargs.get("stop_callbacks")

        monkeypatch.setattr("gepa.optimize_anything.EngineConfig", FakeEngineConfig)
        monkeypatch.setattr("gepa.optimize_anything.GEPAConfig", FakeGEPAConfig)

        result, captured = self._run_optimize_with_config(tmp_path, monkeypatch)

        assert result == 0
        assert captured["config"].engine.parallel is True
        assert "max_workers" not in captured_engine_kwargs
        assert captured_engine_kwargs["track_best_outputs"] is False
        assert "sampling_strategy" not in captured_engine_kwargs

    def test_proposals_per_iteration_sets_same_parent_sampling(
        self, tmp_path: Path, monkeypatch
    ):
        from gepa.strategies.proposal_sampling import SameParentSampling

        result, captured = self._run_optimize_with_config(
            tmp_path,
            monkeypatch,
            "--proposals-per-iteration",
            "4",
        )

        assert result == 0
        sampling = captured["config"].engine.sampling_strategy
        assert isinstance(sampling, SameParentSampling)
        assert sampling.n == 4

    def test_proposals_per_iteration_one_preserves_default_sampling(
        self, tmp_path: Path, monkeypatch
    ):
        captured_engine_kwargs = {}

        class FakeEngineConfig:
            def __init__(self, **kwargs):
                captured_engine_kwargs.update(kwargs)

        class FakeGEPAConfig:
            def __init__(self, **kwargs):
                self.engine = kwargs["engine"]

        monkeypatch.setattr("gepa.optimize_anything.EngineConfig", FakeEngineConfig)
        monkeypatch.setattr("gepa.optimize_anything.GEPAConfig", FakeGEPAConfig)

        result, _ = self._run_optimize_with_config(
            tmp_path,
            monkeypatch,
            "--proposals-per-iteration",
            "1",
        )

        assert result == 0
        assert "sampling_strategy" not in captured_engine_kwargs

    def test_proposals_per_iteration_must_be_positive(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--proposals-per-iteration", "0",
        ])

        assert result == 1
        assert (
            "--proposals-per-iteration must be a positive integer"
            in capsys.readouterr().err
        )

    def test_no_parallel_flag_sets_engine_parallel_false(
        self, tmp_path: Path, monkeypatch
    ):
        result, captured = self._run_optimize_with_config(
            tmp_path, monkeypatch, "--no-parallel"
        )

        assert result == 0
        assert captured["config"].engine.parallel is False

    def test_no_parallel_rejects_worker_count(
        self, tmp_path: Path, capsys
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--no-parallel",
            "--workers", "4",
            "--budget", "1",
        ])

        assert result == 1
        assert "--workers requires parallel execution" in capsys.readouterr().err

    def test_parallel_flag_sets_engine_parallel(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--parallel",
            "--budget", "1",
        ])
        assert result == 0
        assert captured["config"].engine.parallel is True

    def test_workers_sets_max_workers(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--workers", "4",
            "--budget", "1",
        ])
        assert result == 0
        assert captured["config"].engine.max_workers == 4

    def test_workers_auto_enables_parallel(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--workers", "4",
            "--budget", "1",
        ])
        assert result == 0
        assert captured["config"].engine.parallel is True

    def test_cache_flag_sets_cache_evaluation(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--cache",
            "--budget", "1",
        ])
        assert result == 0
        assert captured["config"].engine.cache_evaluation is True

    def test_run_dir_passes_through_to_engine_config(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        run_dir = tmp_path / "runs"
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)
        monkeypatch.setattr(
            "optimize_anything.cli_optimize._timestamped_run_dir",
            lambda base: str(Path(base) / "run-20260303-150000"),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--run-dir", str(run_dir),
            "--budget", "1",
        ])
        assert result == 0
        assert captured["config"].engine.run_dir.endswith("run-20260303-150000")

    def test_early_stop_flag_creates_stop_callbacks(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)
        monkeypatch.setattr("optimize_anything.evaluators.command_evaluator", lambda command, cwd=None, **kwargs: lambda c: (0.5, {}))
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--early-stop",
            "--budget", "10",
        ])
        assert rc == 0
        assert captured["config"].stop_callbacks is not None
        assert len(captured["config"].stop_callbacks) == 1

    def test_early_stop_auto_enabled_when_budget_above_30(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 10

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)
        monkeypatch.setattr("optimize_anything.evaluators.command_evaluator", lambda command, cwd=None, **kwargs: lambda c: (0.5, {}))
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "31",
        ])
        assert rc == 0
        assert captured["config"].stop_callbacks is not None

    def test_cache_from_requires_cache_flag(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--cache-from", str(tmp_path),
            "--budget", "10",
        ])
        assert rc == 1
        assert "requires --cache" in capsys.readouterr().err

    def test_cache_from_rejects_missing_source_directory(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        run_dir = tmp_path / "runs"
        missing_source = tmp_path / "does-not-exist"

        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--cache",
            "--cache-from", str(missing_source),
            "--run-dir", str(run_dir),
            "--budget", "10",
        ])
        assert rc == 1
        err = capsys.readouterr().err
        assert f"Error: --cache-from directory does not exist: {missing_source}" in err

    def test_cache_from_rejects_missing_fitness_cache_subdir(self, tmp_path: Path, capsys, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        run_dir = tmp_path / "runs"
        source_run = tmp_path / "source-run"
        source_run.mkdir()

        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--cache",
            "--cache-from", str(source_run),
            "--run-dir", str(run_dir),
            "--budget", "10",
        ])
        assert rc == 1
        err = capsys.readouterr().err
        assert (
            f"Error: no fitness_cache found in --cache-from directory: {source_run / 'fitness_cache'}"
            in err
        )

    def test_early_stop_not_auto_enabled_when_budget_30_or_less(self, tmp_path: Path, monkeypatch):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        captured = {}

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 10

        def fake_optimize(**kwargs):
            captured["config"] = kwargs["config"]
            return DummyResult()

        monkeypatch.setattr("optimize_anything.cli._preflight_command_evaluator", lambda command, cwd=None: None)
        monkeypatch.setattr("optimize_anything.evaluators.command_evaluator", lambda command, cwd=None, **kwargs: lambda c: (0.5, {}))
        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)

        rc = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--budget", "30",
        ])
        assert rc == 0
        assert captured["config"].stop_callbacks is None


class TestRunDir:
    def test_run_dir_creates_directory_with_expected_files(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("initial seed content")
        run_dir = tmp_path / "runs"

        class DummyResult:
            best_candidate = "optimized content"
            total_metric_calls = 3

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.7, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--run-dir", str(run_dir),
        ])
        assert result == 0

        run_dirs = list(run_dir.iterdir())
        assert len(run_dirs) == 1
        created = run_dirs[0]
        assert created.name.startswith("run-")

        assert (created / "seed.txt").read_text() == "initial seed content"
        assert (created / "best_artifact.txt").read_text() == "optimized content"
        summary = json.loads((created / "summary.json").read_text())
        assert summary["best_artifact"] == "optimized content"

    def test_run_dir_path_in_stdout_summary(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        run_dir = tmp_path / "runs"

        class DummyResult:
            best_candidate = "best"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--run-dir", str(run_dir),
        ])
        out = json.loads(capsys.readouterr().out)
        assert "run_dir" in out
        assert str(run_dir) in out["run_dir"]

    def test_run_dir_write_failure_does_not_exit_nonzero(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """Writing run-dir artifacts can fail without making optimize fail overall."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        run_dir = tmp_path / "run-dir"

        class DummyResult:
            best_candidate = "best"
            total_metric_calls = 1

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.5, {}),
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        def fake_save_run_dir(**kwargs):
            print("Warning: failed to write run-dir '/fake/path': simulated failure", file=sys.stderr)
            return None

        monkeypatch.setattr("optimize_anything.cli_optimize._save_run_dir", fake_save_run_dir)

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--run-dir", str(run_dir),
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "failed to write" in captured.err


class TestHttpEvaluatorPreflight:
    def test_preflight_passes_on_valid_response(self, monkeypatch):
        from optimize_anything.preflight import _preflight_http_evaluator

        class FakeResponse:
            status_code = 200
            text = '{"score": 0.5}'
            def raise_for_status(self): pass
            def json(self): return {"score": 0.5}

        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())
        result = _preflight_http_evaluator("http://localhost:8000/eval")
        assert result is None

    def test_preflight_fails_on_connection_refused(self, monkeypatch):
        import httpx
        from optimize_anything.preflight import _preflight_http_evaluator

        monkeypatch.setattr("httpx.post", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("refused")))
        result = _preflight_http_evaluator("http://localhost:9999/eval")
        assert result is not None
        assert "connection refused" in result.lower()

    def test_preflight_fails_on_timeout(self, monkeypatch):
        import httpx
        from optimize_anything.preflight import _preflight_http_evaluator

        monkeypatch.setattr("httpx.post", lambda *a, **kw: (_ for _ in ()).throw(httpx.TimeoutException("timed out")))
        result = _preflight_http_evaluator("http://localhost:8000/eval")
        assert result is not None
        assert "timed out" in result.lower()

    def test_preflight_fails_on_non_json_response(self, monkeypatch):
        from optimize_anything.preflight import _preflight_http_evaluator

        class FakeResponse:
            status_code = 200
            text = "not json at all"
            def raise_for_status(self): pass
            def json(self): raise ValueError("not json")

        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())
        result = _preflight_http_evaluator("http://localhost:8000/eval")
        assert result is not None
        assert "non-JSON" in result

    def test_preflight_fails_on_missing_score_field(self, monkeypatch):
        from optimize_anything.preflight import _preflight_http_evaluator

        class FakeResponse:
            status_code = 200
            text = '{"feedback": "no score here"}'
            def raise_for_status(self): pass
            def json(self): return {"feedback": "no score here"}

        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())
        result = _preflight_http_evaluator("http://localhost:8000/eval")
        assert result is not None
        assert "score" in result.lower()

    def test_optimize_calls_http_preflight(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """When --evaluator-url is used, _preflight_http_evaluator is called."""
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        preflight_calls = []

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: (preflight_calls.append(url), None)[1],
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            lambda url: lambda c: (0.5, {}),
        )

        class DummyResult:
            best_candidate = "x"
            total_metric_calls = 3

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-url", "http://localhost:8000/eval",
        ])
        assert result == 0
        assert "http://localhost:8000/eval" in preflight_calls

    def test_optimize_returns_1_on_http_preflight_failure(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: "Error: connection refused",
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-url", "http://localhost:9999/eval",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "connection refused" in captured.err


class TestEchoScoreEvaluator:
    """Tests for examples/evaluators/echo_score.sh."""

    def test_echo_score_evaluator_valid_json(self, project_root):
        import subprocess

        evaluator = project_root / "examples" / "evaluators" / "echo_score.sh"
        payload = json.dumps({"candidate": "hello world"})
        proc = subprocess.run(
            ["bash", str(evaluator)],
            input=payload, capture_output=True, text=True,
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert "score" in result
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_echo_score_evaluator_empty_candidate(self, project_root):
        import subprocess

        evaluator = project_root / "examples" / "evaluators" / "echo_score.sh"
        payload = json.dumps({"candidate": ""})
        proc = subprocess.run(
            ["bash", str(evaluator)],
            input=payload, capture_output=True, text=True,
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["score"] == 0.0
        assert result["length"] == 0


class TestScoreCommand:
    def test_score_help(self, capsys):
        try:
            main(["score", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "artifact_file" in captured.out
        assert "--evaluator-command" in captured.out

    def test_score_requires_evaluator(self, tmp_path: Path, capsys):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("some text")
        result = main(["score", str(artifact)])
        assert result == 1
        captured = capsys.readouterr()
        assert "provide --evaluator-command" in captured.err

    def test_score_rejects_both_evaluator_inputs(self, tmp_path: Path, capsys):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("some text")
        result = main([
            "score", str(artifact),
            "--evaluator-command", "bash", "eval.sh",
            "--evaluator-url", "http://localhost:8000/eval",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "only one" in captured.err

    def test_score_missing_artifact(self, capsys):
        result = main([
            "score", "/nonexistent/artifact.txt",
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "file not found" in captured.err

    def test_score_command_evaluator_returns_json(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("hello world")

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None, **kwargs: lambda c: (0.75, {"feedback": "looks good"}),
        )

        result = main([
            "score", str(artifact),
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["score"] == 0.75
        assert payload["feedback"] == "looks good"

    def test_score_http_evaluator_returns_json(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("hello world")

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_http_evaluator",
            lambda url, **kwargs: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.http_evaluator",
            lambda url: lambda c: (0.9, {"confidence": 0.85}),
        )

        result = main([
            "score", str(artifact),
            "--evaluator-url", "http://localhost:8000/eval",
        ])
        assert result == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["score"] == 0.9

    def test_score_evaluator_exception_returns_1(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("test")

        def failing_evaluator(candidate):
            raise ConnectionError("connection refused")

        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: failing_evaluator,
        )

        result = main([
            "score", str(artifact),
            "--evaluator-command", "bash", "eval.sh",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "evaluator call failed" in captured.err


class TestScoreJudgeModel:
    """Tests for score subcommand with --judge-model."""

    def test_score_with_judge_model(self, tmp_path, monkeypatch):
        """score subcommand works with --judge-model."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test artifact content for scoring.")

        mock_response = type("R", (), {
            "choices": [type("C", (), {
                "message": type("M", (), {"content": '{"score": 0.75, "reasoning": "Good"}'})()
            })()]
        })()

        monkeypatch.setattr(
            "litellm.completion",
            lambda **kw: mock_response,
        )

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--judge-model", "openai/gpt-5.1",
                "--objective", "Maximize clarity",
            ])

        assert rc == 0, f"stderr: {stderr.getvalue()}"
        result = json.loads(stdout.getvalue())
        assert "score" in result
        assert result["score"] == 0.75

    def test_score_judge_model_requires_objective(self, tmp_path):
        """score with --judge-model fails without --objective."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main(["score", str(artifact), "--judge-model", "openai/gpt-5.1"])

        assert rc == 1
        assert "objective" in stderr.getvalue().lower()

    def test_score_rejects_judge_and_command(self, tmp_path):
        """score subcommand rejects --judge-model with --evaluator-command."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--evaluator-command", "echo", "{}",
                "--judge-model", "openai/gpt-5.1",
                "--objective", "test",
            ])

        assert rc == 1
        assert "only one" in stderr.getvalue().lower()

    def test_score_rejects_judge_and_url(self, tmp_path):
        """score subcommand rejects --judge-model with --evaluator-url."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--evaluator-url", "http://localhost:9999",
                "--judge-model", "openai/gpt-5.1",
                "--objective", "test",
            ])

        assert rc == 1
        assert "only one" in stderr.getvalue().lower()

    def test_score_judge_with_judge_objective(self, tmp_path, monkeypatch):
        """--judge-objective overrides --objective for LLM judge scoring."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        captured_prompt = {}
        mock_response = type("R", (), {
            "choices": [type("C", (), {
                "message": type("M", (), {"content": '{"score": 0.8, "reasoning": "Nice"}'})()
            })()]
        })()

        def mock_completion(**kwargs):
            captured_prompt["messages"] = kwargs.get("messages", [])
            return mock_response

        monkeypatch.setattr(
            "litellm.completion",
            mock_completion,
        )

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--judge-model", "openai/gpt-5.1",
                "--objective", "general objective",
                "--judge-objective", "specific judge objective",
            ])

        assert rc == 0
        # Verify the judge objective was used (appears in the prompt)
        user_msg = captured_prompt["messages"][1]["content"]
        assert "specific judge objective" in user_msg

    def test_score_no_evaluator_shows_three_options(self, tmp_path):
        """score with no evaluator mentions all three options in error."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main(["score", str(artifact)])

        assert rc == 1
        err = stderr.getvalue().lower()
        assert "judge-model" in err or "judge" in err

    def test_score_judge_with_intake_json_forwards_dimensions(self, tmp_path, monkeypatch):
        """score --judge-model --intake-json forwards quality dimensions to the judge."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test artifact for dimension forwarding.")

        intake = {
            "quality_dimensions": [
                {"name": "clarity", "weight": 0.6},
                {"name": "brevity", "weight": 0.4},
            ],
        }

        captured_kwargs = {}
        mock_response = type("R", (), {
            "choices": [type("C", (), {
                "message": type("M", (), {
                    "content": json.dumps({
                        "score": 0.8,
                        "dimension_scores": {"clarity": 0.85, "brevity": 0.7},
                        "hard_constraints_satisfied": True,
                        "reasoning": "Good",
                    })
                })()
            })()]
        })()

        def mock_completion(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        monkeypatch.setattr("litellm.completion", mock_completion)

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--judge-model", "openai/gpt-5.1",
                "--objective", "Score quality",
                "--intake-json", json.dumps(intake),
            ])

        assert rc == 0, f"stderr: {stderr.getvalue()}"
        # Verify dimensions appeared in the prompt
        user_msg = captured_kwargs["messages"][1]["content"]
        assert "clarity" in user_msg
        assert "brevity" in user_msg

    def test_score_judge_with_api_base_forwarding(self, tmp_path, monkeypatch):
        """score --judge-model --api-base forwards api_base to litellm."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test artifact for api-base forwarding.")

        captured_kwargs = {}
        mock_response = type("R", (), {
            "choices": [type("C", (), {
                "message": type("M", (), {"content": '{"score": 0.7, "reasoning": "OK"}'})()
            })()]
        })()

        def mock_completion(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        monkeypatch.setattr("litellm.completion", mock_completion)

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "score", str(artifact),
                "--judge-model", "openai/gpt-5.1",
                "--objective", "Score quality",
                "--api-base", "http://localhost:11434/v1",
            ])

        assert rc == 0, f"stderr: {stderr.getvalue()}"
        # litellm renames api_base to base_url internally
        assert captured_kwargs.get("api_base") == "http://localhost:11434/v1" or \
            captured_kwargs.get("base_url") == "http://localhost:11434/v1"


class TestValidateCommand:
    def test_validate_help(self, capsys):
        try:
            main(["validate", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "--providers" in captured.out
        assert "--objective" in captured.out

    def test_validate_requires_objective(self, tmp_path: Path):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        with pytest.raises(SystemExit) as exc_info:
            main([
                "validate",
                str(artifact),
                "--providers",
                "openai/gpt-4o-mini",
                "anthropic/claude-sonnet-4-5",
            ])
        assert exc_info.value.code == 2

    def test_validate_providers_requires_at_least_two_models(self, tmp_path: Path, capsys):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "--objective",
            "Score quality",
        ])
        assert rc == 1
        assert "at least 2" in capsys.readouterr().err

    def test_validate_calls_llm_judge_for_each_provider(self, tmp_path: Path, monkeypatch):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        calls: list[tuple[str, str]] = []

        def fake_llm_judge(objective, *, model, **kwargs):
            def _eval(candidate):
                calls.append((objective, model))
                return 0.8, {"reasoning": f"ok-{model}"}
            return _eval

        monkeypatch.setattr("optimize_anything.llm_judge.llm_judge_evaluator", fake_llm_judge)

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-5",
            "google/gemini-2.0-flash",
            "--objective",
            "Score quality",
        ])
        assert rc == 0
        assert calls == [
            ("Score quality", "openai/gpt-4o-mini"),
            ("Score quality", "anthropic/claude-sonnet-4-5"),
            ("Score quality", "google/gemini-2.0-flash"),
        ]

    def test_validate_outputs_aggregates(self, tmp_path: Path, capsys, monkeypatch):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        by_model = {
            "openai/gpt-4o-mini": 0.6,
            "anthropic/claude-sonnet-4-5": 0.8,
        }

        def fake_llm_judge(objective, *, model, **kwargs):
            def _eval(candidate):
                return by_model[model], {"reasoning": f"r-{model}"}
            return _eval

        monkeypatch.setattr("optimize_anything.llm_judge.llm_judge_evaluator", fake_llm_judge)

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-5",
            "--objective",
            "Score quality",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["providers"]) == 2
        assert payload["mean"] == pytest.approx(0.7)
        assert payload["stddev"] == pytest.approx(0.1414213562)
        assert payload["min"] == pytest.approx(0.6)
        assert payload["max"] == pytest.approx(0.8)

    def test_validate_single_provider_failure_continues(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        by_model = {
            "openai/gpt-4o-mini": 0.6,
            "google/gemini-2.0-flash": 0.8,
        }

        def fake_llm_judge(objective, *, model, **kwargs):
            if model == "anthropic/claude-sonnet-4-5":
                raise RuntimeError("provider unavailable")

            def _eval(candidate):
                return by_model[model], {"reasoning": f"r-{model}"}

            return _eval

        monkeypatch.setattr("optimize_anything.llm_judge.llm_judge_evaluator", fake_llm_judge)

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-5",
            "google/gemini-2.0-flash",
            "--objective",
            "Score quality",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["successful"] == 2
        assert payload["summary"]["failed"] == 1
        failed = [item for item in payload["results"] if item["score"] is None]
        assert len(failed) == 1
        assert failed[0]["provider"] == "anthropic/claude-sonnet-4-5"
        assert "provider unavailable" in failed[0]["error"]

    def test_validate_all_providers_fail(self, tmp_path: Path, capsys, monkeypatch):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        def fake_llm_judge(objective, *, model, **kwargs):
            raise RuntimeError(f"down-{model}")

        monkeypatch.setattr("optimize_anything.llm_judge.llm_judge_evaluator", fake_llm_judge)

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-5",
            "--objective",
            "Score quality",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Error: all providers failed" in captured.err
        payload = json.loads(captured.out)
        assert payload["summary"]["successful"] == 0
        assert payload["summary"]["failed"] == 2
        assert payload["mean"] is None
        assert payload["stddev"] is None
        assert payload["min"] is None
        assert payload["max"] is None

    def test_validate_mixed_success_stats(self, tmp_path: Path, capsys, monkeypatch):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        by_model = {
            "openai/gpt-4o-mini": 0.2,
            "anthropic/claude-sonnet-4-5": 0.6,
        }

        def fake_llm_judge(objective, *, model, **kwargs):
            if model == "google/gemini-2.0-flash":
                raise RuntimeError("timeout")

            def _eval(candidate):
                return by_model[model], {"reasoning": f"r-{model}"}

            return _eval

        monkeypatch.setattr("optimize_anything.llm_judge.llm_judge_evaluator", fake_llm_judge)

        rc = main([
            "validate",
            str(artifact),
            "--providers",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-5",
            "google/gemini-2.0-flash",
            "--objective",
            "Score quality",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["successful"] == 2
        assert payload["summary"]["failed"] == 1
        assert payload["mean"] == pytest.approx(0.4)
        assert payload["stddev"] == pytest.approx(0.282842712474619)
        assert payload["min"] == pytest.approx(0.2)
        assert payload["max"] == pytest.approx(0.6)


class TestAnalyzeCommand:
    """Tests for the analyze subcommand."""

    def test_analyze_help(self, capsys):
        try:
            main(["analyze", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "artifact_file" in captured.out
        assert "--judge-model" in captured.out
        assert "--objective" in captured.out

    def test_analyze_happy_path(self, tmp_path, monkeypatch):
        artifact = tmp_path / "readme.md"
        artifact.write_text("# My Project\nSome content here.")

        score_response = json.dumps({"score": 0.82, "reasoning": "Good but verbose"})
        dims_response = json.dumps({
            "dimensions": [
                {"name": "clarity", "weight": 0.4, "score": 0.9, "description": "How clear"},
                {"name": "conciseness", "weight": 0.6, "score": 0.65, "description": "Brevity"},
            ]
        })

        call_count = 0
        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            resp = type("R", (), {
                "choices": [type("C", (), {
                    "message": type("M", (), {
                        "content": score_response if call_count == 1 else dims_response
                    })()
                })()]
            })()
            return resp

        monkeypatch.setattr("litellm.completion", mock_completion)

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "analyze", str(artifact),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "Optimize for OSS quality",
            ])

        assert rc == 0, f"stderr: {stderr.getvalue()}"
        result = json.loads(stdout.getvalue())
        assert result["current_score"] == pytest.approx(0.82)
        assert len(result["suggested_dimensions"]) == 2
        assert "intake_json" in result
        # Verify intake_json is valid and usable
        intake = json.loads(result["intake_json"])
        assert "quality_dimensions" in intake
        assert "recommendation" in result

    def test_analyze_missing_file(self, tmp_path):
        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([
                "analyze", str(tmp_path / "nonexistent.txt"),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "test",
            ])
        assert rc == 1
        assert "not found" in stderr.getvalue().lower()

    def test_analyze_llm_error(self, tmp_path, monkeypatch):
        artifact = tmp_path / "test.txt"
        artifact.write_text("content")

        monkeypatch.setattr(
            "litellm.completion",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("API down")),
        )

        import io, contextlib
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([
                "analyze", str(artifact),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "test",
            ])
        assert rc == 1
        assert "error" in stderr.getvalue().lower()

    def test_analyze_requires_judge_model(self):
        """analyze without --judge-model should fail at argparse level."""
        with pytest.raises(SystemExit):
            main(["analyze", "some_file.txt", "--objective", "test"])

    def test_analyze_requires_objective(self):
        """analyze without --objective should fail at argparse level."""
        with pytest.raises(SystemExit):
            main(["analyze", "some_file.txt", "--judge-model", "openai/gpt-4o-mini"])


class TestJudgePlateauAdvisory:
    """Tests for judge-specific plateau detection advisory output."""

    def test_plateau_advisory_shown_with_judge_model(self, tmp_path, monkeypatch):
        """When plateau detected + --judge-model, print judge-specific suggestions."""
        seed = tmp_path / "seed.txt"
        seed.write_text("test artifact")

        class PlateauResult:
            best_candidate = "test artifact"
            total_metric_calls = 5
            # Flat scores trigger plateau: spread < 0.01, total_gain < 0.02
            val_aggregate_scores = [0.88, 0.88, 0.88, 0.88, 0.88]

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kw: PlateauResult(),
        )

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "optimize", str(seed),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "maximize quality",
                "--budget", "5",
            ])

        assert rc == 0
        err = stderr.getvalue()
        assert "Plateau detected with LLM judge" in err
        assert "optimize-anything analyze" in err
        assert "--model" in err
        assert "--intake-json" in err

    def test_no_advisory_without_judge_model(self, tmp_path, monkeypatch):
        """Plateau advisory is not printed for command evaluators."""
        seed = tmp_path / "seed.txt"
        seed.write_text("test")

        class PlateauResult:
            best_candidate = "test"
            total_metric_calls = 5
            val_aggregate_scores = [0.88, 0.88, 0.88, 0.88, 0.88]

        eval_script = tmp_path / "eval.sh"
        eval_script.write_text('#!/bin/bash\necho \'{"score": 0.88}\'')
        eval_script.chmod(0o755)

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kw: PlateauResult(),
        )

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "optimize", str(seed),
                "--evaluator-command", "bash", str(eval_script),
                "--budget", "5",
            ])

        assert rc == 0
        err = stderr.getvalue()
        assert "Plateau detected with LLM judge" not in err

    def test_no_advisory_when_no_plateau(self, tmp_path, monkeypatch):
        """No advisory when scores are improving."""
        seed = tmp_path / "seed.txt"
        seed.write_text("test")

        class ImprovingResult:
            best_candidate = "better"
            total_metric_calls = 5
            val_aggregate_scores = [0.50, 0.60, 0.70, 0.80, 0.90]

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kw: ImprovingResult(),
        )

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "optimize", str(seed),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "maximize quality",
                "--budget", "5",
            ])

        assert rc == 0
        assert "Plateau detected with LLM judge" not in stderr.getvalue()

    def test_advisory_omits_intake_hint_when_intake_provided(self, tmp_path, monkeypatch):
        """When --intake-json is provided, don't suggest it again."""
        seed = tmp_path / "seed.txt"
        seed.write_text("test artifact")

        class PlateauResult:
            best_candidate = "test artifact"
            total_metric_calls = 5
            val_aggregate_scores = [0.88, 0.88, 0.88, 0.88, 0.88]

        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kw: PlateauResult(),
        )

        intake = json.dumps({
            "quality_dimensions": [{"name": "clarity", "weight": 1.0}],
        })

        import io, contextlib
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                "optimize", str(seed),
                "--judge-model", "openai/gpt-4o-mini",
                "--objective", "maximize quality",
                "--budget", "5",
                "--intake-json", intake,
            ])

        assert rc == 0
        err = stderr.getvalue()
        assert "Plateau detected with LLM judge" in err
        # Should NOT suggest --intake-json since user already provided it
        assert "Try --intake-json" not in err


# ---------------------------------------------------------------------------
# Shared fakes for the create_backend seam (R1, R2, R6, R7 gap-closing tests)
# ---------------------------------------------------------------------------


class _FakeSubscriptionBackend:
    """A minimal CompletionBackend stand-in that records every request it
    receives and returns a canned, schema-shaped CompletionResult, so tests
    can prove a command reached the seam without ever touching a real
    Codex/Claude process or litellm."""

    capabilities = BackendCapabilities(usage_reporting=False)

    _AUTH = {
        "codex": ("subscription", "chatgpt"),
        "claude": ("subscription", "claude_subscription"),
        "api": ("api", "other_api"),
    }

    def __init__(self, backend_name, requests):
        self.backend_name = backend_name
        self._requests = requests

    def preflight(self):
        auth_class, auth_source = self._AUTH[self.backend_name]
        return BackendStatus(
            ready=True, backend=self.backend_name, auth_class=auth_class, auth_source=auth_source,
        )

    def complete(self, request):
        self._requests.append(request)
        properties = (request.output_schema or {}).get("properties", {})
        if "dimensions" in properties:
            text = json.dumps({
                "dimensions": [
                    {"name": "clarity", "weight": 1.0, "score": 0.9, "description": "fake dimension"},
                ],
            })
        else:
            text = json.dumps({"score": 0.91, "reasoning": "fake backend response"})
        auth_class, auth_source = self._AUTH[self.backend_name]
        return CompletionResult(
            text=text,
            structured=None,
            requested_backend=self.backend_name,
            actual_backend=self.backend_name,
            requested_model=request.model,
            actual_model=request.model,
            auth_class=auth_class,
            auth_source=auth_source,
            role=request.role,
        )


class _BackendCallRecorder:
    """Fake for optimize_anything.llm_backends.factory.create_backend.

    Matches the real signature `(spec, *, role, coordinator=None)` used by
    both call sites (cli_tools._completion_backend omits coordinator;
    cli_optimize._configured_optimization_backends passes it), records the
    (spec, role) pair, and hands back a _FakeSubscriptionBackend that
    shares one requests list across every call.
    """

    def __init__(self):
        self.calls: list = []
        self.requests: list = []
        self.stray_calls: list = []

    def __call__(self, spec, *, role, coordinator=None):
        self.calls.append((spec, role))
        return _FakeSubscriptionBackend(spec.backend, self.requests)


@pytest.fixture
def fake_backend_seam(monkeypatch):
    """R1/R2/R6/R7: intercept create_backend at the seam cli_tools and
    cli_optimize both use, and make litellm.completion raise if reached, so
    every test using this fixture proves its command routed through the
    fake subscription backend rather than any stray real API call.
    """
    recorder = _BackendCallRecorder()
    monkeypatch.setattr("optimize_anything.llm_backends.factory.create_backend", recorder)

    def _tripwire(**kwargs):
        recorder.stray_calls.append(kwargs)
        raise AssertionError(
            "litellm.completion must not be called while the create_backend fake is active"
        )

    monkeypatch.setattr("litellm.completion", _tripwire)
    return recorder


def _spy_and_capture(monkeypatch, target):
    """Patch a _cmd_* dispatch target with a spy that records the parsed
    argparse.Namespace it receives and returns 0, so flag-parsing tests can
    assert on real parser output without running any command logic."""
    captured: list = []

    def spy(args):
        captured.append(args)
        return 0

    monkeypatch.setattr(target, spy)
    return captured


def _capture_prepared_optimize_args(monkeypatch):
    """R6b: stub _optimization_backends and _run_optimize so optimize's
    real argument-preparation path -- including _apply_spec_to_args, which
    implements CLI-over-TOML precedence -- runs to completion, and the
    resulting args Namespace can be inspected directly without
    constructing any backend or running the optimization loop."""
    captured: list = []
    monkeypatch.setattr(
        "optimize_anything.cli_optimize._optimization_backends",
        lambda args: nullcontext(None),
    )

    def fake_run_optimize(args, seed, dataset, valset, intake_spec, backend_state):
        captured.append(args)
        return 0

    monkeypatch.setattr("optimize_anything.cli_optimize._run_optimize", fake_run_optimize)
    return captured


class TestSubscriptionBackendSeam:
    """R1, R2: score, analyze, and validate must route completions through
    the codex/claude subscription backend selected via CLI flags, each
    command labeling its completions with its own distinct role -- "score",
    "analysis", or "validation" -- so provenance and per-role concurrency
    tracking never conflate one command's calls with another's.

    Every test here intercepts optimize_anything.llm_backends.factory.
    create_backend, the seam cli_tools._completion_backend uses to turn a
    BackendSpec into a live backend, and monkeypatches litellm.completion
    to raise. This proves the fake -- not a real CodexSdkBackend,
    ClaudeCliBackend, or litellm call -- served every completion.
    """

    @pytest.mark.parametrize("backend_name", ["codex", "claude"])
    def test_r1a_score_uses_selected_subscription_backend(
        self, tmp_path, capsys, fake_backend_seam, backend_name,
    ):
        """R1a: score --judge-backend codex/claude must reach the selected
        subscription backend with completion role "score", and the
        command's JSON output must reflect the backend's structured
        result -- not a silently-substituted API call."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("hello world")

        rc = main([
            "score", str(artifact),
            "--objective", "Score quality",
            "--judge-backend", backend_name,
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == [backend_name]
        assert [role for _spec, role in fake_backend_seam.calls] == ["score"]
        assert [req.role for req in fake_backend_seam.requests] == ["score"]

        payload = json.loads(capsys.readouterr().out)
        assert payload["score"] == pytest.approx(0.91)
        assert "error" not in payload

    @pytest.mark.parametrize("backend_name", ["codex", "claude"])
    def test_r1b_analyze_uses_selected_subscription_backend(
        self, tmp_path, fake_backend_seam, backend_name,
    ):
        """R1b: analyze --analysis-backend codex/claude must reach the
        selected subscription backend for both of its completions, both
        labeled "analysis" -- distinct from score's "score" label -- so
        analyze's provenance is never mistaken for a score call."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("# Title\nSome content.")

        rc = main([
            "analyze", str(artifact),
            "--objective", "Optimize for OSS quality",
            "--analysis-backend", backend_name,
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == [backend_name]
        assert [role for _spec, role in fake_backend_seam.calls] == ["analysis"]
        assert [req.role for req in fake_backend_seam.requests] == ["analysis", "analysis"]

    def test_r2a_validate_reserved_selectors_use_subscription_backends(
        self, tmp_path, capsys, fake_backend_seam,
    ):
        """R2a: validate --providers must recognize codex:<model> and bare
        claude as reserved subscription selectors, route each through its
        own create_backend call labeled "validation" -- distinct from
        score's "score" and analyze's "analysis" -- and pass the
        per-provider model string through to the completion request."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "validate", str(artifact),
            "--objective", "Score quality",
            "--providers", "codex:gpt-5.6-mini", "claude",
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == ["codex", "claude"]
        assert [role for _spec, role in fake_backend_seam.calls] == ["validation", "validation"]
        assert [req.role for req in fake_backend_seam.requests] == ["validation", "validation"]
        assert fake_backend_seam.requests[0].model == "gpt-5.6-mini"
        assert fake_backend_seam.requests[1].model is None

        payload = json.loads(capsys.readouterr().out)
        assert payload["providers"][0]["score"] == pytest.approx(0.91)
        assert payload["providers"][1]["score"] == pytest.approx(0.91)
        assert "error" not in payload["providers"][0]
        assert "error" not in payload["providers"][1]

    def test_r2b_validate_mixed_subscription_and_api_providers(
        self, tmp_path, capsys, fake_backend_seam,
    ):
        """R2b: validate must accept a mix of a reserved subscription
        selector and an ordinary LiteLLM model string in the same
        --providers list, routing one through the subscription BackendSpec
        and the other through the api BackendSpec, and reporting both
        results rather than treating them as mutually exclusive modes."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "validate", str(artifact),
            "--objective", "Score quality",
            "--providers", "codex", "openai/gpt-5.6-luna",
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == ["codex", "api"]

        payload = json.loads(capsys.readouterr().out)
        assert len(payload["providers"]) == 2
        assert payload["providers"][0]["llm_provenance"]["actual_backend"] == "codex"
        assert payload["providers"][1]["llm_provenance"]["actual_backend"] == "api"
        assert payload["providers"][0]["score"] == pytest.approx(0.91)
        assert payload["providers"][1]["score"] == pytest.approx(0.91)


class TestSubscriptionFlagParsing:
    """R6a: every subscription-related flag must parse to the exact value
    the user passed, using the subcommand that actually defines it, and an
    unrecognized backend name must be rejected by argparse rather than
    silently defaulting to api."""

    def test_r6a_optimize_backend_and_subscription_flags_parsed(self, tmp_path, monkeypatch):
        """R6a: optimize's --proposer-backend, --judge-backend,
        --subscription-concurrency, --no-api-fallback,
        --openai-api-fallback-model, and --anthropic-api-fallback-model
        must all reach args with the exact values passed on the CLI."""
        captured = _spy_and_capture(monkeypatch, "optimize_anything.cli_optimize._cmd_optimize")
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")

        rc = main([
            "optimize", str(seed),
            "--proposer-backend", "codex",
            "--judge-backend", "claude",
            "--subscription-concurrency", "7",
            "--no-api-fallback",
            "--openai-api-fallback-model", "openai/gpt-5.6-fallback",
            "--anthropic-api-fallback-model", "anthropic/claude-fallback",
        ])
        assert rc == 0
        assert len(captured) == 1
        args = captured[0]
        assert args.proposer_backend == "codex"
        assert args.judge_backend == "claude"
        assert args.subscription_concurrency == 7
        assert args.no_api_fallback is True
        assert args.openai_api_fallback_model == "openai/gpt-5.6-fallback"
        assert args.anthropic_api_fallback_model == "anthropic/claude-fallback"

    def test_r6a_analyze_analysis_backend_flag_parsed(self, tmp_path, monkeypatch):
        """R6a: analyze's --analysis-backend must reach args with the exact
        value passed on the CLI; this flag only exists on analyze, so it
        must be exercised through analyze's own parser rather than
        optimize's or score's."""
        captured = _spy_and_capture(monkeypatch, "optimize_anything.cli_tools._cmd_analyze")
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "analyze", str(artifact),
            "--objective", "x",
            "--analysis-backend", "codex",
        ])
        assert rc == 0
        assert captured[0].analysis_backend == "codex"

    @pytest.mark.parametrize(
        "command,flag",
        [
            ("optimize", "--proposer-backend"),
            ("optimize", "--judge-backend"),
            ("analyze", "--analysis-backend"),
        ],
    )
    def test_r6a_invalid_backend_choice_rejected(self, tmp_path, capsys, command, flag):
        """R6a: an unrecognized backend name must be rejected by argparse
        itself (exit code 2) rather than silently falling through to the
        api backend, since a typo should never quietly bill the API
        provider instead of the subscription backend the user asked for."""
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")
        argv = [command, str(seed), flag, "not-a-real-backend"]
        if command == "analyze":
            argv += ["--objective", "x"]

        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "invalid choice" in err
        assert "not-a-real-backend" in err


class TestSpecCliPrecedence:
    """R6b: CLI flags must override TOML [model.judge]/[model.proposer]
    role tables so a one-off run can't be hijacked by a stale checked-in
    spec, while a flag the CLI omits must still inherit the spec's value
    so spec files remain useful for repeatable configuration."""

    def test_r6b_spec_role_backend_and_model_used_when_cli_omits_flags(
        self, tmp_path, monkeypatch,
    ):
        """R6b: when the CLI omits --judge-backend, --judge-model, and
        --model, the spec file's [model.judge]/[model.proposer] tables
        must supply them -- otherwise a spec file would be useless for
        selecting a run's backends and models."""
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")
        spec_file = tmp_path / "spec.toml"
        spec_file.write_text(
            '[model.judge]\n'
            'backend = "codex"\n'
            'model = "gpt-5.6-judge-spec"\n'
            '\n'
            '[model.proposer]\n'
            'model = "openai/gpt-5.6-proposer-spec"\n'
        )
        captured = _capture_prepared_optimize_args(monkeypatch)

        rc = main(["optimize", str(seed), "--spec-file", str(spec_file)])
        assert rc == 0
        assert len(captured) == 1
        args = captured[0]
        assert args.judge_backend == "codex"
        assert args.judge_model == "gpt-5.6-judge-spec"
        assert args.model == "openai/gpt-5.6-proposer-spec"

    def test_r6b_cli_flag_overrides_spec_role_backend_and_model(
        self, tmp_path, monkeypatch,
    ):
        """R6b: an explicit CLI --judge-backend/--model must win over the
        spec file's role tables per field -- a stale spec must never
        silently redirect a one-off run's billing route -- while a field
        the CLI does not override still inherits the spec's value."""
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")
        spec_file = tmp_path / "spec.toml"
        spec_file.write_text(
            '[model.judge]\n'
            'backend = "codex"\n'
            'model = "gpt-5.6-judge-spec"\n'
            '\n'
            '[model.proposer]\n'
            'model = "openai/gpt-5.6-proposer-spec"\n'
        )
        captured = _capture_prepared_optimize_args(monkeypatch)

        rc = main([
            "optimize", str(seed), "--spec-file", str(spec_file),
            "--judge-backend", "claude",
            "--model", "openai/gpt-5.6-cli-override",
        ])
        assert rc == 0
        args = captured[0]
        assert args.judge_backend == "claude"
        assert args.model == "openai/gpt-5.6-cli-override"
        # judge_model was not overridden on the CLI, so the spec value survives.
        assert args.judge_model == "gpt-5.6-judge-spec"


class TestJudgeBackendMutualExclusion:
    """R6c: a judge backend (codex/claude) is a judge-model source just
    like --judge-model, so combining it with --evaluator-command or
    --evaluator-url must be rejected with the exact same message the
    built-in API judge uses -- otherwise a user could accidentally pay for
    both a command/HTTP evaluator and an idle subscription backend at
    once."""

    _MESSAGE = (
        "Error: provide only one of --evaluator-command, --evaluator-url, "
        "--judge-model, or --judge-backend"
    )

    def test_r6c_score_evaluator_command_with_judge_backend_rejected(
        self, tmp_path, capsys, fake_backend_seam,
    ):
        """R6c: score --evaluator-command combined with --judge-backend
        codex must fail with the mutual-exclusion error, not a
        Codex-preflight error -- proving the check fires regardless of
        which subscription backend was requested."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "score", str(artifact),
            "--evaluator-command", "bash", "eval.sh",
            "--judge-backend", "codex",
        ])
        assert rc == 1
        assert capsys.readouterr().err.strip() == self._MESSAGE

    def test_r6c_score_evaluator_url_with_judge_backend_rejected(
        self, tmp_path, capsys, fake_backend_seam,
    ):
        """R6c: score --evaluator-url combined with --judge-backend claude
        must fail with the same mutual-exclusion error as
        --evaluator-command, proving the check treats both evaluator
        sources identically."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "score", str(artifact),
            "--evaluator-url", "http://eval.invalid/score",
            "--judge-backend", "claude",
        ])
        assert rc == 1
        assert capsys.readouterr().err.strip() == self._MESSAGE

    def test_r6c_optimize_evaluator_command_with_judge_backend_rejected(
        self, tmp_path, capsys, fake_backend_seam,
    ):
        """R6c: optimize --evaluator-command combined with --judge-backend
        codex must also fail with the mutual-exclusion error. Optimize
        builds and preflights its judge backend before evaluator
        resolution ever runs, so this proves the fake seam is required and
        that the check still fires correctly on the optimize path too."""
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")

        rc = main([
            "optimize", str(seed),
            "--evaluator-command", "bash", "eval.sh",
            "--judge-backend", "codex",
        ])
        assert rc == 1
        assert fake_backend_seam.stray_calls == []
        assert self._MESSAGE in capsys.readouterr().err


class TestParseValidationProvider:
    """R6d: _parse_validation_provider must recognize codex, codex:<model>,
    claude, and claude:<model> as reserved subscription selectors before
    treating anything as an ordinary LiteLLM model string, and that
    recognition must be exact-match-or-prefix-with-colon only -- never a
    bare substring/startswith check -- so a string like "claude-sonnet-5"
    or "openai/codex-mini-latest" is never misrouted to a subscription
    backend it never asked for."""

    @pytest.mark.parametrize(
        "provider,expected_backend,expected_model",
        [
            ("codex", "codex", None),
            ("codex:gpt-5.6-mini", "codex", "gpt-5.6-mini"),
            ("claude", "claude", None),
            ("claude:claude-opus-99", "claude", "claude-opus-99"),
            ("codex:openai/gpt-5.6-luna", "codex", "openai/gpt-5.6-luna"),
            ("openai/gpt-5.6-luna", "api", "openai/gpt-5.6-luna"),
            ("anthropic/claude-sonnet-5", "api", "anthropic/claude-sonnet-5"),
            ("openai/codex-mini-latest", "api", "openai/codex-mini-latest"),
            ("claude-sonnet-5", "api", "claude-sonnet-5"),
        ],
    )
    def test_r6d_reserved_selectors_resolve_before_model_strings(
        self, provider, expected_backend, expected_model,
    ):
        """R6d: reserved selectors must parse to their subscription backend
        (and optional model suffix) while ordinary LiteLLM strings --
        including adversarial ones that merely contain "codex"/"claude" as
        a substring -- must parse to the api backend unchanged."""
        backend, model = _parse_validation_provider(provider)
        assert backend == expected_backend
        assert model == expected_model


class TestApiBaseFallbackWiring:
    """R6e: a custom --api-base must reach the real API fallback
    LiteLLMBackend wrapping a subscription primary, without ever being
    echoed into the stderr backend-plan log -- the plan is meant to be
    safe to paste into a bug report, so it must show only whether a
    custom base was set (a bool), never the base itself."""

    def test_r6e_api_base_reaches_fallback_without_being_logged(
        self, tmp_path, capsys, monkeypatch,
    ):
        """R6e: --api-base combined with a subscription proposer backend
        and an API fallback model must produce a real FallbackBackend
        whose fallback LiteLLMBackend carries the exact api_base value,
        while the printed backend plan exposes only a custom_api_base
        boolean and never the sentinel URL itself."""
        import optimize_anything.llm_backends.factory as llm_backend_factory

        seed = tmp_path / "seed.txt"
        seed.write_text("seed")
        sentinel = "http://sentinel-api-base.invalid"

        real_create_backend = llm_backend_factory.create_backend
        built_backends: list = []

        def spy_create_backend(spec, *, role, coordinator=None):
            # Build the real backend so its structure can be inspected, but
            # hand the caller a harmless fake so no real preflight/complete
            # ever runs against Codex, Claude, or litellm.
            backend = real_create_backend(spec, role=role, coordinator=coordinator)
            built_backends.append((role, backend))
            return _FakeSubscriptionBackend(spec.backend, [])

        monkeypatch.setattr(
            "optimize_anything.llm_backends.factory.create_backend", spy_create_backend,
        )

        def _tripwire(**kwargs):
            raise AssertionError("litellm.completion must not be called in this test")

        monkeypatch.setattr("litellm.completion", _tripwire)

        def fake_run_optimize(args, seed_, dataset, valset, intake_spec, backend_state):
            return 0

        monkeypatch.setattr("optimize_anything.cli_optimize._run_optimize", fake_run_optimize)

        rc = main([
            "optimize", str(seed),
            "--proposer-backend", "codex",
            "--openai-api-fallback-model", "openai/gpt-5.6-fallback",
            "--api-base", sentinel,
        ])
        assert rc == 0
        assert len(built_backends) == 1
        role, backend = built_backends[0]
        assert role == "proposer"
        assert isinstance(backend, FallbackBackend)
        assert isinstance(backend.fallback, LiteLLMBackend)
        assert backend.fallback.api_base == sentinel

        output = capsys.readouterr()
        assert sentinel not in output.out
        assert sentinel not in output.err
        plan_line = next(
            line for line in output.err.splitlines() if line.startswith("Backend plan:")
        )
        plan = json.loads(plan_line[len("Backend plan: "):])
        assert plan["custom_api_base"] is True


class TestHostMarkersNeverInferBackend:
    """R7a: the runtime must decide which backend to bill against only
    from explicit CLI flags, never by sniffing which coding assistant's
    shell it happens to run inside. Ambient markers like CLAUDECODE or
    CODEX_HOME come from the user's own terminal environment, not this
    tool's configuration -- inferring from them would silently bill a
    subscription account whenever this CLI runs inside another agent's
    shell, with no flag the user could point to as the cause."""

    def _set_host_markers(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
        monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")

    def test_r7a_score_ignores_host_markers_without_backend_flags(
        self, tmp_path, monkeypatch, fake_backend_seam,
    ):
        """R7a: score with CLAUDECODE/CODEX_HOME/etc. set but no
        --judge-backend flag must still resolve the judge role to the api
        backend -- host markers must never substitute for an explicit
        backend selection."""
        self._set_host_markers(monkeypatch, tmp_path)
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "score", str(artifact),
            "--objective", "Score quality",
            "--judge-model", "openai/gpt-5.6-luna",
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == ["api"]

    def test_r7a_analyze_ignores_host_markers_without_backend_flags(
        self, tmp_path, monkeypatch, fake_backend_seam,
    ):
        """R7a: analyze with the same host markers set but no
        --analysis-backend flag must still resolve to the api backend."""
        self._set_host_markers(monkeypatch, tmp_path)
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("content")

        rc = main([
            "analyze", str(artifact),
            "--objective", "x",
            "--judge-model", "openai/gpt-5.6-luna",
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [spec.backend for spec, _role in fake_backend_seam.calls] == ["api"]

    def test_r7a_optimize_backend_plan_ignores_host_markers(
        self, tmp_path, capsys, monkeypatch, fake_backend_seam,
    ):
        """R7a: optimize's backend plan for both the proposer and judge
        roles must show "api" when host markers are set but no
        --proposer-backend/--judge-backend flag was passed -- the plan
        that gets logged and inspected must reflect only explicit flags,
        never the environment it happens to run inside."""
        self._set_host_markers(monkeypatch, tmp_path)
        seed = tmp_path / "seed.txt"
        seed.write_text("seed")

        def fake_run_optimize(args, seed_, dataset, valset, intake_spec, backend_state):
            print(json.dumps({"backend_plan": backend_state.plan}))
            return 0

        monkeypatch.setattr("optimize_anything.cli_optimize._run_optimize", fake_run_optimize)

        rc = main([
            "optimize", str(seed),
            "--model", "openai/gpt-5.6-sol",
            "--judge-model", "openai/gpt-5.6-luna",
            "--objective", "x",
        ])
        assert rc == 0
        assert fake_backend_seam.stray_calls == []
        assert [(role, spec.backend) for spec, role in fake_backend_seam.calls] == [
            ("proposer", "api"),
            ("judge", "api"),
        ]
        payload = json.loads(capsys.readouterr().out)
        assert payload["backend_plan"]["proposer"]["backend"] == "api"
        assert payload["backend_plan"]["judge"]["backend"] == "api"
