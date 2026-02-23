# CLAUDE.md

This file provides guidance to Claude Code (`claude.ai/code`) when working in this repository.

## Commands

```bash
uv sync                                           # Install runtime + dev dependencies
uv run pytest                                     # Run full test suite
uv run pytest tests/test_cli.py                   # Run one test module
uv run pytest -k "optimize"                       # Run tests by pattern
uv run optimize-anything --help                   # CLI entry point
uv run optimize-anything score FILE --evaluator-command bash eval.sh  # Score one artifact
uv run python scripts/check.py                    # Unified gate: pytest + smoke + score_check
uv run python scripts/check.py --skip-smoke       # Unified gate without smoke (offline)
uv run python scripts/smoke_harness.py --budget 1 # CLI smoke check
uv run python scripts/score_check.py              # Score regression check
uv run python scripts/score_check.py --update     # Update baselines after improvement
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
  - Subcommands: `optimize`, `generate-evaluator`, `intake`, `explain`, `budget`, `score`
  - Supports evaluator source flags (`--evaluator-command` or `--evaluator-url`)
  - Supports intake flags (`--intake-json`, `--intake-file`) and `--evaluator-cwd`

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
  - Canonical optimize summary for CLI output

## Important Distinction

- `execution_mode` / runtime type: transport and execution path (`command` vs `http`)
- `evaluation_pattern`: scoring strategy intent (`verification`, `judge`, `simulation`, `composite`)

Do not conflate these in docs or implementation.

## Plugin Structure

```text
.claude-plugin/plugin.json
commands/optimize.md
skills/generate-evaluator/
skills/optimization-guide/
```

## Testing Notes

- Use `pytest`.
- CLI tests call `main(argv)`.
- Evaluator tests include command, HTTP, timeout, and malformed payload cases.
- Doc drift checks live in `tests/test_doc_contract.py`.

## Dependencies

- `gepa` (optimization engine)
- `httpx` (HTTP evaluator client)
- `litellm` (runtime dependency required for live optimization flows)
