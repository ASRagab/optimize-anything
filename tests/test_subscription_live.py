"""Opt-in live gates for locally authenticated subscription backends."""

from __future__ import annotations

import os
import io
import json
import sys
from pathlib import Path

import pytest

from optimize_anything.llm_backends.base import CompletionRequest, thaw_json


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE") != "1",
        reason="set OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1 to use local subscription quota",
    ),
]

_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_saved_subscription_structured_completion(provider, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "deliberately-invalid-live-gate")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "deliberately-invalid-live-gate")
    if provider == "codex":
        from optimize_anything.llm_backends.codex_backend import CodexSdkBackend

        backend = CodexSdkBackend()
        expected_source = "chatgpt"
    else:
        from optimize_anything.llm_backends.claude_backend import ClaudeCliBackend

        backend = ClaudeCliBackend()
        expected_source = "claude_subscription"

    status = backend.preflight()
    result = backend.complete(
        CompletionRequest(
            prompt="Return JSON with ok set to true.",
            role="validation",
            output_schema=_SCHEMA,
            timeout_seconds=120,
        )
    )

    assert status.auth_class == "subscription"
    assert result.auth_class == "subscription"
    assert result.auth_source == expected_source
    assert thaw_json(result.structured) == {"ok": True}


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_saved_subscription_seedless_budget_one(provider, monkeypatch, capsys):
    from optimize_anything.cli import main

    monkeypatch.setenv("OPENAI_API_KEY", "deliberately-invalid-live-gate")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "deliberately-invalid-live-gate")
    evaluator = Path(__file__).parents[1] / "examples/evaluators/echo_score.sh"

    return_code = main([
        "optimize",
        "--no-seed",
        "--objective",
        "Write a concise friendly greeting.",
        "--budget",
        "1",
        "--proposer-backend",
        provider,
        "--no-api-fallback",
        "--evaluator-command",
        "bash",
        str(evaluator),
    ])

    captured = capsys.readouterr()
    assert return_code == 0
    assert f'"actual_backend": "{provider}"' in captured.out
    assert '"auth_class": "subscription"' in captured.out


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_generated_evaluator_uses_saved_subscription(provider, monkeypatch):
    from optimize_anything.evaluator_generator import generate_evaluator_script

    monkeypatch.setenv("OPENAI_API_KEY", "deliberately-invalid-live-gate")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "deliberately-invalid-live-gate")
    script = generate_evaluator_script(
        seed="hello",
        objective="Score clarity.",
        evaluator_type="judge",
        backend=provider,
        model=None,
        api_fallback=False,
    )
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"candidate":"Hello there."}\n'))
    monkeypatch.setattr(sys, "stdout", output)
    namespace = {"__name__": "generated_evaluator"}
    exec(compile(script, "<generated-evaluator>", "exec"), namespace)

    assert namespace["main"]() == 0
    result = json.loads(output.getvalue())
    assert 0.0 <= result["score"] <= 1.0
    assert result["llm_provenance"]["actual_backend"] == provider
    assert result["llm_provenance"]["auth_class"] == "subscription"
