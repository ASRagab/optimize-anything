"""Tests for the live integration script."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.live_integration import _extract_json_from_output, main


SCRIPT = "scripts/live_integration.py"


class TestGreenPhase:
    """GREEN phase tests using mock evaluators (no real LLM calls)."""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required for gepa optimization",
    )
    def test_green_phase_produces_structured_output(self, tmp_path):
        """GREEN phase returns JSON with expected keys."""
        seed = tmp_path / "seed.txt"
        seed.write_text("# Test Skill\n\nThis is a test skill with content.")

        evaluator = tmp_path / "eval.sh"
        evaluator.write_text(
            '#!/usr/bin/env bash\ncat > /dev/null\necho \'{"score": 0.75}\'\n'
        )
        evaluator.chmod(0o755)

        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "green",
                "--artifact", str(seed),
                "--evaluator-command", "bash", str(evaluator),
                "--budget", "2",
                "--objective", "Improve clarity",
                "--run-dir", str(tmp_path / "runs"),
                "--round", "1",
                "--baseline", "0.7",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["phase"] == "green"
        assert "green" in result
        assert "initial_score" in result["green"]
        assert "optimized_score" in result["green"]
        assert "metric_calls" in result["green"]
        assert "diff_summary" in result["green"]
        assert result["round"] == 1

    def test_green_phase_missing_artifact(self):
        """GREEN phase returns error for missing artifact."""
        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "green",
                "--artifact", "/nonexistent/path.txt",
                "--evaluator-command", "echo", "{}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert proc.returncode == 1
        result = json.loads(proc.stdout)
        assert "error" in result

    def test_green_phase_zero_proposals_detected(self, tmp_path, capsys):
        """GREEN phase errors when optimizer generates no proposals."""
        from unittest.mock import patch, MagicMock

        artifact = tmp_path / "artifact.txt"
        artifact.write_text("test content")

        # Mock subprocess.run to simulate optimizer returning zero candidates
        zero_proposal_output = json.dumps({
            "score_summary": {"best": 0.5, "num_candidates": 0},
            "total_metric_calls": 0,
            "run_dir": str(tmp_path / "runs"),
        })

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = zero_proposal_output
        mock_result.stderr = ""

        with patch("scripts.live_integration.subprocess.run", return_value=mock_result):
            rc = main([
                "--phase", "green",
                "--artifact", str(artifact),
                "--evaluator-command", "echo", "{}",
            ])

        assert rc == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "no proposals" in result["error"]
        assert "--model" in result["error"]


class TestRedPhase:
    """RED phase tests using mock evaluators."""

    def test_red_phase_command_scoring(self, tmp_path):
        """RED phase scores artifact with command evaluator."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("# Test\n\nContent here.")

        evaluator = tmp_path / "eval.sh"
        evaluator.write_text(
            '#!/usr/bin/env bash\ncat > /dev/null\necho \'{"score": 0.82}\'\n'
        )
        evaluator.chmod(0o755)

        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "red",
                "--artifact", str(artifact),
                "--evaluator-command", "bash", str(evaluator),
                "--objective", "Maximize quality",
                "--baseline", "0.75",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["phase"] == "red"
        assert "command" in result["red"]["scores"]
        assert result["red"]["scores"]["command"] == 0.82
        assert result["improved"] is True

    def test_red_phase_missing_artifact(self):
        """RED phase returns error for missing artifact."""
        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "red",
                "--artifact", "/nonexistent/path.txt",
                "--objective", "test",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert proc.returncode == 1
        result = json.loads(proc.stdout)
        assert "error" in result

    def test_red_phase_no_providers_command_only(self, tmp_path):
        """RED phase works with command evaluator only (no LLM providers)."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("# Test artifact\nWith some content.")

        evaluator = tmp_path / "eval.sh"
        evaluator.write_text(
            '#!/usr/bin/env bash\ncat > /dev/null\necho \'{"score": 0.65}\'\n'
        )
        evaluator.chmod(0o755)

        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "red",
                "--artifact", str(artifact),
                "--evaluator-command", "bash", str(evaluator),
                "--baseline", "0.5",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["red"]["cross_provider_delta"] == 0.0
        assert len(result["red"]["scores"]) == 1

    def test_red_phase_all_providers_none_returns_error(self, tmp_path, capsys):
        """RED phase errors when all evaluators return None."""
        from unittest.mock import patch

        artifact = tmp_path / "artifact.txt"
        artifact.write_text("test content")

        # Mock _score_with_command and _score_with_judge to return None
        with patch("scripts.live_integration._score_with_command", return_value=None), \
             patch("scripts.live_integration._score_with_judge", return_value=None):
            rc = main([
                "--phase", "red",
                "--artifact", str(artifact),
                "--objective", "test",
                "--providers", "fake/model-a", "fake/model-b",
                "--evaluator-command", "echo", "{}",
            ])

        assert rc == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "error" in result
        assert "all evaluators returned None" in result["error"]

    def test_red_phase_baseline_zero_improved_flag(self, tmp_path):
        """RED phase correctly sets improved=True with --baseline 0.0."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("# Test\n\nContent here.")

        evaluator = tmp_path / "eval.sh"
        evaluator.write_text(
            '#!/usr/bin/env bash\ncat > /dev/null\necho \'{"score": 0.5}\'\n'
        )
        evaluator.chmod(0o755)

        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "red",
                "--artifact", str(artifact),
                "--baseline", "0.0",
                "--evaluator-command", "bash", str(evaluator),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["improved"] is True
        assert result["baseline"] == 0.0


class TestExtractJsonFromOutput:
    """Unit tests for _extract_json_from_output."""

    def test_pure_json(self):
        output = '{"score": 0.85, "best_artifact": "hello"}'
        result = _extract_json_from_output(output)
        assert result == {"score": 0.85, "best_artifact": "hello"}

    def test_mixed_output_with_progress_lines(self):
        """gepa prints iteration progress before JSON summary."""
        output = (
            "Iteration 1/5: score=0.72\n"
            "Iteration 2/5: score=0.78\n"
            "Iteration 3/5: score=0.81\n"
            '{"score_summary": {"best": 0.81}, "total_metric_calls": 3}'
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["score_summary"]["best"] == 0.81

    def test_empty_output(self):
        assert _extract_json_from_output("") is None

    def test_whitespace_only_output(self):
        assert _extract_json_from_output("   \n\n  ") is None

    def test_invalid_json(self):
        assert _extract_json_from_output("{not valid json}") is None

    def test_plain_text_no_json(self):
        assert _extract_json_from_output("just some text output\nno json here") is None

    def test_json_with_leading_whitespace(self):
        output = '  \n  {"key": "value"}'
        result = _extract_json_from_output(output)
        assert result == {"key": "value"}

    def test_multiple_json_objects_returns_last(self):
        """When multiple JSON objects appear, return the last one."""
        output = (
            '{"partial": true}\n'
            '{"score_summary": {"best": 0.9}, "total_metric_calls": 5}'
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["total_metric_calls"] == 5


class TestProvidersValidation:
    """Tests for --providers requires --objective validation."""

    def test_providers_without_objective_fails(self, tmp_path):
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("Test content.")

        proc = subprocess.run(
            [
                sys.executable, SCRIPT,
                "--phase", "red",
                "--artifact", str(artifact),
                "--providers", "openai/gpt-5.1-mini",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert proc.returncode == 1
        result = json.loads(proc.stdout)
        assert "error" in result
        assert "objective" in result["error"].lower()


class TestArgparseOrdering:
    """Tests for --evaluator-command nargs="+" flag-swallowing protection."""

    def test_model_flag_parsed_independently_of_evaluator_command(self, tmp_path, capsys):
        """--model is parsed correctly even when --evaluator-command appears before it."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("test")

        # Place --evaluator-command BEFORE --model.
        # argparse recognizes --model as a known flag and parses it separately.
        rc = main([
            "--phase", "green",
            "--artifact", str(artifact),
            "--evaluator-command", "echo", "{}",
            "--model", "openai/gpt-4o-mini",
        ])

        captured = capsys.readouterr()
        # May fail on optimization subprocess, but NOT on argument parsing.
        # The error should reference optimize/artifact issues, not flag consumption.
        if rc != 0:
            result = json.loads(captured.out)
            assert "consumed flag-like tokens" not in result.get("error", "")

    def test_evaluator_command_at_end_of_args(self, tmp_path, capsys):
        """--evaluator-command works correctly when placed last (recommended pattern)."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("test")

        rc = main([
            "--phase", "green",
            "--artifact", str(artifact),
            "--model", "openai/gpt-4o-mini",
            "--budget", "2",
            "--evaluator-command", "echo", "{}",
        ])

        captured = capsys.readouterr()
        if rc != 0:
            result = json.loads(captured.out)
            assert "consumed flag-like tokens" not in result.get("error", "")

    def test_evaluator_command_flag_swallowing_validation(self, capsys):
        """Flag-like tokens in --evaluator-command list are rejected."""
        import argparse as _argparse

        # Simulate what happens when evaluator_command accidentally contains flags.
        # This defense-in-depth validation catches edge cases where --tokens end up
        # in the evaluator command list (e.g. via shell expansion or wrapper scripts).
        from unittest.mock import patch

        original_parse = _argparse.ArgumentParser.parse_args

        def mock_parse(self, args=None, namespace=None):
            result = original_parse(self, args, namespace)
            # Inject a flag-like token to simulate the swallowing scenario
            if hasattr(result, "evaluator_command") and result.evaluator_command:
                result.evaluator_command.append("--stolen-flag")
            return result

        with patch.object(_argparse.ArgumentParser, "parse_args", mock_parse):
            rc = main([
                "--phase", "green",
                "--artifact", "/tmp/test.txt",
                "--evaluator-command", "echo", "{}",
            ])

        assert rc == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "consumed flag-like tokens" in result["error"]
        assert "--stolen-flag" in result["error"]
