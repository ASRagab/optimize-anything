"""Run-directory persistence, diff output, and artifact writing."""
from __future__ import annotations

import difflib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, TextIO


def _timestamped_run_dir(run_dir: str) -> str:
    """Build a timestamped run directory path under the user-provided base path."""
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return str(Path(run_dir).expanduser() / f"run-{timestamp}")


def _save_run_dir(
    *,
    run_dir: str,
    seed: str,
    best_artifact: str | object,
    summary: dict,
) -> str | None:
    """Save supplementary run artifacts to an already-resolved run directory.

    Returns the created directory path, or None if writing failed.
    """
    out = Path(run_dir).expanduser()
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "seed.txt").write_text(seed)
        best_text = best_artifact if isinstance(best_artifact, str) else json.dumps(best_artifact)
        (out / "best_artifact.txt").write_text(best_text)
        (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        return str(out)
    except OSError as exc:
        print(f"Warning: failed to write run-dir '{out}': {exc}", file=sys.stderr)
        return None


def _copy_cache_from_run(source_run_dir: str, target_run_dir: str) -> str | None:
    """Copy fitness cache files from an existing run into a new run dir."""
    source = Path(source_run_dir).expanduser()
    if not source.exists() or not source.is_dir():
        return f"--cache-from directory does not exist: {source}"

    source_cache = source / "fitness_cache"
    if not source_cache.exists() or not source_cache.is_dir():
        return f"no fitness_cache found in --cache-from directory: {source_cache}"

    destination_cache = Path(target_run_dir).expanduser() / "fitness_cache"
    try:
        destination_cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_cache, destination_cache, dirs_exist_ok=True)
    except OSError as exc:
        return f"failed to copy cache from '{source_cache}' to '{destination_cache}': {exc}"
    return None


def _print_optimize_diff(
    seed: str | None,
    best_artifact: Any,
    *,
    file: TextIO | None = None,
) -> None:
    if seed is None:
        print("(no diff: seedless mode has no seed artifact)", file=file)
        return

    seed_lines = seed.splitlines(keepends=True)
    best_str = best_artifact if isinstance(best_artifact, str) else json.dumps(best_artifact)
    best_lines = best_str.splitlines(keepends=True)
    diff_output = difflib.unified_diff(
        seed_lines,
        best_lines,
        fromfile="seed",
        tofile="optimized",
    )
    diff_text = "".join(diff_output)
    if diff_text:
        print("\n--- diff: seed vs optimized ---", file=file)
        print(diff_text, end="", file=file)
        print("--- end diff ---", file=file)
    else:
        print("(no diff: seed and optimized artifact are identical)", file=file)


def _print_judge_plateau_advisory(
    *,
    judge_model: str,
    proposer_model: str | None,
    has_intake: bool,
    file: TextIO | None = None,
) -> None:
    """Print actionable suggestions when LLM judge optimization plateaus."""
    lines = [
        "",
        "Plateau detected with LLM judge. Suggestions:",
        f"  1. Run `optimize-anything analyze <artifact> --judge-model {judge_model} --objective <objective>` to discover quality dimensions",
    ]
    if proposer_model:
        lines.append(
            f"  2. Consider a stronger --model (current: {proposer_model})"
        )
    else:
        lines.append("  2. Try specifying --model with a stronger proposer LLM")
    if not has_intake:
        lines.append(
            "  3. Try --intake-json with quality_dimensions for more granular scoring"
        )
    for line in lines:
        print(line, file=file)
