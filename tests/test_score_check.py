"""Tests for scripts/score_check.py regression gate."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SCRIPT = "scripts/score_check.py"


def _make_evaluator(tmp_path: Path, score: float) -> Path:
    """Create a fake evaluator that always returns the given score."""
    script = tmp_path / "fake_eval.sh"
    script.write_text(
        textwrap.dedent(f"""\
            #!/usr/bin/env bash
            # Ignore stdin, return fixed score
            cat > /dev/null
            echo '{{"score": {score}}}'
        """)
    )
    script.chmod(0o755)
    return script


def _make_scores_json(
    tmp_path: Path,
    artifact_rel: str,
    evaluator_rel: str,
    baseline: float,
) -> Path:
    """Create a scores.json with one entry."""
    scores = {
        artifact_rel: {
            "evaluator": evaluator_rel,
            "baseline": baseline,
            "current": baseline,
            "target": 0.95,
            "last_run": "2026-02-23",
        }
    }
    scores_path = tmp_path / "scores.json"
    scores_path.write_text(json.dumps(scores, indent=2))
    return scores_path


def _run_score_check(scores_path: Path, root: Path) -> subprocess.CompletedProcess:
    """Run score_check.py as a subprocess."""
    return subprocess.run(
        [sys.executable, SCRIPT, "--scores", str(scores_path), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )


class TestScoreCheck:
    def test_score_check_passes_when_above_baseline(self, tmp_path: Path):
        """Evaluator returns 0.6, baseline is 0.5 => PASS (exit 0)."""
        # Set up artifact
        artifact_dir = tmp_path / "skills" / "test"
        artifact_dir.mkdir(parents=True)
        artifact = artifact_dir / "SKILL.md"
        artifact.write_text("# Test Skill\nSome content here.")

        # Set up evaluator that returns 0.6
        evaluator = _make_evaluator(tmp_path, 0.6)

        # Set up scores.json
        scores_path = _make_scores_json(
            tmp_path,
            artifact_rel="skills/test/SKILL.md",
            evaluator_rel=str(evaluator.relative_to(tmp_path)),
            baseline=0.5,
        )

        result = _run_score_check(scores_path, root=tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 but got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    def test_score_check_fails_when_below_baseline(self, tmp_path: Path):
        """Evaluator returns 0.3, baseline is 0.7 => FAIL (exit 1)."""
        # Set up artifact
        artifact_dir = tmp_path / "skills" / "test"
        artifact_dir.mkdir(parents=True)
        artifact = artifact_dir / "SKILL.md"
        artifact.write_text("# Test Skill\nSome content here.")

        # Set up evaluator that returns 0.3
        evaluator = _make_evaluator(tmp_path, 0.3)

        # Set up scores.json
        scores_path = _make_scores_json(
            tmp_path,
            artifact_rel="skills/test/SKILL.md",
            evaluator_rel=str(evaluator.relative_to(tmp_path)),
            baseline=0.7,
        )

        result = _run_score_check(scores_path, root=tmp_path)
        assert result.returncode == 1, (
            f"Expected exit 1 but got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "FAIL" in result.stdout

    def test_score_check_handles_missing_artifact(self, tmp_path: Path):
        """scores.json references a file that doesn't exist => FAIL (exit 1)."""
        evaluator = _make_evaluator(tmp_path, 0.9)

        # scores.json references a non-existent artifact
        scores_path = _make_scores_json(
            tmp_path,
            artifact_rel="skills/nonexistent/SKILL.md",
            evaluator_rel=str(evaluator.relative_to(tmp_path)),
            baseline=0.5,
        )

        result = _run_score_check(scores_path, root=tmp_path)
        assert result.returncode == 1, (
            f"Expected exit 1 but got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
