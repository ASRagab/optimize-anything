#!/usr/bin/env python3
"""Run the smoke harness twice and fail if either pass fails."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return (Path.cwd() / "smoke_outputs" / f"consecutive-{_timestamp()}").resolve()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _run_pass(
    *,
    harness_path: Path,
    budget: int,
    pass_output_dir: Path,
    gate_output_dir: Path,
    pass_name: str,
) -> bool:
    command = [
        sys.executable,
        str(harness_path),
        "--budget",
        str(budget),
        "--output-dir",
        str(pass_output_dir),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)

    _write_text(gate_output_dir / f"{pass_name}_command.txt", shlex.join(command))
    _write_text(gate_output_dir / f"{pass_name}_stdout.log", proc.stdout)
    _write_text(gate_output_dir / f"{pass_name}_stderr.log", proc.stderr)

    return proc.returncode == 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run smoke_harness.py twice consecutively and enforce pass/fail gate."
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=1,
        help="Max metric calls per harness run (must be 1-3).",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save gate logs. Defaults to smoke_outputs/consecutive-<timestamp>.",
    )
    args = parser.parse_args(argv)
    if args.budget < 1 or args.budget > 3:
        parser.error("--budget must be between 1 and 3")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    harness_path = Path(__file__).resolve().with_name("smoke_harness.py")

    pass1_dir = output_dir / "pass1"
    pass2_dir = output_dir / "pass2"

    pass1_ok = _run_pass(
        harness_path=harness_path,
        budget=args.budget,
        pass_output_dir=pass1_dir,
        gate_output_dir=output_dir,
        pass_name="pass1",
    )
    pass2_ok = _run_pass(
        harness_path=harness_path,
        budget=args.budget,
        pass_output_dir=pass2_dir,
        gate_output_dir=output_dir,
        pass_name="pass2",
    )

    overall_ok = pass1_ok and pass2_ok
    pass1_label = "PASS" if pass1_ok else "FAIL"
    pass2_label = "PASS" if pass2_ok else "FAIL"
    overall_label = "PASS" if overall_ok else "FAIL"

    summary = {
        "pass1": pass1_label,
        "pass2": pass2_label,
        "overall": overall_label,
        "output_dir": str(output_dir),
    }
    _write_json(output_dir / "summary.json", summary)

    print(f"pass1={pass1_label}")
    print(f"pass2={pass2_label}")
    print(f"overall={overall_label}")
    print(f"output_dir={output_dir}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
