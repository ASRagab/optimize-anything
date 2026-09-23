"""CLI entry point for optimize-anything."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shlex
import sys
from typing import Any, Callable

from optimize_anything.preflight import (
    _preflight_command_evaluator,
    _preflight_http_evaluator,
)
from optimize_anything.model_defaults import DEFAULT_EVALUATOR_MODEL
from optimize_anything.llm_backends.base import Role

EvaluatorFn = Callable[..., tuple[float, dict[str, Any]]]
EvaluatorFactory = Callable[..., EvaluatorFn]


def _add_subscription_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--subscription-concurrency",
        type=int,
        default=1,
        help="Maximum concurrent calls per subscription provider (default: 1).",
    )
    parser.add_argument(
        "--no-api-fallback",
        action="store_true",
        default=False,
        help="Never switch a subscription request to a billed API call.",
    )
    parser.add_argument(
        "--openai-api-fallback-model",
        help="OpenAI API model used if an eligible Codex subscription call fails.",
    )
    parser.add_argument(
        "--anthropic-api-fallback-model",
        help="Anthropic API model used if an eligible Claude subscription call fails.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="optimize-anything",
        description="Optimize any text artifact using gepa",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # optimize subcommand
    opt_parser = subparsers.add_parser("optimize", help="Run optimization")
    opt_parser.add_argument("seed_file", nargs="?", help="Path to seed artifact file")
    opt_parser.add_argument(
        "--no-seed",
        action="store_true",
        default=False,
        help="Run without a seed file; GEPA bootstraps from --objective.",
    )
    opt_parser.add_argument(
        "--evaluator-command", nargs="+", help="Shell command for evaluation"
    )
    opt_parser.add_argument("--evaluator-url", help="HTTP endpoint for evaluation")
    opt_parser.add_argument(
        "--intake-json", help="Evaluator intake spec as an inline JSON string"
    )
    opt_parser.add_argument(
        "--intake-file", help="Path to evaluator intake specification JSON file"
    )
    opt_parser.add_argument(
        "--evaluator-cwd",
        help="Working directory for evaluator command execution",
    )
    opt_parser.add_argument("--objective", help="Natural language objective")
    opt_parser.add_argument("--background", help="Domain context")
    opt_parser.add_argument("--dataset", help="Path to training dataset JSONL file")
    opt_parser.add_argument("--valset", help="Path to validation dataset JSONL file")
    opt_parser.add_argument(
        "--budget", type=int, default=None, help="Max evaluator calls (default: 100)"
    )
    opt_parser.add_argument("--output", "-o", help="Output file for best candidate")
    opt_parser.add_argument(
        "--model",
        help=(
            "LiteLLM model string for the proposer LLM. Proposer: "
            "openai/gpt-5.6-sol or anthropic/claude-sonnet-5. "
            "Falls back to OPTIMIZE_ANYTHING_MODEL env var."
        ),
    )
    opt_parser.add_argument(
        "--proposer-backend",
        choices=["api", "codex", "claude"],
        default=None,
        help="Backend for proposal generation (default: api).",
    )
    opt_parser.add_argument(
        "--judge-model",
        help=(
            "LiteLLM model string for built-in LLM-as-judge evaluation. "
            "Judge: openai/gpt-5.6-luna. "
            "Mutually exclusive with --evaluator-command and --evaluator-url."
        ),
    )
    opt_parser.add_argument(
        "--judge-backend",
        choices=["api", "codex", "claude"],
        default=None,
        help="Backend for the built-in LLM judge (default: api).",
    )
    _add_subscription_options(opt_parser)
    opt_parser.add_argument(
        "--judge-objective",
        help="Objective for the LLM judge. Falls back to --objective if not set.",
    )
    opt_parser.add_argument(
        "--api-base",
        help=(
            "Override API base URL for litellm calls "
            "(e.g. https://openrouter.ai/api/v1 or http://localhost:11434/v1)."
        ),
    )
    opt_parser.add_argument(
        "--diff",
        action="store_true",
        default=False,
        help="After optimization, print a unified diff of seed vs best artifact to stderr",
    )
    opt_parser.add_argument(
        "--run-dir",
        help=(
            "Directory to save run artifacts. Creates <path>/run-<timestamp>/ "
            "with seed.txt, best_artifact.txt, summary.json, and GEPA runtime artifacts."
        ),
    )
    opt_parser.add_argument(
        "--parallel",
        dest="parallel",
        action="store_true",
        default=None,
        help="Enable parallel evaluator calls (default).",
    )
    opt_parser.add_argument(
        "--no-parallel",
        dest="parallel",
        action="store_false",
        help="Run evaluator calls serially.",
    )
    opt_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Maximum worker count for parallel evaluation.",
    )
    opt_parser.add_argument(
        "--proposals-per-iteration",
        type=int,
        default=None,
        help=(
            "Candidate mutations per GEPA iteration (default: 1). "
            "Independent of evaluator --workers."
        ),
    )
    opt_parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Enable evaluator result caching.",
    )
    opt_parser.add_argument(
        "--cache-from",
        help=(
            "Path to a previous run directory whose fitness_cache/ entries should be reused. "
            "Requires --cache."
        ),
    )
    opt_parser.add_argument(
        "--early-stop",
        action="store_true",
        default=False,
        help="Enable plateau-based early stopping (auto-enabled when budget > 30).",
    )
    opt_parser.add_argument(
        "--early-stop-window",
        type=int,
        default=10,
        help="Plateau window size for early stopping.",
    )
    opt_parser.add_argument(
        "--early-stop-threshold",
        type=float,
        default=0.005,
        help="Minimum required score improvement over the early-stop window.",
    )
    opt_parser.add_argument(
        "--spec-file",
        help="Path to a TOML spec file for repeatable optimization runs.",
    )
    opt_parser.add_argument(
        "--task-model",
        help="Optional task model metadata to forward to evaluators.",
    )
    opt_parser.add_argument(
        "--score-range",
        choices=["unit", "any"],
        default="unit",
        help="Score validation mode for command/http evaluators: unit (0..1) or any finite float.",
    )

    # generate-evaluator subcommand
    gen_parser = subparsers.add_parser(
        "generate-evaluator", help="Generate an evaluator script"
    )
    gen_parser.add_argument("seed_file", help="Path to seed artifact file")
    gen_parser.add_argument(
        "--objective", required=True, help="Natural language objective"
    )
    gen_parser.add_argument(
        "--evaluator-type",
        choices=["judge", "command", "http", "composite"],
        default="judge",
        help="Script type: 'judge' (Python litellm), 'command' (bash), 'http' (Python server), or 'composite'",
    )
    gen_parser.add_argument(
        "--model",
        default=None,
        help=(
            "LiteLLM model to hardcode in generated judge/composite evaluators "
            f"(API default: {DEFAULT_EVALUATOR_MODEL}; subscription default: provider choice)"
        ),
    )
    gen_parser.add_argument(
        "--judge-backend",
        choices=["api", "codex", "claude"],
        default=None,
        help="Backend configured in generated judge/composite evaluators.",
    )
    gen_parser.add_argument("--api-base", help="API base for the generated evaluator runtime.")
    _add_subscription_options(gen_parser)
    gen_parser.add_argument(
        "--dataset",
        action="store_true",
        default=False,
        help="Generate dataset-aware template (expects {'candidate': '...', 'example': {...}} input).",
    )
    gen_parser.add_argument(
        "--intake-json", help="Evaluator intake spec as an inline JSON string"
    )
    gen_parser.add_argument(
        "--intake-file", help="Path to evaluator intake specification JSON file"
    )

    # intake subcommand
    intake_parser = subparsers.add_parser(
        "intake", help="Normalize evaluator intake specification"
    )
    intake_parser.add_argument("--artifact-class", help="Type of artifact being optimized")
    intake_parser.add_argument(
        "--execution-mode", choices=["command", "http"], help="Evaluator transport"
    )
    intake_parser.add_argument(
        "--evaluation-pattern",
        choices=["verification", "judge", "simulation", "composite"],
        help="Scoring strategy",
    )
    intake_parser.add_argument(
        "--hard-constraint", action="append", dest="hard_constraints", help="Hard constraint (repeatable)"
    )
    intake_parser.add_argument("--evaluator-cwd", help="Working directory for evaluator")
    intake_parser.add_argument(
        "--intake-json", help="Evaluator intake spec as an inline JSON string"
    )
    intake_parser.add_argument(
        "--intake-file", help="Path to evaluator intake specification JSON file"
    )

    # explain subcommand
    explain_parser = subparsers.add_parser("explain", help="Explain optimization plan")
    explain_parser.add_argument("seed_file", help="Path to seed artifact file")
    explain_parser.add_argument("--objective", help="Natural language objective")

    # budget subcommand
    budget_parser = subparsers.add_parser(
        "budget", help="Recommend evaluation budget"
    )
    budget_parser.add_argument("seed_file", help="Path to seed artifact file")

    # score subcommand
    score_parser = subparsers.add_parser(
        "score", help="Score an artifact with an evaluator (without optimizing)"
    )
    score_parser.add_argument("artifact_file", help="Path to artifact file to score")
    score_parser.add_argument(
        "--evaluator-command", nargs="+", help="Shell command for evaluation"
    )
    score_parser.add_argument("--evaluator-url", help="HTTP endpoint for evaluation")
    score_parser.add_argument(
        "--evaluator-cwd",
        help="Working directory for evaluator command execution",
    )
    score_parser.add_argument(
        "--judge-model",
        help=(
            "LiteLLM model string for LLM-as-judge scoring. "
            "Judge: openai/gpt-5.6-luna. "
            "Mutually exclusive with --evaluator-command and --evaluator-url."
        ),
    )
    score_parser.add_argument(
        "--judge-backend",
        choices=["api", "codex", "claude"],
        default=None,
        help="Backend for LLM scoring (default: api).",
    )
    _add_subscription_options(score_parser)
    score_parser.add_argument(
        "--objective",
        help="Objective for the LLM judge (required with --judge-model).",
    )
    score_parser.add_argument(
        "--judge-objective",
        help="Override objective for the LLM judge. Falls back to --objective.",
    )
    score_parser.add_argument(
        "--api-base",
        help="Override API base URL for litellm calls.",
    )
    score_parser.add_argument(
        "--intake-json", help="Evaluator intake spec as an inline JSON string"
    )
    score_parser.add_argument(
        "--intake-file", help="Path to evaluator intake specification JSON file"
    )
    score_parser.add_argument(
        "--task-model",
        help="Optional task model metadata to forward to evaluators.",
    )
    score_parser.add_argument(
        "--score-range",
        choices=["unit", "any"],
        default="unit",
        help="Score validation mode for command/http evaluators: unit (0..1) or any finite float.",
    )

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Cross-validate an artifact with multiple LLM judge providers",
    )
    validate_parser.add_argument("artifact_file", help="Path to artifact file to validate")
    validate_parser.add_argument(
        "--providers",
        nargs="+",
        required=True,
        help=(
            "Two or more LiteLLM provider model strings. Validation: "
            "openai/gpt-5.6-luna anthropic/claude-sonnet-5 "
            "gemini/gemini-3.6-flash"
        ),
    )
    _add_subscription_options(validate_parser)
    validate_parser.add_argument(
        "--objective",
        required=True,
        help="Objective for LLM judge scoring.",
    )
    validate_parser.add_argument(
        "--intake-json", help="Evaluator intake spec as an inline JSON string"
    )
    validate_parser.add_argument(
        "--intake-file", help="Path to evaluator intake specification JSON file"
    )
    validate_parser.add_argument(
        "--api-base",
        help="Override API base URL for litellm calls.",
    )

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze an artifact to discover quality dimensions for optimization",
    )
    analyze_parser.add_argument(
        "artifact_file", help="Path to artifact file to analyze"
    )
    analyze_parser.add_argument(
        "--judge-model",
        required=False,
        help="LiteLLM model string for the LLM judge. Judge: openai/gpt-5.6-luna.",
    )
    analyze_parser.add_argument(
        "--analysis-backend",
        choices=["api", "codex", "claude"],
        default=None,
        help="Backend for scoring and dimension discovery (default: api).",
    )
    _add_subscription_options(analyze_parser)
    analyze_parser.add_argument(
        "--objective",
        required=True,
        help="Natural language scoring objective",
    )
    analyze_parser.add_argument(
        "--api-base",
        help="Override API base URL for litellm calls.",
    )
    analyze_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=(
            "Sampling temperature for LLM calls "
            "(default: provider model default)"
        ),
    )
    analyze_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Max seconds per LLM call (default: 60.0)",
    )

    args = parser.parse_args(argv)
    if (
        args.command == "analyze"
        and (args.analysis_backend or "api") == "api"
        and not args.judge_model
    ):
        parser.error("analyze with the API backend requires --judge-model")

    if args.command == "optimize":
        from optimize_anything.cli_optimize import _cmd_optimize
        return _cmd_optimize(args)
    elif args.command == "generate-evaluator":
        from optimize_anything.cli_tools import _cmd_generate_evaluator
        return _cmd_generate_evaluator(args)
    elif args.command == "intake":
        from optimize_anything.cli_tools import _cmd_intake
        return _cmd_intake(args)
    elif args.command == "explain":
        from optimize_anything.cli_tools import _cmd_explain
        return _cmd_explain(args)
    elif args.command == "budget":
        from optimize_anything.cli_tools import _cmd_budget
        return _cmd_budget(args)
    elif args.command == "score":
        from optimize_anything.cli_tools import _cmd_score
        return _cmd_score(args)
    elif args.command == "validate":
        from optimize_anything.cli_tools import _cmd_validate
        return _cmd_validate(args)
    elif args.command == "analyze":
        from optimize_anything.cli_tools import _cmd_analyze
        return _cmd_analyze(args)
    return 1


# ---------------------------------------------------------------------------
# Shared utilities used by cli_optimize.py and cli_tools.py
# ---------------------------------------------------------------------------

def _call_factory_with_compat(
    factory: EvaluatorFactory,
    *args: object,
    **kwargs: object,
) -> EvaluatorFn:
    """Call a factory, explicitly dropping unsupported kwargs with warnings."""
    signature = inspect.signature(factory)
    parameters = signature.parameters
    accepts_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in parameters.values()
    )

    if accepts_var_kwargs:
        return factory(*args, **kwargs)

    filtered_kwargs: dict[str, object] = {}
    for key, value in kwargs.items():
        if key in parameters:
            filtered_kwargs[key] = value
        else:
            print(
                f"Warning: evaluator factory does not accept '{key}', skipping",
                file=sys.stderr,
            )

    return factory(*args, **filtered_kwargs)


def _resolve_evaluator(
    *,
    evaluator_command: list[str] | None,
    evaluator_url: str | None,
    judge_model: str | None,
    judge_objective: str | None,
    objective: str | None,
    evaluator_cwd: str | None,
    intake_spec: dict[str, Any] | None,
    allow_intake_fallback: bool = False,
    api_base: str | None = None,
    task_model: str | None = None,
    score_range: str = "unit",
    judge_backend: str = "api",
    completion_backend: object | None = None,
    completion_role: Role = "judge",
) -> tuple[EvaluatorFn | None, str]:
    """Resolve evaluator from command, URL, judge model, or intake spec.

    Returns (eval_fn, evaluator_label) on success, or (None, error_message) on failure.
    """
    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from optimize_anything.llm_judge import llm_judge_evaluator

    command_cwd = evaluator_cwd
    if command_cwd is None and intake_spec is not None:
        command_cwd = intake_spec.get("evaluator_cwd")

    evaluator_sources = sum([
        bool(evaluator_command),
        bool(evaluator_url),
        bool(judge_model) or judge_backend != "api",
    ])
    if evaluator_sources > 1:
        return (None, "Error: provide only one of --evaluator-command, --evaluator-url, --judge-model, or --judge-backend")

    if evaluator_sources == 0:
        if allow_intake_fallback and intake_spec is not None:
            execution_mode = intake_spec["execution_mode"]
            if execution_mode == "command":
                return (None, "Error: intake execution_mode='command' requires --evaluator-command")
            else:
                return (None, "Error: intake execution_mode='http' requires --evaluator-url")
        return (None, "Error: provide --evaluator-command, --evaluator-url, --judge-model, or a subscription --judge-backend")

    if evaluator_command:
        return _resolve_command_evaluator_source(
            command_evaluator=command_evaluator,
            evaluator_command=evaluator_command,
            evaluator_cwd=command_cwd,
            task_model=task_model,
            score_range=score_range,
        )
    if evaluator_url:
        return _resolve_http_evaluator_source(
            http_evaluator=http_evaluator,
            evaluator_url=evaluator_url,
            task_model=task_model,
            score_range=score_range,
        )

    return _resolve_judge_evaluator_source(
        llm_judge_evaluator=llm_judge_evaluator,
        judge_model=judge_model,
        judge_objective=judge_objective,
        objective=objective,
        intake_spec=intake_spec,
        api_base=api_base,
        task_model=task_model,
        judge_backend=judge_backend,
        completion_backend=completion_backend,
        completion_role=completion_role,
    )


def _resolve_command_evaluator_source(
    *,
    command_evaluator: EvaluatorFactory,
    evaluator_command: list[str],
    evaluator_cwd: str | None,
    task_model: str | None,
    score_range: str,
) -> tuple[EvaluatorFn | None, str]:
    preflight_kwargs: dict[str, Any] = {"cwd": evaluator_cwd}
    factory_kwargs: dict[str, Any] = {
        "cwd": evaluator_cwd,
        "task_model": task_model,
    }
    if score_range == "any":
        preflight_kwargs["score_range"] = score_range
        factory_kwargs["score_range"] = score_range

    preflight_error = _preflight_command_evaluator(
        evaluator_command,
        **preflight_kwargs,
    )
    if preflight_error is not None:
        return None, preflight_error

    eval_fn = _call_factory_with_compat(
        command_evaluator,
        evaluator_command,
        **factory_kwargs,
    )
    return eval_fn, shlex.join(evaluator_command)


def _resolve_http_evaluator_source(
    *,
    http_evaluator: EvaluatorFactory,
    evaluator_url: str,
    task_model: str | None,
    score_range: str,
) -> tuple[EvaluatorFn | None, str]:
    preflight_kwargs: dict[str, Any] = {}
    factory_kwargs: dict[str, Any] = {"task_model": task_model}
    if score_range == "any":
        preflight_kwargs["score_range"] = score_range
        factory_kwargs["score_range"] = score_range

    preflight_error = _preflight_http_evaluator(
        evaluator_url,
        **preflight_kwargs,
    )
    if preflight_error is not None:
        return None, preflight_error

    eval_fn = _call_factory_with_compat(
        http_evaluator,
        evaluator_url,
        **factory_kwargs,
    )
    return eval_fn, evaluator_url


def _resolve_judge_evaluator_source(
    *,
    llm_judge_evaluator: EvaluatorFactory,
    judge_model: str | None,
    judge_objective: str | None,
    objective: str | None,
    intake_spec: dict[str, Any] | None,
    api_base: str | None,
    task_model: str | None,
    judge_backend: str = "api",
    completion_backend: object | None = None,
    completion_role: Role = "judge",
) -> tuple[EvaluatorFn | None, str]:
    judge_obj = judge_objective or objective
    if not judge_obj:
        if judge_backend == "api":
            return (None, "Error: --judge-model requires --objective or --judge-objective")
        return (None, "Error: the built-in judge requires --objective or --judge-objective")

    quality_dimensions = None
    hard_constraints = None
    if intake_spec is not None:
        quality_dimensions = intake_spec.get("quality_dimensions")
        hard_constraints = intake_spec.get("hard_constraints") or None
    eval_fn = _call_factory_with_compat(
        llm_judge_evaluator,
        judge_obj,
        model=judge_model,
        quality_dimensions=quality_dimensions,
        hard_constraints=hard_constraints,
        api_base=api_base,
        task_model=task_model,
        backend=completion_backend,
        role=completion_role,
    )
    model_label = judge_model or "provider default"
    if judge_backend == "api":
        return eval_fn, f"LLM judge ({model_label})"
    return eval_fn, f"LLM judge ({judge_backend}:{model_label})"


def _read_seed(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
        return None


def _load_and_normalize_intake_spec(
    *,
    intake_json: str | None,
    intake_file: str | None,
) -> dict[str, Any] | None:
    from optimize_anything.intake import normalize_intake_spec

    if intake_json is not None and intake_file is not None:
        print(
            "Error: provide either --intake-json or --intake-file, not both",
            file=sys.stderr,
        )
        return None

    if intake_json is None and intake_file is None:
        return None

    raw_data: Any
    if intake_json is not None:
        try:
            raw_data = json.loads(intake_json)
        except json.JSONDecodeError as e:
            print(
                f"Error: invalid JSON for --intake-json: {e.msg} (line {e.lineno}, column {e.colno})",
                file=sys.stderr,
            )
            return None
    else:
        assert intake_file is not None
        try:
            with open(intake_file) as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: intake file not found: {intake_file}", file=sys.stderr)
            return None
        except json.JSONDecodeError as e:
            print(
                f"Error: invalid JSON in --intake-file '{intake_file}': {e.msg} (line {e.lineno}, column {e.colno})",
                file=sys.stderr,
            )
            return None
        except OSError as e:
            print(f"Error reading intake file '{intake_file}': {e}", file=sys.stderr)
            return None

    try:
        return normalize_intake_spec(raw_data)
    except ValueError as e:
        print(f"Error: invalid intake spec: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    sys.exit(main())
