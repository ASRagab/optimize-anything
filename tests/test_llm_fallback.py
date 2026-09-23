"""Conservative subscription-to-API fallback behavior."""

from dataclasses import replace
from contextlib import contextmanager

import pytest

from optimize_anything.llm_backends import (
    AuthenticationError,
    BackendUnavailable,
    CompletionRequest,
    CompletionResult,
    FallbackBackend,
    InvalidResponse,
    RunCoordinator,
    Timeout,
)


class FakeBackend:
    def __init__(self, backend: str, result_or_error):
        self.backend = backend
        self.result_or_error = result_or_error
        self.calls = 0

    def preflight(self):
        return None

    def complete(self, request):
        self.calls += 1
        if isinstance(self.result_or_error, Exception):
            raise self.result_or_error
        return replace(self.result_or_error, requested_model=request.model)


def _result(backend, model, auth_class, auth_source):
    return CompletionResult(text="ok", structured=None, requested_backend=backend,
                            actual_backend=backend, requested_model=model, actual_model=model,
                            auth_class=auth_class, auth_source=auth_source)


def test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api(capsys):
    primary = FakeBackend("codex", BackendUnavailable("unavailable"))
    api = FakeBackend("api", _result("api", "openai/fallback", "api", "openai_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="codex",
                              fallback_model="openai/fallback", fallback_ready=lambda: True)
    result = wrapper.complete(CompletionRequest(prompt="secret", role="judge"))
    assert result.requested_backend == "codex"
    assert result.actual_backend == "api"
    assert result.fallback.reason == "backend_unavailable"
    assert "API billing may apply" in capsys.readouterr().err
    wrapper.complete(CompletionRequest(prompt="secret", role="judge"))
    assert primary.calls == 1
    wrapper.complete(CompletionRequest(prompt="secret", role="score"))
    assert primary.calls == 2


@pytest.mark.parametrize("error", [Timeout("late"), InvalidResponse("bad")])
def test_no_fallback_for_ambiguous_or_invalid_result(error):
    primary = FakeBackend("claude", error)
    api = FakeBackend("api", _result("api", "anthropic/fallback", "api", "anthropic_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="claude",
                              fallback_model="anthropic/fallback", fallback_ready=lambda: True)
    with pytest.raises(type(error)):
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert api.calls == 0


def test_no_fallback_to_other_vendor_or_without_readiness():
    primary = FakeBackend("codex", AuthenticationError("logged out"))
    api = FakeBackend("api", _result("api", "anthropic/fallback", "api", "anthropic_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="codex",
                              fallback_model="anthropic/fallback", fallback_ready=lambda: True)
    with pytest.raises(AuthenticationError):
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert api.calls == 0


def test_preflight_failure_routes_first_request_directly_to_api(capsys):
    primary = FakeBackend("claude", _result("claude", "sonnet", "subscription", "claude_subscription"))
    primary.preflight = lambda: (_ for _ in ()).throw(AuthenticationError("logged out"))
    api = FakeBackend("api", _result("api", "anthropic/fallback", "api", "anthropic_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="claude",
                              fallback_model="anthropic/fallback", fallback_ready=lambda: True)
    assert wrapper.preflight().ready
    wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert primary.calls == 0
    assert api.calls == 1
    assert "API billing may apply" in capsys.readouterr().err


def test_fallback_provenance_is_shared_with_child_coordinator():
    with RunCoordinator.create() as coordinator:
        child = RunCoordinator.attach(str(coordinator.path))
        primary = FakeBackend("codex", BackendUnavailable("unavailable"))
        api = FakeBackend("api", _result("api", "openai/fallback", "api", "openai_api"))
        wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="codex",
                                  fallback_model="openai/fallback", fallback_ready=lambda: True,
                                  coordinator=child)
        wrapper.complete(CompletionRequest(prompt="private prompt", role="judge"))
        event = coordinator.events()[0]
        assert (event["role"], event["requested_backend"], event["actual_backend"]) == (
            "judge", "codex", "api")
        assert "private prompt" not in str(event)


def test_queued_call_rechecks_circuit_after_acquiring_slot():
    class Coordinator:
        def circuit_reason(self, provider, role):
            return "rate_limit" if self.acquired else None

        @contextmanager
        def slot(self, provider, *, timeout_seconds):
            self.acquired = True
            yield

        def record_event(self, event):
            pass

        acquired = False

    primary = FakeBackend("codex", _result("codex", "gpt", "subscription", "chatgpt"))
    api = FakeBackend("api", _result("api", "openai/fallback", "api", "openai_api"))
    wrapper = FallbackBackend(
        primary=primary, fallback=api, source_backend="codex",
        fallback_model="openai/fallback", fallback_ready=lambda: True,
        coordinator=Coordinator(),
    )

    result = wrapper.complete(CompletionRequest(prompt="x", role="judge"))

    assert result.actual_backend == "api"
    assert primary.calls == 0
