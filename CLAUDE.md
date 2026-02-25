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
uv run optimize-anything score FILE --judge-model openai/gpt-4o-mini --objective "Score clarity"  # LLM judge scoring
uv run optimize-anything analyze FILE --judge-model openai/gpt-4o-mini --objective "Quality"    # Discover quality dimensions
uv run python scripts/check.py                    # Unified gate: pytest + smoke + score_check
uv run python scripts/check.py --skip-smoke       # Unified gate without smoke (offline)
uv run python scripts/smoke_harness.py --budget 1 # CLI smoke check
uv run python scripts/score_check.py              # Score regression check
uv run python scripts/score_check.py --update     # Update baselines after improvement
uv run python scripts/live_integration.py --phase green \
    --artifact FILE --model openai/gpt-4o-mini --budget 15 \
    --objective "..." --run-dir integration_runs \
    --evaluator-command bash evaluators/skill_clarity.sh  # GREEN phase optimization
uv run python scripts/live_integration.py --phase red \
    --artifact FILE --objective "..." \
    --providers openai/gpt-5.1-mini anthropic/claude-sonnet-4-5-20250929 \
    --baseline 0.85 \
    --evaluator-command bash evaluators/skill_clarity.sh  # RED phase validation
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
  - Subcommands: `optimize`, `generate-evaluator`, `intake`, `explain`, `budget`, `score`, `analyze`
  - Three mutually exclusive evaluator sources: `--evaluator-command`, `--evaluator-url`, `--judge-model`
  - Multi-provider flags: `--model` (proposer LLM), `--judge-model` (judge LLM), `--api-base`
  - `--judge-objective` overrides `--objective` for the judge; falls back to `--objective`
  - `--model` env fallback: `OPTIMIZE_ANYTHING_MODEL`
  - Supports intake flags (`--intake-json`, `--intake-file`) and `--evaluator-cwd`

- `src/optimize_anything/evaluators.py`
  - `command_evaluator(...)`, `http_evaluator(...)`, strict score validation

- `src/optimize_anything/llm_judge.py`
  - `llm_judge_evaluator(objective, *, model, quality_dimensions, hard_constraints, timeout, temperature, api_base)`
  - `analyze_for_dimensions(artifact, objective, model, *, api_base, timeout, temperature)` — 2 LLM calls: score + dimension discovery
  - Uses litellm for multi-provider LLM calls; returns gepa-compatible `(score, side_info)` tuples
  - Supports simple (score+reasoning) and dimension-weighted scoring modes
  - Hard constraint gate: score forced to 0.0 on violation

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

- `src/optimize_anything/spec_loader.py`
  - TOML spec file loading for repeatable optimization runs
  - `--spec-file` flag overrides CLI arguments with spec values

- `scripts/live_integration.py`
  - RED-GREEN-OBSERVER cycle orchestrator
  - `--phase green`: optimize artifact, output structured JSON
  - `--phase red`: multi-provider scoring, output score matrix
  - `--model`: proposer LLM (REQUIRED — gepa default may be unavailable)
  - `--evaluator-command` MUST be the last flag (nargs="+" greedy parsing)

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
- LLM judge unit tests mock `litellm.completion`; integration tests skip via `@pytest.mark.skipif` when API keys absent.
- Live integration tests in `tests/test_live_integration.py`.
- `@pytest.mark.integration` for tests requiring API keys.
- Code fence stripping tested in `test_llm_judge.py`.
- Doc drift checks live in `tests/test_doc_contract.py`.

## Known Gotchas

- `--evaluator-command` in `live_integration.py` uses `nargs="+"` — must be the LAST
  flag or it swallows subsequent arguments like `--model`
- gepa's default proposer model may be unavailable — always pass `--model` explicitly
- Anthropic models wrap JSON responses in markdown code fences — `llm_judge.py`
  strips these automatically
- `scores.json` baselines: use `score_check.py --update` after accepting improvements

## Dependencies

- `gepa` (optimization engine)
- `httpx` (HTTP evaluator client)
- `litellm` (runtime dependency required for live optimization flows)
