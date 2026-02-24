#!/usr/bin/env python3
"""Live integration test -- RED-GREEN orchestrator.

Run one GREEN (optimize) or RED (multi-provider score) phase and output
structured JSON. Designed to be driven by Claude Code as an interactive observer.

Usage:
    # GREEN phase: optimize an artifact
    python scripts/live_integration.py --phase green \
        --artifact skills/generate-evaluator/SKILL.md \
        --evaluator-command bash evaluators/skill_clarity.sh \
        --budget 15 --objective "Improve clarity" \
        --run-dir integration_runs

    # RED phase: score with multiple providers
    python scripts/live_integration.py --phase red \
        --artifact skills/generate-evaluator/SKILL.md \
        --objective "Score skill quality" \
        --providers openai/gpt-5.1-mini anthropic/claude-sonnet-4-5-20250929 \
        --evaluator-command bash evaluators/skill_clarity.sh
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="live-integration",
        description="RED-GREEN integration test orchestrator",
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["green", "red"],
        help="Which phase to run",
    )
    parser.add_argument("--artifact", required=True, help="Path to artifact file")
    parser.add_argument("--objective", help="Natural language objective")
    parser.add_argument("--budget", type=int, default=15, help="GREEN: max evaluator calls")
    parser.add_argument(
        "--evaluator-command",
        nargs="+",
        help="Command evaluator for GREEN phase or RED command scoring",
    )
    parser.add_argument("--run-dir", help="GREEN: directory to save run artifacts")
    parser.add_argument(
        "--providers",
        nargs="+",
        help="RED: LLM provider model strings for multi-provider scoring",
    )
    parser.add_argument("--round", type=int, default=1, help="Current round number")
    parser.add_argument("--baseline", type=float, help="Baseline score for comparison")

    args = parser.parse_args(argv)

    if args.phase == "green":
        return _run_green(args)
    elif args.phase == "red":
        return _run_red(args)
    return 1


def _run_green(args: argparse.Namespace) -> int:
    """Run GREEN phase: optimize artifact, return structured results."""
    artifact_path = Path(args.artifact)
    if not artifact_path.exists():
        print(json.dumps({"error": f"Artifact not found: {args.artifact}"}))
        return 1

    # Score the artifact before optimization
    initial_score = _score_with_command(artifact_path, args.evaluator_command)

    # Build optimize command
    cmd = [
        sys.executable, "-m", "optimize_anything.cli",
        "optimize", str(artifact_path),
        "--budget", str(args.budget),
        "--diff",
    ]
    if args.evaluator_command:
        cmd.extend(["--evaluator-command"] + args.evaluator_command)
    if args.objective:
        cmd.extend(["--objective", args.objective])
    if args.run_dir:
        cmd.extend(["--run-dir", args.run_dir])

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if proc.returncode != 0:
        print(json.dumps({
            "phase": "green",
            "error": f"optimize failed (rc={proc.returncode})",
            "stderr": proc.stderr[:2000],
        }))
        return 1

    optimize_result = _extract_json_from_output(proc.stdout)
    if optimize_result is None:
        print(json.dumps({
            "phase": "green",
            "error": "optimize output not valid JSON",
            "stdout": proc.stdout[:2000],
        }))
        return 1

    # Extract optimized score from summary
    score_summary = optimize_result.get("score_summary", {})
    optimized_score = score_summary.get("best", initial_score)
    metric_calls = optimize_result.get("total_metric_calls", 0)

    # Count diff lines from stderr
    diff_add = sum(1 for l in proc.stderr.split("\n") if l.startswith("+") and not l.startswith("+++"))
    diff_del = sum(1 for l in proc.stderr.split("\n") if l.startswith("-") and not l.startswith("---"))
    diff_summary = f"+{diff_add} -{diff_del}"

    result = {
        "phase": "green",
        "round": args.round,
        "artifact": args.artifact,
        "green": {
            "initial_score": initial_score,
            "optimized_score": optimized_score,
            "metric_calls": metric_calls,
            "diff_summary": diff_summary,
            "best_artifact_preview": str(optimize_result.get("best_artifact", ""))[:500],
        },
        "baseline": args.baseline,
        "improved": optimized_score is not None and optimized_score > (args.baseline or initial_score or 0),
    }

    print(json.dumps(result, indent=2, default=str))
    return 0


def _run_red(args: argparse.Namespace) -> int:
    """Run RED phase: score artifact with multiple evaluator backends."""
    artifact_path = Path(args.artifact)
    if not artifact_path.exists():
        print(json.dumps({"error": f"Artifact not found: {args.artifact}"}))
        return 1

    scores = {}

    # 1. Command evaluator score (if provided)
    if args.evaluator_command:
        cmd_score = _score_with_command(artifact_path, args.evaluator_command)
        scores["command"] = cmd_score

    # 2. LLM judge scores (one per provider)
    providers = args.providers or []
    for provider in providers:
        judge_score = _score_with_judge(artifact_path, provider, args.objective)
        # Use a clean key: "openai/gpt-5.1-mini" -> "openai_gpt_5_1_mini"
        key = provider.replace("/", "_").replace("-", "_").replace(".", "_")
        scores[key] = judge_score

    # Cross-provider analysis
    judge_scores = [v for k, v in scores.items() if k != "command" and v is not None]
    cross_provider_delta = (
        round(max(judge_scores) - min(judge_scores), 4) if len(judge_scores) >= 2 else 0.0
    )

    all_scores = [v for v in scores.values() if v is not None]
    avg_score = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0

    result = {
        "phase": "red",
        "round": args.round,
        "artifact": args.artifact,
        "red": {
            "scores": scores,
            "cross_provider_delta": cross_provider_delta,
            "average_score": avg_score,
        },
        "baseline": args.baseline,
        "improved": avg_score > (args.baseline or 0.0),
    }

    print(json.dumps(result, indent=2, default=str))
    return 0


def _extract_json_from_output(output: str) -> dict | None:
    """Extract the last JSON object from mixed stdout output.

    The gepa engine prints iteration progress lines to stdout before the
    CLI prints its JSON summary. This function finds and parses that
    trailing JSON object.
    """
    # Try parsing the entire output first (fast path)
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    # Find the last '{' that starts a valid JSON object
    # Search backwards for the outermost opening brace
    idx = output.rfind("\n{")
    if idx >= 0:
        try:
            return json.loads(output[idx + 1:])
        except json.JSONDecodeError:
            pass

    # Try from the very start if output starts with '{'
    if output.lstrip().startswith("{"):
        try:
            return json.loads(output.lstrip())
        except json.JSONDecodeError:
            pass

    return None


def _score_with_command(
    artifact_path: Path,
    evaluator_command: list[str] | None,
) -> float | None:
    """Score artifact using command evaluator via CLI."""
    if not evaluator_command:
        return None

    cmd = [
        sys.executable, "-m", "optimize_anything.cli",
        "score", str(artifact_path),
        "--evaluator-command",
    ] + evaluator_command

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return None
        result = json.loads(proc.stdout)
        return result.get("score")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


def _score_with_judge(
    artifact_path: Path,
    model: str,
    objective: str | None,
) -> float | None:
    """Score artifact using LLM judge via CLI."""
    if not objective:
        return None

    cmd = [
        sys.executable, "-m", "optimize_anything.cli",
        "score", str(artifact_path),
        "--judge-model", model,
        "--objective", objective,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return None
        result = json.loads(proc.stdout)
        return result.get("score")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


if __name__ == "__main__":
    sys.exit(main())
