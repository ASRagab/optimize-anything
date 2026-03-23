#!/usr/bin/env python3
"""Run repeatable Claude Code plugin regression scenarios and validate outputs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PluginRegressionFailure(RuntimeError):
    pass


SEED_BASELINE = "You are a helpful assistant."


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return (Path.cwd() / "plugin_regressions" / f"plugin-{_timestamp()}").resolve()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _require_env(name: str) -> None:
    if not os.environ.get(name):
        raise PluginRegressionFailure(f"missing required environment variable: {name}")


def _ensure_seed(repo_root: Path) -> Path:
    seed_path = repo_root / "runs" / "zo-eval" / "seed.txt"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    if not seed_path.exists():
        seed_path.write_text(SEED_BASELINE + "\n")
    return seed_path


def _claude_base(repo_root: Path) -> list[str]:
    return [
        "claude",
        "-p",
        "--plugin-dir",
        str(repo_root),
        "--output-format",
        "json",
        "--allowedTools",
        "Bash Read Write Edit Glob Grep",
        "--max-budget-usd",
        "0.50",
    ]


def _run_claude(repo_root: Path, prompt: str, output_file: Path, stderr_file: Path) -> dict[str, Any]:
    cmd = _claude_base(repo_root) + [prompt]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    _write_text(output_file, proc.stdout)
    _write_text(stderr_file, proc.stderr)
    if proc.returncode != 0:
        raise PluginRegressionFailure(f"claude exited {proc.returncode}; see {stderr_file.name}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PluginRegressionFailure(f"invalid JSON from claude: {exc}; see {output_file.name}") from exc


def _assert_success(payload: dict[str, Any], scenario: str) -> str:
    if payload.get("subtype") != "success" or payload.get("is_error"):
        raise PluginRegressionFailure(f"{scenario}: claude did not report success")
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise PluginRegressionFailure(f"{scenario}: missing textual result summary")
    return result


def _assert_contains(result: str, scenario: str, needles: list[str]) -> None:
    lowered = result.lower()
    missing = [needle for needle in needles if needle.lower() not in lowered]
    if missing:
        raise PluginRegressionFailure(f"{scenario}: result missing expected text: {', '.join(missing)}")


def scenario_analyze(repo_root: Path, output_dir: Path, seed_path: Path) -> dict[str, Any]:
    prompt = (
        f"Use the optimize-anything plugin to analyze the artifact at {seed_path} for quality dimensions. "
        "Run: optimize-anything analyze runs/zo-eval/seed.txt --judge-model openai/gpt-4o-mini "
        "--objective 'Score the quality of this system prompt'"
    )
    payload = _run_claude(repo_root, prompt, output_dir / "analyze.json", output_dir / "analyze.stderr.log")
    result = _assert_success(payload, "analyze")
    _assert_contains(result, "analyze", ["current score", "specificity", "optimize-anything optimize"])
    return {
        "scenario": "analyze",
        "turns": payload.get("num_turns"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
    }


def scenario_validate(repo_root: Path, output_dir: Path, seed_path: Path) -> dict[str, Any]:
    prompt = (
        f"Use the optimize-anything plugin to validate the artifact at {seed_path} across multiple providers. "
        "Run: optimize-anything validate runs/zo-eval/seed.txt --providers openai/gpt-4o-mini "
        "anthropic/claude-haiku-4-5-20251001 --objective 'Score the quality and clarity of this system prompt'"
    )
    payload = _run_claude(repo_root, prompt, output_dir / "validate.json", output_dir / "validate.stderr.log")
    result = _assert_success(payload, "validate")
    _assert_contains(result, "validate", ["mean", "stddev", "provider"])
    return {
        "scenario": "validate",
        "turns": payload.get("num_turns"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
    }


def scenario_quick(repo_root: Path, output_dir: Path, seed_path: Path) -> dict[str, Any]:
    best_path = repo_root / "runs" / "plugin-eval" / "quick-best.txt"
    prompt = (
        f"Use the optimize-anything plugin to quickly optimize the seed at {seed_path}. "
        f"Run: optimize-anything optimize runs/zo-eval/seed.txt --judge-model openai/gpt-4o-mini "
        f"--objective 'Improve clarity and specificity of this system prompt' --budget 5 "
        f"--model openai/gpt-4o-mini --output {best_path}"
    )
    payload = _run_claude(repo_root, prompt, output_dir / "quick.json", output_dir / "quick.stderr.log")
    result = _assert_success(payload, "quick")
    quick_lower = result.lower()
    if not (("initial score" in quick_lower and "best score" in quick_lower) or ("0.4" in quick_lower and "0.85" in quick_lower)):
        raise PluginRegressionFailure("quick: result is missing recognizable score reporting")
    if "delta" not in quick_lower and "retained" not in quick_lower and "improvement" not in quick_lower and "better version" not in quick_lower:
        raise PluginRegressionFailure("quick: result is missing improvement/retention evidence")
    if not best_path.exists():
        raise PluginRegressionFailure("quick: expected optimized artifact file was not written")
    best_text = best_path.read_text().strip()
    if len(best_text) <= len(SEED_BASELINE):
        raise PluginRegressionFailure("quick: optimized artifact did not materially improve on seed length/detail")
    specificity_cues = ["clear", "concise", "clarify", "context", "specific", "knowledgeable", "supportive"]
    if not any(cue in best_text.lower() for cue in specificity_cues):
        raise PluginRegressionFailure("quick: optimized artifact lacks obvious specificity cues")
    return {
        "scenario": "quick",
        "turns": payload.get("num_turns"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
        "best_artifact_file": str(best_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Claude Code plugin regression scenarios and validate outputs."
    )
    parser.add_argument("--output-dir", help="Directory for saved plugin regression artifacts.")
    parser.add_argument(
        "--scenario",
        choices=["all", "analyze", "validate", "quick"],
        default="all",
        help="Which scenario to run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _require_env("OPENAI_API_KEY")
        _require_env("ANTHROPIC_API_KEY")
        seed_path = _ensure_seed(repo_root)

        scenarios: list[tuple[str, Any]] = []
        if args.scenario in {"all", "analyze"}:
            scenarios.append(("analyze", scenario_analyze))
        if args.scenario in {"all", "validate"}:
            scenarios.append(("validate", scenario_validate))
        if args.scenario in {"all", "quick"}:
            scenarios.append(("quick", scenario_quick))

        results = [fn(repo_root, output_dir, seed_path) for _, fn in scenarios]
        summary = {"overall": "PASS", "results": results}
        _write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 0
    except PluginRegressionFailure as exc:
        payload = {"overall": "FAIL", "error": str(exc)}
        _write_json(output_dir / "summary.json", payload)
        print(json.dumps(payload, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
