"""MCP server exposing optimize-anything tools via FastMCP."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("optimize-anything")


@mcp.tool()
async def optimize(
    seed: str,
    evaluator_command: list[str] | None = None,
    evaluator_url: str | None = None,
    evaluator_cwd: str | None = None,
    objective: str | None = None,
    background: str | None = None,
    max_metric_calls: int = 100,
) -> str:
    """Optimize a text artifact using gepa.

    Provide either evaluator_command (shell command) or evaluator_url (HTTP endpoint).
    evaluator_cwd is optional and only applies to evaluator_command.
    The evaluator receives {"candidate": "<text>"} and returns {"score": <float>, ...}.
    """
    from optimize_anything.evaluators import command_evaluator, http_evaluator
    from optimize_anything.result_contract import build_optimize_summary
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig

    if evaluator_command and evaluator_url:
        return json.dumps(
            {"error": "Provide either evaluator_command or evaluator_url, not both"}
        )

    if evaluator_command:
        eval_fn = command_evaluator(evaluator_command, cwd=evaluator_cwd)
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

    return json.dumps(build_optimize_summary(result), default=str)


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
    evaluator_type: str | None = None,
    intake: dict[str, Any] | None = None,
) -> str:
    """Generate an evaluator script for a given artifact and objective."""
    from optimize_anything.evaluator_generator import generate_evaluator_script
    from optimize_anything.intake import normalize_intake_spec

    normalized_intake: dict[str, Any] | None = None
    if intake is not None:
        try:
            normalized_intake = normalize_intake_spec(intake)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    script = generate_evaluator_script(
        seed=seed,
        objective=objective,
        evaluator_type=evaluator_type,
        intake=normalized_intake,
    )
    return script


@mcp.tool()
async def evaluator_intake(
    artifact_class: str | None = None,
    quality_dimensions: list[dict[str, Any]] | None = None,
    hard_constraints: list[str] | None = None,
    evaluation_pattern: str | None = None,
    execution_mode: str | None = None,
    evaluator_cwd: str | None = None,
) -> str:
    """Normalize evaluator intake fields and return canonical JSON."""
    from optimize_anything.intake import normalize_intake_spec

    intake_spec: dict[str, Any] = {}
    if artifact_class is not None:
        intake_spec["artifact_class"] = artifact_class
    if quality_dimensions is not None:
        intake_spec["quality_dimensions"] = quality_dimensions
    if hard_constraints is not None:
        intake_spec["hard_constraints"] = hard_constraints
    if evaluation_pattern is not None:
        intake_spec["evaluation_pattern"] = evaluation_pattern
    if execution_mode is not None:
        intake_spec["execution_mode"] = execution_mode
    if evaluator_cwd is not None:
        intake_spec["evaluator_cwd"] = evaluator_cwd

    try:
        normalized = normalize_intake_spec(intake_spec)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    return json.dumps(normalized)


# Entry point for python -m optimize_anything.server
def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
