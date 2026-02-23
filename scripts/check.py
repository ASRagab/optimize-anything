#!/usr/bin/env python3
"""Unified validation gate: runs pytest, smoke harness, and score check.

Usage:
    python scripts/check.py [--skip-smoke]

Exits 0 if all gates pass, 1 if any gate fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run_gate(label: str, cmd: list[str], cwd: Path) -> bool:
    """Run a single gate command and return True if it passed."""
    print(f"\n{'='*60}")
    print(f"Gate: {label}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=str(cwd))

    if result.returncode == 0:
        print(f"\n[PASS] {label}")
        return True
    else:
        print(f"\n[FAIL] {label} (exit code {result.returncode})")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run all validation gates: pytest, smoke harness, score check."
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        default=False,
        help="Skip the smoke harness gate (use for offline testing).",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).parent.parent.resolve()

    results: list[tuple[str, bool]] = []

    # Gate 1: pytest
    passed = _run_gate(
        "pytest",
        ["uv", "run", "pytest"],
        cwd=root,
    )
    results.append(("pytest", passed))

    # Gate 2: smoke harness
    if args.skip_smoke:
        print("\n[SKIP] smoke harness (--skip-smoke)")
        results.append(("smoke harness", True))
    else:
        passed = _run_gate(
            "smoke harness",
            ["uv", "run", "python", "scripts/smoke_harness.py", "--budget", "1"],
            cwd=root,
        )
        results.append(("smoke harness", passed))

    # Gate 3: score check
    passed = _run_gate(
        "score check",
        ["uv", "run", "python", "scripts/score_check.py"],
        cwd=root,
    )
    results.append(("score check", passed))

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print("=" * 60)
    all_passed = True
    for label, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            all_passed = False

    if all_passed:
        print("\nAll gates passed.")
        return 0
    else:
        print("\nOne or more gates failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
