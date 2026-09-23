"""Resolve immutable backend specifications into completion adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .base import (
    BackendCapabilities,
    BackendName,
    BackendSpec,
    BackendStatus,
    CompletionBackend,
    CompletionRequest,
    CompletionResult,
    Role,
)
from .coordination import RunCoordinator
from .fallback import FallbackBackend
from .litellm_backend import LiteLLMBackend
from .provenance import completion_event


def resolve_backend_spec(
    *,
    backend: BackendName,
    model: str | None,
    api_base: str | None = None,
    no_api_fallback: bool = False,
    openai_api_fallback_model: str | None = None,
    anthropic_api_fallback_model: str | None = None,
    max_concurrency: int = 1,
) -> BackendSpec:
    """Resolve CLI-style provider-wide fallback options into a backend spec."""
    fallback_model = None
    if backend == "codex":
        fallback_model = openai_api_fallback_model
        if fallback_model is None and model and model.startswith("openai/"):
            fallback_model = model
    elif backend == "claude":
        fallback_model = anthropic_api_fallback_model
        if fallback_model is None and model and model.startswith("anthropic/"):
            fallback_model = model
    return BackendSpec(
        backend=backend,
        model=model,
        api_base=api_base,
        api_fallback=backend != "api" and not no_api_fallback and fallback_model is not None,
        api_fallback_model=fallback_model,
        max_concurrency=max_concurrency,
    )


def create_backend(
    spec: BackendSpec,
    *,
    role: Role,
    coordinator: RunCoordinator | None = None,
) -> CompletionBackend:
    """Create one role backend without probing or dispatching it."""
    if spec.backend == "api":
        return LiteLLMBackend(model=spec.model, api_base=spec.api_base)

    if coordinator is None:
        coordinator = RunCoordinator.from_environment()
    if spec.backend == "codex":
        from .codex_backend import CodexSdkBackend

        primary: CompletionBackend = CodexSdkBackend(model=spec.model)
    else:
        from .claude_backend import ClaudeCliBackend

        primary = ClaudeCliBackend(model=spec.model)

    if not spec.api_fallback:
        return _CoordinatedBackend(primary, spec.backend, coordinator)

    fallback = LiteLLMBackend(model=spec.api_fallback_model, api_base=spec.api_base)
    return FallbackBackend(
        primary=primary,
        fallback=fallback,
        source_backend=spec.backend,
        fallback_model=spec.api_fallback_model,
        coordinator=coordinator,
    )


@dataclass
class _CoordinatedBackend:
    """Apply provider slots even when API fallback is disabled."""

    backend: CompletionBackend
    provider: str
    coordinator: RunCoordinator | None
    capabilities: BackendCapabilities = field(init=False)

    def __post_init__(self) -> None:
        self.capabilities = self.backend.capabilities

    def preflight(self) -> BackendStatus:
        return self.backend.preflight()

    def complete(self, request: CompletionRequest) -> CompletionResult:
        if self.coordinator is None:
            return self.backend.complete(request)
        with self.coordinator.slot(self.provider, timeout_seconds=request.timeout_seconds):
            result = self.backend.complete(request)
        self.coordinator.record_event(completion_event(result))
        return result


class BackendLanguageModel:
    """Adapt a completion backend to GEPA's callable language-model protocol."""

    def __init__(
        self,
        backend: CompletionBackend,
        *,
        model: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.backend = backend
        self.model = model
        self.timeout_seconds = timeout_seconds

    def __call__(self, prompt: str | list[dict[str, Any]]) -> str:
        if not isinstance(prompt, str):
            prompt = json.dumps(prompt, ensure_ascii=False)
        return self.backend.complete(
            CompletionRequest(
                prompt=prompt,
                role="proposer",
                model=self.model,
                timeout_seconds=self.timeout_seconds,
            )
        ).text
