"""Shared JSON Schema trust-boundary checks."""

from __future__ import annotations

from .base import ConfigurationError


def score_output_schema(
    dimension_names: list[str], *, include_hard_constraints: bool,
) -> dict[str, object]:
    """Build the shared strict score response contract."""
    properties: dict[str, object] = {
        "score": {"type": "number"},
        "reasoning": {"type": "string"},
    }
    required = ["score", "reasoning"]
    for name in dimension_names:
        properties[name] = {"type": "number"}
        if name not in required:
            required.append(name)
    if include_hard_constraints:
        properties["hard_constraints_satisfied"] = {"type": "boolean"}
        required.append("hard_constraints_satisfied")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def reject_external_refs(value: object) -> None:
    """Allow only document-local references; reject remote and rebasing identifiers."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("$ref", "$dynamicRef", "$recursiveRef", "$id") and (
                not isinstance(item, str) or key == "$id" or not item.startswith("#/")
            ):
                raise ConfigurationError("output schema may only use local references")
            reject_external_refs(item)
    elif isinstance(value, list):
        for item in value:
            reject_external_refs(item)


def strip_code_fences(text: str) -> str:
    """Remove one optional Markdown fence around provider JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.partition("\n")[2]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    return cleaned
