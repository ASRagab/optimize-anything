"""Jev (TypeSafe System One) evaluator factory.

Scores an artifact with one Jev request: a Score question per quality
dimension and a Noul (yes/no) question per hard constraint. Weights and the
hard-constraint gate stay in code, because Jev is a judgment model, not a
calculator.

Protocol is compatible with gepa's evaluator contract:
    evaluator(candidate: str, example: Any | None = None) -> tuple[float, dict]
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Callable

import httpx

API_URL = "https://api.typesafe.ai/v1/systemone"
API_KEY_ENV = "TYPESAFE_API_KEY"
DEFAULT_JEV_MODEL = "jev-latest"
HARD_CONSTRAINT_THRESHOLD = 0.5

# Generic levels: intake carries only dimension names, so the rubric is built here.
# shortcut: one rubric for every dimension, upgrade to per-dimension levels in intake
# if the live A/B shows these are too coarse.
SCORE_LEVELS = [
    "Fails the dimension: the quality is absent or wrong",
    "Weak on the dimension: present but with major gaps",
    "Adequate on the dimension: meets the basics with notable gaps",
    "Strong on the dimension: meets it well with only minor gaps",
]

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_MAX_RETRY_WAIT = 30.0
_DEFAULT_DIMENSIONS = [{"name": "overall quality", "weight": 1.0}]


class _JevError(Exception):
    """Raised internally; converted to a 0.0 score at the evaluator boundary."""


def jev_judge_evaluator(
    objective: str,
    *,
    model: str | None = None,
    quality_dimensions: list[dict[str, Any]] | None = None,
    hard_constraints: list[str] | None = None,
    timeout: float = 60.0,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> Callable[[str, Any | None], tuple[float, dict[str, Any]]]:
    """Create a Jev-backed evaluator compatible with gepa's evaluator contract."""
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective must be a non-empty string")
    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        raise ValueError(f"{API_KEY_ENV} is not set")

    model_id = model or DEFAULT_JEV_MODEL
    dims = quality_dimensions or _DEFAULT_DIMENSIONS
    constraints = hard_constraints or []
    # httpx.Client is thread-safe, so GEPA's parallel workers share one.
    http = client or httpx.Client(timeout=timeout)
    headers = {"Authorization": f"Bearer {key}"}

    def evaluate(candidate: str, example: Any | None = None) -> tuple[float, dict[str, Any]]:
        state: dict[str, Any] = {"objective": objective, "artifact": candidate}
        if example is not None:
            state["example"] = example
        body = {
            "model": model_id,
            "state": state,
            "questions": _build_questions(dims, constraints),
        }
        try:
            response = _post(http, body, headers)
            return _score_response(response, dims, constraints)
        except _JevError as exc:
            side_info: dict[str, Any] = {
                "error": f"Jev call failed: {exc}",
                "reasoning": "Jev call failed; returned fallback score 0.0.",
            }
            for dim in dims:
                side_info.setdefault(dim["name"], 0.0)
            return 0.0, side_info

    return evaluate


def _levels(dim: dict[str, Any]) -> list[str]:
    # A dimension's own rubric (intake `levels`) wins over the generic scale.
    return dim.get("levels") or SCORE_LEVELS


def _build_questions(
    dims: list[dict[str, Any]], constraints: list[str]
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for i, dim in enumerate(dims):
        questions[f"d{i}"] = {
            "type": "score",
            "instructions": (
                f'How well does `artifact` satisfy the quality dimension "{dim["name"]}" '
                "for the goal stated in `objective`?"
            ),
            "criteria": _levels(dim),
        }
    for i, constraint in enumerate(constraints):
        questions[f"c{i}"] = {
            "type": "noul",
            "instructions": f"Does `artifact` satisfy this requirement: {constraint}?",
        }
    return questions


def _post(http: httpx.Client, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = http.post(API_URL, json=body, headers=headers)
        except httpx.TimeoutException:
            raise _JevError("request timed out") from None
        except httpx.RequestError as exc:
            raise _JevError(f"request failed: {exc}") from None

        if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_retry_wait(resp, attempt))
            continue
        if resp.status_code >= 400:
            raise _JevError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            parsed = resp.json()
        except ValueError:
            raise _JevError("response is not valid JSON") from None
        if not isinstance(parsed, dict):
            raise _JevError("response is not a JSON object")
        return parsed
    raise _JevError("retries exhausted")  # unreachable: the last attempt returns or raises


def _retry_wait(resp: httpx.Response, attempt: int) -> float:
    try:
        wait = float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        wait = 0.5 * 2**attempt
    return max(0.0, min(wait, _MAX_RETRY_WAIT))


def _score_response(
    response: dict[str, Any],
    dims: list[dict[str, Any]],
    constraints: list[str],
) -> tuple[float, dict[str, Any]]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise _JevError("response has no 'answers' object")

    side_info: dict[str, Any] = {}
    violated = False
    for i, constraint in enumerate(constraints):
        probability = _number(answers.get(f"c{i}"), "noul", f"c{i}")
        if probability < HARD_CONSTRAINT_THRESHOLD:
            violated = True
    side_info["hard_constraints_satisfied"] = not violated

    total_weight = sum(d["weight"] for d in dims)
    weighted = 0.0
    parts: list[str] = []
    for i, dim in enumerate(dims):
        answer = answers.get(f"d{i}")
        raw = _number(answer, "score", f"d{i}")
        confidence = _number(answer, "confidence", f"d{i}")
        levels = _levels(dim)
        top_level = len(levels) - 1
        value = max(0.0, min(1.0, raw / top_level))
        weighted += value * dim["weight"]
        level = levels[min(top_level, max(0, round(raw)))]
        side_info[dim["name"]] = value
        parts.append(f'{dim["name"]}: {value:.2f} ({level}; confidence {confidence:.2f})')

    side_info["reasoning"] = "; ".join(parts)
    side_info["jev_model"] = response.get("model")
    side_info["usage"] = response.get("usage")

    if violated:
        side_info["hard_constraint_violation"] = True
        return 0.0, side_info
    score = weighted / total_weight if total_weight > 0 else 0.0
    return max(0.0, min(1.0, score)), side_info


def _number(answer: Any, field: str, question_id: str) -> float:
    value = answer.get(field) if isinstance(answer, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _JevError(f"answer {question_id} has no numeric '{field}'")
    return float(value)
