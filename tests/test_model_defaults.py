from __future__ import annotations

from pathlib import Path

import pytest

from optimize_anything.model_defaults import (
    DEFAULT_EVALUATOR_MODEL,
    DEFAULT_PROPOSER_MODEL,
    resolve_proposer_model,
)


ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_MODEL_REFERENCE_FILES = (
    "src/optimize_anything/cli.py",
    "src/optimize_anything/evaluator_generator.py",
    "scripts/live_integration.py",
    "scripts/plugin_eval.sh",
    "scripts/plugin_regression.py",
    "skills/evaluator-patterns/SKILL.md",
    "skills/generate-evaluator/SKILL.md",
)
STALE_CANONICAL_MODEL_STRINGS = (
    "openai/gpt-4o-mini",
    "openai/gpt-5.1",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-sonnet-4-5-20250929",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.0-flash",
    "gemini/gemini-2.0-flash",
)


@pytest.mark.parametrize("relative_path", EXECUTABLE_MODEL_REFERENCE_FILES)
def test_executable_surfaces_do_not_recommend_stale_models(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    assert not [
        model for model in STALE_CANONICAL_MODEL_STRINGS if model in text
    ]


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
