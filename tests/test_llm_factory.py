from __future__ import annotations

from optimize_anything.llm_backends.base import CompletionRequest, CompletionResult
from optimize_anything.llm_backends.factory import BackendLanguageModel, resolve_backend_spec


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
