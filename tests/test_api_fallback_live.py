"""Opt-in live gate for the paid same-vendor API fallback path."""

# Fallback trigger design (Verification Contract step 11).
#
# Chosen: option (a), a test-only fake subscription adapter. `create_backend`
# has no DI parameter, so the tests monkeypatch the module attributes it
# resolves lazily (`codex_backend.CodexSdkBackend`,
# `claude_backend.ClaudeCliBackend`) and `factory.LiteLLMBackend`, then build
# backends through `resolve_backend_spec` + `create_backend`. Real spec
# resolution, `FallbackBackend`, `RunCoordinator`, and `LiteLLMBackend` run,
# and `--no-api-fallback` hits its real branch (`_CoordinatedBackend`, which
# never builds an API backend); constructing `FallbackBackend` directly would
# skip both.
#
# Not (b): `CODEX_HOME` / `PATH` can make the real adapters fail, but that
# depends on the local install layout, and counting subscription attempts would
# still need a wrapper around the real adapter. The fake is deterministic and
# never touches subscription credentials. Adapter isolation is untouched; the
# only new environment variable is the opt-in gate.
#
# Invariants (checked offline with fakes before writing the tests):
# - The fake passes `preflight()` and raises `BackendUnavailable` only from
#   `complete()`: a preflight failure sends every role straight to API and
#   would hide the per-role circuit.
# - The fake accepts `model=` and exposes `capabilities`, which
#   `_CoordinatedBackend` reads unconditionally.
# - The API leg subclasses the real `LiteLLMBackend`, only records each call
#   (count, model, order relative to stderr), and calls `super().complete()`
#   without `completion=`, so calls are real, billed, and report real usage.
# - Each case passes an explicit `RunCoordinator.create()`, so circuits use the
#   production store and provenance events carry usage and the no-API proof.

from __future__ import annotations

import json
import os

import pytest

from optimize_anything.llm_backends import (
    BackendCapabilities,
    BackendStatus,
    BackendUnavailable,
    CompletionRequest,
    LiteLLMBackend,
    RunCoordinator,
    aggregate_provenance,
    factory,
)
from optimize_anything.model_defaults import DEFAULT_EVALUATOR_MODEL


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE") != "1",
        reason="set OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1 to bill the OpenAI and Anthropic API accounts",
    ),
]

# Fallback models have no project default (billing stays opt-in), so pin them.
_FALLBACK_MODELS = {"codex": DEFAULT_EVALUATOR_MODEL, "claude": "anthropic/claude-sonnet-5"}
_API_KEYS = {"codex": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}
_AUTH_SOURCES = {"codex": "openai_api", "claude": "anthropic_api"}
_ADAPTERS = {
    "codex": "optimize_anything.llm_backends.codex_backend.CodexSdkBackend",
    "claude": "optimize_anything.llm_backends.claude_backend.ClaudeCliBackend",
}
_WARNING = "API billing may apply"


def _require_key(provider):
    key = _API_KEYS[provider]
    if not os.environ.get(key):
        pytest.fail(f"export {key} before running the paid fallback gate")


def _force_subscription_failure(provider, monkeypatch, capsys):
    """Fail the subscription leg eligibly and record every real API dispatch."""
    timeline: list[tuple[str, str | None]] = []
    stderr_at_dispatch: list[str] = []

    class FailingSubscriptionBackend:
        capabilities = BackendCapabilities()

        def __init__(self, model=None):
            self.model = model

        def preflight(self):
            return BackendStatus(ready=True, backend=provider, auth_class="subscription")

        def complete(self, request):
            timeline.append(("subscription", request.role))
            raise BackendUnavailable("forced subscription failure")

    class CountingLiteLLMBackend(LiteLLMBackend):
        def complete(self, request):
            timeline.append(("api", request.model))
            stderr_at_dispatch.append(capsys.readouterr().err)
            return super().complete(request)

    monkeypatch.setattr(_ADAPTERS[provider], FailingSubscriptionBackend)
    monkeypatch.setattr(factory, "LiteLLMBackend", CountingLiteLLMBackend)
    return timeline, stderr_at_dispatch


def _spec(provider, *, no_api_fallback=False):
    # Both vendors' fallback flags are set; resolution must keep the same vendor.
    return factory.resolve_backend_spec(
        backend=provider,
        model=None,
        no_api_fallback=no_api_fallback,
        openai_api_fallback_model=_FALLBACK_MODELS["codex"],
        anthropic_api_fallback_model=_FALLBACK_MODELS["claude"],
    )


def _request(role):
    # Tiny prompt and no sampling cap: a tight cap can empty a reasoning reply.
    return CompletionRequest(prompt="Reply with the single word: ok", role=role, timeout_seconds=120)


def _report(capsys, provider, **observations):
    """Print content-free observations for the evidence log (visible with -s)."""
    with capsys.disabled():
        print(f"\n[paid-fallback] {provider} {json.dumps(observations, sort_keys=True)}")


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_eligible_failure_uses_same_vendor_api_with_sticky_role_circuit(
    provider, monkeypatch, capsys,
):
    _require_key(provider)
    model = _FALLBACK_MODELS[provider]
    timeline, stderr_at_dispatch = _force_subscription_failure(provider, monkeypatch, capsys)

    with RunCoordinator.create() as coordinator:
        judge = factory.create_backend(_spec(provider), role="judge", coordinator=coordinator)
        score = factory.create_backend(_spec(provider), role="score", coordinator=coordinator)
        assert judge.preflight().ready and score.preflight().ready
        results = [
            judge.complete(_request("judge")),
            judge.complete(_request("judge")),
            score.complete(_request("score")),
        ]
        events = coordinator.events()
    _report(
        capsys, provider, timeline=timeline,
        billing_warning_before_dispatch=[_WARNING in err for err in stderr_at_dispatch],
        provenance=aggregate_provenance(events), events=events,
    )

    # A repeated role skips the subscription; a new role still tries it first.
    assert timeline == [
        ("subscription", "judge"), ("api", model),
        ("api", model),
        ("subscription", "score"), ("api", model),
    ]
    assert f"judge switched from {provider} to API model {model}" in stderr_at_dispatch[0]
    assert _WARNING in stderr_at_dispatch[0]
    assert _WARNING not in stderr_at_dispatch[1]
    assert f"score switched from {provider} to API model {model}" in stderr_at_dispatch[2]
    for result in results:
        assert (result.requested_backend, result.actual_backend, result.auth_class) == (
            provider, "api", "api")
        assert result.auth_source == _AUTH_SOURCES[provider]
        assert result.fallback is not None
        assert (result.fallback.source_backend, result.fallback.reason) == (
            provider, "backend_unavailable")
        assert result.text and result.usage and result.usage.total_tokens
    assert [
        (e.get("role"), e.get("requested_backend"), e.get("actual_backend"),
         e.get("auth_class"), e.get("fallback_source"))
        for e in events
    ] == [(role, provider, "api", "api", provider) for role in ("judge", "judge", "score")]


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_no_api_fallback_raises_typed_error_without_api_calls(provider, monkeypatch, capsys):
    # The real key stays exported, so only the flag can explain zero API calls.
    _require_key(provider)
    timeline, _ = _force_subscription_failure(provider, monkeypatch, capsys)

    with RunCoordinator.create() as coordinator:
        backend = factory.create_backend(
            _spec(provider, no_api_fallback=True), role="judge", coordinator=coordinator,
        )
        assert backend.preflight().ready
        with pytest.raises(BackendUnavailable, match="forced subscription failure"):
            backend.complete(_request("judge"))
        events = coordinator.events()
    stderr = capsys.readouterr().err
    _report(capsys, provider, timeline=timeline, events=events)

    assert timeline == [("subscription", "judge")]
    assert events == []
    assert _WARNING not in stderr
