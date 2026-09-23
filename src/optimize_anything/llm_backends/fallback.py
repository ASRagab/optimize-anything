"""Conservative, visible subscription-to-API continuity policy."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .base import (
    AuthenticationError,
    BackendCapabilities,
    BackendStatus,
    BackendUnavailable,
    CompletionBackend,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    FallbackRecord,
    QuotaExceeded,
    RateLimitError,
    Timeout,
)
from .coordination import RunCoordinator
from .provenance import completion_event

_ELIGIBLE = (BackendUnavailable, AuthenticationError, RateLimitError, QuotaExceeded)


def fallback_ready(source_backend: str, model: str | None) -> bool:
    """Check only canonical key presence, never read or retain its value."""
    if source_backend == "codex":
        return bool(model and model.startswith("openai/") and os.environ.get("OPENAI_API_KEY"))
    if source_backend == "claude":
        return bool(model and model.startswith("anthropic/") and os.environ.get("ANTHROPIC_API_KEY"))
    return False


_canonical_fallback_ready = fallback_ready


class FallbackBackend:
    """Wrap a subscription adapter with per-role sticky same-vendor fallback."""

    def __init__(
        self, *, primary: CompletionBackend, fallback: CompletionBackend,
        source_backend: str, fallback_model: str | None,
        fallback_ready: Callable[[], bool] | None = None,
        coordinator: RunCoordinator | None = None,
    ) -> None:
        if source_backend not in ("codex", "claude"):
            raise ConfigurationError("fallback source must be a subscription backend")
        self.primary = primary
        self.fallback = fallback
        self.source_backend = source_backend
        self.fallback_model = fallback_model
        self._ready = fallback_ready or (lambda: _canonical_fallback_ready(source_backend, fallback_model))
        self.coordinator = coordinator
        self.capabilities = getattr(primary, "capabilities", BackendCapabilities())
        self._circuits: dict[str, str] = {}
        self._lock = threading.Lock()
        self._preflight_reason: str | None = None

    def _can_fallback(self) -> bool:
        return self._same_vendor() and self._ready()

    def _same_vendor(self) -> bool:
        prefix = "openai/" if self.source_backend == "codex" else "anthropic/"
        return bool(self.fallback_model and self.fallback_model.startswith(prefix))

    def _reason(self, role: str) -> str | None:
        if self.coordinator:
            return self.coordinator.circuit_reason(self.source_backend, role)
        with self._lock:
            return self._circuits.get(role)

    def _open(self, role: str, reason: str) -> bool:
        if self.coordinator:
            return self.coordinator.open_circuit(self.source_backend, role, reason)
        with self._lock:
            if role in self._circuits:
                return False
            self._circuits[role] = reason
            return True

    def preflight(self) -> BackendStatus:
        try:
            return self.primary.preflight()
        except _ELIGIBLE as exc:
            if not self._can_fallback():
                raise
            self._preflight_reason = exc.category
            # Role-specific circuits are opened when each role is first used.
            return BackendStatus(ready=True, backend=self.source_backend, auth_class="subscription",
                                 detail=f"API fallback available after {exc.category}")

    def complete(self, request: CompletionRequest) -> CompletionResult:
        reason = self._reason(request.role)
        if reason is not None:
            return self._complete_fallback(request, reason)
        if self._preflight_reason is not None:
            reason = self._preflight_reason
            if self._open(request.role, reason):
                self._warn(request.role, reason)
            return self._complete_fallback(request, reason)
        try:
            if self.coordinator:
                started = time.monotonic()
                with self.coordinator.slot(self.source_backend, timeout_seconds=request.timeout_seconds):
                    reason = self._reason(request.role)
                    if reason is not None:
                        return self._complete_fallback(request, reason)
                    primary_request = request
                    if request.timeout_seconds is not None:
                        remaining = request.timeout_seconds - (time.monotonic() - started)
                        if remaining <= 0:
                            raise Timeout("subscription completion timed out waiting for a provider slot")
                        primary_request = replace(request, timeout_seconds=remaining)
                    result = self.primary.complete(primary_request)
            else:
                result = self.primary.complete(request)
            if result.actual_backend != self.source_backend:
                raise ConfigurationError("subscription adapter reported another backend")
            result = replace(
                result, role=request.role,
                prompt_contract_version=request.prompt_contract_version,
                schema_contract_version=request.schema_contract_version,
            )
            if self.coordinator:
                self.coordinator.record_event(completion_event(result))
            return result
        except _ELIGIBLE as exc:
            if not self._can_fallback():
                raise
            opened = self._open(request.role, exc.category)
            if opened:
                self._warn(request.role, exc.category)
            return self._complete_fallback(request, exc.category)

    def _warn(self, role: str, reason: str) -> None:
        print(
            f"Warning: {role} switched from {self.source_backend} to API model "
            f"{self.fallback_model} after {reason}; API billing may apply.",
            file=sys.stderr,
        )

    def _complete_fallback(self, request: CompletionRequest, reason: str) -> CompletionResult:
        if not self._can_fallback():
            raise BackendUnavailable("API fallback is not ready")
        api_request = replace(request, model=self.fallback_model)
        result = self.fallback.complete(api_request)
        if result.actual_backend != "api":
            raise ConfigurationError("fallback adapter did not use API")
        resolved = replace(
            result, requested_backend=self.source_backend,
            requested_model=request.model,
            role=request.role,
            prompt_contract_version=request.prompt_contract_version,
            schema_contract_version=request.schema_contract_version,
            fallback=FallbackRecord(
                source_backend=self.source_backend, reason=reason,
                switched_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
        if self.coordinator:
            self.coordinator.record_event(completion_event(resolved))
        return resolved
