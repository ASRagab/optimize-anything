# CLAUDE.md

Repository guidance for Claude Code.

## Core commands

```bash
uv sync
uv run pytest
uv run optimize-anything --help

# Optimize
uv run optimize-anything optimize seed.txt --evaluator-command bash eval.sh --model openai/gpt-4o-mini --objective "Improve quality"

# Generate evaluator (default type: judge)
uv run optimize-anything generate-evaluator seed.txt --objective "Score quality" > eval.py

# Score one artifact
uv run optimize-anything score artifact.txt --judge-model openai/gpt-4o-mini --objective "Score clarity"

# Analyze for quality dimensions
uv run optimize-anything analyze artifact.txt --judge-model openai/gpt-4o-mini --objective "Quality"

# Validate across providers
uv run optimize-anything validate artifact.txt \
  --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5 google/gemini-2.0-flash \
  --objective "Score quality" \
  --intake-file intake.json
```

## Delivery surfaces

- CLI subcommands: `optimize`, `generate-evaluator`, `intake`, `explain`, `budget`, `score`, `analyze`, `validate`
- Evaluator runtimes: command / http / LLM judge
- Protocol source of truth: `PROTOCOL.md`

## Optimize flags (complete, 28)

| Flag | Description |
|---|---|
| `--no-seed` | Run without seed file; requires `--objective` and `--model` |
| `--evaluator-command <cmd...>` | Command evaluator (stdin/stdout JSON) |
| `--evaluator-url <url>` | HTTP evaluator endpoint |
| `--intake-json <json>` | Inline intake spec |
| `--intake-file <path>` | Intake spec JSON file |
| `--evaluator-cwd <path>` | Working directory for command evaluator |
| `--objective <text>` | Optimization objective |
| `--background <text>` | Domain context |
| `--dataset <path>` | Train dataset JSONL |
| `--valset <path>` | Validation dataset JSONL (requires `--dataset`) |
| `--budget <int>` | Max evaluator calls (default 100) |
| `--output, -o <file>` | Write best artifact to file |
| `--model <model>` | Proposer model (fallback: `OPTIMIZE_ANYTHING_MODEL`) |
| `--judge-model <model>` | Built-in LLM judge evaluator model |
| `--judge-objective <text>` | Judge objective override |
| `--api-base <url>` | LiteLLM API base override |
| `--diff` | Print unified diff (seed vs best) |
| `--run-dir <path>` | Persist run artifacts in timestamped dir |
| `--parallel` | Enable parallel evaluator calls |
| `--workers <int>` | Max workers for parallel mode |
| `--cache` | Enable evaluator cache |
| `--cache-from <run-dir>` | Reuse previous run `fitness_cache` (requires `--cache`) |
| `--early-stop` | Enable plateau-based early stopping |
| `--early-stop-window <int>` | Early-stop plateau window (default 10) |
| `--early-stop-threshold <float>` | Min improvement threshold (default 0.005) |
| `--spec-file <path>` | Load TOML spec defaults |
| `--task-model <model>` | Optional metadata forwarded to evaluator payload/env |
| `--score-range unit|any` | Score validation mode for command/http evaluators |

Notes:
- Exactly one evaluator source: `--evaluator-command` OR `--evaluator-url` OR `--judge-model`.
- Early stop auto-activates when budget > 30.

## Validate subcommand

`validate` runs LLM-judge scoring for one artifact across 2+ providers and reports mean/stddev/min/max.

```bash
uv run optimize-anything validate runs/run-20260303-130000/best_artifact.txt \
  --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5 google/gemini-2.0-flash \
  --objective "Score clarity, constraints, and robustness" \
  --intake-file intake.json
```

## Plugin structure

```text
.claude-plugin/plugin.json
commands/optimize.md
commands/quick.md
commands/validate.md
skills/generate-evaluator/
skills/optimization-guide/
skills/evaluator-patterns/
```

Be explicit about the distinction:
- `execution_mode` = runtime transport (`command`/`http`)
- `evaluation_pattern` = scoring strategy (`verification`/`judge`/`simulation`/`composite`)

## Intake schema

The intake specification (`--intake-json` / `--intake-file`) normalizes these fields:
- `artifact_class` — type of artifact (prompt, code, config, docs)
- `quality_dimensions` — named scoring axes with float weights
- `hard_constraints` — boolean pass/fail conditions (violation forces score to 0.0)
- `evaluation_pattern` — scoring strategy (`verification`, `judge`, `simulation`, `composite`)
- `execution_mode` — evaluator transport (`command`, `http`)
- `evaluator_cwd` — working directory for command evaluators
