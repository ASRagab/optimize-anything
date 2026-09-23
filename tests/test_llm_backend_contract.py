"""Contract tests for provider-neutral completions."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from optimize_anything.llm_backends import (
    BackendCapabilities,
    BackendSpec,
    CompletionRequest,
    ConfigurationError,
    InvalidResponse,
    LiteLLMBackend,
    SamplingOptions,
    cache_fingerprint,
)


def test_contract_values_are_immutable() -> None:
    request = CompletionRequest(
        prompt="private prompt", role="judge", output_schema={"type": "object", "required": ["score"]}
    )
    spec = BackendSpec(backend="api", model="openai/test")
    capabilities = BackendCapabilities()
    with pytest.raises(FrozenInstanceError):
        request.prompt = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.output_schema["type"] = "string"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        spec.model = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        capabilities.structured_output = False  # type: ignore[misc]


def test_litellm_text_preserves_existing_kwargs_and_provenance() -> None:
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
            model="openai/actual",
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )

    backend = LiteLLMBackend(model="openai/test", api_base="https://api.example", completion=completion)
    result = backend.complete(
        CompletionRequest(prompt="hi", system_prompt="system", role="analysis", timeout_seconds=8,
                          sampling=SamplingOptions(temperature=0.3))
    )
    assert calls == [{"model": "openai/test", "messages": [
        {"role": "system", "content": "system"}, {"role": "user", "content": "hi"}],
        "timeout": 8, "temperature": 0.3, "base_url": "https://api.example"}]
    assert (result.text, result.auth_class, result.auth_source) == ("hello", "api", "openai_api")
    assert (result.requested_model, result.actual_model) == ("openai/test", "openai/actual")
    assert result.usage.total_tokens == 5
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"  # type: ignore[misc]


def test_litellm_schema_is_validated_locally() -> None:
    def completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"score": "bad"}'))])

    backend = LiteLLMBackend(model="openai/test", completion=completion)
    request = CompletionRequest(prompt="score", role="judge", output_schema={
        "type": "object", "required": ["score"],
        "properties": {"score": {"type": "number"}},
    })
    with pytest.raises(InvalidResponse):
        backend.complete(request)


def test_litellm_rejects_unsupported_schema_before_dispatch() -> None:
    calls = []
    backend = LiteLLMBackend(model="openai/test", completion=lambda **kw: calls.append(kw))
    with pytest.raises(ConfigurationError):
        backend.complete(CompletionRequest(prompt="x", role="judge", output_schema={"$ref": "remote"}))
    assert calls == []


def test_provider_error_does_not_expose_provider_message() -> None:
    class AuthenticationException(Exception):
        pass

    def completion(**_kwargs):
        raise AuthenticationException("sk-secret private prompt")

    backend = LiteLLMBackend(model="openai/test", completion=completion)
    from optimize_anything.llm_backends import AuthenticationError
    with pytest.raises(AuthenticationError) as caught:
        backend.complete(CompletionRequest(prompt="private prompt", role="judge"))
    assert "sk-secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_cache_fingerprint_uses_actual_route_without_exposing_input() -> None:
    from optimize_anything.llm_backends import CompletionResult

    request = CompletionRequest(prompt="private prompt", role="judge")
    subscription = CompletionResult("ok", None, "codex", "codex", None, "gpt", "subscription", "chatgpt")
    fallback = CompletionResult("ok", None, "codex", "api", None, "openai/gpt", "api", "openai_api")
    first = cache_fingerprint(request, subscription, input_identity="private prompt")
    second = cache_fingerprint(request, fallback, input_identity="private prompt")
    assert first != second
    assert "private prompt" not in first + second
