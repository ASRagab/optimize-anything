from __future__ import annotations

from types import SimpleNamespace

from optimize_anything.llm_backends.base import CompletionRequest, CompletionResult
from optimize_anything.llm_backends.coordination import RunCoordinator
from optimize_anything.llm_backends.factory import BackendLanguageModel, create_backend, resolve_backend_spec


class _Backend:
    def __init__(self) -> None:
        self.request: CompletionRequest | None = None

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.request = request
        return CompletionResult(
            text="improved",
            structured=None,
            requested_backend="codex",
            actual_backend="codex",
            requested_model=request.model,
            actual_model=request.model,
            auth_class="subscription",
            auth_source="chatgpt",
            role=request.role,
        )


def test_resolve_subscription_fallback_is_same_vendor_and_explicit():
    spec = resolve_backend_spec(
        backend="codex",
        model=None,
        openai_api_fallback_model="openai/gpt-5.6-sol",
    )

    assert spec.api_fallback is True
    assert spec.api_fallback_model == "openai/gpt-5.6-sol"


def test_no_api_fallback_overrides_resolvable_model():
    spec = resolve_backend_spec(
        backend="claude",
        model="anthropic/claude-sonnet-5",
        no_api_fallback=True,
    )

    assert spec.api_fallback is False


def test_backend_language_model_adapts_gepa_prompt_lists():
    backend = _Backend()
    language_model = BackendLanguageModel(backend, model="gpt-5.6-sol")

    assert language_model([{"role": "user", "content": "improve"}]) == "improved"
    assert backend.request is not None
    assert backend.request.role == "proposer"
    assert backend.request.model == "gpt-5.6-sol"
    assert '\"content\": \"improve\"' in backend.request.prompt


def test_api_language_model_preserves_gepa_chat_messages():
    """R4/R5: API proposal chat roles and content survive the callable adapter."""
    backend = _Backend()
    messages = [
        {"role": "system", "content": "Follow the rubric"},
        {"role": "user", "content": "Improve this"},
    ]

    BackendLanguageModel(backend, model="openai/test")(messages)

    assert backend.request is not None
    assert backend.request.messages == tuple(messages)


def test_api_role_records_provenance_in_shared_run(tmp_path):
    """R4: API completions contribute the same safe event fields as subscriptions."""
    coordinator = RunCoordinator.create({"codex": 1, "claude": 1})
    try:
        backend = create_backend(
            resolve_backend_spec(backend="api", model="openai/test"),
            role="proposer", coordinator=coordinator,
        )
        backend.backend._completion = lambda **kwargs: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="improved"))],
            model=kwargs["model"], usage=None,
        )
        assert BackendLanguageModel(backend, model="openai/test")("improve") == "improved"
        event, = coordinator.events()
        assert event["role"] == "proposer"
        assert event["actual_backend"] == "api"
        assert event["auth_class"] == "api"
        assert event["call_id"]
    finally:
        coordinator.close()
