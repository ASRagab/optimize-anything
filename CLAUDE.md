# CLAUDE.md

This file provides guidance to Claude Code (`claude.ai/code`) when working in this repository.

## Commands

```bash
uv sync                                           # Install runtime + dev dependencies
uv run pytest                                     # Run full test suite
uv run pytest tests/test_server.py                # Run one test module
uv run pytest -k "optimize"                       # Run tests by pattern
uv run optimize-anything --help                   # CLI entry point
uv run python -m optimize_anything.server         # Start MCP server (stdio)
uv run python scripts/smoke_harness.py --budget 1 # CLI+MCP smoke check
uv run python scripts/consecutive_smoke_gate.py --budget 1
```

## Architecture

`optimize-anything` is a Claude Code plugin + CLI wrapper around `gepa.optimize_anything()`:

- `gepa` performs propose/evaluate/reflect optimization.
- This repo provides evaluator adapters, intake normalization, generation helpers, and delivery surfaces.

Core evaluator protocol:

```text
evaluator(candidate: str) -> tuple[float, dict]
```

Input/output contract for external evaluators:
- Input: `{"candidate": "<text>"}` (stdin for command mode, POST JSON for http mode)
- Output: JSON object with required numeric `score` and optional diagnostic keys

## Delivery Surfaces

- `src/optimize_anything/cli.py`
  - Subcommands: `optimize`, `explain`, `budget`
  - Supports evaluator source flags (`--evaluator-command` or `--evaluator-url`)
  - Supports intake flags (`--intake-json`, `--intake-file`) and `--evaluator-cwd`

- `src/optimize_anything/server.py`
  - FastMCP tools: `optimize`, `explain`, `recommend_budget`, `generate_evaluator`, `evaluator_intake`

- `src/optimize_anything/evaluators.py`
  - `command_evaluator(...)`, `http_evaluator(...)`, strict score validation

- `src/optimize_anything/intake.py`
  - Normalizes intake schema and validates:
    - `artifact_class`
    - `quality_dimensions`
    - `hard_constraints`
    - `evaluation_pattern` (`verification|judge|simulation|composite`)
    - `execution_mode` (`command|http`)
    - `evaluator_cwd`

- `src/optimize_anything/result_contract.py`
  - Canonical optimize summary for both CLI and MCP outputs

## Important Distinction

- `execution_mode` / runtime type: transport and execution path (`command` vs `http`)
- `evaluation_pattern`: scoring strategy intent (`verification`, `judge`, `simulation`, `composite`)

Do not conflate these in docs or implementation.

## Plugin Structure

```text
.claude-plugin/plugin.json
.mcp.json
commands/optimize.md
skills/generate-evaluator/
skills/optimization-guide/
```

## Testing Notes

- Use `pytest` + `pytest-asyncio`.
- CLI tests call `main(argv)`.
- Server tests call async tool functions directly.
- Evaluator tests include command, HTTP, timeout, and malformed payload cases.
- Doc drift checks live in `tests/test_doc_contract.py`.

## Dependencies

- `gepa` (optimization engine)
- `mcp[cli]` (FastMCP server/runtime)
- `httpx` (HTTP evaluator client)
- `litellm` (runtime dependency required for live optimization flows)
