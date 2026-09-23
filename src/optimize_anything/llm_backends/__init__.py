"""Completion backends and run-scoped execution primitives."""

from .base import (
    AuthenticationError,
    BackendCapabilities,
    BackendError,
    BackendSpec,
    BackendStatus,
    BackendUnavailable,
    Cancelled,
    CompletionBackend,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    FallbackRecord,
    InvalidResponse,
    QuotaExceeded,
    RateLimitError,
    SamplingOptions,
    Timeout,
    Usage,
    thaw_json,
    validate_capabilities,
)
from .coordination import RunCoordinator
from .fallback import FallbackBackend, fallback_ready
from .factory import BackendLanguageModel, create_backend, resolve_backend_spec
from .litellm_backend import LiteLLMBackend, validate_structured
from .provenance import aggregate_provenance, cache_fingerprint, completion_event

__all__ = [
    "AuthenticationError", "BackendCapabilities", "BackendError", "BackendSpec", "BackendStatus",
    "BackendUnavailable", "Cancelled", "CompletionBackend", "CompletionRequest", "CompletionResult",
    "ConfigurationError", "FallbackBackend", "FallbackRecord", "InvalidResponse", "LiteLLMBackend",
    "QuotaExceeded", "RateLimitError", "RunCoordinator", "SamplingOptions", "Timeout", "Usage",
    "aggregate_provenance", "cache_fingerprint", "completion_event", "fallback_ready", "thaw_json",
    "validate_capabilities", "validate_structured", "BackendLanguageModel", "create_backend",
    "resolve_backend_spec",
]
