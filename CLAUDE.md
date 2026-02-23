# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # Install dependencies (includes dev group with pytest)
uv run pytest                        # Run all 32 tests
uv run pytest tests/test_server.py   # Run a single test file
uv run pytest -k "test_explain"      # Run tests matching a pattern
uv run optimize-anything --help      # CLI entry point
uv run python -m optimize_anything.server  # Start MCP server (stdio)
```

## Architecture

This is a **Claude Code plugin** and **CLI tool** that wraps [gepa](https://pypi.org/project/gepa/) — a library for optimizing text artifacts via evolutionary search with LLM-guided mutations. Our code is a thin integration layer; all optimization logic lives in gepa.

### Core abstraction

gepa's `optimize_anything()` takes a `seed_candidate` string and an `evaluator` callable, then evolves the text through LLM-proposed mutations scored by the evaluator. Our added value is bridging external scoring systems (shell commands, HTTP endpoints) to gepa's evaluator protocol:

```
evaluator(candidate: str) -> tuple[float, dict]
```

The two factory functions in `evaluators.py` (`command_evaluator`, `http_evaluator`) create this callable from external processes. They send `{"candidate": "..."}` and parse back `{"score": <float>, ...}`.

### Delivery layers

The same gepa wrapper is exposed through three independent interfaces:

- **`server.py`** — FastMCP server with 4 async tools (`optimize`, `explain`, `recommend_budget`, `generate_evaluator`). Uses `mcp.server.fastmcp.FastMCP`. Runs over stdio transport. The module-level `mcp` instance is also used directly in tests.
- **`cli.py`** — argparse CLI with 3 subcommands (`optimize`, `explain`, `budget`). Registered as `optimize-anything` via `[project.scripts]` in pyproject.toml. Accepts `argv` parameter for testability.
- **`__init__.py`** — Public Python API re-exporting `optimize_anything` from gepa plus our evaluator factories.

### Plugin structure

```
.claude-plugin/plugin.json   # Plugin manifest
.mcp.json                    # Auto-starts MCP server via uv --directory ${CLAUDE_PLUGIN_ROOT}
commands/optimize.md         # /optimize slash command
skills/                      # generate-evaluator, optimization-guide
```

### Evaluator contract

Evaluators receive `{"candidate": "..."}` on stdin (command) or as POST body (HTTP) and must return JSON with at least a `"score"` field. All other fields become side information for gepa's reflection LM. The `objective` and `background` strings are NOT passed to evaluators — they go to gepa directly.

## Testing

Tests use `pytest` with `pytest-asyncio` for the async MCP tool tests. Shared fixtures in `conftest.py` create temporary bash evaluator scripts (`tmp_evaluator_script`, `tmp_bad_evaluator_script`, `tmp_failing_evaluator_script`). HTTP evaluator tests mock `httpx.post`. Server tool tests call the async functions directly (not through MCP transport). CLI tests call `main(argv)` and capture output via `capsys`.

## Dependencies

- **gepa** — optimization engine (the core dependency; we delegate all search/reflection to it)
- **mcp[cli]** — FastMCP server framework
- **httpx** — HTTP client for `http_evaluator`
- Dev deps are in `[dependency-groups]` (not `[project.optional-dependencies]`), so `uv sync` always includes pytest
