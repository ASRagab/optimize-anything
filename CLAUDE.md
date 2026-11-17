# CLAUDE.md

CLI and plugin reference for Claude Code. Repository workflow, quality gates, and test-enforced constraints are in @AGENTS.md.

## Core commands

```bash
uv sync
uv run pytest
uv run optimize-anything --help

# Optimize
uv run optimize-anything optimize seed.txt --evaluator-command bash eval.sh --model openai/gpt-5.6-sol --objective "Improve quality"

# Generate evaluator (default type: judge)
uv run optimize-anything generate-evaluator seed.txt --objective "Score quality" > eval.py

# Score one artifact
uv run optimize-anything score artifact.txt --judge-model openai/gpt-5.6-luna --objective "Score clarity"

# Analyze for quality dimensions
uv run optimize-anything analyze artifact.txt --judge-model openai/gpt-5.6-luna --objective "Quality"

# Validate across providers
uv run optimize-anything validate artifact.txt \
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score quality" \
  --intake-file intake.json
```

## Delivery surfaces

- CLI subcommands: `optimize`, `generate-evaluator`, `intake`, `explain`, `budget`, `score`, `analyze`, `validate`
- Evaluator runtimes: command, http, LLM judge, TypeSafe Jev
- Protocol source of truth: `PROTOCOL.md`

## Optimize flags

| Flag | Description |
| --- | --- |
| `--no-seed` | Run without a seed file; requires `--objective` and `--model` |
| `--evaluator-command <cmd...>` | Command evaluator (stdin/stdout JSON) |
| `--evaluator-url <url>` | HTTP evaluator endpoint |
| `--intake-json <json>` | Inline intake spec |
| `--intake-file <path>` | Intake spec JSON file |
| `--evaluator-cwd <path>` | Working directory for a command evaluator |
| `--objective <text>` | Optimization objective |
| `--background <text>` | Domain context |
| `--dataset <path>` | Train dataset JSONL |
| `--valset <path>` | Validation dataset JSONL (requires `--dataset`) |
| `--budget <int>` | Max evaluator calls (default 100) |
| `--output, -o <file>` | Write the best artifact to a file |
| `--model <model>` | Proposer model (fallback: `OPTIMIZE_ANYTHING_MODEL`) |
| `--judge-model <model>` | Built-in LLM judge evaluator model |
| `--jev-model <model>` | TypeSafe Jev evaluator (such as `jev-latest`); needs `TYPESAFE_API_KEY` |
| `--judge-backend api\|codex\|claude` | Backend for the built-in LLM judge (default: api) |
| `--proposer-backend api\|codex\|claude` | Backend for proposal generation (default: api) |
| `--subscription-concurrency <int>` | Concurrent calls per subscription provider (default 1) |
| `--no-api-fallback` | Forbid subscription-to-API fallback |
| `--openai-api-fallback-model <model>` | Same-vendor API fallback for Codex |
| `--anthropic-api-fallback-model <model>` | Same-vendor API fallback for Claude |
| `--judge-objective <text>` | Judge objective override |
| `--api-base <url>` | LiteLLM API base override |
| `--diff` | Print a unified diff (seed vs best) |
| `--run-dir <path>` | Persist run artifacts in a timestamped directory |
| `--parallel` | Enable parallel evaluator calls (default) |
| `--no-parallel` | Run evaluator calls serially |
| `--workers <int>` | Max workers for parallel mode |
| `--proposals-per-iteration <int>` | Candidate mutations per GEPA iteration (default 1) |
| `--cache` | Enable the evaluator cache |
| `--cache-from <run-dir>` | Reuse a previous run's `fitness_cache` (requires `--cache`) |
| `--early-stop` | Enable plateau-based early stopping |
| `--early-stop-window <int>` | Early-stop plateau window (default 10) |
| `--early-stop-threshold <float>` | Min improvement threshold (default 0.005) |
| `--spec-file <path>` | Load TOML spec defaults |
| `--task-model <model>` | Metadata forwarded to the evaluator payload and environment |
| `--score-range unit\|any` | Score validation mode for command/http evaluators |

Notes:

- Exactly one evaluator source: `--evaluator-command`, `--evaluator-url`, `--judge-model` (or `--judge-backend`), or `--jev-model`.
- Jev scores quality dimensions and hard constraints in one request. It cannot propose candidates, so `--model` still selects the proposer.
- Early stop auto-activates when budget > 30.
- The proposer defaults to `openai/gpt-5.6-sol` after checking `--model` and `OPTIMIZE_ANYTHING_MODEL`. Generated judge and composite evaluators default to `openai/gpt-5.6-luna`.
- LLM judge calls use each provider's sampling defaults unless an explicit temperature is supplied.

## Validate subcommand

`validate` runs LLM-judge scoring for one artifact across 2 or more providers and reports mean, stddev, min, and max. A provider whose judge call fails reports `score: null` and is excluded from the statistics.

```bash
uv run optimize-anything validate runs/run-20260303-130000/best_artifact.txt \
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score clarity, constraints, and robustness" \
  --intake-file intake.json
```

Gemini uses LiteLLM's `gemini/` provider prefix.

## Plugin structure

The Claude Code plugin (`.claude-plugin/`) and the Codex plugin (`.codex-plugin/`) share one `skills/` tree. Slash commands are Claude Code only.

```text
.claude-plugin/plugin.json, marketplace.json
.codex-plugin/plugin.json
commands/   optimize, quick, analyze, score, validate, compare, budget, explain, intake
skills/     optimize-prompt, optimization-guide, generate-evaluator, evaluator-patterns
```

Keep these two axes distinct:

- `execution_mode` = runtime transport (`command`/`http`)
- `evaluation_pattern` = scoring strategy (`verification`/`judge`/`simulation`/`composite`)

## Intake schema

The intake specification (`--intake-json` / `--intake-file`) normalizes these fields:

- `artifact_class`: type of artifact (prompt, code, config, docs)
- `quality_dimensions`: named scoring axes with float weights. Each may add optional `levels` (2 to 10 rubric strings, lowest to highest) that `--jev-model` uses as that dimension's scale
- `hard_constraints`: boolean pass/fail conditions (a violation forces the score to 0.0)
- `evaluation_pattern`: scoring strategy (`verification`, `judge`, `simulation`, `composite`)
- `execution_mode`: evaluator transport (`command`, `http`)
- `evaluator_cwd`: working directory for command evaluators

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `ASRagab/optimize-anything`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, with `needs-triage`→`triage`, `ready-for-agent`→`dev`, `ready-for-human`→`review` remapped. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
