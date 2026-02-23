# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/optimize_anything/`:
- `cli.py` for `optimize-anything` subcommands (`optimize`, `explain`, `budget`)
- `server.py` for FastMCP tools (`optimize`, `explain`, `recommend_budget`, `generate_evaluator`, `evaluator_intake`)
- `evaluators.py` for command/HTTP evaluator adapters
- `intake.py` for intake schema normalization (`evaluation_pattern`, `execution_mode`, `quality_dimensions`, constraints)
- `evaluator_generator.py` for evaluator scaffolding from seed/objective/intake
- `result_contract.py` for canonical optimize summary output used by CLI + MCP

Tests are in `tests/` with shared fixtures in `tests/conftest.py`. Supporting material is in `docs/` (protocol, smoke gates, remediation, release/handoff), `examples/` (seed/evaluator samples), `commands/` (slash command docs), `skills/` (packaged skills), plus root guides `install.md` and `evaluator-cookbook.md`.

## Build, Test, and Development Commands
- `uv sync` — install runtime and dev dependencies.
- `uv run pytest` — run the full test suite.
- `uv run pytest tests/test_server.py` — run one test module.
- `uv run pytest -k "explain"` — run tests by name pattern.
- `uv run optimize-anything --help` — inspect CLI usage.
- `uv run python -m optimize_anything.server` — start MCP server over stdio.
- `uv run python scripts/smoke_harness.py --budget 1` — run CLI+MCP smoke harness.
- `uv run python scripts/consecutive_smoke_gate.py --budget 1` — run consecutive smoke gate.

## Coding Style & Naming Conventions
Target Python is `>=3.10`. Follow existing style:
- 4-space indentation, explicit type hints, concise module/function docstrings.
- `snake_case` for modules, functions, and variables; `CapWords` for classes.
- Keep interfaces separated by layer: CLI behavior in `cli.py`, MCP behavior in `server.py`, evaluator plumbing in `evaluators.py`.
- Preserve evaluator JSON contract: input includes `candidate`; output must include numeric `score`.
- Keep runtime mode and strategy distinct in docs/code:
  - `execution_mode` (`command`/`http`) controls transport/runtime.
  - `evaluation_pattern` (`verification`/`judge`/`simulation`/`composite`) describes scoring approach.

## Testing Guidelines
Use `pytest` and `pytest-asyncio` for async tool tests.
- Name files `tests/test_<unit>.py` and functions `test_<behavior>`.
- Prefer focused unit tests for each command/tool path and error mode.
- Reuse fixtures for temp evaluator scripts and mock external HTTP calls where possible.

## Commit & Pull Request Guidelines
Recent history uses conventional prefixes: `feat:`, `fix:`, `docs:`, `chore:` (optionally scoped). Keep commits small and single-purpose.

For PRs, include:
- a short problem/solution summary,
- linked issue (if any),
- test evidence (command + result),
- sample CLI/MCP output when behavior changes.
