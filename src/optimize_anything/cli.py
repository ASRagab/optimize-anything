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
    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig

    seed = _read_seed(args.seed_file)
    if seed is None:
        return 1

    if args.evaluator_command:
        eval_fn = command_evaluator(args.evaluator_command)
    elif args.evaluator_url:
        eval_fn = http_evaluator(args.evaluator_url)
    else:
        print("Error: provide --evaluator-command or --evaluator-url", file=sys.stderr)
        return 1

    config = GEPAConfig(engine=EngineConfig(max_metric_calls=args.budget))
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=eval_fn,
        objective=args.objective,
        background=args.background,
        config=config,
    )

    best = result.best_candidate
    if args.output:
        with open(args.output, "w") as f:
            f.write(best if isinstance(best, str) else json.dumps(best))
        print(f"Best candidate written to {args.output}")
    else:
        print(best)

    print(f"\nMetric calls: {result.total_metric_calls}", file=sys.stderr)
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


if __name__ == "__main__":
    sys.exit(main())
