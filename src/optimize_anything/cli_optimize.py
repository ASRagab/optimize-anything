"""Optimize subcommand implementation."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from optimize_anything.persist import (
    _copy_cache_from_run,
    _print_judge_plateau_advisory,
    _print_optimize_diff,
    _save_run_dir,
    _timestamped_run_dir,
)

OptimizeInputs = tuple[
    argparse.Namespace,
    str | None,
    list[dict] | None,
    list[dict] | None,
    dict[str, Any] | None,
]


def _cmd_optimize(args: argparse.Namespace) -> int:
    from optimize_anything.cli import _resolve_evaluator

    prepared = _prepare_optimize_inputs(args)
    if prepared is None:
        return 1
    args, seed, dataset, valset, intake_spec = prepared

    from optimize_anything.result_contract import build_optimize_summary
    from gepa.optimize_anything import optimize_anything

    eval_fn, evaluator_label = _resolve_evaluator(
        evaluator_command=args.evaluator_command,
        evaluator_url=args.evaluator_url,
        judge_model=args.judge_model,
        judge_objective=args.judge_objective,
        objective=args.objective,
        evaluator_cwd=args.evaluator_cwd,
        intake_spec=intake_spec,
        allow_intake_fallback=True,
        api_base=args.api_base,
        task_model=args.task_model,
        score_range=args.score_range,
    )
    if eval_fn is None:
        print(evaluator_label, file=sys.stderr)
        return 1

    if args.evaluator_url and args.evaluator_cwd:
        print(
            "Warning: --evaluator-cwd has no effect when using --evaluator-url. "
            "The HTTP evaluator runs in the server's own working directory.",
            file=sys.stderr,
        )

    print(
        f"Running optimization (budget: {args.budget}, evaluator: {evaluator_label})...",
        file=sys.stderr,
    )

    model = args.model or os.environ.get("OPTIMIZE_ANYTHING_MODEL")
    config, gepa_run_dir, early_stop_active, runtime_error = _build_optimize_runtime(
        args,
        model=model,
    )
    if runtime_error is not None:
        print(runtime_error, file=sys.stderr)
        return 1

    try:
        result = optimize_anything(
            seed_candidate=seed,
            evaluator=eval_fn,
            dataset=dataset,
            valset=valset,
            objective=args.objective,
            background=args.background,
            config=config,
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        if "api_key" in exc_str or "authentication" in exc_str or "unauthorized" in exc_str:
            print(
                f"Error: optimization failed — API authentication error. "
                f"Check your API key environment variables.\nDetail: {exc}",
                file=sys.stderr,
            )
        else:
            print(f"Error: optimization failed: {exc}", file=sys.stderr)
        return 1

    print("Optimization complete.", file=sys.stderr)
    summary = build_optimize_summary(
        result,
        requested_budget=args.budget,
        early_stop_active=early_stop_active,
    )
    best = summary["best_artifact"]
    persist_error = _persist_optimize_outputs(
        args=args,
        seed=seed,
        best_artifact=best,
        summary=summary,
        gepa_run_dir=gepa_run_dir,
    )
    if persist_error is not None:
        print(persist_error, file=sys.stderr)
        return 1

    if args.diff:
        _print_optimize_diff(seed, best, file=sys.stderr)

    if summary.get("plateau_detected") and args.judge_model:
        _print_judge_plateau_advisory(
            judge_model=args.judge_model,
            proposer_model=model,
            has_intake=intake_spec is not None,
            file=sys.stderr,
        )

    print(json.dumps(summary, indent=2, default=str))
    return 0


def _build_optimize_runtime(
    args: argparse.Namespace,
    *,
    model: str | None,
) -> tuple[Any, str | None, bool, str | None]:
    """Build GEPA runtime config plus run-dir state for optimize."""
    from optimize_anything.stop import plateau_stop_callback
    from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig

    gepa_run_dir = _timestamped_run_dir(args.run_dir) if getattr(args, "run_dir", None) else None

    if args.cache_from:
        if gepa_run_dir is None:
            return None, None, False, (
                "Error: --cache-from requires --run-dir so cache can be copied into a new run"
            )
        cache_copy_error = _copy_cache_from_run(args.cache_from, gepa_run_dir)
        if cache_copy_error is not None:
            return None, gepa_run_dir, False, f"Error: {cache_copy_error}"

    early_stop_active = bool(
        args.early_stop or (args.budget is not None and args.budget > 30)
    )
    stop_callbacks = None
    if early_stop_active:
        stop_callbacks = [
            plateau_stop_callback(
                window=args.early_stop_window,
                threshold=args.early_stop_threshold,
            )
        ]

    engine = EngineConfig(
        max_metric_calls=args.budget,
        run_dir=gepa_run_dir,
        parallel=args.parallel or (args.workers is not None),
        max_workers=args.workers,
        cache_evaluation=args.cache,
    )
    if model:
        config = GEPAConfig(
            engine=engine,
            reflection=ReflectionConfig(reflection_lm=model),
            stop_callbacks=stop_callbacks,
        )
    else:
        config = GEPAConfig(engine=engine, stop_callbacks=stop_callbacks)

    return config, gepa_run_dir, early_stop_active, None


def _persist_optimize_outputs(
    *,
    args: argparse.Namespace,
    seed: str | None,
    best_artifact: Any,
    summary: dict[str, Any],
    gepa_run_dir: str | None,
) -> str | None:
    """Persist optimize outputs and attach any saved paths to the summary."""
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(
                    best_artifact if isinstance(best_artifact, str) else json.dumps(best_artifact)
                )
        except OSError as exc:
            return f"Error writing output file '{args.output}': {exc}"
        summary["output_file"] = args.output

    if not gepa_run_dir:
        return None

    saved_dir = _save_run_dir(
        run_dir=gepa_run_dir,
        seed=seed or "",
        best_artifact=best_artifact,
        summary=summary,
    )
    if saved_dir:
        summary["run_dir"] = saved_dir
    return None


def _prepare_optimize_inputs(args: argparse.Namespace) -> OptimizeInputs | None:
    from optimize_anything.cli import _load_and_normalize_intake_spec, _read_seed

    if getattr(args, "spec_file", None):
        spec = _load_spec_if_provided(args.spec_file)
        if spec is None:
            return None
        args = _apply_spec_to_args(args, spec)

    seed_ok, seed = _resolve_optimize_seed(args)
    if not seed_ok:
        return None

    argument_error = _validate_optimize_args(args)
    if argument_error is not None:
        print(argument_error, file=sys.stderr)
        return None

    dataset = _load_dataset_arg(args.dataset)
    if args.dataset and dataset is None:
        return None

    valset = _load_dataset_arg(args.valset)
    if args.valset and valset is None:
        return None

    intake_spec = _load_and_normalize_intake_spec(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    intake_requested = args.intake_json is not None or args.intake_file is not None
    if intake_requested and intake_spec is None:
        return None

    output_error = _validate_output_path(args.output)
    if output_error is not None:
        print(output_error, file=sys.stderr)
        return None

    return args, seed, dataset, valset, intake_spec


def _resolve_optimize_seed(args: argparse.Namespace) -> tuple[bool, str | None]:
    from optimize_anything.cli import _read_seed

    if args.seed_file is not None:
        seed = _read_seed(args.seed_file)
        return (seed is not None, seed)
    if not args.no_seed:
        print("Error: provide seed_file or pass --no-seed", file=sys.stderr)
        return False, None
    if not args.objective or not args.model:
        print(
            "Error: seedless mode (--no-seed) requires both --objective and --model",
            file=sys.stderr,
        )
        return False, None
    return True, None


def _validate_optimize_args(args: argparse.Namespace) -> str | None:
    if args.budget is None:
        args.budget = 100
    if args.budget < 1:
        return "Error: --budget must be at least 1"
    if args.early_stop_window < 1:
        return "Error: --early-stop-window must be at least 1"
    if args.early_stop_threshold < 0:
        return "Error: --early-stop-threshold must be non-negative"
    if args.cache_from and not args.cache:
        return "Error: --cache-from requires --cache"
    if args.valset and not args.dataset:
        return "Error: --valset requires --dataset"
    return None


def _load_dataset_arg(path: str | None) -> list[dict] | None:
    if path is None:
        return None

    from optimize_anything.dataset import load_dataset

    try:
        return load_dataset(path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None


def _validate_output_path(output_path: str | None) -> str | None:
    if output_path is None:
        return None
    output = Path(output_path)
    if output.exists() and output.is_dir():
        return f"Error: --output must be a file path, got directory: {output_path}"
    return None


def _load_spec_if_provided(spec_file: str) -> dict[str, Any] | None:
    """Load a provided spec file, returning None when loading fails."""
    from optimize_anything.spec_loader import SpecLoadError, load_spec

    try:
        return load_spec(spec_file)
    except SpecLoadError as exc:
        print(f"Error loading spec file: {exc}", file=sys.stderr)
        return None


def _apply_spec_to_args(
    args: argparse.Namespace,
    spec: dict,
) -> argparse.Namespace:
    """Apply spec values to args. CLI flags take precedence over spec values."""
    args = copy.copy(args)

    _apply_spec_values_if_missing(
        args,
        spec,
        "seed_file",
        "objective",
        "background",
        "output",
        "evaluator_url",
        "evaluator_cwd",
        "task_model",
        "cache_from",
        "evaluator_command",
        "budget",
        "judge_model",
        "workers",
    )
    _apply_spec_alias_if_missing(args, spec, arg_key="model", spec_key="proposer_model")
    _apply_true_flags_from_spec(args, spec, "parallel", "cache", "early_stop")
    _apply_spec_value_if_default(args, spec, "early_stop_window", default=10)
    _apply_spec_value_if_default(args, spec, "early_stop_threshold", default=0.005)

    if (
        getattr(args, "intake_json", None) is None
        and getattr(args, "intake_file", None) is None
        and spec.get("intake")
    ):
        args.intake_json = json.dumps(spec["intake"])

    return args


def _apply_spec_values_if_missing(
    args: argparse.Namespace,
    spec: dict[str, Any],
    *keys: str,
) -> None:
    for key in keys:
        if getattr(args, key, None) is None and spec.get(key) is not None:
            setattr(args, key, spec[key])


def _apply_spec_alias_if_missing(
    args: argparse.Namespace,
    spec: dict[str, Any],
    *,
    arg_key: str,
    spec_key: str,
) -> None:
    if getattr(args, arg_key, None) is None and spec.get(spec_key) is not None:
        setattr(args, arg_key, spec[spec_key])


def _apply_true_flags_from_spec(
    args: argparse.Namespace,
    spec: dict[str, Any],
    *keys: str,
) -> None:
    for key in keys:
        if not getattr(args, key, False) and spec.get(key) is True:
            setattr(args, key, True)


def _apply_spec_value_if_default(
    args: argparse.Namespace,
    spec: dict[str, Any],
    key: str,
    *,
    default: object,
) -> None:
    if getattr(args, key, None) == default and spec.get(key) is not None:
        setattr(args, key, spec[key])
