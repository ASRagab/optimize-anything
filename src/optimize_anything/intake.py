"""Normalization and validation for evaluator intake specifications."""

from __future__ import annotations

from collections.abc import Mapping
from math import floor, isfinite
from numbers import Real
from typing import Any

DEFAULT_ARTIFACT_CLASS = "general_text"
DEFAULT_EVALUATION_PATTERN = "judge"
DEFAULT_EXECUTION_MODE = "command"

ALLOWED_EVALUATION_PATTERNS = {
    "verification",
    "judge",
    "simulation",
    "composite",
}
ALLOWED_EXECUTION_MODES = {"command", "http"}

DEFAULT_QUALITY_DIMENSIONS: tuple[tuple[str, float], ...] = (
    ("correctness", 0.4),
    ("clarity", 0.35),
    ("conciseness", 0.25),
)


def normalize_intake_spec(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize evaluator intake input and validate required structure."""
    if data is None:
        data = {}
    elif not isinstance(data, Mapping):
        raise ValueError("intake spec must be a mapping")

    artifact_class = _normalize_non_empty_string(
        data.get("artifact_class", DEFAULT_ARTIFACT_CLASS),
        field_name="artifact_class",
    )
    quality_dimensions = _normalize_quality_dimensions(data.get("quality_dimensions"))
    hard_constraints = _normalize_hard_constraints(data.get("hard_constraints", []))
    evaluation_pattern = _normalize_enum(
        data.get("evaluation_pattern", DEFAULT_EVALUATION_PATTERN),
        field_name="evaluation_pattern",
        allowed=ALLOWED_EVALUATION_PATTERNS,
    )
    execution_mode = _normalize_enum(
        data.get("execution_mode", DEFAULT_EXECUTION_MODE),
        field_name="execution_mode",
        allowed=ALLOWED_EXECUTION_MODES,
    )
    evaluator_cwd = _normalize_optional_string(
        data.get("evaluator_cwd"),
        field_name="evaluator_cwd",
    )

    return {
        "artifact_class": artifact_class,
        "quality_dimensions": quality_dimensions,
        "hard_constraints": hard_constraints,
        "evaluation_pattern": evaluation_pattern,
        "execution_mode": execution_mode,
        "evaluator_cwd": evaluator_cwd,
    }


def _normalize_non_empty_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_string(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or None")
    normalized = value.strip()
    return normalized or None


def _normalize_enum(value: Any, *, field_name: str, allowed: set[str]) -> str:
    normalized = _normalize_non_empty_string(value, field_name=field_name).lower()
    if normalized not in allowed:
        options = ", ".join(f"'{item}'" for item in sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {options}")
    return normalized


def _normalize_quality_dimensions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return [
            {"name": name, "weight": weight}
            for name, weight in DEFAULT_QUALITY_DIMENSIONS
        ]

    if not isinstance(value, list):
        raise ValueError("quality_dimensions must be a list of objects")
    if not value:
        raise ValueError("quality_dimensions must contain at least one dimension")

    names: list[str] = []
    weights: list[float] = []

    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"quality_dimensions[{idx}] must be an object with 'name' and 'weight'"
            )
        if "name" not in item:
            raise ValueError(f"quality_dimensions[{idx}] missing required field 'name'")
        if "weight" not in item:
            raise ValueError(f"quality_dimensions[{idx}] missing required field 'weight'")

        name = item["name"]
        if not isinstance(name, str):
            raise ValueError(f"quality_dimensions[{idx}].name must be a string")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError(
                f"quality_dimensions[{idx}].name must be a non-empty string"
            )

        raw_weight = item["weight"]
        if isinstance(raw_weight, bool) or not isinstance(raw_weight, Real):
            raise ValueError(f"quality_dimensions[{idx}].weight must be numeric")

        weight = float(raw_weight)
        if not isfinite(weight):
            raise ValueError(f"quality_dimensions[{idx}].weight must be finite")
        if weight <= 0:
            raise ValueError(f"quality_dimensions[{idx}].weight must be > 0")

        names.append(normalized_name)
        weights.append(weight)

    normalized_weights = _normalize_weights(weights)
    return [
        {"name": name, "weight": normalized_weights[idx]}
        for idx, name in enumerate(names)
    ]


def _normalize_weights(weights: list[float]) -> list[float]:
    total = sum(weights)
    scaled = [(weight / total) * 10000 for weight in weights]

    base_units = [int(floor(value)) for value in scaled]
    units_to_distribute = 10000 - sum(base_units)

    fractional_parts = [
        (scaled[idx] - base_units[idx], idx) for idx in range(len(weights))
    ]
    fractional_parts.sort(key=lambda item: (-item[0], item[1]))

    for _, idx in fractional_parts[:units_to_distribute]:
        base_units[idx] += 1

    return [unit / 10000 for unit in base_units]


def _normalize_hard_constraints(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("hard_constraints must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"hard_constraints[{idx}] must be a string")
        stripped = item.strip()
        if not stripped or stripped in seen:
            continue
        normalized.append(stripped)
        seen.add(stripped)

    return normalized
