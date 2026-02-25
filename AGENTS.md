# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/optimize_anything/`:
- `cli.py` for `optimize-anything` subcommands (`optimize`, `generate-evaluator`, `intake`, `explain`, `budget`, `score`, `analyze`)
- `evaluators.py` for command/HTTP evaluator adapters
- `llm_judge.py` for LLM-as-judge evaluator and dimension analysis
- `intake.py` for intake schema normalization (`evaluation_pattern`, `execution_mode`, `quality_dimensions`, constraints)
- `evaluator_generator.py` for evaluator scaffolding from seed/objective/intake
- `spec_loader.py` for TOML spec file loading
- `result_contract.py` for canonical optimize summary output used by CLI

Tests are in `tests/` with shared fixtures in `tests/conftest.py`. Supporting material is in `docs/` (protocol, smoke gates, remediation, release/handoff), `examples/` (seed/evaluator samples), `commands/` (slash command docs), `skills/` (packaged skills), plus root guides `install.md` and `evaluator-cookbook.md`.

## Build, Test, and Development Commands
- `uv sync` — install runtime and dev dependencies.
- `uv run pytest` — run the full test suite.
- `uv run pytest tests/test_cli.py` — run one test module.
- `uv run pytest -k "explain"` — run tests by name pattern.
- `uv run optimize-anything --help` — inspect CLI usage.
- `uv run python scripts/check.py` — unified gate: pytest + smoke + score_check.
- `uv run python scripts/check.py --skip-smoke` — unified gate without smoke (offline).
- `uv run python scripts/smoke_harness.py --budget 1` — run CLI smoke harness.
- `uv run python scripts/score_check.py` — score regression check.
- `uv run python scripts/score_check.py --update` — update baselines after improvement.
- `uv run python scripts/live_integration.py --phase green --artifact FILE --model openai/gpt-4o-mini --budget 15 --objective "..." --evaluator-command bash evaluators/eval.sh` — GREEN phase optimization.

## Coding Style & Naming Conventions
Target Python is `>=3.10`. Follow existing style:
- 4-space indentation, explicit type hints, concise module/function docstrings.
- `snake_case` for modules, functions, and variables; `CapWords` for classes.
- Keep interfaces separated by layer: CLI behavior in `cli.py`, evaluator plumbing in `evaluators.py`.
- Preserve evaluator JSON contract: input includes `candidate`; output must include numeric `score`.
- Keep runtime mode and strategy distinct in docs/code:
  - `execution_mode` (`command`/`http`) controls transport/runtime.
  - `evaluation_pattern` (`verification`/`judge`/`simulation`/`composite`) describes scoring approach.

## Testing Guidelines
Use `pytest` for tests.
- Name files `tests/test_<unit>.py` and functions `test_<behavior>`.
- Prefer focused unit tests for each command path and error mode.
- Reuse fixtures for temp evaluator scripts and mock external HTTP calls where possible.

## Commit & Pull Request Guidelines
Recent history uses conventional prefixes: `feat:`, `fix:`, `docs:`, `chore:` (optionally scoped). Keep commits small and single-purpose.

For PRs, include:
- a short problem/solution summary,
- linked issue (if any),
- test evidence (command + result),
- sample CLI output when behavior changes.

## Optimization Workflow

When running RED-GREEN-OBSERVER cycles:
1. Always pass `--model` explicitly to `live_integration.py`
2. Place `--evaluator-command` as the LAST flag
3. Run RED validation after every GREEN improvement
4. Accept artifacts only when cross_provider_delta < 0.2
5. Update baselines with `score_check.py --update` after accepting
6. Commit with descriptive message including score deltas

## File Organization

- `src/optimize_anything/` — package source (all Python modules)
- `scripts/` — operational scripts (gates, smoke, live integration)
- `skills/` — optimizable skill artifacts (SKILL.md files)
- `evaluators/` — production evaluator scripts
- `examples/` — sample evaluators and seeds
- `tests/` — pytest test suite
- `docs/` — planning and handoff documents (gitignored from commits)
- `integration_runs/` — optimization run artifacts (gitignored)
