"""Conservative subscription-to-API fallback behavior."""

from dataclasses import replace
from contextlib import contextmanager

import pytest

from optimize_anything.llm_backends import (
    AuthenticationError,
    BackendUnavailable,
    Cancelled,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    FallbackBackend,
    InvalidResponse,
    QuotaExceeded,
    RateLimitError,
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


@pytest.mark.parametrize("error", [Cancelled("user cancelled"), ConfigurationError("bad config")])
def test_cancelled_and_configuration_error_never_fall_back(error, capsys):
    """R12: Cancelled and ConfigurationError must never fall back — a user cancel or a
    misconfiguration must not silently turn into a billed API call."""
    primary = FakeBackend("claude", error)
    api = FakeBackend("api", _result("api", "anthropic/fallback", "api", "anthropic_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="claude",
                              fallback_model="anthropic/fallback", fallback_ready=lambda: True)
    with pytest.raises(type(error)) as excinfo:
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert excinfo.value is error
    assert primary.calls == 1
    assert api.calls == 0
    assert "API billing may apply" not in capsys.readouterr().err


@pytest.mark.parametrize("error", [RateLimitError("rate limited"), QuotaExceeded("quota exceeded")])
def test_rate_limit_and_quota_exceeded_are_eligible_for_fallback(error, capsys):
    """R12: RateLimitError and QuotaExceeded are eligible failures — a busy or exhausted
    subscription must still complete the run through the approved API fallback rather
    than failing the run outright."""
    primary = FakeBackend("codex", error)
    api = FakeBackend("api", _result("api", "openai/fallback", "api", "openai_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="codex",
                              fallback_model="openai/fallback", fallback_ready=lambda: True)
    result = wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert api.calls == 1
    assert result.actual_backend == "api"
    assert result.fallback.reason == error.category
    assert "API billing may apply" in capsys.readouterr().err


class _WarnOrderCheckingBackend:
    """Fake API backend that asserts the billing warning is ALREADY on stderr the moment
    it is dispatched, proving `_warn` runs strictly before the fallback backend is called."""

    def __init__(self, capsys, result):
        self._capsys = capsys
        self._result = result
        self.calls = 0

    def preflight(self):
        return None

    def complete(self, request):
        self.calls += 1
        captured_err = self._capsys.readouterr().err
        assert "API billing may apply" in captured_err, (
            "the billing warning must be printed before the fallback backend is dispatched"
        )
        return replace(self._result, requested_model=request.model)


def test_warning_is_printed_before_fallback_backend_is_dispatched(capsys):
    """R12: the API-billing warning must land on stderr strictly before the fallback
    backend is dispatched, not merely before complete() returns — a caller watching
    stderr to gate billed calls must never observe the call before the warning."""
    primary = FakeBackend("codex", BackendUnavailable("unavailable"))
    api = _WarnOrderCheckingBackend(capsys, _result("api", "openai/fallback", "api", "openai_api"))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend="codex",
                              fallback_model="openai/fallback", fallback_ready=lambda: True)
    result = wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert result.actual_backend == "api"
    assert api.calls == 1


_FAKE_CREDENTIAL = "fake-credential-for-tests-not-a-real-key"
_VENDOR_READINESS_CASES = [
    pytest.param("codex", "openai/gpt-fallback", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                 "openai_api", id="codex-openai"),
    pytest.param("claude", "anthropic/claude-fallback", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                 "anthropic_api", id="claude-anthropic"),
]


@pytest.mark.parametrize(
    "source_backend,fallback_model,own_key,other_key,auth_source", _VENDOR_READINESS_CASES
)
def test_real_fallback_ready_allows_fallback_when_matching_vendor_key_present(
    source_backend, fallback_model, own_key, other_key, auth_source, monkeypatch, capsys,
):
    """R12: with no injected fallback_ready stub, the REAL readiness check (fallback.py:33)
    must permit fallback once the matching vendor's API key is present — that presence
    check is the readiness gate behind `_can_fallback`, and no test exercised the real
    function before this one."""
    monkeypatch.delenv(other_key, raising=False)
    monkeypatch.setenv(own_key, _FAKE_CREDENTIAL)
    primary = FakeBackend(source_backend, BackendUnavailable("unavailable"))
    api = FakeBackend("api", _result("api", fallback_model, "api", auth_source))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend=source_backend,
                              fallback_model=fallback_model)
    result = wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert result.actual_backend == "api"
    assert result.fallback.reason == "backend_unavailable"
    assert api.calls == 1
    assert "API billing may apply" in capsys.readouterr().err


@pytest.mark.parametrize(
    "source_backend,fallback_model,own_key,other_key,auth_source", _VENDOR_READINESS_CASES
)
def test_real_fallback_ready_blocks_fallback_when_vendor_key_absent(
    source_backend, fallback_model, own_key, other_key, auth_source, monkeypatch, capsys,
):
    """R12: with no injected fallback_ready stub, a missing vendor key must block fallback
    for real — the primary's own error must propagate unchanged and the fallback backend
    must never be dispatched, so a logged-out user is not silently billed."""
    monkeypatch.delenv(own_key, raising=False)
    monkeypatch.delenv(other_key, raising=False)
    err = BackendUnavailable("unavailable")
    primary = FakeBackend(source_backend, err)
    api = FakeBackend("api", _result("api", fallback_model, "api", auth_source))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend=source_backend,
                              fallback_model=fallback_model)
    with pytest.raises(BackendUnavailable) as excinfo:
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert excinfo.value is err
    assert api.calls == 0
    assert "API billing may apply" not in capsys.readouterr().err
    with pytest.raises(BackendUnavailable):
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert primary.calls == 2
    assert api.calls == 0


@pytest.mark.parametrize(
    "source_backend,fallback_model,own_key,other_key,auth_source", _VENDOR_READINESS_CASES
)
def test_real_fallback_ready_blocks_fallback_when_only_other_vendor_key_present(
    source_backend, fallback_model, own_key, other_key, auth_source, monkeypatch, capsys,
):
    """R12: with no injected fallback_ready stub, the real readiness gate must key off
    the SOURCE backend's own vendor — fallback_ready() only ever reads the env var
    matching `source_backend`, so the other vendor's API key existing in the
    environment must not unlock this vendor's fallback."""
    monkeypatch.delenv(own_key, raising=False)
    monkeypatch.setenv(other_key, _FAKE_CREDENTIAL)
    err = BackendUnavailable("unavailable")
    primary = FakeBackend(source_backend, err)
    api = FakeBackend("api", _result("api", fallback_model, "api", auth_source))
    wrapper = FallbackBackend(primary=primary, fallback=api, source_backend=source_backend,
                              fallback_model=fallback_model)
    with pytest.raises(BackendUnavailable) as excinfo:
        wrapper.complete(CompletionRequest(prompt="x", role="judge"))
    assert excinfo.value is err
    assert api.calls == 0
    assert "API billing may apply" not in capsys.readouterr().err
