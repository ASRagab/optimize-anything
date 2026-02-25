"""LLM-as-Judge evaluator factory and analysis tools.

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
    cleaned = _strip_code_fences(raw_content)

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


# ---------------------------------------------------------------------------
# analyze_for_dimensions — pre-optimization dimension discovery
# ---------------------------------------------------------------------------

ANALYZE_SYSTEM_PROMPT = """\
You are a careful, objective evaluator and quality analyst. You will be given
a text artifact, its current score, and the scoring objective. Your job is to
identify specific quality dimensions where improvement is possible.
You must return ONLY a JSON object — no markdown, no preamble, no explanation
outside the JSON.
"""

ANALYZE_DIMENSIONS_PROMPT = """\
## Context
A text artifact was scored {score:.2f} out of 1.0 on the objective:
"{objective}"

## Artifact
```
{artifact}
```

## Task
Identify 4-6 specific, measurable quality dimensions where this artifact
could improve. For each dimension, provide:
- "name": a short snake_case identifier (e.g. "quickstart_speed")
- "weight": a float between 0.0 and 1.0 representing relative importance
  (weights should sum to approximately 1.0)
- "score": a float in [0.0, 1.0] — current score on this dimension
- "description": one sentence describing what this dimension measures

Focus on dimensions that provide gradient for improvement — areas where the
artifact is not already perfect. Avoid overly generic dimensions like
"overall_quality".

## Required JSON Output
Return a JSON object with:
- "dimensions": array of dimension objects as described above

Example:
{{"dimensions": [{{"name": "quickstart_speed", "weight": 0.25, "score": 0.85, "description": "Time from first read to first successful run"}}]}}
"""


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM response text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-len("```")].rstrip()
    return cleaned


def analyze_for_dimensions(
    artifact: str,
    objective: str,
    model: str,
    *,
    api_base: str | None = None,
    timeout: float = 60.0,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Score an artifact, then discover quality dimensions for refinement.

    Makes 2 LLM calls:
    1. Score the artifact with the vague objective (baseline)
    2. Ask the judge to identify 4-6 specific quality dimensions

    Args:
        artifact: The text artifact to analyze.
        objective: Natural language scoring objective.
        model: LiteLLM model string.
        api_base: Optional custom API base URL.
        timeout: Max seconds per LLM call.
        temperature: Sampling temperature.

    Returns:
        Dict with current_score, suggested_dimensions, intake_json, and
        recommendation.

    Raises:
        ValueError: If objective or model is invalid.
        RuntimeError: If either LLM call fails.
    """
    _validate_objective(objective)
    _validate_model_string(model)

    import litellm

    # --- Call 1: Score the artifact with vague objective ---
    score_prompt = _build_prompt(
        candidate=artifact,
        objective=objective,
        quality_dimensions=[],
        hard_constraints=[],
    )
    completion_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": score_prompt},
        ],
        "temperature": temperature,
        "timeout": timeout,
        "response_format": {"type": "json_object"},
    }
    if api_base:
        completion_kwargs["base_url"] = api_base

    try:
        response = litellm.completion(**completion_kwargs)
        raw_score_content = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"Scoring LLM call failed: {type(exc).__name__}: {exc}") from exc

    score, score_info = _parse_judge_response(raw_score_content, [], [])
    if "error" in score_info:
        raise RuntimeError(f"Scoring failed: {score_info['error']}")

    # --- Call 2: Discover quality dimensions ---
    analyze_prompt = ANALYZE_DIMENSIONS_PROMPT.format(
        score=score,
        objective=objective,
        artifact=artifact,
    )
    analyze_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": analyze_prompt},
        ],
        "temperature": temperature,
        "timeout": timeout,
        "response_format": {"type": "json_object"},
    }
    if api_base:
        analyze_kwargs["base_url"] = api_base

    try:
        response = litellm.completion(**analyze_kwargs)
        raw_dims_content = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(
            f"Dimension discovery LLM call failed: {type(exc).__name__}: {exc}"
        ) from exc

    dimensions = _parse_dimensions_response(raw_dims_content)

    # Build intake JSON for use with optimize
    intake = {
        "quality_dimensions": [
            {"name": d["name"], "weight": d["weight"]}
            for d in dimensions
        ],
    }
    intake_json_str = json.dumps(intake)

    return {
        "current_score": score,
        "reasoning": score_info.get("reasoning", ""),
        "suggested_dimensions": dimensions,
        "intake_json": intake_json_str,
        "recommendation": (
            f"Use the suggested dimensions with:\n"
            f"  optimize-anything optimize <artifact> "
            f"--judge-model {model} "
            f"--objective \"{objective}\" "
            f"--intake-json '{intake_json_str}'"
        ),
    }


def _parse_dimensions_response(raw_content: str | None) -> list[dict[str, Any]]:
    """Parse the dimension discovery LLM response.

    Returns a list of validated dimension dicts.
    Raises RuntimeError on parse failure.
    """
    if not raw_content:
        raise RuntimeError("Dimension discovery returned empty response")

    cleaned = _strip_code_fences(raw_content)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Dimension discovery returned malformed JSON: {exc.msg}"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Dimension discovery returned non-object JSON")

    raw_dims = parsed.get("dimensions")
    if not isinstance(raw_dims, list) or len(raw_dims) == 0:
        raise RuntimeError(
            "Dimension discovery did not return a 'dimensions' array"
        )

    validated: list[dict[str, Any]] = []
    for i, d in enumerate(raw_dims):
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        try:
            weight = float(d.get("weight", 0))
        except (TypeError, ValueError):
            weight = 0.0
        weight = max(0.0, min(1.0, weight))
        try:
            dim_score = float(d.get("score", 0))
        except (TypeError, ValueError):
            dim_score = 0.0
        dim_score = max(0.0, min(1.0, dim_score))
        description = d.get("description", "")
        if not isinstance(description, str):
            description = str(description)

        validated.append({
            "name": name.strip(),
            "weight": weight,
            "score": dim_score,
            "description": description,
        })

    if not validated:
        raise RuntimeError("No valid dimensions found in LLM response")

    return validated
