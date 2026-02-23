"""Tests for MCP server tools."""

from __future__ import annotations

import asyncio
import json

import pytest

from optimize_anything.server import mcp


class TestServerTools:
    def test_server_has_tools(self):
        """Verify all 4 tools are registered."""
        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "optimize" in tool_names
        assert "explain" in tool_names
        assert "recommend_budget" in tool_names
        assert "generate_evaluator" in tool_names

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
    async def test_generate_evaluator_tool(self):
        from optimize_anything.server import generate_evaluator

        result = await generate_evaluator(
            seed="hello", objective="make it better"
        )
        assert "#!/usr/bin/env bash" in result
        assert "make it better" in result
