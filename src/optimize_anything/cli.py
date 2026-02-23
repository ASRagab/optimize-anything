"""CLI entry point for optimize-anything."""

from __future__ import annotations

import argparse
import json
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

    if args.evaluator_command:
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
        with open(args.output, "w") as f:
            f.write(best if isinstance(best, str) else json.dumps(best))
        summary["output_file"] = args.output

    print(json.dumps(summary, indent=2, default=str))
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


if __name__ == "__main__":
    sys.exit(main())
