#!/usr/bin/env python3
"""Set up and summarize realistic optimization benchmark runs."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_PATH = (
    REPO_ROOT / "examples/optimization-observability/evaluator-generation-benchmark.json"
)


def setup_benchmark(benchmark_path: Path, work_dir: Path) -> dict[str, Any]:
    """Copy the benchmark seed into a work directory and return run metadata."""
    config = _load_benchmark(benchmark_path)
    benchmark_id = str(config["id"])
    seed_source = str(config["seed_artifact"])
    source_path = REPO_ROOT / seed_source
    if not source_path.exists():
        raise FileNotFoundError(f"Benchmark seed not found: {source_path}")

    target_dir = work_dir / benchmark_id
    target_dir.mkdir(parents=True, exist_ok=True)
    seed_file = target_dir / "seed.md"
    shutil.copyfile(source_path, seed_file)

    objective_file = target_dir / "objective.txt"
    objective = str(config["objective"])
    objective_file.write_text(objective + "\n", encoding="utf-8")

    run_base_dir = target_dir / "runs"
    run_base_dir.mkdir(exist_ok=True)

    training_command = list(config["training_evaluator_command"])
    heldout_command = list(config["heldout_evaluator_command"])
    optimize_command = [
        "uv",
        "run",
        "optimize-anything",
        "optimize",
        str(seed_file),
        "--objective",
        objective,
        "--budget",
        str(config.get("recommended_budget", 6)),
        "--run-dir",
        str(run_base_dir),
        "--evaluator-command",
        *training_command,
    ]

    return {
        "benchmark": benchmark_id,
        "why": config["why"],
        "seed_source": seed_source,
        "seed_file": str(seed_file),
        "objective_file": str(objective_file),
        "objective": objective,
        "constraints": list(config.get("constraints", [])),
        "run_base_dir": str(run_base_dir),
        "training_evaluator_command": training_command,
        "heldout_evaluator_command": heldout_command,
        "meaningful_delta": float(config.get("meaningful_delta", 0.03)),
        "validation_delta": float(config.get("validation_delta", 0.01)),
        "optimize_command": optimize_command,
    }


def build_observation_report(
    run_dir: Path,
    *,
    benchmark_path: Path | None = None,
    validation_command: list[str] | None = None,
    meaningful_delta: float | None = None,
    validation_delta: float | None = None,
) -> dict[str, Any]:
    """Summarize optimization telemetry and optional held-out validation."""
    config = _load_benchmark(benchmark_path) if benchmark_path else {}
    threshold = _coalesce_float(
        meaningful_delta,
        config.get("meaningful_delta"),
        0.03,
    )
    heldout_threshold = _coalesce_float(
        validation_delta,
        config.get("validation_delta"),
        0.01,
    )
    validation_command = validation_command or config.get("heldout_evaluator_command")

    seed_path = run_dir / "seed.txt"
    best_path = run_dir / "best_artifact.txt"
    summary_path = run_dir / "summary.json"
    _require_file(seed_path)
    _require_file(best_path)
    _require_file(summary_path)

    seed_text = seed_path.read_text(encoding="utf-8")
    best_text = best_path.read_text(encoding="utf-8")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    score_summary = summary.get("score_summary")
    warnings: list[dict[str, str]] = []
    if not isinstance(score_summary, dict):
        score_summary = {}
        _warn(
            warnings,
            "missing_score_summary",
            "summary.json does not include a score_summary object.",
            "Inspect optimizer output and result-contract generation.",
        )

    initial_score = _optional_float(score_summary.get("initial"))
    best_score = _optional_float(score_summary.get("best"))
    score_delta = _score_delta(score_summary, initial_score, best_score)
    candidate_count = _optional_int(score_summary.get("num_candidates"))
    metric_calls = _optional_int(summary.get("total_metric_calls"))
    if metric_calls is None:
        budget = summary.get("budget_utilization")
        if isinstance(budget, dict):
            metric_calls = _optional_int(budget.get("evaluator_calls"))

    diagnostics = summary.get("top_diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
    has_actionable_diagnostics = any(
        isinstance(item, dict) and item.get("name") != "overall_score"
        for item in diagnostics
    )
    if not has_actionable_diagnostics:
        _warn(
            warnings,
            "missing_diagnostics",
            "No actionable top diagnostics were recorded for the best candidate.",
            "Return dimension scores from the evaluator so reflection has actionable feedback.",
        )

    if candidate_count is None or candidate_count <= 1:
        _warn(
            warnings,
            "seed_only",
            "The run did not show candidate exploration beyond the seed.",
            "Increase budget, confirm proposer model credentials, and inspect GEPA artifacts.",
        )

    if score_delta is None:
        _warn(
            warnings,
            "missing_score_delta",
            "The report could not compute best-vs-initial score movement.",
            "Check score_summary.initial and score_summary.best in summary.json.",
        )
    elif abs(score_delta) < 1e-12:
        _warn(
            warnings,
            "flat_scores",
            "Best score did not move from the initial score.",
            "Improve scorer diagnostics, objective specificity, or budget.",
        )

    if score_delta is None or score_delta < threshold:
        _warn(
            warnings,
            "insufficient_improvement",
            f"Score delta is below the meaningful threshold ({threshold:.4f}).",
            "Treat this as weak evidence until a larger gain appears.",
        )

    diff_summary = _diff_summary(seed_text, best_text)
    if not diff_summary["changed"]:
        _warn(
            warnings,
            "seed_and_best_identical",
            "Best artifact is identical to the seed artifact.",
            "Inspect whether optimization produced or accepted any candidate changes.",
        )

    validation = None
    if validation_command:
        validation = _validate_heldout(
            seed_text,
            best_text,
            list(validation_command),
            heldout_threshold,
        )
        if not validation["accepted"]:
            kind = (
                "heldout_regression"
                if validation["score_delta"] is not None
                and validation["score_delta"] < 0
                else "heldout_validation_failed"
            )
            _warn(
                warnings,
                kind,
                "Held-out validation does not agree that the optimized artifact improved.",
                "Review the diff and scorer rubrics before accepting the artifact.",
            )
    else:
        _warn(
            warnings,
            "validation_not_run",
            "No held-out validation command was provided.",
            "Run with --validation-command or use the benchmark default validation scorer.",
        )

    blocking_kinds = {
        "missing_diagnostics",
        "missing_score_summary",
        "seed_only",
        "missing_score_delta",
        "flat_scores",
        "insufficient_improvement",
        "seed_and_best_identical",
        "heldout_regression",
        "heldout_validation_failed",
        "validation_not_run",
    }
    accepted = not any(warning["kind"] in blocking_kinds for warning in warnings)

    return {
        "benchmark": config.get("id"),
        "run_dir": str(run_dir),
        "training": {
            "initial_score": initial_score,
            "best_score": best_score,
            "score_delta": score_delta,
            "candidate_count": candidate_count,
            "metric_calls": metric_calls,
            "diagnostics": diagnostics,
        },
        "diff_summary": diff_summary,
        "validation": validation,
        "warnings": warnings,
        "accepted": accepted,
        "artifacts": {
            "seed": str(seed_path),
            "best_artifact": str(best_path),
            "summary": str(summary_path),
            "optimizer_artifacts": _optimizer_artifacts(run_dir),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="optimization-observer",
        description="Set up and summarize realistic optimization benchmark runs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Copy benchmark seed into a work dir")
    setup_parser.add_argument(
        "--benchmark",
        default=str(DEFAULT_BENCHMARK_PATH),
        help="Benchmark config JSON path.",
    )
    setup_parser.add_argument(
        "--work-dir",
        default="integration_runs/optimization-observability",
        help="Directory for copied seed, objective, and run outputs.",
    )

    report_parser = subparsers.add_parser("report", help="Summarize a saved run directory")
    report_parser.add_argument("--run-dir", required=True, help="Run dir containing summary.json")
    report_parser.add_argument(
        "--benchmark",
        default=None,
        help="Benchmark config JSON path. Supplies thresholds and held-out scorer.",
    )
    report_parser.add_argument(
        "--meaningful-delta",
        type=float,
        default=None,
        help="Minimum training score delta considered meaningful.",
    )
    report_parser.add_argument(
        "--validation-delta",
        type=float,
        default=None,
        help="Minimum held-out score delta required for acceptance.",
    )
    report_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit non-zero when the report is not accepted.",
    )
    report_parser.add_argument(
        "--validation-command",
        nargs="+",
        help="Held-out evaluator command. Must be last when provided.",
    )

    args = parser.parse_args(argv)
    if args.command == "setup":
        result = setup_benchmark(Path(args.benchmark), Path(args.work_dir))
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "report":
        report = build_observation_report(
            Path(args.run_dir),
            benchmark_path=Path(args.benchmark) if args.benchmark else None,
            validation_command=args.validation_command,
            meaningful_delta=args.meaningful_delta,
            validation_delta=args.validation_delta,
        )
        print(json.dumps(report, indent=2))
        return 1 if args.strict and not report["accepted"] else 0

    return 1


def _load_benchmark(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    resolved = path if path.is_absolute() else REPO_ROOT / path
    return json.loads(resolved.read_text(encoding="utf-8"))


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required run artifact missing: {path}")


def _coalesce_float(*values: Any) -> float:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    raise ValueError("No numeric value provided")


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _score_delta(
    score_summary: dict[str, Any],
    initial_score: float | None,
    best_score: float | None,
) -> float | None:
    explicit = _optional_float(score_summary.get("delta_best_vs_initial"))
    if explicit is not None:
        return explicit
    if initial_score is None or best_score is None:
        return None
    return round(best_score - initial_score, 6)


def _warn(
    warnings: list[dict[str, str]],
    kind: str,
    message: str,
    recommendation: str,
) -> None:
    warnings.append({
        "kind": kind,
        "message": message,
        "recommendation": recommendation,
    })


def _diff_summary(seed_text: str, best_text: str) -> dict[str, Any]:
    diff_lines = list(
        difflib.unified_diff(
            seed_text.splitlines(),
            best_text.splitlines(),
            fromfile="seed",
            tofile="optimized",
            lineterm="",
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return {
        "changed": seed_text != best_text,
        "added": added,
        "removed": removed,
        "preview": diff_lines[:40],
    }


def _validate_heldout(
    seed_text: str,
    best_text: str,
    command: list[str],
    threshold: float,
) -> dict[str, Any]:
    seed_result = _run_evaluator(command, seed_text)
    best_result = _run_evaluator(command, best_text)
    seed_score = _optional_float(seed_result.get("score"))
    best_score = _optional_float(best_result.get("score"))
    score_delta = (
        None
        if seed_score is None or best_score is None
        else round(best_score - seed_score, 6)
    )
    accepted = score_delta is not None and score_delta >= threshold
    return {
        "command": command,
        "threshold": threshold,
        "seed_score": seed_score,
        "best_score": best_score,
        "score_delta": score_delta,
        "accepted": accepted,
        "seed_feedback": seed_result.get("feedback", []),
        "best_feedback": best_result.get("feedback", []),
    }


def _run_evaluator(command: list[str], candidate: str) -> dict[str, Any]:
    payload = json.dumps({"candidate": candidate})
    proc = subprocess.run(
        command,
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    if proc.returncode != 0:
        return {
            "score": None,
            "error": f"Evaluator exited with code {proc.returncode}",
            "stderr": proc.stderr.strip()[:500],
        }
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "score": None,
            "error": f"Evaluator output is not valid JSON: {exc}",
            "stdout": proc.stdout.strip()[:500],
        }
    score = _optional_float(result.get("score"))
    if score is None:
        result["error"] = "Evaluator did not return a finite numeric score"
    return result


def _optimizer_artifacts(run_dir: Path) -> list[str]:
    core = {"seed.txt", "best_artifact.txt", "summary.json"}
    return [
        str(path)
        for path in sorted(run_dir.iterdir())
        if path.name not in core
    ]


if __name__ == "__main__":
    raise SystemExit(main())
