"""Tests for spec file loading and normalization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimize_anything.spec_loader import SpecLoadError, load_spec


class TestLoadSpec:
    def test_minimal_valid_spec(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[optimization]\nobjective = "maximize clarity"\n')
        result = load_spec(spec_file)
        assert result["objective"] == "maximize clarity"
        assert result["budget"] is None

    def test_seed_file_resolved_relative_to_spec_dir(self, tmp_path: Path):
        (tmp_path / "seed.txt").write_text("hello")
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[optimization]\nseed_file = "seed.txt"\n')
        result = load_spec(spec_file)
        assert result["seed_file"] == str(tmp_path / "seed.txt")

    def test_evaluator_command_parsed(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[evaluator]\ncommand = ["bash", "eval.sh"]\n')
        result = load_spec(spec_file)
        assert result["evaluator_command"] == ["bash", "eval.sh"]

    def test_model_section_parsed(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text(
            '[model]\nproposer = "anthropic/claude-sonnet-4-6"\njudge = "openai/gpt-4o-mini"\n'
        )
        result = load_spec(spec_file)
        assert result["proposer_model"] == "anthropic/claude-sonnet-4-6"
        assert result["judge_model"] == "openai/gpt-4o-mini"

    def test_intake_section_preserved(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text(
            '[intake]\nartifact_class = "prompt"\nevaluation_pattern = "judge"\n'
        )
        result = load_spec(spec_file)
        assert result["intake"]["artifact_class"] == "prompt"
        assert result["intake"]["evaluation_pattern"] == "judge"

    def test_missing_file_raises_spec_load_error(self, tmp_path: Path):
        with pytest.raises(SpecLoadError, match="spec file not found"):
            load_spec(tmp_path / "nonexistent.toml")

    def test_invalid_toml_raises_spec_load_error(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text("this is not [ valid toml ===")
        with pytest.raises(SpecLoadError, match="invalid TOML"):
            load_spec(spec_file)

    def test_invalid_budget_type_raises(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[optimization]\nbudget = "fifty"\n')
        with pytest.raises(SpecLoadError, match="budget must be a positive integer"):
            load_spec(spec_file)

    def test_evaluator_command_must_be_list(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[evaluator]\ncommand = "bash eval.sh"\n')
        with pytest.raises(SpecLoadError, match="must be a non-empty list"):
            load_spec(spec_file)

    def test_evaluator_cwd_resolved_relative_to_spec(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[evaluator]\ncwd = "scripts"\n')
        result = load_spec(spec_file)
        assert result["evaluator_cwd"] == str(tmp_path / "scripts")

    def test_budget_value_parsed(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text("[optimization]\nbudget = 50\n")
        result = load_spec(spec_file)
        assert result["budget"] == 50

    def test_empty_spec_returns_all_none(self, tmp_path: Path):
        spec_file = tmp_path / "opt.toml"
        spec_file.write_text("")
        result = load_spec(spec_file)
        assert all(v is None for v in result.values())


class TestSpecCliIntegration:
    def test_cli_flags_take_precedence_over_spec(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """CLI --objective overrides spec objective."""
        from optimize_anything.cli import main

        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test artifact")

        spec_file = tmp_path / "opt.toml"
        spec_file.write_text('[optimization]\nobjective = "from spec"\nbudget = 5\n')

        captured: dict = {}

        class DummyResult:
            best_candidate = "best"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured.update(kwargs)
            return DummyResult()

        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: "fake-evaluator",
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--objective", "from cli",
            "--spec-file", str(spec_file),
        ])
        assert result == 0
        assert captured.get("objective") == "from cli"

    def test_spec_budget_used_when_no_cli_budget(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        from optimize_anything.cli import main

        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        spec_file = tmp_path / "opt.toml"
        spec_file.write_text("[optimization]\nbudget = 7\n")

        captured_config: dict = {}

        class DummyResult:
            best_candidate = "best"
            total_metric_calls = 1

        def fake_optimize(**kwargs):
            captured_config["config"] = kwargs.get("config")
            return DummyResult()

        monkeypatch.setattr("gepa.optimize_anything.optimize_anything", fake_optimize)
        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: "fake",
        )
        monkeypatch.setattr(
            "optimize_anything.cli._preflight_command_evaluator",
            lambda command, cwd=None: None,
        )

        main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--spec-file", str(spec_file),
        ])
        cfg = captured_config.get("config")
        assert cfg is not None
        assert cfg.engine.max_metric_calls == 7

    def test_invalid_spec_file_returns_1(self, tmp_path: Path, capsys):
        from optimize_anything.cli import main

        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")

        spec_file = tmp_path / "bad.toml"
        spec_file.write_text("this is not valid [[[toml")

        result = main([
            "optimize", str(seed_file),
            "--evaluator-command", "bash", "eval.sh",
            "--spec-file", str(spec_file),
        ])
        assert result == 1
        assert "Error loading spec file" in capsys.readouterr().err
