"""Tests for MCP server tools."""

from __future__ import annotations

import asyncio
import json

import pytest

from optimize_anything.server import mcp


class TestServerTools:
    def test_server_has_tools(self):
        """Verify all tools are registered."""
        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "optimize" in tool_names
        assert "explain" in tool_names
        assert "recommend_budget" in tool_names
        assert "generate_evaluator" in tool_names
        assert "evaluator_intake" in tool_names

    @pytest.mark.asyncio
    async def test_explain_tool(self):
        """Test the explain tool returns plan text."""
        from optimize_anything.server import explain

        result = await explain(seed="Hello world", objective="Make it formal")
        assert "Optimization Plan" in result
        assert "11" in result  # seed length

    @pytest.mark.asyncio
    async def test_recommend_budget_short(self):
        from optimize_anything.server import recommend_budget

        result = await recommend_budget(seed="Hi")
        data = json.loads(result)
        assert data["recommended_budget"] == 50
        assert data["seed_length"] == 2

    @pytest.mark.asyncio
    async def test_recommend_budget_medium(self):
        from optimize_anything.server import recommend_budget

        result = await recommend_budget(seed="x" * 300)
        data = json.loads(result)
        assert data["recommended_budget"] == 100

    @pytest.mark.asyncio
    async def test_recommend_budget_long(self):
        from optimize_anything.server import recommend_budget

        result = await recommend_budget(seed="x" * 1000)
        data = json.loads(result)
        assert data["recommended_budget"] == 200

    @pytest.mark.asyncio
    async def test_recommend_budget_very_long(self):
        from optimize_anything.server import recommend_budget

        result = await recommend_budget(seed="x" * 3000)
        data = json.loads(result)
        assert data["recommended_budget"] == 300

    @pytest.mark.asyncio
    async def test_optimize_requires_evaluator(self):
        from optimize_anything.server import optimize

        result = await optimize(seed="test")
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_optimize_rejects_both_evaluator_inputs(self):
        from optimize_anything.server import optimize

        result = await optimize(
            seed="test",
            evaluator_command=["bash", "eval.sh"],
            evaluator_url="http://localhost:8000/eval",
        )
        data = json.loads(result)
        assert "error" in data
        assert "not both" in data["error"]

    @pytest.mark.asyncio
    async def test_generate_evaluator_tool(self):
        from optimize_anything.server import generate_evaluator

        result = await generate_evaluator(
            seed="hello", objective="make it better"
        )
        assert "#!/usr/bin/env bash" in result
        assert "make it better" in result

    @pytest.mark.asyncio
    async def test_generate_evaluator_uses_intake_execution_mode_when_not_explicit(self):
        from optimize_anything.server import generate_evaluator

        result = await generate_evaluator(
            seed="hello",
            objective="make it better",
            intake={"execution_mode": "http"},
        )
        assert result.startswith("#!/usr/bin/env python3")

    @pytest.mark.asyncio
    async def test_generate_evaluator_explicit_type_overrides_intake_mode(self):
        from optimize_anything.server import generate_evaluator

        result = await generate_evaluator(
            seed="hello",
            objective="make it better",
            evaluator_type="command",
            intake={"execution_mode": "http"},
        )
        assert result.startswith("#!/usr/bin/env bash")

    @pytest.mark.asyncio
    async def test_generate_evaluator_invalid_intake_returns_error_json(self):
        from optimize_anything.server import generate_evaluator

        result = await generate_evaluator(
            seed="hello",
            objective="make it better",
            intake={"execution_mode": "grpc"},
        )
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_evaluator_intake_defaults(self):
        from optimize_anything.server import evaluator_intake

        result = await evaluator_intake()
        data = json.loads(result)

        assert data == {
            "artifact_class": "general_text",
            "quality_dimensions": [
                {"name": "correctness", "weight": 0.4},
                {"name": "clarity", "weight": 0.35},
                {"name": "conciseness", "weight": 0.25},
            ],
            "hard_constraints": [],
            "evaluation_pattern": "judge",
            "execution_mode": "command",
            "evaluator_cwd": None,
        }

    @pytest.mark.asyncio
    async def test_evaluator_intake_partial_input_normalization(self):
        from optimize_anything.server import evaluator_intake

        result = await evaluator_intake(
            artifact_class="  policy_memo  ",
            hard_constraints=[
                " keep length <= 120 words ",
                "keep length <= 120 words",
                "   ",
            ],
            execution_mode="HTTP",
        )
        data = json.loads(result)

        assert data == {
            "artifact_class": "policy_memo",
            "quality_dimensions": [
                {"name": "correctness", "weight": 0.4},
                {"name": "clarity", "weight": 0.35},
                {"name": "conciseness", "weight": 0.25},
            ],
            "hard_constraints": ["keep length <= 120 words"],
            "evaluation_pattern": "judge",
            "execution_mode": "http",
            "evaluator_cwd": None,
        }

    @pytest.mark.asyncio
    async def test_evaluator_intake_invalid_value_returns_error_json(self):
        from optimize_anything.server import evaluator_intake

        result = await evaluator_intake(execution_mode="grpc")
        data = json.loads(result)

        assert data == {"error": "execution_mode must be one of: 'command', 'http'"}

    @pytest.mark.asyncio
    async def test_optimize_returns_canonical_summary(self, monkeypatch):
        from optimize_anything.server import optimize

        class DummyResult:
            best_candidate = "improved artifact"
            total_metric_calls = 9
            val_aggregate_scores = [0.3, 0.41, 0.47]
            val_aggregate_subscores = [
                {"clarity": 0.2, "safety": 0.1},
                {"clarity": 0.3, "safety": 0.2},
                {"clarity": 0.4, "safety": 0.35},
            ]
            best_idx = 2

        monkeypatch.setattr(
            "optimize_anything.evaluators.command_evaluator",
            lambda command, cwd=None: "fake-evaluator",
        )
        monkeypatch.setattr(
            "gepa.optimize_anything.optimize_anything",
            lambda **kwargs: DummyResult(),
        )

        result = await optimize(seed="seed", evaluator_command=["bash", "eval.sh"])
        data = json.loads(result)
        assert data["best_artifact"] == "improved artifact"
        assert data["total_metric_calls"] == 9
        assert data["score_summary"]["best"] == pytest.approx(0.47)
        assert data["top_diagnostics"][0]["name"] == "clarity"
        assert "plateau_guidance" in data
