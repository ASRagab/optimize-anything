#!/usr/bin/env python3
"""Run repeatable CLI smoke checks with saved artifacts/logs."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SmokeFailure(RuntimeError):
    """Raised when a smoke run fails a contract check."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return (Path.cwd() / "smoke_outputs" / f"smoke-{_timestamp()}").resolve()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _parse_json_with_optional_prefix(text: str, run_name: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise SmokeFailure(f"{run_name}: empty output; expected JSON summary")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, consumed = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if text[idx + consumed :].strip():
                continue
            if isinstance(parsed, dict):
                return parsed
        raise SmokeFailure(f"{run_name}: failed to parse JSON summary from output")

    if not isinstance(parsed, dict):
        raise SmokeFailure(f"{run_name}: expected JSON object summary")
    return parsed


def _prepare_temp_inputs(tmp_dir: Path) -> tuple[str, Path, Path]:
    seed_text = (
        "You are a writing assistant. Improve this blurb while preserving facts:\n"
        "Our launch is Monday and the beta has room for 20 teams."
    )
    seed_path = tmp_dir / "seed.txt"
    seed_path.write_text(seed_text)

    evaluator_path = tmp_dir / "eval.sh"
    evaluator_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "input_payload=$(cat)\n"
        "python3 - \"$input_payload\" <<'PY'\n"
        "import json\n"
        "import sys\n"
        "payload = json.loads(sys.argv[1])\n"
        "candidate = str(payload.get('candidate', ''))\n"
        "score = min(1.0, 0.2 + len(candidate) / 200.0)\n"
        "json.dump({'score': score, 'length': len(candidate), 'quality_hint': 'length_proxy'}, sys.stdout)\n"
        "sys.stdout.write('\\n')\n"
        "PY\n"
    )
    evaluator_path.chmod(0o755)

    return seed_text, seed_path, evaluator_path


def _assert_summary(run_name: str, summary: dict[str, Any]) -> None:
    best_artifact = summary.get("best_artifact")
    if not isinstance(best_artifact, str) or not best_artifact.strip():
        raise SmokeFailure(f"{run_name}: best_artifact is empty")

    metric_calls = summary.get("total_metric_calls")
    if not isinstance(metric_calls, int) or metric_calls <= 0:
        raise SmokeFailure(f"{run_name}: total_metric_calls must be > 0")

    if "top_diagnostics" not in summary:
        raise SmokeFailure(f"{run_name}: missing top_diagnostics")
    if "score_summary" not in summary:
        raise SmokeFailure(f"{run_name}: missing score_summary")


def _run_cli_smoke(
    *,
    seed_path: Path,
    evaluator_path: Path,
    evaluator_cwd: Path,
    budget: int,
    output_dir: Path,
) -> dict[str, Any]:
    cli_output_path = output_dir / "cli_best_artifact.txt"
    command = [
        sys.executable,
        "-m",
        "optimize_anything.cli",
        "optimize",
        str(seed_path),
        "--evaluator-command",
        "bash",
        evaluator_path.name,
        "--evaluator-cwd",
        str(evaluator_cwd),
        "--budget",
        str(budget),
        "--output",
        str(cli_output_path),
    ]

    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    _write_text(output_dir / "cli_command.txt", shlex.join(command))
    _write_text(output_dir / "cli_stdout.log", proc.stdout)
    _write_text(output_dir / "cli_stderr.log", proc.stderr)

    if proc.returncode != 0:
        raise SmokeFailure(
            f"cli: command failed (exit {proc.returncode}). See cli_stderr.log."
        )

    summary = _parse_json_with_optional_prefix(proc.stdout, "cli")
    _write_json(output_dir / "cli_summary.json", summary)
    return summary


def _run_generate_evaluator_smoke(
    *,
    seed_path: Path,
    output_dir: Path,
) -> None:
    command = [
        sys.executable,
        "-m",
        "optimize_anything.cli",
        "generate-evaluator",
        str(seed_path),
        "--objective",
        "maximize clarity",
    ]

    proc = subprocess.run(command, capture_output=True, text=True)

    _write_text(output_dir / "generate_evaluator_stdout.log", proc.stdout)
    _write_text(output_dir / "generate_evaluator_stderr.log", proc.stderr)

    if proc.returncode != 0:
        raise SmokeFailure(
            f"generate-evaluator: command failed (exit {proc.returncode}). "
            "See generate_evaluator_stderr.log."
        )

    if not proc.stdout.startswith("#!/"):
        raise SmokeFailure(
            "generate-evaluator: output missing shebang (expected script)"
        )


def _run_intake_smoke(*, output_dir: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "optimize_anything.cli",
        "intake",
        "--artifact-class",
        "prompt",
        "--execution-mode",
        "command",
    ]

    proc = subprocess.run(command, capture_output=True, text=True)

    _write_text(output_dir / "intake_stdout.log", proc.stdout)
    _write_text(output_dir / "intake_stderr.log", proc.stderr)

    if proc.returncode != 0:
        raise SmokeFailure(
            f"intake: command failed (exit {proc.returncode}). See intake_stderr.log."
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise SmokeFailure("intake: output is not valid JSON")

    if not isinstance(data, dict) or "execution_mode" not in data:
        raise SmokeFailure("intake: output missing expected fields")


def run_smoke_suite(*, budget: int, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="opt-anything-smoke-") as tmp:
        tmp_dir = Path(tmp)
        seed_text, seed_path, evaluator_path = _prepare_temp_inputs(tmp_dir)

        cli_summary = _run_cli_smoke(
            seed_path=seed_path,
            evaluator_path=evaluator_path,
            evaluator_cwd=tmp_dir,
            budget=budget,
            output_dir=output_dir,
        )
        _assert_summary("cli", cli_summary)

        _run_generate_evaluator_smoke(seed_path=seed_path, output_dir=output_dir)
        _run_intake_smoke(output_dir=output_dir)

    combined = {"budget": budget, "cli": cli_summary}
    _write_json(output_dir / "combined_summary.json", combined)
    return combined


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CLI optimize smokes and enforce output contract checks."
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=1,
        help="Max metric calls per smoke run (must be 1-3).",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save logs/artifacts. Defaults to smoke_outputs/smoke-<timestamp>.",
    )
    args = parser.parse_args(argv)
    if args.budget < 1 or args.budget > 3:
        parser.error("--budget must be between 1 and 3")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = _resolve_output_dir(args.output_dir)

    try:
        run_smoke_suite(budget=args.budget, output_dir=output_dir)
    except SmokeFailure as exc:
        _write_json(output_dir / "failure.json", {"error": str(exc)})
        print(f"overall=FAIL output_dir={output_dir}")
        print(f"reason={exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive fallback
        _write_json(
            output_dir / "failure.json",
            {"error": f"unexpected exception: {type(exc).__name__}: {exc}"},
        )
        print(f"overall=FAIL output_dir={output_dir}")
        print(f"reason=unexpected exception: {type(exc).__name__}: {exc}")
        return 1

    print(f"cli=PASS overall=PASS output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
