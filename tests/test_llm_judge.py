"""Tests for LLM-as-judge evaluator factory."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from optimize_anything.llm_judge import (
    llm_judge_evaluator,
    analyze_for_dimensions,
    _build_prompt,
    _compute_weighted_score,
    _parse_judge_response,
    _parse_dimensions_response,
    _strip_code_fences,
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

    def test_hard_constraint_violation_simple_mode(self):
        """Hard constraint gate fires even without quality dimensions."""
        constraints = ["must be under 10 words"]
        response_content = json.dumps({
            "score": 0.9,
            "reasoning": "Violates length constraint",
            "hard_constraints_satisfied": False,
        })
        evaluator = llm_judge_evaluator(
            "maximize clarity",
            model="openai/gpt-4o-mini",
            hard_constraints=constraints,
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)):
            score, side_info = evaluator("very long text " * 50)

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


    def test_task_model_appears_in_prompt(self):
        response_content = json.dumps({"score": 0.6, "reasoning": "ok"})
        evaluator = llm_judge_evaluator(
            "maximize quality",
            model="openai/gpt-4o-mini",
            task_model="anthropic/claude-sonnet-4-6",
        )
        with patch("litellm.completion", return_value=self._make_mock_completion(response_content)) as mock_call:
            evaluator("artifact")

        prompt_sent = mock_call.call_args.kwargs["messages"][1]["content"]
        assert "Task Model Context" in prompt_sent
        assert "anthropic/claude-sonnet-4-6" in prompt_sent

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


class TestLlmJudgeIntegration:
    """Live integration tests — call real provider APIs.

    Each test is named to match the CI matrix's -k filter
    (e.g., -k "integration_openai") and skipped when the
    corresponding API key is absent.
    """

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required",
    )
    def test_integration_openai_judge(self):
        evaluator = llm_judge_evaluator(
            "Score this text on clarity and conciseness. Be strict.",
            model="openai/gpt-4o-mini",
        )
        score, side_info = evaluator("The quick brown fox jumps over the lazy dog.")
        assert 0.0 <= score <= 1.0
        assert "reasoning" in side_info or "error" not in side_info

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY required",
    )
    def test_integration_anthropic_judge(self):
        evaluator = llm_judge_evaluator(
            "Score this text on clarity and conciseness. Be strict.",
            model="anthropic/claude-haiku-4-5-20251001",
        )
        score, side_info = evaluator("The quick brown fox jumps over the lazy dog.")
        assert 0.0 <= score <= 1.0
        assert "reasoning" in side_info or "error" not in side_info

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY required",
    )
    def test_integration_google_judge(self):
        evaluator = llm_judge_evaluator(
            "Score this text on clarity and conciseness. Be strict.",
            model="gemini/gemini-2.0-flash",
        )
        score, side_info = evaluator("The quick brown fox jumps over the lazy dog.")
        assert 0.0 <= score <= 1.0
        assert "reasoning" in side_info or "error" not in side_info

    # --- Dimension-weighted scoring (production path) ---

    _DIMS = [
        {"name": "clarity", "weight": 0.5},
        {"name": "specificity", "weight": 0.3},
        {"name": "conciseness", "weight": 0.2},
    ]
    _DIM_ARTIFACT = (
        "To install, run `pip install my-package`. "
        "Then call `my_package.run(config_path='settings.toml')` "
        "to start the service on port 8080."
    )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required",
    )
    def test_integration_openai_dimension_scoring(self):
        evaluator = llm_judge_evaluator(
            "Score technical documentation quality.",
            model="openai/gpt-4o-mini",
            quality_dimensions=self._DIMS,
        )
        score, side_info = evaluator(self._DIM_ARTIFACT)
        assert 0.0 <= score <= 1.0
        # Dimension-weighted mode should return per-dimension scores
        assert any(k in side_info for k in ("clarity", "specificity", "conciseness"))

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY required",
    )
    def test_integration_anthropic_dimension_scoring(self):
        evaluator = llm_judge_evaluator(
            "Score technical documentation quality.",
            model="anthropic/claude-haiku-4-5-20251001",
            quality_dimensions=self._DIMS,
        )
        score, side_info = evaluator(self._DIM_ARTIFACT)
        assert 0.0 <= score <= 1.0
        assert any(k in side_info for k in ("clarity", "specificity", "conciseness"))

    # --- Hard constraint enforcement ---

    _CONSTRAINT_ARTIFACT_VIOLATING = "x " * 300  # ~300 words, violates "under 50 words"

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required",
    )
    def test_integration_openai_hard_constraint_violation(self):
        evaluator = llm_judge_evaluator(
            "Score text quality.",
            model="openai/gpt-4o-mini",
            quality_dimensions=[{"name": "clarity", "weight": 1.0}],
            hard_constraints=["Text must be under 50 words"],
        )
        score, side_info = evaluator(self._CONSTRAINT_ARTIFACT_VIOLATING)
        # Model should detect the constraint violation → score forced to 0.0
        assert score == 0.0 or side_info.get("hard_constraint_violation") is True

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("os").environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY required",
    )
    def test_integration_anthropic_hard_constraint_violation(self):
        evaluator = llm_judge_evaluator(
            "Score text quality.",
            model="anthropic/claude-haiku-4-5-20251001",
            quality_dimensions=[{"name": "clarity", "weight": 1.0}],
            hard_constraints=["Text must be under 50 words"],
        )
        score, side_info = evaluator(self._CONSTRAINT_ARTIFACT_VIOLATING)
        assert score == 0.0 or side_info.get("hard_constraint_violation") is True


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


class TestStripCodeFences:
    def test_strips_json_fence(self):
        assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_plain_fence(self):
        assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_fence_with_trailing_whitespace(self):
        assert _strip_code_fences('```json\n{"a": 1}\n```  \n') == '{"a": 1}'

    def test_no_fence_passthrough(self):
        assert _strip_code_fences('{"a": 1}') == '{"a": 1}'


class TestParseDimensionsResponse:
    def test_happy_path(self):
        response = json.dumps({
            "dimensions": [
                {"name": "clarity", "weight": 0.3, "score": 0.85, "description": "How clear"},
                {"name": "brevity", "weight": 0.7, "score": 0.6, "description": "How short"},
            ]
        })
        dims = _parse_dimensions_response(response)
        assert len(dims) == 2
        assert dims[0]["name"] == "clarity"
        assert dims[0]["weight"] == pytest.approx(0.3)
        assert dims[0]["score"] == pytest.approx(0.85)
        assert dims[1]["name"] == "brevity"

    def test_clamps_weight_and_score(self):
        response = json.dumps({
            "dimensions": [
                {"name": "a", "weight": 1.5, "score": -0.2, "description": "test"},
            ]
        })
        dims = _parse_dimensions_response(response)
        assert dims[0]["weight"] == 1.0
        assert dims[0]["score"] == 0.0

    def test_skips_invalid_entries(self):
        response = json.dumps({
            "dimensions": [
                {"name": "", "weight": 0.5, "score": 0.5, "description": "empty name"},
                "not a dict",
                {"name": "valid", "weight": 0.5, "score": 0.5, "description": "ok"},
            ]
        })
        dims = _parse_dimensions_response(response)
        assert len(dims) == 1
        assert dims[0]["name"] == "valid"

    def test_empty_response_raises(self):
        with pytest.raises(RuntimeError, match="empty response"):
            _parse_dimensions_response("")

    def test_malformed_json_raises(self):
        with pytest.raises(RuntimeError, match="malformed JSON"):
            _parse_dimensions_response("{not json")

    def test_missing_dimensions_key_raises(self):
        with pytest.raises(RuntimeError, match="dimensions"):
            _parse_dimensions_response('{"other": "stuff"}')

    def test_empty_dimensions_array_raises(self):
        with pytest.raises(RuntimeError, match="dimensions"):
            _parse_dimensions_response('{"dimensions": []}')

    def test_code_fences_stripped(self):
        response = '```json\n' + json.dumps({
            "dimensions": [
                {"name": "a", "weight": 0.5, "score": 0.5, "description": "test"},
            ]
        }) + '\n```'
        dims = _parse_dimensions_response(response)
        assert len(dims) == 1


class TestAnalyzeForDimensions:
    """Unit tests for analyze_for_dimensions — both LLM calls mocked."""

    def _make_mock_response(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.choices[0].message.content = content
        return mock

    def test_happy_path_returns_structured_result(self):
        score_response = json.dumps({"score": 0.82, "reasoning": "Good clarity, verbose"})
        dims_response = json.dumps({
            "dimensions": [
                {"name": "clarity", "weight": 0.4, "score": 0.9, "description": "How clear"},
                {"name": "conciseness", "weight": 0.3, "score": 0.6, "description": "How short"},
                {"name": "examples", "weight": 0.3, "score": 0.75, "description": "Example quality"},
            ]
        })

        call_count = 0
        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_mock_response(score_response)
            return self._make_mock_response(dims_response)

        with patch("litellm.completion", side_effect=mock_completion):
            result = analyze_for_dimensions(
                artifact="Some text artifact",
                objective="Maximize quality",
                model="openai/gpt-4o-mini",
            )

        assert result["current_score"] == pytest.approx(0.82)
        assert result["reasoning"] == "Good clarity, verbose"
        assert len(result["suggested_dimensions"]) == 3
        assert result["suggested_dimensions"][0]["name"] == "clarity"
        # intake_json should be valid JSON
        intake = json.loads(result["intake_json"])
        assert "quality_dimensions" in intake
        assert len(intake["quality_dimensions"]) == 3
        # Each intake dim has name and weight but NOT score (that's analysis-only)
        for d in intake["quality_dimensions"]:
            assert "name" in d
            assert "weight" in d
            assert "score" not in d
        assert "recommendation" in result
        assert "optimize-anything optimize" in result["recommendation"]

    def test_makes_exactly_two_llm_calls(self):
        score_response = json.dumps({"score": 0.5, "reasoning": "ok"})
        dims_response = json.dumps({
            "dimensions": [
                {"name": "a", "weight": 1.0, "score": 0.5, "description": "d"},
            ]
        })

        call_count = 0
        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_mock_response(score_response)
            return self._make_mock_response(dims_response)

        with patch("litellm.completion", side_effect=mock_completion):
            analyze_for_dimensions("text", "obj", "openai/gpt-4o-mini")

        assert call_count == 2

    def test_scoring_failure_raises_runtime_error(self):
        with patch("litellm.completion", side_effect=RuntimeError("API down")):
            with pytest.raises(RuntimeError, match="Scoring LLM call failed"):
                analyze_for_dimensions("text", "obj", "openai/gpt-4o-mini")

    def test_dimension_discovery_failure_raises(self):
        score_response = json.dumps({"score": 0.5, "reasoning": "ok"})
        call_count = 0
        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_mock_response(score_response)
            raise RuntimeError("API quota exceeded")

        with patch("litellm.completion", side_effect=mock_completion):
            with pytest.raises(RuntimeError, match="Dimension discovery LLM call failed"):
                analyze_for_dimensions("text", "obj", "openai/gpt-4o-mini")

    def test_invalid_objective_raises(self):
        with pytest.raises(ValueError, match="objective must be"):
            analyze_for_dimensions("text", "", "openai/gpt-4o-mini")

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError, match="model must be"):
            analyze_for_dimensions("text", "obj", "")

    def test_api_base_forwarded(self):
        score_response = json.dumps({"score": 0.5, "reasoning": "ok"})
        dims_response = json.dumps({
            "dimensions": [
                {"name": "a", "weight": 1.0, "score": 0.5, "description": "d"},
            ]
        })

        calls: list[dict] = []
        call_count = 0
        def mock_completion(**kwargs):
            nonlocal call_count
            calls.append(kwargs)
            call_count += 1
            if call_count == 1:
                return self._make_mock_response(score_response)
            return self._make_mock_response(dims_response)

        with patch("litellm.completion", side_effect=mock_completion):
            analyze_for_dimensions(
                "text", "obj", "openai/gpt-4o-mini",
                api_base="https://custom.api/v1",
            )

        assert all(c["base_url"] == "https://custom.api/v1" for c in calls)

    def test_score_parse_error_raises(self):
        """If the scoring call returns unparseable JSON, raise RuntimeError."""
        bad_response = self._make_mock_response("not json {")
        with patch("litellm.completion", return_value=bad_response):
            with pytest.raises(RuntimeError, match="Scoring failed"):
                analyze_for_dimensions("text", "obj", "openai/gpt-4o-mini")
