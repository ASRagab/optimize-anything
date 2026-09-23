"""Tool subcommand implementations: score, validate, analyze, explain, budget, intake, generate-evaluator."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from contextlib import contextmanager
from typing import Any, Iterator, cast

from optimize_anything.cli import (
    EvaluatorFn,
    _load_and_normalize_intake_spec,
    _read_seed,
    _resolve_evaluator,
)
from optimize_anything.llm_backends.base import BackendName, Role


def _cmd_intake(args: argparse.Namespace) -> int:
    from optimize_anything.intake import normalize_intake_spec

    flag_fields = {
        "artifact_class": args.artifact_class,
        "execution_mode": args.execution_mode,
        "evaluation_pattern": args.evaluation_pattern,
        "hard_constraints": args.hard_constraints,
        "evaluator_cwd": args.evaluator_cwd,
    }
    has_flags = any(v is not None for v in flag_fields.values())
    has_json_source = args.intake_json is not None or args.intake_file is not None

    if has_flags and has_json_source:
        print(
            "Error: provide individual flags or --intake-json/--intake-file, not both",
            file=sys.stderr,
        )
        return 1

    if has_json_source:
        intake_spec = _load_and_normalize_intake_spec(
            intake_json=args.intake_json,
            intake_file=args.intake_file,
        )
        if intake_spec is None:
            return 1
        print(json.dumps(intake_spec, indent=2))
        return 0

    spec: dict[str, object] = {}
    if args.artifact_class is not None:
        spec["artifact_class"] = args.artifact_class
    if args.execution_mode is not None:
        spec["execution_mode"] = args.execution_mode
    if args.evaluation_pattern is not None:
        spec["evaluation_pattern"] = args.evaluation_pattern
    if args.hard_constraints is not None:
        spec["hard_constraints"] = args.hard_constraints
    if args.evaluator_cwd is not None:
        spec["evaluator_cwd"] = args.evaluator_cwd

    try:
        normalized = normalize_intake_spec(spec)
    except ValueError as e:
        print(f"Error: invalid intake spec: {e}", file=sys.stderr)
        return 1

    print(json.dumps(normalized, indent=2))
    return 0


def _cmd_generate_evaluator(args: argparse.Namespace) -> int:
    seed = _read_seed(args.seed_file)
    if seed is None:
        return 1

    intake_spec = _load_and_normalize_intake_spec(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    intake_requested = args.intake_json is not None or args.intake_file is not None
    if intake_requested and intake_spec is None:
        return 1

    from optimize_anything.evaluator_generator import generate_evaluator_script

    from optimize_anything.model_defaults import DEFAULT_EVALUATOR_MODEL

    backend_name = args.judge_backend or "api"
    model = args.model or (DEFAULT_EVALUATOR_MODEL if backend_name == "api" else None)
    script = generate_evaluator_script(
        seed=seed,
        objective=args.objective,
        evaluator_type=args.evaluator_type,
        intake=intake_spec,
        model=model,
        dataset=args.dataset,
        backend=backend_name,
        api_base=args.api_base,
        api_fallback=not args.no_api_fallback,
        api_fallback_model=(
            args.openai_api_fallback_model
            if args.judge_backend == "codex"
            else args.anthropic_api_fallback_model
        ),
        max_concurrency=args.subscription_concurrency,
    )
    print(script, end="")
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    seed = _read_seed(args.seed_file)
    if seed is None:
        return 1
    print(f"Seed: {len(seed)} chars")
    print(f"Objective: {args.objective or 'maximize evaluator score'}")
    print("\ngepa will evolve the seed through LLM-guided mutations,")
    print("scoring each variant with your evaluator.")
    return 0


def _cmd_budget(args: argparse.Namespace) -> int:
    seed = _read_seed(args.seed_file)
    if seed is None:
        return 1
    length = len(seed)
    if length < 100:
        budget, rationale = 50, "Short artifact"
    elif length < 500:
        budget, rationale = 100, "Medium artifact"
    elif length < 2000:
        budget, rationale = 200, "Long artifact"
    else:
        budget, rationale = 300, "Very long artifact"
    print(
        json.dumps(
            {
                "recommended_budget": budget,
                "rationale": rationale,
                "seed_length": length,
            },
            indent=2,
        )
    )
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    artifact = _read_seed(args.artifact_file)
    if artifact is None:
        return 1

    intake_spec = _load_and_normalize_intake_spec(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    intake_requested = args.intake_json is not None or args.intake_file is not None
    if intake_requested and intake_spec is None:
        return 1

    judge_name = cast(BackendName, args.judge_backend or "api")
    try:
        with _completion_backend(args, judge_name, args.judge_model, "score") as backend:
            eval_fn, error = _resolve_evaluator(
                evaluator_command=args.evaluator_command,
                evaluator_url=args.evaluator_url,
                judge_model=args.judge_model,
                judge_objective=args.judge_objective,
                objective=args.objective,
                evaluator_cwd=args.evaluator_cwd,
                intake_spec=intake_spec,
                allow_intake_fallback=False,
                api_base=args.api_base,
                task_model=args.task_model,
                score_range=args.score_range,
                judge_backend=judge_name,
                completion_backend=backend,
                completion_role="score",
            )
            if eval_fn is None:
                print(error, file=sys.stderr)
                return 1

            if args.evaluator_url and args.evaluator_cwd:
                print(
                    "Warning: --evaluator-cwd has no effect when using --evaluator-url. "
                    "The HTTP evaluator runs in the server's own working directory.",
                    file=sys.stderr,
                )

            score, side_info = eval_fn(artifact)
    except Exception as exc:
        print(f"Error: evaluator call failed: {exc}", file=sys.stderr)
        return 1

    result = {"score": score, **side_info}
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    artifact = _read_seed(args.artifact_file)
    if artifact is None:
        return 1

    if len(args.providers) < 2:
        print("Error: --providers requires at least 2 model strings", file=sys.stderr)
        return 1

    intake_spec = _load_and_normalize_intake_spec(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    intake_requested = args.intake_json is not None or args.intake_file is not None
    if intake_requested and intake_spec is None:
        return 1

    quality_dimensions = intake_spec.get("quality_dimensions") if intake_spec else None
    hard_constraints = intake_spec.get("hard_constraints") if intake_spec else None

    provider_results: list[dict[str, object]] = []
    successful_scores: list[float] = []
    for provider in args.providers:
        backend_name, model = _parse_validation_provider(provider)
        result, numeric_score = _validate_provider(
            artifact=artifact,
            provider=provider,
            backend_name=backend_name,
            model=model,
            objective=args.objective,
            quality_dimensions=quality_dimensions,
            hard_constraints=hard_constraints,
            api_base=args.api_base,
            args=args,
        )
        provider_results.append(result)
        if numeric_score is not None:
            successful_scores.append(numeric_score)

    successful_count = len(successful_scores)
    failed_count = len(provider_results) - successful_count
    aggregate_mean = statistics.mean(successful_scores) if successful_scores else None
    aggregate_stddev = (
        statistics.stdev(successful_scores)
        if len(successful_scores) > 1
        else (0.0 if successful_scores else None)
    )
    aggregate_min = min(successful_scores) if successful_scores else None
    aggregate_max = max(successful_scores) if successful_scores else None

    summary = {
        "artifact_file": args.artifact_file,
        "objective": args.objective,
        "results": provider_results,
        "providers": provider_results,  # backward-compatible alias
        "summary": {
            "successful": successful_count,
            "failed": failed_count,
            "mean": aggregate_mean,
            "stddev": aggregate_stddev,
            "min": aggregate_min,
            "max": aggregate_max,
        },
        "mean": aggregate_mean,
        "stddev": aggregate_stddev,
        "min": aggregate_min,
        "max": aggregate_max,
    }
    print(json.dumps(summary, indent=2, default=str))
    if successful_count == 0:
        print("Error: all providers failed", file=sys.stderr)
        return 1
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    artifact = _read_seed(args.artifact_file)
    if artifact is None:
        return 1

    from optimize_anything.llm_judge import analyze_for_dimensions

    print(
        f"Analyzing artifact with {args.analysis_backend or 'api'}:{args.judge_model or 'provider default'}...",
        file=sys.stderr,
    )

    try:
        backend_name = cast(BackendName, args.analysis_backend or "api")
        with _completion_backend(args, backend_name, args.judge_model, "analysis") as backend:
            result = analyze_for_dimensions(
                artifact=artifact,
                objective=args.objective,
                model=args.judge_model,
                api_base=args.api_base,
                timeout=args.timeout,
                temperature=args.temperature,
                backend=backend,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


def _validate_provider(
    *,
    artifact: str,
    provider: str,
    backend_name: BackendName,
    model: str | None,
    objective: str,
    quality_dimensions: Any,
    hard_constraints: Any,
    api_base: str | None,
    args: argparse.Namespace,
) -> tuple[dict[str, object], float | None]:
    from optimize_anything.llm_judge import llm_judge_evaluator

    try:
        with _completion_backend(args, backend_name, model, "validation") as backend:
            evaluator = cast(
                EvaluatorFn,
                llm_judge_evaluator(
                    objective,
                    model=model,
                    quality_dimensions=quality_dimensions,
                    hard_constraints=hard_constraints,
                    api_base=api_base,
                    backend=backend,
                    role="validation",
                ),
            )
            score, side_info = evaluator(artifact)
        numeric_score = float(score)
    except Exception as exc:
        return {
            "provider": provider,
            "score": None,
            "error": str(exc),
        }, None

    result: dict[str, object] = {
        "provider": provider,
        "score": numeric_score,
    }
    if isinstance(side_info, dict):
        result.update(side_info)
    return result, numeric_score


def _parse_validation_provider(provider: str) -> tuple[BackendName, str | None]:
    if provider == "codex" or provider.startswith("codex:"):
        return "codex", provider.partition(":")[2] or None
    if provider == "claude" or provider.startswith("claude:"):
        return "claude", provider.partition(":")[2] or None
    return "api", provider


@contextmanager
def _completion_backend(
    args: argparse.Namespace,
    backend_name: BackendName,
    model: str | None,
    role: Role,
) -> Iterator[Any]:
    from optimize_anything.llm_backends.factory import create_backend, resolve_backend_spec

    concurrency = getattr(args, "subscription_concurrency", 1)
    if concurrency < 1:
        raise ValueError("--subscription-concurrency must be at least 1")
    spec = resolve_backend_spec(
        backend=backend_name,
        model=model,
        api_base=getattr(args, "api_base", None),
        no_api_fallback=getattr(args, "no_api_fallback", False),
        openai_api_fallback_model=getattr(args, "openai_api_fallback_model", None),
        anthropic_api_fallback_model=getattr(args, "anthropic_api_fallback_model", None),
        max_concurrency=concurrency,
    )
    backend = create_backend(spec, role=role)
    if backend_name != "api":
        backend.preflight()
    yield backend
