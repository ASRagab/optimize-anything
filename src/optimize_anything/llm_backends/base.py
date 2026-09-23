"""Provider-neutral, immutable single-completion contract."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol

Role = Literal["proposer", "judge", "analysis", "score", "validation"]
BackendName = Literal["api", "codex", "claude"]
AuthClass = Literal["api", "subscription"]
AuthSource = Literal["chatgpt", "claude_subscription", "openai_api", "anthropic_api", "other_api"]
JsonValue = Any


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Return plain JSON-compatible containers from an immutable contract value."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class SamplingOptions:
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None and (
            not math.isfinite(self.temperature) or self.temperature < 0
        ):
            raise ConfigurationError("temperature must be finite and nonnegative")
        if self.top_p is not None and (
            not math.isfinite(self.top_p) or not 0 < self.top_p <= 1
        ):
            raise ConfigurationError("top_p must be between zero and one")
        if self.max_output_tokens is not None and (
            not isinstance(self.max_output_tokens, int) or self.max_output_tokens < 1
        ):
            raise ConfigurationError("max_output_tokens must be positive")


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    role: Role
    model: str | None = None
    output_schema: Mapping[str, object] | None = None
    json_mode: bool = False
    timeout_seconds: float | None = None
    sampling: SamplingOptions | None = None
    system_prompt: str | None = None
    prompt_contract_version: str = "1"
    schema_contract_version: str = "1"

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt:
            raise ConfigurationError("prompt must be a non-empty string")
        if self.role not in ("proposer", "judge", "analysis", "score", "validation"):
            raise ConfigurationError("unsupported completion role")
        if self.model is not None and (not isinstance(self.model, str) or not self.model.strip()):
            raise ConfigurationError("model must be a non-empty string")
        if self.timeout_seconds is not None and (
            not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
        ):
            raise ConfigurationError("timeout must be finite and positive")
        if self.output_schema is not None:
            if not isinstance(self.output_schema, Mapping):
                raise ConfigurationError("output schema must be a mapping")
            object.__setattr__(self, "output_schema", _freeze(self.output_schema))
        if not isinstance(self.json_mode, bool):
            raise ConfigurationError("json_mode must be a boolean")
        if self.sampling is not None and not isinstance(self.sampling, SamplingOptions):
            raise ConfigurationError("sampling must be SamplingOptions")


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True)
class FallbackRecord:
    source_backend: str
    reason: str
    switched_at: str


@dataclass(frozen=True)
class CompletionResult:
    text: str
    structured: JsonValue | None
    requested_backend: str
    actual_backend: str
    requested_model: str | None
    actual_model: str | None
    auth_class: AuthClass
    auth_source: AuthSource
    usage: Usage | None = None
    fallback: FallbackRecord | None = None
    role: Role | None = None
    started_at: str | None = None
    duration_seconds: float | None = None
    retry_count: int = 0
    prompt_contract_version: str = "1"
    schema_contract_version: str = "1"

    def __post_init__(self) -> None:
        if self.structured is not None:
            object.__setattr__(self, "structured", _freeze(self.structured))


@dataclass(frozen=True)
class BackendSpec:
    backend: BackendName = "api"
    model: str | None = None
    api_base: str | None = None
    api_fallback: bool = False
    api_fallback_model: str | None = None
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if self.backend not in ("api", "codex", "claude"):
            raise ConfigurationError("unsupported backend")
        if self.model is not None and (not isinstance(self.model, str) or not self.model.strip()):
            raise ConfigurationError("model must be a non-empty string")
        if self.max_concurrency < 1:
            raise ConfigurationError("max_concurrency must be positive")


@dataclass(frozen=True)
class BackendCapabilities:
    structured_output: bool = True
    model_override: bool = True
    sampling: bool = True
    cancellation: bool = False
    usage_reporting: bool = False


@dataclass(frozen=True)
class BackendStatus:
    ready: bool
    backend: str
    auth_class: AuthClass
    auth_source: AuthSource | None = None
    detail: str | None = None


class BackendError(Exception):
    """A normalized backend failure; never attach provider exception payloads."""

    category = "backend_error"


class BackendUnavailable(BackendError):
    category = "backend_unavailable"


class AuthenticationError(BackendError):
    category = "authentication"


class RateLimitError(BackendError):
    category = "rate_limit"


class QuotaExceeded(BackendError):
    category = "quota_exceeded"


class Timeout(BackendError):
    category = "timeout"


class Cancelled(BackendError):
    category = "cancelled"


class InvalidResponse(BackendError):
    category = "invalid_response"


class ConfigurationError(BackendError):
    category = "configuration"


class CompletionBackend(Protocol):
    capabilities: BackendCapabilities

    def preflight(self) -> BackendStatus: ...

    def complete(self, request: CompletionRequest) -> CompletionResult: ...


def validate_capabilities(request: CompletionRequest, capabilities: BackendCapabilities) -> None:
    """Reject unsupported controls before any provider dispatch."""
    if request.output_schema is not None and not capabilities.structured_output:
        raise ConfigurationError("backend does not support structured output")
    if request.model is not None and not capabilities.model_override:
        raise ConfigurationError("backend does not support model override")
    if request.sampling is not None and not capabilities.sampling:
        raise ConfigurationError("backend does not support sampling controls")
