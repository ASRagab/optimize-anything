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
EMBEDDED_PREFIX = 'SYSTEM_PROMPT = """'
EMBEDDED_PROMPT = "Be helpful."
EMBEDDED_SUFFIX = '"""\nKEEP = 1\n'
EMBEDDED_BASELINE = EMBEDDED_PREFIX + EMBEDDED_PROMPT + EMBEDDED_SUFFIX


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


def _required_env_names(scenario: str) -> list[str]:
    names = ["OPENAI_API_KEY"]
    if scenario in {"all", "validate"}:
        names.append("ANTHROPIC_API_KEY")
    return names


def _ensure_seed(repo_root: Path) -> Path:
    seed_path = repo_root / "runs" / "zo-eval" / "seed.txt"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    if not seed_path.exists():
        seed_path.write_text(SEED_BASELINE + "\n")
    return seed_path


def _ensure_repository_fixture(output_dir: Path) -> Path:
    fixture = output_dir / "repository-apply" / "prompt_module.py"
    _write_text(fixture, EMBEDDED_BASELINE)
    return fixture


def _inline_prompt() -> str:
    return (
        "Use $optimize-prompt in fast mode on this inline prompt: "
        "'You are a helpful assistant.' Use openai/gpt-4o-mini as proposer and judge, "
        "a budget of 3, and return the complete accepted prompt with prompt-quality "
        "evidence and score delta. Do not modify repository files."
    )


def _repository_apply_prompt(fixture: Path) -> str:
    return (
        f"Use $optimize-prompt in fast mode on SYSTEM_PROMPT in {fixture}. "
        "Improve clarity and specificity with openai/gpt-4o-mini as proposer and judge "
        "and a budget of 3. Apply only an accepted candidate to that exact string, "
        "preserve KEEP = 1 and valid Python syntax, then report prompt-quality evidence "
        "and score delta."
    )


def _workflow_fixture_ids(repo_root: Path) -> list[str]:
    path = repo_root / "tests" / "fixtures" / "optimize_prompt_workflow.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    return [str(case["id"]) for case in cases]


def _write_dry_run(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    fixture = _ensure_repository_fixture(output_dir)
    summary = {
        "overall": "DRY_RUN",
        "workflow_fixture_ids": _workflow_fixture_ids(repo_root),
        "live_scenarios": [
            {"scenario": "inline", "prompt": _inline_prompt()},
            {
                "scenario": "repository-apply",
                "prompt": _repository_apply_prompt(fixture),
                "artifact": str(fixture),
            },
        ],
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _validate_repository_apply(updated: str, fixture: Path) -> str:
    if not updated.startswith(EMBEDDED_PREFIX) or not updated.endswith(EMBEDDED_SUFFIX):
        raise PluginRegressionFailure(
            "repository-apply: content outside the recorded prompt region changed"
        )
    candidate = updated[len(EMBEDDED_PREFIX) : -len(EMBEDDED_SUFFIX)]
    if not candidate.strip() or candidate == EMBEDDED_PROMPT:
        raise PluginRegressionFailure("repository-apply: prompt fixture was not updated")
    try:
        compile(updated, str(fixture), "exec")
    except SyntaxError as exc:
        raise PluginRegressionFailure(f"repository-apply: invalid Python after apply: {exc}") from exc
    return candidate


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
        "Run: optimize-anything analyze runs/zo-eval/seed.txt --judge-model openai/gpt-5.6-luna "
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
        "Run: optimize-anything validate runs/zo-eval/seed.txt --providers openai/gpt-5.6-luna "
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
        f"Run: optimize-anything optimize runs/zo-eval/seed.txt --judge-model openai/gpt-5.6-luna "
        f"--objective 'Improve clarity and specificity of this system prompt' --budget 5 "
        f"--model openai/gpt-5.6-sol --output {best_path}"
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


def scenario_inline(repo_root: Path, output_dir: Path, seed_path: Path) -> dict[str, Any]:
    payload = _run_claude(
        repo_root,
        _inline_prompt(),
        output_dir / "inline.json",
        output_dir / "inline.stderr.log",
    )
    result = _assert_success(payload, "inline")
    _assert_contains(result, "inline", ["prompt-quality", "score", "helpful assistant"])
    return {
        "scenario": "inline",
        "turns": payload.get("num_turns"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
        "returned": True,
    }


def scenario_repository_apply(
    repo_root: Path, output_dir: Path, seed_path: Path
) -> dict[str, Any]:
    fixture = _ensure_repository_fixture(output_dir)
    payload = _run_claude(
        repo_root,
        _repository_apply_prompt(fixture),
        output_dir / "repository-apply.json",
        output_dir / "repository-apply.stderr.log",
    )
    result = _assert_success(payload, "repository-apply")
    _assert_contains(result, "repository-apply", ["prompt-quality", "score"])
    updated = fixture.read_text(encoding="utf-8")
    _validate_repository_apply(updated, fixture)
    return {
        "scenario": "repository-apply",
        "turns": payload.get("num_turns"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
        "artifact": str(fixture),
        "applied": True,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Claude Code plugin regression scenarios and validate outputs."
    )
    parser.add_argument("--output-dir", help="Directory for saved plugin regression artifacts.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write workflow prompts and fixture artifacts without credentials or model calls.",
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "analyze", "validate", "quick", "inline", "repository-apply"],
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
        if args.dry_run:
            summary = _write_dry_run(repo_root, output_dir)
            print(json.dumps(summary, indent=2))
            return 0

        for name in _required_env_names(args.scenario):
            _require_env(name)
        seed_path = _ensure_seed(repo_root)

        scenarios: list[tuple[str, Any]] = []
        if args.scenario in {"all", "analyze"}:
            scenarios.append(("analyze", scenario_analyze))
        if args.scenario in {"all", "validate"}:
            scenarios.append(("validate", scenario_validate))
        if args.scenario in {"all", "quick"}:
            scenarios.append(("quick", scenario_quick))
        if args.scenario in {"all", "inline"}:
            scenarios.append(("inline", scenario_inline))
        if args.scenario in {"all", "repository-apply"}:
            scenarios.append(("repository-apply", scenario_repository_apply))

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
