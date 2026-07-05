"""Tests for the realistic optimization observer workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import optimization_observer


def _write_run_dir(
    path: Path,
    *,
    seed: str,
    best: str,
    initial: float | None = 0.4,
    best_score: float | None = 0.7,
    candidates: int = 3,
    diagnostics: list[dict] | None = None,
) -> Path:
    path.mkdir()
    (path / "seed.txt").write_text(seed, encoding="utf-8")
    (path / "best_artifact.txt").write_text(best, encoding="utf-8")
    summary = {
        "best_artifact": best,
        "total_metric_calls": candidates + 1,
        "score_summary": {
            "initial": initial,
            "latest": best_score,
            "best": best_score,
            "delta_best_vs_initial": (
                None
                if initial is None or best_score is None
                else round(best_score - initial, 6)
            ),
            "num_candidates": candidates,
        },
        "top_diagnostics": diagnostics
        if diagnostics is not None
        else [{"name": "contract_completeness", "value": best_score or 0.0}],
        "plateau_guidance": "No strong plateau detected.",
    }
    (path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return path


def _scorer(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "payload=$(cat)",
                "python3 - \"$payload\" <<'PY'",
                "import json",
                "import sys",
                "data = json.loads(sys.argv[1])",
                "candidate = data.get('candidate', '')",
                "score = 0.9 if 'feedback' in candidate.lower() else 0.6",
                "print(json.dumps({'score': score, 'feedback': ['ok']}))",
                "PY",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_setup_benchmark_copies_seed_without_overwriting_source(tmp_path: Path):
    result = optimization_observer.setup_benchmark(
        optimization_observer.DEFAULT_BENCHMARK_PATH,
        tmp_path,
    )

    seed_file = Path(result["seed_file"])
    assert seed_file.exists()
    assert seed_file != optimization_observer.REPO_ROOT / result["seed_source"]
    assert seed_file.read_text(encoding="utf-8") == (
        optimization_observer.REPO_ROOT / result["seed_source"]
    ).read_text(encoding="utf-8")
    assert "generate-evaluator" in result["why"]
    assert result["training_evaluator_command"][-1].endswith(
        "evaluator_generation_training.sh"
    )


def test_training_scorer_returns_score_dimensions_and_feedback():
    candidate = (optimization_observer.REPO_ROOT / "skills/generate-evaluator/SKILL.md").read_text(
        encoding="utf-8"
    )
    proc = subprocess.run(
        ["bash", "evaluators/evaluator_generation_training.sh"],
        input=json.dumps({"candidate": candidate}),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert 0.0 <= result["score"] <= 1.0
    assert result["contract_completeness"] > 0
    assert result["runnable_examples"] > 0
    assert result["feedback"]


def test_training_scorer_rejects_malformed_payload():
    proc = subprocess.run(
        ["bash", "evaluators/evaluator_generation_training.sh"],
        input=json.dumps({"not_candidate": "missing field"}),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result["score"] == 0.0
    assert "candidate" in result["error"]


def test_observation_report_summarizes_successful_run(tmp_path: Path):
    run_dir = _write_run_dir(
        tmp_path / "run",
        seed="# Skill\n\n- Add evaluator code.",
        best="# Skill\n\n- Add evaluator code.\n- Return JSON score and feedback.",
    )
    scorer = _scorer(tmp_path / "heldout.sh")

    report = optimization_observer.build_observation_report(
        run_dir,
        validation_command=["bash", str(scorer)],
        meaningful_delta=0.05,
        validation_delta=0.01,
    )

    assert report["training"]["initial_score"] == 0.4
    assert report["training"]["best_score"] == 0.7
    assert report["training"]["score_delta"] == 0.3
    assert report["training"]["candidate_count"] == 3
    assert report["training"]["metric_calls"] == 4
    assert report["diff_summary"]["added"] > 0
    assert report["validation"]["accepted"] is True
    assert report["accepted"] is True


def test_observation_report_flags_seed_only_and_insufficient_improvement(tmp_path: Path):
    run_dir = _write_run_dir(
        tmp_path / "run",
        seed="same",
        best="same",
        initial=0.5,
        best_score=0.5,
        candidates=1,
        diagnostics=[],
    )

    report = optimization_observer.build_observation_report(
        run_dir,
        meaningful_delta=0.05,
    )

    kinds = {warning["kind"] for warning in report["warnings"]}
    assert "seed_only" in kinds
    assert "missing_diagnostics" in kinds
    assert "insufficient_improvement" in kinds
    assert "seed_and_best_identical" in kinds
    assert report["accepted"] is False


def test_observation_report_rejects_score_only_diagnostics(tmp_path: Path):
    run_dir = _write_run_dir(
        tmp_path / "run",
        seed="old",
        best="new feedback",
        initial=0.4,
        best_score=0.6,
        candidates=3,
        diagnostics=[{"name": "overall_score", "value": 0.6}],
    )
    scorer = _scorer(tmp_path / "heldout.sh")

    report = optimization_observer.build_observation_report(
        run_dir,
        validation_command=["bash", str(scorer)],
        meaningful_delta=0.05,
        validation_delta=0.01,
    )

    assert any(w["kind"] == "missing_diagnostics" for w in report["warnings"])
    assert report["accepted"] is False


def test_held_out_regression_prevents_acceptance(tmp_path: Path):
    run_dir = _write_run_dir(
        tmp_path / "run",
        seed="# Skill\n\nReturn JSON score.",
        best="# Skill\n\nReturn JSON score.\nRepeat score score score score.",
        initial=0.4,
        best_score=0.8,
        candidates=4,
    )
    scorer = tmp_path / "heldout.sh"
    scorer.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "payload=$(cat)",
                "python3 - \"$payload\" <<'PY'",
                "import json",
                "import sys",
                "data = json.loads(sys.argv[1])",
                "score = 0.3 if 'Repeat' in data.get('candidate', '') else 0.8",
                "print(json.dumps({'score': score, 'feedback': ['heldout']}))",
                "PY",
            ]
        ),
        encoding="utf-8",
    )
    scorer.chmod(0o755)

    report = optimization_observer.build_observation_report(
        run_dir,
        validation_command=["bash", str(scorer)],
        meaningful_delta=0.05,
        validation_delta=0.01,
    )

    assert report["training"]["score_delta"] == 0.4
    assert report["validation"]["accepted"] is False
    assert report["accepted"] is False
    assert any(w["kind"] == "heldout_regression" for w in report["warnings"])


def test_main_report_strict_returns_nonzero_for_unaccepted_run(tmp_path: Path, capsys):
    run_dir = _write_run_dir(
        tmp_path / "run",
        seed="same",
        best="same",
        initial=0.5,
        best_score=0.5,
        candidates=1,
        diagnostics=[],
    )

    rc = optimization_observer.main(["report", "--run-dir", str(run_dir), "--strict"])

    assert rc == 1
    result = json.loads(capsys.readouterr().out)
    assert result["accepted"] is False
