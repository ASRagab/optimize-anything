"""Tests for the live integration script."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = "scripts/live_integration.py"


class TestGreenPhase:
    """GREEN phase tests using mock evaluators (no real LLM calls)."""

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
