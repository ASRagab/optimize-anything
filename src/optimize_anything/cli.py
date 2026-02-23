"""CLI entry point for optimize-anything."""

from __future__ import annotations

import argparse
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
    return 1


def _cmd_optimize(args: argparse.Namespace) -> int:
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

    if args.evaluator_command and args.evaluator_url:
        print(
            "Error: provide either --evaluator-command or --evaluator-url, not both",
            file=sys.stderr,
        )
        return 1

    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from optimize_anything.result_contract import build_optimize_summary
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig

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
        eval_fn = http_evaluator(args.evaluator_url)
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
                "Error: provide --evaluator-command or --evaluator-url",
                file=sys.stderr,
            )
        return 1

    config = GEPAConfig(engine=EngineConfig(max_metric_calls=args.budget))
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=eval_fn,
        objective=args.objective,
        background=args.background,
        config=config,
    )

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
    if not isinstance(result, dict):
        return "evaluator output must be a JSON object"

    if "score" not in result:
        return "evaluator output missing required 'score' field"

    raw_score = result.get("score")
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return "evaluator output 'score' must be numeric"

    if not math.isfinite(score):
        return "evaluator output 'score' must be finite"

    return None


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
