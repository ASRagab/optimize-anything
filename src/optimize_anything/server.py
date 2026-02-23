"""MCP server exposing optimize-anything tools via FastMCP."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("optimize-anything")


@mcp.tool()
async def optimize(
    seed: str,
    evaluator_command: list[str] | None = None,
    evaluator_url: str | None = None,
    objective: str | None = None,
    background: str | None = None,
    max_metric_calls: int = 100,
) -> str:
    """Optimize a text artifact using gepa.

    Provide either evaluator_command (shell command) or evaluator_url (HTTP endpoint).
    The evaluator receives {"candidate": "<text>"} and returns {"score": <float>, ...}.
    """
    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig

    if evaluator_command:
        eval_fn = command_evaluator(evaluator_command)
    elif evaluator_url:
        eval_fn = http_evaluator(evaluator_url)
    else:
        return json.dumps({"error": "Provide either evaluator_command or evaluator_url"})

    config = GEPAConfig(engine=EngineConfig(max_metric_calls=max_metric_calls))

    result = optimize_anything(
        seed_candidate=seed,
        evaluator=eval_fn,
        objective=objective,
        background=background,
        config=config,
    )

    return json.dumps(
        {
            "best_candidate": result.best_candidate,
            "total_metric_calls": result.total_metric_calls,
            "val_scores": result.val_aggregate_scores,
        },
        default=str,
    )


@mcp.tool()
async def explain(seed: str, objective: str | None = None) -> str:
    """Explain what optimization would do for a given artifact."""
    lines = [
        "Optimization Plan:",
        f"- Seed length: {len(seed)} chars",
        f"- Objective: {objective or 'maximize evaluator score'}",
        "",
        "gepa will:",
        "1. Use the seed as the starting candidate",
        "2. Generate mutations via LLM reflection",
        "3. Evaluate each candidate with your evaluator",
        "4. Select the best-performing variant",
        "",
        "Provide an evaluator (command or HTTP URL) to begin.",
    ]
    return "\n".join(lines)


@mcp.tool()
async def recommend_budget(seed: str, evaluator_type: str = "command") -> str:
    """Recommend an evaluation budget based on artifact characteristics."""
    length = len(seed)
    if length < 100:
        budget = 50
        rationale = "Short artifact — fewer mutations needed"
    elif length < 500:
        budget = 100
        rationale = "Medium artifact — moderate exploration"
    elif length < 2000:
        budget = 200
        rationale = "Long artifact — more exploration needed"
    else:
        budget = 300
        rationale = "Very long artifact — extensive exploration recommended"

    return json.dumps(
        {
            "recommended_budget": budget,
            "rationale": rationale,
            "seed_length": length,
            "evaluator_type": evaluator_type,
        }
    )


@mcp.tool()
async def generate_evaluator(
    seed: str,
    objective: str,
    evaluator_type: str = "command",
) -> str:
    """Generate an evaluator script for a given artifact and objective."""
    from optimize_anything.evaluator_generator import generate_evaluator_script

    script = generate_evaluator_script(
        seed=seed, objective=objective, evaluator_type=evaluator_type
    )
    return script


# Entry point for python -m optimize_anything.server
def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
