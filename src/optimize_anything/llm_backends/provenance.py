"""Content-free completion provenance and cache identity primitives."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable, Mapping

from .base import CompletionRequest, CompletionResult


def completion_event(result: CompletionResult, *, call_id: str | None = None) -> dict[str, Any]:
    """Select the safe, stable fields allowed in the run event stream."""
    event: dict[str, Any] = {
        "role": result.role,
        "requested_backend": result.requested_backend,
        "actual_backend": result.actual_backend,
        "requested_model": result.requested_model,
        "actual_model": result.actual_model,
        "auth_class": result.auth_class,
        "auth_source": result.auth_source,
        "started_at": result.started_at,
        "duration_seconds": result.duration_seconds,
        "retry_count": result.retry_count,
        "prompt_contract_version": result.prompt_contract_version,
        "schema_contract_version": result.schema_contract_version,
    }
    if call_id:
        event["call_id"] = call_id
    if result.usage:
        event.update({
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        })
    if result.fallback:
        event["fallback_source"] = result.fallback.source_backend
        event["fallback_reason"] = result.fallback.reason
    return {key: value for key, value in event.items() if value is not None}


def aggregate_provenance(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate only provider metadata, with no prompts or account identifiers."""
    rows = list(events)
    dimensions = ("actual_backend", "actual_model", "auth_class", "role")
    counts = {dimension: dict(Counter(str(row.get(dimension, "unknown")) for row in rows))
              for dimension in dimensions}
    usage = {
        name: sum(value for row in rows if isinstance((value := row.get(name)), int))
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }
    return {
        "call_count": len(rows),
        "counts": counts,
        "usage": usage,
        "fallback_causes": dict(Counter(str(row["fallback_reason"]) for row in rows
                                        if "fallback_reason" in row)),
        "mixed_backend": len({row.get("actual_backend") for row in rows}) > 1,
    }


def cache_fingerprint(
    request: CompletionRequest, result: CompletionResult, *, input_identity: str,
) -> str:
    """Hash cache identity under the actual billing/backend route."""
    identity = {
        "actual_backend": result.actual_backend,
        "actual_model": result.actual_model or "provider-default",
        "auth_class": result.auth_class,
        "role": request.role,
        "prompt_contract_version": request.prompt_contract_version,
        "schema_contract_version": request.schema_contract_version,
        "input_identity": input_identity,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
