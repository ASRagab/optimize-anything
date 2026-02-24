"""CLI entry point for optimize-anything."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="optimize-anything",
        description="Optimize any text artifact using gepa",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # optimize subcommand
    opt_parser = subparsers.add_parser("optimize", help="Run optimization")
    opt_parser.add_argument("seed_file", help="Path to seed artifact file")
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
    opt_parser.add_argument(
        "--budget", type=int, default=100, help="Max evaluator calls (default: 100)"
    )
    opt_parser.add_argument("--output", "-o", help="Output file for best candidate")
    opt_parser.add_argument(
        "--model",
        help=(
            "LiteLLM model string for the proposer LLM "
            "(e.g. 'openai/gpt-4o-mini', 'claude-sonnet-4-6'). "
            "Falls back to OPTIMIZE_ANYTHING_MODEL env var."
        ),
    )
    opt_parser.add_argument(
        "--judge-model",
        help=(
            "LiteLLM model string for built-in LLM-as-judge evaluation "
            "(e.g. 'openai/gpt-4o-mini'). "
            "Mutually exclusive with --evaluator-command and --evaluator-url."
        ),
    )
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
            "containing seed.txt, best_artifact.txt, and summary.json."
        ),
    )
    opt_parser.add_argument(
        "--spec-file",
        help="Path to a TOML spec file for repeatable optimization runs.",
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
        choices=["command", "http"],
        help="Script type: 'command' (bash) or 'http' (Python server)",
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
            "LiteLLM model string for LLM-as-judge scoring "
            "(e.g. 'openai/gpt-5.1-mini'). "
            "Mutually exclusive with --evaluator-command and --evaluator-url."
        ),
    )
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

    args = parser.parse_args(argv)

    if args.command == "optimize":
        return _cmd_optimize(args)
    elif args.command == "generate-evaluator":
        return _cmd_generate_evaluator(args)
    elif args.command == "intake":
        return _cmd_intake(args)
    elif args.command == "explain":
        return _cmd_explain(args)
    elif args.command == "budget":
        return _cmd_budget(args)
    elif args.command == "score":
        return _cmd_score(args)
    return 1


def _cmd_optimize(args: argparse.Namespace) -> int:
    # Apply spec file defaults (lower precedence than CLI flags)
    if getattr(args, "spec_file", None):
        spec = _load_spec_if_provided(args.spec_file)
        if spec is False:
            return 1  # error already printed
        if spec is not None:
            args = _apply_spec_to_args(args, spec)

    seed = _read_seed(args.seed_file)
    if seed is None:
        return 1

    if args.budget < 1:
        print("Error: --budget must be at least 1", file=sys.stderr)
        return 1

    intake_spec = _load_and_normalize_intake_spec(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    intake_requested = args.intake_json is not None or args.intake_file is not None
    if intake_requested and intake_spec is None:
        return 1

    evaluator_sources = sum([
        bool(args.evaluator_command),
        bool(args.evaluator_url),
        bool(args.judge_model),
    ])
    if evaluator_sources > 1:
        print(
            "Error: provide only one of --evaluator-command, --evaluator-url, or --judge-model",
            file=sys.stderr,
        )
        return 1

    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from optimize_anything.llm_judge import llm_judge_evaluator
    from optimize_anything.result_contract import build_optimize_summary
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig

    command_cwd = args.evaluator_cwd
    if command_cwd is None and intake_spec is not None:
        command_cwd = intake_spec.get("evaluator_cwd")

    output_error = _validate_output_path(args.output)
    if output_error is not None:
        print(output_error, file=sys.stderr)
        return 1

    if args.evaluator_command:
        preflight_error = _preflight_command_evaluator(
            args.evaluator_command,
            cwd=command_cwd,
        )
        if preflight_error is not None:
            print(preflight_error, file=sys.stderr)
            return 1
        eval_fn = command_evaluator(args.evaluator_command, cwd=command_cwd)
    elif args.evaluator_url:
        preflight_error = _preflight_http_evaluator(args.evaluator_url)
        if preflight_error is not None:
            print(preflight_error, file=sys.stderr)
            return 1
        eval_fn = http_evaluator(args.evaluator_url)
    elif args.judge_model:
        judge_objective = args.judge_objective or args.objective
        if not judge_objective:
            print(
                "Error: --judge-model requires --objective or --judge-objective",
                file=sys.stderr,
            )
            return 1
        quality_dimensions = None
        hard_constraints = None
        if intake_spec is not None:
            quality_dimensions = intake_spec.get("quality_dimensions")
            hard_constraints = intake_spec.get("hard_constraints") or None
        eval_fn = llm_judge_evaluator(
            judge_objective,
            model=args.judge_model,
            quality_dimensions=quality_dimensions,
            hard_constraints=hard_constraints,
            api_base=args.api_base,
        )
    else:
        if intake_spec is not None:
            execution_mode = intake_spec["execution_mode"]
            if execution_mode == "command":
                print(
                    "Error: intake execution_mode='command' requires --evaluator-command",
                    file=sys.stderr,
                )
            else:
                print(
                    "Error: intake execution_mode='http' requires --evaluator-url",
                    file=sys.stderr,
                )
        else:
            print(
                "Error: provide --evaluator-command, --evaluator-url, or --judge-model",
                file=sys.stderr,
            )
        return 1

    if args.evaluator_url and args.evaluator_cwd:
        print(
            "Warning: --evaluator-cwd has no effect when using --evaluator-url. "
            "The HTTP evaluator runs in the server's own working directory.",
            file=sys.stderr,
        )

    if args.evaluator_command:
        evaluator_label = shlex.join(args.evaluator_command)
    elif args.evaluator_url:
        evaluator_label = args.evaluator_url
    else:
        evaluator_label = f"LLM judge ({args.judge_model})"

    print(
        f"Running optimization (budget: {args.budget}, evaluator: {evaluator_label})...",
        file=sys.stderr,
    )

    model = args.model or os.environ.get("OPTIMIZE_ANYTHING_MODEL")
    if model:
        config = GEPAConfig(
            engine=EngineConfig(max_metric_calls=args.budget),
            reflection=ReflectionConfig(reflection_lm=model),
        )
    else:
        config = GEPAConfig(engine=EngineConfig(max_metric_calls=args.budget))
    try:
        result = optimize_anything(
            seed_candidate=seed,
            evaluator=eval_fn,
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
    summary = build_optimize_summary(result)
    best = summary["best_artifact"]
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(best if isinstance(best, str) else json.dumps(best))
        except OSError as e:
            print(f"Error writing output file '{args.output}': {e}", file=sys.stderr)
            return 1
        summary["output_file"] = args.output

    if getattr(args, "run_dir", None):
        saved_dir = _save_run_dir(
            run_dir=args.run_dir,
            seed=seed,
            best_artifact=best,
            summary=summary,
        )
        if saved_dir:
            summary["run_dir"] = saved_dir

    if args.diff:
        seed_lines = seed.splitlines(keepends=True)
        best_str = best if isinstance(best, str) else json.dumps(best)
        best_lines = best_str.splitlines(keepends=True)
        diff_output = difflib.unified_diff(
            seed_lines, best_lines, fromfile="seed", tofile="optimized",
        )
        diff_text = "".join(diff_output)
        if diff_text:
            print("\n--- diff: seed vs optimized ---", file=sys.stderr)
            print(diff_text, end="", file=sys.stderr)
            print("--- end diff ---", file=sys.stderr)
        else:
            print("(no diff: seed and optimized artifact are identical)", file=sys.stderr)

    print(json.dumps(summary, indent=2, default=str))
    return 0


def _cmd_intake(args: argparse.Namespace) -> int:
    from optimize_anything.intake import normalize_intake_spec

    # Detect if user passed any individual flags
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

    # Build spec from flags
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

    script = generate_evaluator_script(
        seed=seed,
        objective=args.objective,
        evaluator_type=args.evaluator_type,
        intake=intake_spec,
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
    """Score a single artifact using an evaluator without running optimization."""
    artifact = _read_seed(args.artifact_file)
    if artifact is None:
        return 1

    evaluator_sources = sum([
        bool(args.evaluator_command),
        bool(args.evaluator_url),
        bool(getattr(args, "judge_model", None)),
    ])
    if evaluator_sources > 1:
        print(
            "Error: provide only one of --evaluator-command, --evaluator-url, or --judge-model",
            file=sys.stderr,
        )
        return 1

    if evaluator_sources == 0:
        print(
            "Error: provide --evaluator-command, --evaluator-url, or --judge-model",
            file=sys.stderr,
        )
        return 1

    from optimize_anything.evaluators import command_evaluator, http_evaluator

    if args.evaluator_command:
        preflight_error = _preflight_command_evaluator(
            args.evaluator_command,
            cwd=args.evaluator_cwd,
        )
        if preflight_error is not None:
            print(preflight_error, file=sys.stderr)
            return 1
        eval_fn = command_evaluator(args.evaluator_command, cwd=args.evaluator_cwd)
    elif args.evaluator_url:
        preflight_error = _preflight_http_evaluator(args.evaluator_url)
        if preflight_error is not None:
            print(preflight_error, file=sys.stderr)
            return 1
        eval_fn = http_evaluator(args.evaluator_url)
    else:
        from optimize_anything.llm_judge import llm_judge_evaluator

        judge_objective = getattr(args, "judge_objective", None) or getattr(args, "objective", None)
        if not judge_objective:
            print(
                "Error: --judge-model requires --objective or --judge-objective",
                file=sys.stderr,
            )
            return 1

        intake_spec = _load_and_normalize_intake_spec(
            intake_json=getattr(args, "intake_json", None),
            intake_file=getattr(args, "intake_file", None),
        )
        intake_requested = getattr(args, "intake_json", None) is not None or getattr(args, "intake_file", None) is not None
        if intake_requested and intake_spec is None:
            return 1

        quality_dimensions = None
        hard_constraints = None
        if intake_spec is not None:
            quality_dimensions = intake_spec.get("quality_dimensions")
            hard_constraints = intake_spec.get("hard_constraints") or None

        eval_fn = llm_judge_evaluator(
            judge_objective,
            model=args.judge_model,
            quality_dimensions=quality_dimensions,
            hard_constraints=hard_constraints,
            api_base=getattr(args, "api_base", None),
        )

    try:
        score, side_info = eval_fn(artifact)
    except Exception as exc:
        print(f"Error: evaluator call failed: {exc}", file=sys.stderr)
        return 1

    result = {"score": score, **side_info}
    print(json.dumps(result, indent=2, default=str))
    return 0


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
) -> dict[str, object] | None:
    from optimize_anything.intake import normalize_intake_spec

    if intake_json is not None and intake_file is not None:
        print(
            "Error: provide either --intake-json or --intake-file, not both",
            file=sys.stderr,
        )
        return None

    if intake_json is None and intake_file is None:
        return None

    raw_data: object
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


def _validate_output_path(output_path: str | None) -> str | None:
    if output_path is None:
        return None
    output = Path(output_path)
    if output.exists() and output.is_dir():
        return f"Error: --output must be a file path, got directory: {output_path}"
    return None


def _preflight_command_evaluator(command: list[str], *, cwd: str | None) -> str | None:
    cwd_path: Path | None = None
    if cwd is not None:
        cwd_path = _resolve_path(cwd, base=Path.cwd())
        if not cwd_path.exists():
            return _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=f"evaluator cwd does not exist: {cwd}",
            )
        if not cwd_path.is_dir():
            return _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=f"evaluator cwd is not a directory: {cwd}",
            )

    executable_error = _validate_command_executable(command[0], cwd_path)
    if executable_error is not None:
        return _format_preflight_error(command=command, cwd=cwd, detail=executable_error)

    script_arg = _maybe_script_path_arg(command)
    if script_arg is not None:
        script_path = _resolve_path(script_arg, base=cwd_path or Path.cwd())
        if not script_path.exists():
            return _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=(
                    f"script path not found: {script_arg}. "
                    "Use a correct relative path or set --evaluator-cwd."
                ),
            )
        if script_path.is_dir():
            return _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=f"script path is a directory: {script_arg}",
            )

    payload = json.dumps({"candidate": "__optimize_anything_preflight__"})
    run_cwd = str(cwd_path) if cwd_path is not None else None
    try:
        proc = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=10.0,
            cwd=run_cwd,
        )
    except FileNotFoundError:
        return _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=f"command executable not found: {command[0]}",
        )
    except subprocess.TimeoutExpired:
        return _format_preflight_error(
            command=command,
            cwd=cwd,
            detail="command timed out during preflight after 10.0s",
        )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        detail = f"command exited with code {proc.returncode}"
        if stderr:
            detail = f"{detail}; stderr: {stderr[:300]}"
        return _format_preflight_error(command=command, cwd=cwd, detail=detail)

    stdout = proc.stdout.strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        snippet = stdout[:300] if stdout else "<empty stdout>"
        return _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=f"stdout is not valid JSON: {e.msg}; stdout: {snippet}",
        )

    payload_error = _validate_evaluator_payload(result)
    if payload_error is not None:
        return _format_preflight_error(command=command, cwd=cwd, detail=payload_error)

    return None


def _preflight_http_evaluator(url: str, *, timeout: float = 10.0) -> str | None:
    """Send a preflight request to an HTTP evaluator and validate the response.

    Returns None if the evaluator is healthy, or an error string.
    """
    import httpx

    payload = {"candidate": "__optimize_anything_preflight__"}
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.TimeoutException:
        return (
            f"Error: HTTP evaluator preflight timed out after {timeout}s "
            f"(url: {url})"
        )
    except httpx.HTTPStatusError as e:
        return (
            f"Error: HTTP evaluator preflight returned HTTP {e.response.status_code} "
            f"(url: {url})"
        )
    except httpx.ConnectError:
        return (
            f"Error: HTTP evaluator preflight failed — connection refused "
            f"(url: {url}). Is the evaluator server running?"
        )
    except httpx.RequestError as e:
        return f"Error: HTTP evaluator preflight request failed (url: {url}): {e}"

    try:
        result = resp.json()
    except (ValueError, Exception):
        snippet = resp.text[:300] if resp.text else "<empty body>"
        return (
            f"Error: HTTP evaluator preflight returned non-JSON response "
            f"(url: {url}): {snippet}"
        )

    payload_error = _validate_evaluator_payload(result)
    if payload_error is not None:
        return f"Error: HTTP evaluator preflight response invalid (url: {url}): {payload_error}"

    return None


def _load_spec_if_provided(spec_file: str) -> dict | None | bool:
    """Load spec file if provided.

    Returns:
        dict: loaded spec
        None: no spec file (not an error)
        False: load failed (error already printed)
    """
    from optimize_anything.spec_loader import SpecLoadError, load_spec

    try:
        return load_spec(spec_file)
    except SpecLoadError as exc:
        print(f"Error loading spec file: {exc}", file=sys.stderr)
        return False


def _apply_spec_to_args(
    args: argparse.Namespace,
    spec: dict,
) -> argparse.Namespace:
    """Apply spec values to args. CLI flags take precedence over spec values."""
    import copy

    args = copy.copy(args)

    for key in ("objective", "background", "output", "evaluator_url", "evaluator_cwd"):
        if getattr(args, key, None) is None and spec.get(key) is not None:
            setattr(args, key, spec[key])

    if getattr(args, "evaluator_command", None) is None and spec.get("evaluator_command"):
        args.evaluator_command = spec["evaluator_command"]

    # budget: default is 100; spec overrides only if CLI user didn't explicitly set it
    if args.budget == 100 and spec.get("budget") is not None:
        args.budget = spec["budget"]

    if getattr(args, "judge_model", None) is None and spec.get("judge_model") is not None:
        args.judge_model = spec["judge_model"]

    if getattr(args, "model", None) is None and spec.get("proposer_model") is not None:
        args.model = spec["proposer_model"]

    # Intake: apply only if neither --intake-json nor --intake-file was provided
    if (
        getattr(args, "intake_json", None) is None
        and getattr(args, "intake_file", None) is None
        and spec.get("intake")
    ):
        args.intake_json = json.dumps(spec["intake"])

    return args


def _save_run_dir(
    *,
    run_dir: str,
    seed: str,
    best_artifact: str | object,
    summary: dict,
) -> str | None:
    """Save run artifacts to <run_dir>/run-<timestamp>/.

    Returns the created directory path, or None if writing failed.
    """
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(run_dir).expanduser() / f"run-{timestamp}"
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


def _validate_command_executable(command_part: str, cwd: Path | None) -> str | None:
    if "/" in command_part:
        executable = _resolve_path(command_part, base=cwd or Path.cwd())
        if not executable.exists():
            return f"command executable path not found: {command_part}"
        if executable.is_dir():
            return f"command executable is a directory: {command_part}"
        return None

    if shutil.which(command_part) is None:
        return f"command executable not found in PATH: {command_part}"
    return None


def _maybe_script_path_arg(command: list[str]) -> str | None:
    if len(command) < 2:
        return None
    executable = Path(command[0]).name.lower()
    if executable in {"bash", "sh", "zsh", "python", "python3", "node", "ruby", "perl"}:
        script_arg = command[1]
        if script_arg in {"-c", "-m"} or script_arg.startswith("-"):
            return None
        return script_arg
    return None


def _validate_evaluator_payload(result: object) -> str | None:
    from optimize_anything.evaluators import validate_evaluator_payload
    return validate_evaluator_payload(result)


def _resolve_path(path: str, *, base: Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = base / resolved
    return resolved


def _format_preflight_error(*, command: list[str], cwd: str | None, detail: str) -> str:
    command_text = " ".join(shlex.quote(part) for part in command)
    cwd_text = cwd or os.getcwd()
    return (
        f"Error: evaluator preflight failed for command '{command_text}' "
        f"(cwd: {cwd_text}): {detail}"
    )


if __name__ == "__main__":
    sys.exit(main())
