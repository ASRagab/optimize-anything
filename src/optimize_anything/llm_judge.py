"""LLM-as-Judge evaluator factory and analysis tools.

Uses a provider-neutral completion backend to call a language model as an evaluator. The model receives a
structured prompt describing the objective, quality dimensions, and hard
constraints, then returns a JSON score object.

Protocol is compatible with gepa's evaluator contract:
    evaluator(candidate: str) -> tuple[float, dict]
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable

from optimize_anything.llm_backends.base import (
    CompletionBackend,
    CompletionRequest,
    InvalidResponse,
    Role,
    SamplingOptions,
)
from optimize_anything.llm_backends.litellm_backend import LiteLLMBackend
from optimize_anything.llm_backends.provenance import completion_event
from optimize_anything.llm_backends.schema import score_output_schema, strip_code_fences

_strip_code_fences = strip_code_fences

JUDGE_SYSTEM_PROMPT = """\
You are a careful, objective evaluator. You will be given a text artifact and
asked to score it. You must return ONLY a JSON object — no markdown, no
preamble, no explanation outside the JSON.
"""

JUDGE_PROMPT_WITH_DIMENSIONS = """\
## Objective
{objective}

## Task Model Context
{task_model_context}

## Quality Dimensions (higher is better, weights shown)
{dimensions_text}

## Hard Constraints (all must be satisfied; if any is violated, score must be 0.0)
{constraints_text}

## Example Context (optional)
{example_text}

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

## Task Model Context
{task_model_context}

## Example Context (optional)
{example_text}

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
    model: str | None = None,
    quality_dimensions: list[dict[str, Any]] | None = None,
    hard_constraints: list[str] | None = None,
    timeout: float = 60.0,
    temperature: float | None = None,
    api_base: str | None = None,
    task_model: str | None = None,
    backend: CompletionBackend | None = None,
    role: Role = "judge",
) -> Callable[[str, Any | None], tuple[float, dict[str, Any]]]:
    """Create an LLM-as-judge evaluator compatible with gepa's evaluator contract."""
    _validate_objective(objective)
    use_backend_schema = backend is not None
    if backend is None:
        _validate_model_string(model)
        backend = LiteLLMBackend(model=model, api_base=api_base)
    dims = quality_dimensions or []
    constraints = hard_constraints or []

    def evaluate(candidate: str, example: Any | None = None) -> tuple[float, dict[str, Any]]:
        prompt = _build_prompt(
            candidate=candidate,
            objective=objective,
            quality_dimensions=dims,
            hard_constraints=constraints,
            task_model=task_model,
            example=example,
        )
        try:
            result = backend.complete(CompletionRequest(
                prompt=prompt,
                role=role,
                model=model,
                output_schema=(score_output_schema(
                    [dim["name"] for dim in dims if isinstance(dim.get("name"), str) and dim["name"]],
                    include_hard_constraints=bool(dims or constraints),
                ) if use_backend_schema else None),
                json_mode=not use_backend_schema,
                timeout_seconds=timeout,
                sampling=(SamplingOptions(temperature=temperature) if temperature is not None else None),
                system_prompt=JUDGE_SYSTEM_PROMPT,
            ))
            raw_content = result.text
        except Exception as exc:
            error_side_info: dict[str, Any] = {
                "error": f"LLM call failed: {type(exc).__name__}: {exc}",
                "reasoning": "LLM judge call failed; returned fallback score 0.0.",
            }
            if isinstance(exc, InvalidResponse):
                error_side_info["raw_response"] = ""
            for dim in dims:
                name = dim.get("name")
                if isinstance(name, str) and name:
                    error_side_info.setdefault(name, 0.0)
            return 0.0, error_side_info

        score, side_info = _parse_judge_response(raw_content, dims, constraints)
        side_info["llm_provenance"] = completion_event(result)
        return score, side_info

    return evaluate


def _validate_objective(objective: str) -> None:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective must be a non-empty string")


def _validate_model_string(model: str | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")


def _build_prompt(
    *,
    candidate: str,
    objective: str,
    quality_dimensions: list[dict[str, Any]],
    hard_constraints: list[str],
    task_model: str | None = None,
    example: Any | None = None,
) -> str:
    task_model_context = task_model if task_model else "(not provided)"
    example_text = json.dumps(example, ensure_ascii=False, indent=2) if example is not None else "(none)"
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
            task_model_context=task_model_context,
            example_text=example_text,
        )
    return JUDGE_PROMPT_SIMPLE.format(
        objective=objective,
        candidate=candidate,
        task_model_context=task_model_context,
        example_text=example_text,
    )


def _parse_judge_response(
    raw_content: str | None,
    quality_dimensions: list[dict[str, Any]],
    hard_constraints: list[str],
) -> tuple[float, dict[str, Any]]:
    if not raw_content:
        return 0.0, {"error": "LLM returned empty response"}

    # Strip markdown code fences (e.g. ```json ... ```) that some providers add
    cleaned = strip_code_fences(raw_content)

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
        coerced_score = _coerce_float(raw_score)
        if coerced_score is None:
            return 0.0, {
                "error": "LLM 'score' field is not numeric",
                "raw_response": raw_content[:500],
                **side_info,
            }
        score = coerced_score

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
        value = _coerce_float(raw_value)
        if value is None:
            value = 0.0
        value = max(0.0, min(1.0, value))
        weighted_sum += value * dim["weight"]
    return weighted_sum / total_weight


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def analyze_for_dimensions(
    artifact: str,
    objective: str,
    model: str | None = None,
    *,
    api_base: str | None = None,
    timeout: float = 60.0,
    temperature: float | None = None,
    backend: CompletionBackend | None = None,
) -> dict[str, Any]:
    """Score an artifact then discover quality dimensions for refinement.

    Makes 2 LLM calls: (1) score with vague objective, (2) identify 4-6
    specific quality dimensions where improvement is possible.
    """
    _validate_objective(objective)
    use_backend_schema = backend is not None
    if backend is None:
        _validate_model_string(model)
        backend = LiteLLMBackend(model=model, api_base=api_base)

    # --- Call 1: Score the artifact with vague objective ---
    score_prompt = _build_prompt(
        candidate=artifact,
        objective=objective,
        quality_dimensions=[],
        hard_constraints=[],
    )
    try:
        response = backend.complete(CompletionRequest(
            prompt=score_prompt,
            role="analysis",
            model=model,
            output_schema=(score_output_schema([], include_hard_constraints=False)
                           if use_backend_schema else None),
            json_mode=not use_backend_schema,
            timeout_seconds=timeout,
            sampling=(SamplingOptions(temperature=temperature) if temperature is not None else None),
            system_prompt=JUDGE_SYSTEM_PROMPT,
        ))
        score_result = response
        raw_score_content = response.text
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
    try:
        response = backend.complete(CompletionRequest(
            prompt=analyze_prompt,
            role="analysis",
            model=model,
            output_schema=(_dimensions_output_schema() if use_backend_schema else None),
            json_mode=not use_backend_schema,
            timeout_seconds=timeout,
            sampling=(SamplingOptions(temperature=temperature) if temperature is not None else None),
            system_prompt=ANALYZE_SYSTEM_PROMPT,
        ))
        raw_dims_content = response.text
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
        "llm_provenance": [completion_event(score_result), completion_event(response)],
        "recommendation": (
            f"Use the suggested dimensions with:\n"
            f"  optimize-anything optimize <artifact> "
            f"--judge-model {model or '<provider-default>'} "
            f"--objective \"{objective}\" "
            f"--intake-json '{intake_json_str}'"
        ),
    }


def _dimensions_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "dimensions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "weight": {"type": "number"},
                        "score": {"type": "number"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "weight", "score", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["dimensions"],
        "additionalProperties": False,
    }


def _parse_dimensions_response(raw_content: str | None) -> list[dict[str, Any]]:
    """Parse the dimension discovery LLM response into validated dimension dicts."""
    if not raw_content:
        raise RuntimeError("Dimension discovery returned empty response")

    cleaned = strip_code_fences(raw_content)

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
    for raw_dimension in raw_dims:
        normalized = _normalize_dimension_entry(raw_dimension)
        if normalized is not None:
            validated.append(normalized)

    if not validated:
        raise RuntimeError("No valid dimensions found in LLM response")

    return validated


def _normalize_dimension_entry(raw_dimension: Any) -> dict[str, Any] | None:
    if not isinstance(raw_dimension, dict):
        return None

    name = raw_dimension.get("name")
    if not isinstance(name, str):
        return None
    normalized_name = name.strip()
    if not normalized_name:
        return None

    description = raw_dimension.get("description", "")
    return {
        "name": normalized_name,
        "weight": _clamp_dimension_value(raw_dimension.get("weight", 0)),
        "score": _clamp_dimension_value(raw_dimension.get("score", 0)),
        "description": description if isinstance(description, str) else str(description),
    }


def _clamp_dimension_value(value: Any) -> float:
    coerced = _coerce_float(value)
    if coerced is None:
        return 0.0
    return max(0.0, min(1.0, coerced))
