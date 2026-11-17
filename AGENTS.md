# Repository Guidelines

optimize-anything is a Python 3.10+ package (built with `uv` and hatchling) that wraps GEPA to optimize text artifacts against a command, HTTP, LLM-judge, or Jev evaluator. [README.md](README.md) is the user guide. [CLAUDE.md](CLAUDE.md) is the CLI reference for agents.

## Commands

```bash
uv sync                                          # runtime + dev dependencies
uv run pytest                                    # full suite (stops at the first failure)
uv run pytest tests/test_cli.py -k explain       # one module or name pattern
uv run python scripts/check.py --skip-smoke      # offline gate: pytest + score check
uv run python scripts/check.py                   # adds the smoke harness (real API calls)
uv run python scripts/check.py --with-plugin     # adds plugin regression (needs the claude CLI)
uv run python scripts/smoke_harness.py --budget 1
uv run python scripts/score_check.py             # score regression gate
uv run python scripts/score_check.py --update    # re-baseline after a confirmed improvement
uv run mypy src                                  # type check
```

CI runs `pytest -m "not integration"`, the smoke harness, and `score_check.py`. Tests marked `integration` call real provider APIs. The opt-in subscription and paid-fallback live gates are in [docs/smoke-gates.md](docs/smoke-gates.md).

## Layout

- `src/optimize_anything/`: `cli.py` builds the parsers and dispatches. `cli_optimize.py` and `cli_tools.py` hold the subcommand handlers. `evaluators.py` runs command and HTTP evaluators. `llm_judge.py` and `jev_judge.py` are the built-in judges. `intake.py` normalizes intake specs. `result_contract.py` defines the `optimize` summary. `llm_backends/` holds the API, Codex, and Claude backends and the fallback logic. `model_defaults.py` holds the default models.
- `commands/` and `skills/` are shared by the Claude Code plugin (`.claude-plugin/`) and the Codex plugin (`.codex-plugin/`). Skills run the bundled runtime through `scripts/run-optimize-anything` and never assume a global CLI.
- `scripts/` holds the gates, smoke harness, live integration, plugin regression, and optimization observability tools.
- `.claude/skills/verify-optimize-anything/` drives the real CLI offline against a local stub. Use it to confirm a change works beyond pytest.
- `docs/` is gitignored except `docs/smoke-gates.md` and `docs/verification/`.

## Constraints that tests enforce

- **Docs are pinned to code.** `tests/test_doc_contract.py`, `tests/test_model_defaults.py`, and `tests/test_prompt_plugin_contract.py` require specific flags, intake keys, result keys, and model names in `README.md`, `CLAUDE.md`, `PROTOCOL.md`, and the skills. When you change a flag, key, or default, update the docs and these tests together, then rerun them.
- **No stale model names in docs.** Use the current defaults from `model_defaults.py`.
- **Release versions match.** `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (twice), and `.codex-plugin/plugin.json` carry one version.
- **Score baselines.** `scores.json` records baselines for `evaluator-cookbook.md`, `skills/generate-evaluator/SKILL.md`, and `skills/optimization-guide/SKILL.md`. Editing those files can fail `score_check.py` in CI. Fix the text (shorter wording usually helps). Do not re-baseline to hide a regression.
- **Evaluator contract.** Input always includes `candidate`. Output must include a numeric `score`. See [PROTOCOL.md](PROTOCOL.md).
- **Two separate axes.** `execution_mode` (`command` or `http`) is the transport. `evaluation_pattern` (`verification`, `judge`, `simulation`, `composite`) is the scoring strategy. Keep them distinct in code and docs.

## Conventions

- Match the surrounding style: 4-space indentation, type hints, `snake_case` names, `CapWords` classes. Keep CLI behavior in the `cli*` modules and evaluator plumbing in `evaluators.py`.
- Tests are `tests/test_<unit>.py` with `test_<behavior>` functions. Reuse the fixtures in `tests/conftest.py` for temp evaluator scripts and mocked HTTP.
- Docs describe the current behavior only. Release history belongs in [CHANGELOG.md](CHANGELOG.md), and dated evidence belongs in `docs/verification/`.
- Never commit API keys or `.env` files.

## Commits and pull requests

Use conventional prefixes: `feat:`, `fix:`, `docs:`, `chore:`. Keep commits small and single-purpose. Issues live in GitHub (`ASRagab/optimize-anything`).

A pull request includes a short problem and solution summary, the linked issue (if any), test evidence (command and result), and sample CLI output when behavior changes.

## Optimization observability benchmark

Use this benchmark to check that an optimization loop improved a useful artifact and did not just game the scorer:

```bash
uv run python scripts/optimization_observer.py setup
uv run python scripts/optimization_observer.py report \
  --run-dir integration_runs/optimization-observability/evaluator-generation-guidance/runs/run-YYYYMMDD-HHMMSS \
  --benchmark examples/optimization-observability/evaluator-generation-benchmark.json \
  --strict
```

[examples/optimization-observability/README.md](examples/optimization-observability/README.md) lists the report fields, acceptance criteria, and troubleshooting.
