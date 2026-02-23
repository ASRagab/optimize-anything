#!/usr/bin/env python3
"""Regression gate: verify artifact scores have not dropped below baseline.

Reads a scores.json file, runs each evaluator against its artifact, and
exits non-zero if any score falls below the recorded baseline (with a
small tolerance).

Usage:
    python scripts/score_check.py [--scores scores.json] [--root .]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOLERANCE = 0.01


def load_scores(scores_path: Path) -> dict:
    """Read and parse the scores.json file."""
    with open(scores_path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_artifact(artifact_path: Path) -> str:
    """Read an artifact file and return its text content."""
    return artifact_path.read_text(encoding="utf-8")


def run_evaluator(evaluator_path: Path, candidate: str, cwd: Path) -> float:
    """Pipe a candidate through an evaluator and return the score.

    The evaluator receives JSON on stdin: {"candidate": "<text>"}
    and must output JSON on stdout with a numeric "score" field.
    """
    payload = json.dumps({"candidate": candidate})
    proc = subprocess.run(
        ["bash", str(evaluator_path)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Evaluator {evaluator_path} exited with code {proc.returncode}: "
            f"{proc.stderr.strip()}"
        )
    result = json.loads(proc.stdout)
    score = result["score"]
    if not isinstance(score, (int, float)):
        raise ValueError(f"Evaluator returned non-numeric score: {score!r}")
    return float(score)


def check_scores(scores_path: Path, root: Path) -> int:
    """Run all evaluators and compare scores to baselines.

    Returns 0 if all artifacts pass, 1 if any fail.
    """
    scores = load_scores(scores_path)
    any_failed = False

    for artifact_rel, entry in scores.items():
        artifact_path = root / artifact_rel
        evaluator_rel = entry["evaluator"]
        evaluator_path = root / evaluator_rel
        baseline = entry["baseline"]

        # Check artifact exists
        if not artifact_path.exists():
            print(f"FAIL  {artifact_rel}  (artifact not found: {artifact_path})")
            any_failed = True
            continue

        # Check evaluator exists
        if not evaluator_path.exists():
            print(f"FAIL  {artifact_rel}  (evaluator not found: {evaluator_path})")
            any_failed = True
            continue

        try:
            candidate = read_artifact(artifact_path)
            score = run_evaluator(evaluator_path, candidate, cwd=root)
        except Exception as exc:
            print(f"FAIL  {artifact_rel}  (error: {exc})")
            any_failed = True
            continue

        if score >= baseline - TOLERANCE:
            print(f"PASS  {artifact_rel}  score={score:.4f}  baseline={baseline:.4f}")
        else:
            print(
                f"FAIL  {artifact_rel}  score={score:.4f}  baseline={baseline:.4f}  "
                f"(dropped by {baseline - score:.4f})"
            )
            any_failed = True

    return 1 if any_failed else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regression gate: check artifact scores against baselines."
    )
    parser.add_argument(
        "--scores",
        default="scores.json",
        help="Path to scores.json (default: scores.json)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory for resolving artifact and evaluator paths (default: .)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scores_path = Path(args.scores)
    root = Path(args.root)

    if not scores_path.exists():
        print(f"Error: scores file not found: {scores_path}", file=sys.stderr)
        return 1

    return check_scores(scores_path, root)


if __name__ == "__main__":
    raise SystemExit(main())
