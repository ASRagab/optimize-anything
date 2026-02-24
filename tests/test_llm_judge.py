"""Tests for LLM-as-judge evaluator factory."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from optimize_anything.llm_judge import (
    llm_judge_evaluator,
    _build_prompt,
    _compute_weighted_score,
    _parse_judge_response,
)


class TestLlmJudgeEvaluatorUnit:

    def _make_mock_completion(self, content: str) -> MagicMock:
        """Build a fake litellm.completion() return value."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = content
        return mock_response

    def test_happy_path_returns_score_and_subscores(self):
        dims = [
            {"name": "clarity", "weight": 0.6},
            {"name": "conciseness", "weight": 0.4},
        ]
        response_content = json.dumps({
            "score": 0.72,
            "reasoning": "Good structure",
            "clarity": 0.85,
            "conciseness": 0.52,
            "hard_constraints_satisfied": True,
        })
        evaluator = llm_judge_evaluator(
            "maximize clarity",
            model="openai/gpt-4o-mini",
            quality_dimensions=dims,
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, side_info = evaluator("This is a test artifact.")

        # Score is weighted: 0.85*0.6 + 0.52*0.4 = 0.51 + 0.208 = 0.718
        assert abs(score - 0.718) < 0.01
        assert side_info["reasoning"] == "Good structure"
        assert side_info["clarity"] == pytest.approx(0.85)
        assert side_info["conciseness"] == pytest.approx(0.52)

    def test_malformed_json_returns_zero_score(self):
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion("not json {")):
            score, side_info = evaluator("some artifact")

        assert score == 0.0
        assert "error" in side_info
        assert "malformed JSON" in side_info["error"]
        assert "raw_response" in side_info

    def test_markdown_code_fences_stripped_before_parsing(self):
        fenced = '```json\n{"score": 0.88, "reasoning": "Good"}\n```'
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(fenced)):
            score, side_info = evaluator("some artifact")

        assert score == 0.88
        assert side_info["reasoning"] == "Good"

    def test_code_fence_without_language_tag(self):
        """Code fences with no language tag (```) are also stripped."""
        fenced = '```\n{"score": 0.76, "reasoning": "OK"}\n```'
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(fenced)):
            score, side_info = evaluator("some artifact")

        assert score == 0.76
        assert side_info["reasoning"] == "OK"

    def test_code_fence_with_trailing_whitespace(self):
        """Code fences with trailing whitespace after closing ``` are stripped."""
        fenced = '```json\n{"score": 0.91, "reasoning": "Great"}\n```  \n'
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(fenced)):
            score, side_info = evaluator("some artifact")

        assert score == 0.91
        assert side_info["reasoning"] == "Great"

    def test_api_error_returns_zero_with_error_details(self):
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", side_effect=RuntimeError("API unavailable")):
            score, side_info = evaluator("some artifact")

        assert score == 0.0
        assert "error" in side_info
        assert "LLM call failed" in side_info["error"]
        assert "RuntimeError" in side_info["error"]

    def test_hard_constraint_violation_forces_zero(self):
        dims = [{"name": "clarity", "weight": 1.0}]
        constraints = ["must be under 200 words"]
        response_content = json.dumps({
            "score": 0.9,
            "reasoning": "Good but too long",
            "clarity": 0.9,
            "hard_constraints_satisfied": False,
        })
        evaluator = llm_judge_evaluator(
            "maximize clarity",
            model="openai/gpt-4o-mini",
            quality_dimensions=dims,
            hard_constraints=constraints,
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, side_info = evaluator("x " * 500)

        assert score == 0.0
        assert side_info.get("hard_constraint_violation") is True

    def test_no_quality_dimensions_uses_simple_prompt_and_score(self):
        response_content = json.dumps({"score": 0.65, "reasoning": "Adequate"})
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, side_info = evaluator("artifact text")

        assert score == pytest.approx(0.65)
        assert side_info["reasoning"] == "Adequate"

    def test_temperature_passed_through_to_litellm(self):
        response_content = json.dumps({"score": 0.5, "reasoning": "ok"})
        evaluator = llm_judge_evaluator(
            "maximize quality",
            model="openai/gpt-4o-mini",
            temperature=0.7,
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator("artifact")

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7

    def test_model_string_passed_through(self):
        response_content = json.dumps({"score": 0.5, "reasoning": "ok"})
        evaluator = llm_judge_evaluator(
            "maximize quality",
            model="anthropic/claude-haiku-4-5-20251001",
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator("artifact")

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-haiku-4-5-20251001"

    def test_api_base_passed_when_set(self):
        response_content = json.dumps({"score": 0.5, "reasoning": "ok"})
        evaluator = llm_judge_evaluator(
            "maximize quality",
            model="openai/gpt-4o-mini",
            api_base="https://openrouter.ai/api/v1",
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator("artifact")

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1"

    def test_api_base_not_passed_when_none(self):
        response_content = json.dumps({"score": 0.5, "reasoning": "ok"})
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator("artifact")

        call_kwargs = mock_call.call_args.kwargs
        assert "base_url" not in call_kwargs

    def test_score_clamped_to_zero_one(self):
        response_content = json.dumps({"score": 1.5, "reasoning": "exceeds bounds"})
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, _ = evaluator("artifact")
        assert score == pytest.approx(1.0)

    def test_empty_response_returns_zero(self):
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion("")):
            score, side_info = evaluator("artifact")
        assert score == 0.0
        assert "error" in side_info

    def test_non_object_json_returns_zero(self):
        response_content = json.dumps([1, 2, 3])
        evaluator = llm_judge_evaluator("maximize quality", model="openai/gpt-4o-mini")
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, side_info = evaluator("artifact")
        assert score == 0.0
        assert "non-object JSON" in side_info["error"]

    def test_quality_dimensions_appear_in_prompt(self):
        dims = [{"name": "originality", "weight": 1.0}]
        response_content = json.dumps({"score": 0.5, "reasoning": "ok", "originality": 0.5})
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator = llm_judge_evaluator(
                "test",
                model="openai/gpt-4o-mini",
                quality_dimensions=dims,
            )
            evaluator("candidate")
        prompt_sent = mock_call.call_args.kwargs["messages"][1]["content"]
        assert "originality" in prompt_sent

    def test_hard_constraints_appear_in_prompt(self):
        dims = [{"name": "clarity", "weight": 1.0}]
        response_content = json.dumps({"score": 0.5, "reasoning": "ok", "clarity": 0.5})
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator = llm_judge_evaluator(
                "test",
                model="openai/gpt-4o-mini",
                quality_dimensions=dims,
                hard_constraints=["Must not exceed 500 words"],
            )
            evaluator("candidate")
        prompt_sent = mock_call.call_args.kwargs["messages"][1]["content"]
        assert "500 words" in prompt_sent

    def test_invalid_objective_raises(self):
        with pytest.raises(ValueError, match="objective must be"):
            llm_judge_evaluator("", model="openai/gpt-4o-mini")

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError, match="model must be"):
            llm_judge_evaluator("maximize quality", model="")


class TestComputeWeightedScore:
    def test_basic_weighted_average(self):
        dims = [{"name": "a", "weight": 0.7}, {"name": "b", "weight": 0.3}]
        result = _compute_weighted_score({"a": 1.0, "b": 0.0}, dims)
        assert result == pytest.approx(0.7)

    def test_missing_dimension_treated_as_zero(self):
        dims = [{"name": "a", "weight": 0.5}, {"name": "b", "weight": 0.5}]
        result = _compute_weighted_score({"a": 1.0}, dims)
        assert result == pytest.approx(0.5)

    def test_non_numeric_dimension_treated_as_zero(self):
        dims = [{"name": "a", "weight": 1.0}]
        result = _compute_weighted_score({"a": "not-a-number"}, dims)
        assert result == pytest.approx(0.0)

    def test_dimension_values_clamped(self):
        dims = [{"name": "a", "weight": 1.0}]
        result = _compute_weighted_score({"a": 1.5}, dims)
        assert result == pytest.approx(1.0)


class TestBuildPrompt:
    def test_simple_prompt_used_without_dimensions(self):
        prompt = _build_prompt(
            candidate="hello",
            objective="maximize quality",
            quality_dimensions=[],
            hard_constraints=[],
        )
        assert "hello" in prompt
        assert "maximize quality" in prompt
        assert "Quality Dimensions" not in prompt

    def test_dimensions_prompt_used_with_dimensions(self):
        dims = [{"name": "clarity", "weight": 0.5}]
        prompt = _build_prompt(
            candidate="hello",
            objective="maximize quality",
            quality_dimensions=dims,
            hard_constraints=["must be concise"],
        )
        assert "Quality Dimensions" in prompt
        assert "clarity" in prompt
        assert "must be concise" in prompt
