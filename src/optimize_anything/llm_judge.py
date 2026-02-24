"""LLM-as-Judge evaluator factory.

Uses litellm to call a language model as an evaluator. The model receives a
structured prompt describing the objective, quality dimensions, and hard
constraints, then returns a JSON score object.

Protocol is compatible with gepa's evaluator contract:
    evaluator(candidate: str) -> tuple[float, dict]
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable

JUDGE_SYSTEM_PROMPT = """\
You are a careful, objective evaluator. You will be given a text artifact and
asked to score it. You must return ONLY a JSON object — no markdown, no
preamble, no explanation outside the JSON.
"""

JUDGE_PROMPT_WITH_DIMENSIONS = """\
## Objective
{objective}

## Quality Dimensions (higher is better, weights shown)
{dimensions_text}

## Hard Constraints (all must be satisfied; if any is violated, score must be 0.0)
{constraints_text}

## Artifact to Evaluate
```
{candidate}
```

## Required JSON Output
Return a JSON object with:
- "score": float in [0.0, 1.0] — weighted aggregate across all dimensions
- "reasoning": string — brief explanation of strengths and weaknesses
- One key per dimension named exactly as the dimension name, each a float in [0.0, 1.0]
- "hard_constraints_satisfied": boolean — true only if ALL hard constraints pass
- If hard_constraints_satisfied is false, set score to 0.0

Example:
{{"score": 0.72, "reasoning": "Clear structure but verbose.", "clarity": 0.85, "conciseness": 0.55, "hard_constraints_satisfied": true}}
"""

JUDGE_PROMPT_SIMPLE = """\
## Objective
{objective}

## Artifact to Evaluate
```
{candidate}
```

## Required JSON Output
Return a JSON object with:
- "score": float in [0.0, 1.0]
- "reasoning": string — brief explanation

Example:
{{"score": 0.72, "reasoning": "Solid overall with minor clarity issues."}}
"""


def llm_judge_evaluator(
    objective: str,
    *,
    model: str,
    quality_dimensions: list[dict[str, Any]] | None = None,
    hard_constraints: list[str] | None = None,
    timeout: float = 60.0,
    temperature: float = 0.0,
    api_base: str | None = None,
) -> Callable[[str], tuple[float, dict[str, Any]]]:
    """Create an LLM-as-judge evaluator.

    Args:
        objective: Natural language description of what a good artifact looks like.
        model: LiteLLM model string (e.g. "openai/gpt-4o-mini").
        quality_dimensions: List of {"name": str, "weight": float} dicts from intake spec.
        hard_constraints: List of constraint strings.
        timeout: Max seconds to wait for the LLM response.
        temperature: Sampling temperature. Default 0.0 for determinism.
        api_base: Optional custom API base URL.

    Returns:
        An evaluator function compatible with gepa: candidate -> (score, side_info).
    """
    _validate_objective(objective)
    _validate_model_string(model)
    dims = quality_dimensions or []
    constraints = hard_constraints or []

    def evaluate(candidate: str) -> tuple[float, dict[str, Any]]:
        prompt = _build_prompt(
            candidate=candidate,
            objective=objective,
            quality_dimensions=dims,
            hard_constraints=constraints,
        )
        try:
            import litellm

            completion_kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "timeout": timeout,
                "response_format": {"type": "json_object"},
            }
            if api_base:
                completion_kwargs["base_url"] = api_base

            response = litellm.completion(**completion_kwargs)
            raw_content = response.choices[0].message.content
        except Exception as exc:
            return 0.0, {"error": f"LLM call failed: {type(exc).__name__}: {exc}"}

        return _parse_judge_response(raw_content, dims, constraints)

    return evaluate


def _validate_objective(objective: str) -> None:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective must be a non-empty string")


def _validate_model_string(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")


def _build_prompt(
    *,
    candidate: str,
    objective: str,
    quality_dimensions: list[dict[str, Any]],
    hard_constraints: list[str],
) -> str:
    if quality_dimensions:
        dimensions_text = "\n".join(
            f"- {d['name']} (weight={d['weight']:.4f})" for d in quality_dimensions
        )
        constraints_text = (
            "\n".join(f"- {c}" for c in hard_constraints)
            if hard_constraints
            else "(none)"
        )
        return JUDGE_PROMPT_WITH_DIMENSIONS.format(
            objective=objective,
            dimensions_text=dimensions_text,
            constraints_text=constraints_text,
            candidate=candidate,
        )
    return JUDGE_PROMPT_SIMPLE.format(objective=objective, candidate=candidate)


def _parse_judge_response(
    raw_content: str | None,
    quality_dimensions: list[dict[str, Any]],
    hard_constraints: list[str],
) -> tuple[float, dict[str, Any]]:
    if not raw_content:
        return 0.0, {"error": "LLM returned empty response"}

    # Strip markdown code fences (e.g. ```json ... ```) that some providers add
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1 :]
        # Remove closing fence
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -len("```")].rstrip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return 0.0, {
            "error": f"LLM returned malformed JSON: {exc.msg}",
            "raw_response": raw_content[:500],
        }

    if not isinstance(parsed, dict):
        return 0.0, {
            "error": "LLM returned non-object JSON",
            "raw_response": raw_content[:500],
        }

    side_info: dict[str, Any] = {k: v for k, v in parsed.items() if k != "score"}

    # Hard constraint gate
    if hard_constraints and not parsed.get("hard_constraints_satisfied", True):
        side_info["hard_constraint_violation"] = True
        return 0.0, side_info

    # Compute score
    if quality_dimensions:
        score = _compute_weighted_score(parsed, quality_dimensions)
    else:
        raw_score = parsed.get("score")
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            return 0.0, {
                "error": "LLM 'score' field is not numeric",
                "raw_response": raw_content[:500],
                **side_info,
            }

    if not math.isfinite(score):
        return 0.0, {"error": "LLM score is not finite", **side_info}

    score = max(0.0, min(1.0, score))
    return score, side_info


def _compute_weighted_score(
    parsed: dict[str, Any],
    quality_dimensions: list[dict[str, Any]],
) -> float:
    total_weight = sum(d["weight"] for d in quality_dimensions)
    if total_weight <= 0:
        return 0.0
    weighted_sum = 0.0
    for dim in quality_dimensions:
        dim_name = dim["name"]
        raw_value = parsed.get(dim_name)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = 0.0
        value = max(0.0, min(1.0, value))
        weighted_sum += value * dim["weight"]
    return weighted_sum / total_weight
