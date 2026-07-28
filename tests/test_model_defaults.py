from __future__ import annotations

import pytest

from optimize_anything.model_defaults import (
    DEFAULT_EVALUATOR_MODEL,
    DEFAULT_PROPOSER_MODEL,
    resolve_proposer_model,
)


def test_default_models_match_current_capability_tiers() -> None:
    assert DEFAULT_PROPOSER_MODEL == "openai/gpt-5.6-sol"
    assert DEFAULT_EVALUATOR_MODEL == "openai/gpt-5.6-luna"


@pytest.mark.parametrize(
    ("explicit_model", "environ", "expected"),
    [
        (
            "anthropic/claude-sonnet-5",
            {"OPTIMIZE_ANYTHING_MODEL": "gemini/gemini-3.6-flash"},
            "anthropic/claude-sonnet-5",
        ),
        (
            None,
            {"OPTIMIZE_ANYTHING_MODEL": "gemini/gemini-3.6-flash"},
            "gemini/gemini-3.6-flash",
        ),
        (None, {}, "openai/gpt-5.6-sol"),
    ],
)
def test_resolve_proposer_model_precedence(
    explicit_model: str | None,
    environ: dict[str, str],
    expected: str,
) -> None:
    assert resolve_proposer_model(explicit_model, environ) == expected


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("openai/gpt-5.6-sol", "openai"),
        ("openai/gpt-5.6-luna", "openai"),
        ("anthropic/claude-sonnet-5", "anthropic"),
        ("gemini/gemini-3.6-flash", "gemini"),
    ],
)
def test_recommended_models_route_through_pinned_litellm(
    model: str,
    provider: str,
) -> None:
    import litellm

    assert litellm.get_llm_provider(model)[1] == provider
