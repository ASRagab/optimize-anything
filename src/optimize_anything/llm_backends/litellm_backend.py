"""API completion adapter with local JSON Schema validation."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .base import (
    AuthSource,
    AuthenticationError,
    BackendCapabilities,
    BackendStatus,
    BackendUnavailable,
    Cancelled,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    InvalidResponse,
    QuotaExceeded,
    RateLimitError,
    Timeout,
    Usage,
    validate_capabilities,
)
from .schema import strip_code_fences

_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "description",
    "title", "default", "examples", "$schema",
}
_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def _check_schema(schema: Mapping[str, Any]) -> None:
    unknown = set(schema) - _SCHEMA_KEYS
    if unknown:
        raise ConfigurationError("unsupported JSON Schema keyword")
    kind = schema.get("type")
    if kind is not None and (not isinstance(kind, str) or kind not in _TYPES):
        raise ConfigurationError("unsupported JSON Schema type")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ConfigurationError("schema properties must be an object")
    for child in properties.values():
        if not isinstance(child, Mapping):
            raise ConfigurationError("schema property must be an object")
        _check_schema(child)
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, Mapping):
            raise ConfigurationError("schema items must be an object")
        _check_schema(items)
    required = schema.get("required", ())
    if not isinstance(required, (list, tuple)) or any(not isinstance(k, str) for k in required):
        raise ConfigurationError("schema required must be a list of strings")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        raise ConfigurationError("schema additionalProperties must be a boolean")
    if "enum" in schema and not isinstance(schema["enum"], (list, tuple)):
        raise ConfigurationError("schema enum must be an array")
    for key in ("minimum", "maximum"):
        value = schema.get(key)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                  or not math.isfinite(value)):
            raise ConfigurationError("schema numeric bound must be finite")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        value = schema.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ConfigurationError("schema size bound must be nonnegative")


def _valid(value: Any, schema: Mapping[str, Any]) -> bool:
    kind = schema.get("type")
    matches = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }
    if kind and not matches[kind]():
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", ())):
            return False
        if schema.get("additionalProperties") is False and any(key not in props for key in value):
            return False
        if any(not _valid(item, props[key]) for key, item in value.items() if key in props):
            return False
    if isinstance(value, list):
        if "items" in schema and any(not _valid(item, schema["items"]) for item in value):
            return False
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            return False
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", float("-inf")) or value > schema.get("maximum", float("inf")):
            return False
    return True


def validate_structured(text: str, schema: Mapping[str, Any]) -> Any:
    """Parse and validate a response locally, without echoing provider content."""
    _check_schema(schema)
    cleaned = strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        raise InvalidResponse("provider returned malformed JSON") from None
    if not _valid(parsed, schema):
        raise InvalidResponse("provider response did not satisfy output schema")
    return parsed


def _error_for(exc: Exception) -> Exception:
    name = type(exc).__name__.lower()
    if "cancel" in name:
        return Cancelled("API completion cancelled")
    if "timeout" in name:
        return Timeout("API completion timed out")
    if "authentication" in name or "permission" in name or "unauthorized" in name:
        return AuthenticationError("API authentication failed")
    if "quota" in name or "budget" in name:
        return QuotaExceeded("API quota exceeded")
    if "ratelimit" in name or "rate_limit" in name:
        return RateLimitError("API rate limited")
    if "badrequest" in name or "invalidrequest" in name:
        return ConfigurationError("API rejected completion request")
    return BackendUnavailable(f"API completion unavailable ({type(exc).__name__})")


def _usage(response: Any) -> Usage | None:
    raw = getattr(response, "usage", None)
    if raw is None:
        return None
    def get(name: str) -> Any:
        return raw.get(name) if isinstance(raw, Mapping) else getattr(raw, name, None)
    return Usage(
        input_tokens=get("prompt_tokens"),
        output_tokens=get("completion_tokens"),
        total_tokens=get("total_tokens"),
    )


class LiteLLMBackend:
    """Preserve LiteLLM model and API-base behavior behind the shared contract."""

    capabilities = BackendCapabilities(usage_reporting=True)

    def __init__(
        self, model: str | None = None, *, api_base: str | None = None,
        completion: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model
        self.api_base = api_base
        self._completion = completion

    def preflight(self) -> BackendStatus:
        return BackendStatus(ready=True, backend="api", auth_class="api",
                             auth_source=self._auth_source(self.model))

    @staticmethod
    def _auth_source(model: str | None) -> AuthSource:
        if model and (model.startswith("openai/") or model.startswith("azure/")):
            return "openai_api"
        if model and model.startswith("anthropic/"):
            return "anthropic_api"
        return "other_api"

    def complete(self, request: CompletionRequest) -> CompletionResult:
        validate_capabilities(request, self.capabilities)
        model = request.model or self.model
        if not model:
            raise ConfigurationError("API model is required")
        if request.output_schema is not None:
            _check_schema(request.output_schema)
        messages = []
        if request.system_prompt is not None:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if request.timeout_seconds is not None:
            kwargs["timeout"] = request.timeout_seconds
        if request.output_schema is not None or request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if request.sampling is not None:
            if request.sampling.temperature is not None:
                kwargs["temperature"] = request.sampling.temperature
            if request.sampling.top_p is not None:
                kwargs["top_p"] = request.sampling.top_p
            if request.sampling.max_output_tokens is not None:
                kwargs["max_tokens"] = request.sampling.max_output_tokens
        if self.api_base:
            kwargs["base_url"] = self.api_base
        completion = self._completion
        if completion is None:
            import litellm
            completion = litellm.completion
        started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        try:
            response = completion(**kwargs)
        except Exception as exc:
            raise _error_for(exc) from None
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError):
            raise InvalidResponse("API response did not include completion content") from None
        if not isinstance(content, str) or not content:
            raise InvalidResponse("API response content was empty or non-text")
        structured = None
        if request.output_schema is not None:
            structured = validate_structured(content, request.output_schema)
        return CompletionResult(
            text=content, structured=structured, requested_backend="api", actual_backend="api",
            requested_model=model, actual_model=getattr(response, "model", None) or model,
            auth_class="api", auth_source=self._auth_source(model), usage=_usage(response),
            role=request.role, started_at=started_at, duration_seconds=time.monotonic() - start,
            prompt_contract_version=request.prompt_contract_version,
            schema_contract_version=request.schema_contract_version,
        )
