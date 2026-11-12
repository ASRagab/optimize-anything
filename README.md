# optimize-anything

Improve any text artifact (a prompt, config, doc, code file, or agent skill) against an evaluator you control.

optimize-anything runs a [GEPA](https://github.com/gepa-ai/gepa) (Genetic-Pareto) loop. An LLM proposes edits, your evaluator scores them, and the scores and diagnostics guide the next round. You supply the artifact and a way to score it. The tool handles proposals, reflection, caching, parallelism, and early stopping.

## Install

| Method | Gives you | Requirements |
|---|---|---|
| **Claude Code plugin** | Skills and slash commands | `uv`, Python 3.10 or newer |
| **Codex plugin** | Skills | `uv`, Python 3.10 or newer |
| **CLI installer** | Global `optimize-anything` command | None (the installer adds `uv`) |
| **From source** | `uv run optimize-anything` | `uv`, Python 3.10 or newer |

```bash
# CLI installer
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash

# Claude Code plugin
/plugin marketplace add ASRagab/optimize-anything
/plugin install optimize-anything@optimize-anything

# Codex plugin
codex plugin marketplace add ASRagab/optimize-anything
codex plugin add optimize-anything@optimize-anything
```

Restart Claude Code, or start a new Codex thread, after installing or updating a plugin. The plugins bundle a locked runtime, so they do not need the global CLI. [install.md](install.md) covers updates, removal, local clones, and verification.

## Quickstart

Export an API key for every provider you select. The default proposer and judge use OpenAI.

```bash
export OPENAI_API_KEY="..."
```

Create a seed and optimize it with the built-in LLM judge:

```bash
echo "Write a concise support prompt" > seed.txt

optimize-anything optimize seed.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Improve clarity and specificity" \
  --model openai/gpt-5.6-sol \
  --budget 20 \
  --workers 4 \
  --cache \
  --run-dir runs \
  --output result.txt
```

The best artifact is written to `result.txt`. Stdout is a JSON summary (see [Result contract](#result-contract)). With `--run-dir`, each run also saves `seed.txt`, `best_artifact.txt`, and `summary.json` in a timestamped directory.

API calls are billed by the provider. `--budget` limits evaluator calls, not cost.

### Model defaults

The proposer is `--model`, then `OPTIMIZE_ANYTHING_MODEL`, then `openai/gpt-5.6-sol`. Generated judge and composite evaluators default to `openai/gpt-5.6-luna`. Judge calls use each provider's sampling defaults unless you pass an explicit temperature.

### Authentication

| Selected by | Environment variable |
|---|---|
| `openai/...` models | `OPENAI_API_KEY` |
| `anthropic/...` models | `ANTHROPIC_API_KEY` |
| `gemini/...` models | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) |
| `openrouter/...` models | `OPENROUTER_API_KEY` |
| `--jev-model` | `TYPESAFE_API_KEY` |

Export the keys before you launch the CLI or the plugin host, and restart the host after a change. `--api-base` changes the endpoint, not the provider or its credentials. Claude Code and Codex logins are separate from provider API keys. Do not commit keys or `.env` files.

## How it works

```
seed.txt ──► [Propose] ──► candidates
                 ▲               │
                 │           [Evaluate]
             [Reflect] ◄──── scores + diagnostics
```

1. **Propose.** The proposer model generates candidates from your seed, or from the objective alone in seedless mode.
2. **Evaluate.** Your evaluator scores each candidate.
3. **Reflect.** Scores and diagnostics shape the next proposal. The loop stops when the budget is spent or early stopping detects a plateau.

### Evaluators

Pick exactly one evaluator source:

| Evaluator | Flag | Use it when |
|---|---|---|
| **LLM judge** | `--judge-model` | You want rubric scoring with no script. |
| **Command** | `--evaluator-command <cmd...>` | Scoring is a script or program (tests, linters, checks). |
| **HTTP** | `--evaluator-url <url>` | Scoring lives in a service. |
| **TypeSafe Jev** | `--jev-model` | You want calibrated scores per quality dimension and hard constraint. Needs `TYPESAFE_API_KEY`. |

A command evaluator reads JSON on stdin and writes JSON on stdout. An HTTP evaluator receives the same JSON as a POST body.

```json
{"candidate": "..."}
```

```json
{"score": 0.75, "notes": "optional diagnostics"}
```

`score` is required and must be in `[0, 1]` unless you pass `--score-range any`. Other keys are kept as diagnostics for reflection. See [PROTOCOL.md](PROTOCOL.md) for the full contract and [evaluator-cookbook.md](evaluator-cookbook.md) for working examples. `generate-evaluator` scaffolds one from your seed and objective.

Jev only scores, so `--model` still selects the proposer.

## Commands

| Command | Purpose |
|---|---|
| `optimize` | Run the optimization loop. |
| `score` | Score one artifact with an evaluator. |
| `analyze` | Discover quality dimensions for an artifact and objective. |
| `validate` | Score one artifact with 2 or more judge providers and report mean, stddev, min, and max. |
| `generate-evaluator` | Scaffold an evaluator script (`judge`, `command`, `http`, or `composite`). |
| `intake` | Normalize and validate an intake spec. |
| `explain` | Preview the optimization plan without running it. |
| `budget` | Recommend an iteration budget for a seed. |

Run `optimize-anything <command> --help` for every flag.

## Common workflows

### Datasets and held-out validation

`--dataset` runs one evaluator call per example. Add `--valset` to measure generalization on examples the optimizer never trained on.

```bash
optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Generalize across customer request types" \
  --dataset data/train.jsonl \
  --valset data/val.jsonl \
  --model openai/gpt-5.6-sol \
  --budget 120 --workers 6 --cache --run-dir runs
```

Each dataset line is one JSON object. The evaluator receives it as `example`.

### Cross-provider validation

Check that one artifact scores consistently across judges:

```bash
optimize-anything validate result.txt \
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score clarity, constraints, and robustness" \
  --intake-file intake.json
```

A provider whose judge call fails reports `score: null` and is left out of the statistics. Gemini uses LiteLLM's `gemini/` prefix.

### Seedless mode

Start from an objective alone. `--no-seed` requires `--objective` and `--model`.

```bash
optimize-anything optimize --no-seed \
  --objective "Draft a concise, testable API prompt" \
  --model openai/gpt-5.6-sol \
  --judge-model openai/gpt-5.6-luna
```

### Budget, early stopping, caching, and parallelism

- Early stopping turns on automatically when `--budget` is above 30. Force it with `--early-stop`, and tune it with `--early-stop-window` and `--early-stop-threshold`.
- `--cache` stores evaluator results. `--cache-from <run-dir>` copies the fitness cache of an earlier run (it requires `--cache` and `--run-dir`).
- Evaluator calls run in parallel by default. Pass `--no-parallel` for evaluators that write shared temp files, use process-global state, or need strict rate-limit control. `--workers` caps concurrency.
- `--proposals-per-iteration N` asks GEPA for `N` mutations per iteration from the selected parent. It is independent of `--workers` and defaults to 1.

Proposal fan-out adds reflection and evaluation work. GEPA checks the budget between iterations, so the final iteration can exceed `--budget` after its work is scheduled.

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash eval.sh \
  --model openai/gpt-5.6-sol \
  --budget 150 \
  --cache --cache-from runs/run-20260303-120000 \
  --run-dir runs \
  --early-stop --early-stop-window 12 --early-stop-threshold 0.003
```

### Intake

Intake is optional structured guidance for evaluation. Declare quality dimensions, hard constraints, an evaluation pattern, and execution preferences instead of relying on `--objective` alone. Use it when criteria have several dimensions, when constraints are absolute, or when you need consistent scoring across runs.

```bash
# Inline
optimize-anything optimize seed.txt \
  --intake-json '{"quality_dimensions": [{"name": "clarity", "weight": 0.6}, {"name": "specificity", "weight": 0.4}], "hard_constraints": ["max 100 words"]}' \
  --judge-model openai/gpt-5.6-luna

# From file
optimize-anything optimize seed.txt \
  --intake-file intake.json \
  --judge-model openai/gpt-5.6-luna
```

Intake keys:

- `artifact_class`
- `quality_dimensions` (each may add optional `levels`: 2 to 10 rubric strings, lowest to highest, used by `--jev-model`; in one ground-truth test they did not beat the generic scale, see `docs/verification/jev-judge-ab-2026-10-17.md`)
- `hard_constraints`
- `evaluation_pattern`
- `execution_mode`
- `evaluator_cwd`

`execution_mode` (`command` or `http`) is the transport. `evaluation_pattern` (`verification`, `judge`, `simulation`, or `composite`) is the scoring strategy. They are independent.

## Codex and Claude subscription backends

Local Codex and Claude Code logins can power the proposer and the built-in judge without API keys. Selection is explicit. Without backend flags, calls use the LiteLLM API.

```bash
# Codex: install the pinned SDK adapter, then sign in with ChatGPT.
uv sync --extra codex
codex login
optimize-anything optimize seed.txt \
  --proposer-backend codex --judge-backend codex \
  --objective "Improve clarity"

# Claude Code: install and sign in to the claude CLI first.
optimize-anything optimize seed.txt \
  --proposer-backend claude --judge-backend claude \
  --objective "Improve clarity"
```

- Single-role commands use `--analysis-backend` (`analyze`) or `--judge-backend` (`score`). `validate --providers` also accepts `codex`, `codex:<model>`, `claude`, and `claude:<model>`.
- Structured TOML spec files set roles with tables such as `[model.proposer] backend = "codex"` and `[model.judge] backend = "claude"`.
- Subscription calls are serialized per provider by default (`--subscription-concurrency 1`).
- A failed subscription call can fall back to a same-vendor API only when a matching key and fallback model exist. The CLI prints a billing warning first. `--no-api-fallback` makes every subscription failure final.
- Claude support is local-only and experimental. Use of a subscription through a third-party tool carries provider-policy risk.
- Each call runs in an empty temporary workspace with no repository context, tools, or MCP servers.

[install.md](install.md#optional-local-subscription-backends) has supported versions, the fallback rules, data handling, and removal steps.

## Agent plugins

The Claude Code and Codex plugins share one `skills/` tree and one locked runtime.

### Skills

| Skill | Use it to |
|---|---|
| **optimize-prompt** | Build a rubric, pick fast or rigorous evidence, optimize outside the source, and return or safely apply an accepted prompt. |
| **optimization-guide** | Walk through modes, configuration, budget, and result interpretation. |
| **generate-evaluator** | Choose an evaluator pattern (judge, command, composite) and generate the script. |
| **evaluator-patterns** | Start from ready-made evaluator templates for prompts, code, docs, and agent instructions. |

Claude Code users invoke `$optimize-prompt`. Codex users invoke `$optimize-anything:optimize-prompt`.

### Prompt optimization

`optimize-prompt` accepts prompt text, a standalone file, an embedded prompt region, or a list of independent prompt files.

| Evidence mode | Evaluation | What it proves |
|---|---|---|
| **Fast mode** | Scores the prompt text for clarity, constraints, and task fitness | Prompt-quality evidence only |
| **Rigorous mode** | Runs the candidate on representative inputs, then scores the task outputs | Task-performance evidence for the tested examples |
| **Composite mode** | Runs deterministic hard constraints before the rigorous judge | No subjective score can override a failed gate |

Rigorous datasets are JSONL records with `input`, and optional `expected`, `criteria`, and `hard_constraints`. See [`prompt-execution-dataset.md`](skills/optimize-prompt/references/prompt-execution-dataset.md) for examples, the default system-prompt adapter, custom adapters, and cost controls. Use explicit proposer, target, and judge models, and bound calls with a small dataset, a budget, and early stopping.

The workflow captures a baseline and writes search output to a temporary or run directory. It accepts a candidate only when the comparable score improves, every hard constraint holds, and (in rigorous mode) held-out acceptance passes. Independent prompt files get separate decisions. Coupled components need an explicit structured-candidate adapter and are not optimized as unrelated files.

```text
$optimize-prompt Improve this prompt in fast mode and return the accepted result:
"Summarize this."
```

An inline prompt returns the full accepted prompt, the evidence mode, and the score delta. It does not write a file.

```text
$optimize-prompt Optimize SYSTEM_PROMPT in src/agent.py with the examples in
evals/prompt.jsonl. Apply it only if held-out acceptance passes.
```

For an embedded prompt, the workflow optimizes a captured copy, replaces only `SYSTEM_PROMPT`, keeps the source representation, and runs the cheapest relevant parse or test. A rejected candidate leaves the file unchanged.

### Slash commands (Claude Code)

| Command | Purpose |
|---|---|
| `/optimize-anything:optimize` | Guided workflow: mode, evaluator setup, execution, results |
| `/optimize-anything:quick` | Zero-config one-shot optimization from a file and an objective |
| `/optimize-anything:analyze` | Discover quality dimensions |
| `/optimize-anything:score` | Score one artifact |
| `/optimize-anything:validate` | Cross-validate with multiple LLM judges |
| `/optimize-anything:compare` | Compare two artifacts side by side |
| `/optimize-anything:budget` | Recommend a budget |
| `/optimize-anything:explain` | Preview the plan without running it |
| `/optimize-anything:intake` | Normalize and validate an intake spec |

A typical session:

```text
/optimize-anything:analyze prompt.txt --objective "Score clarity"
/optimize-anything:quick prompt.txt "improve clarity and specificity"
/optimize-anything:validate result.txt --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash
```

## Reference

### Result contract

`optimize` prints a JSON summary with these fields:

- `best_artifact`
- `total_metric_calls`
- `score_summary` (`initial`, `latest`, `best`, deltas, `num_candidates`)
- `top_diagnostics` (a list of `{name, value}`)
- `plateau_detected`, `plateau_guidance`
- `evaluator_failure_signal` (optional)
- `early_stopped`, `stopped_at_iteration` (optional)
- `budget_utilization` (`requested`, `evaluator_calls`, `candidates_accepted`, `efficiency`)

`num_candidates` counts retained candidates. It does not count every evaluated proposal.

If every proposer call fails, `optimize` exits 1 with `Error: all N proposer call(s) failed`. The summary, run directory, and `-o` output are still written.

### Evaluator payload

```json
{"_protocol_version": 2, "candidate": "...", "example": {...}, "task_model": "..."}
```

`candidate` is always present. `example` appears only with `--dataset`. `task_model` appears only with `--task-model`. Evaluators may ignore any key they do not use. Details: [PROTOCOL.md](PROTOCOL.md).

### `optimize` flags

Exactly one evaluator source is required: `--evaluator-command`, `--evaluator-url`, a built-in judge (`--judge-model` or `--judge-backend`), or `--jev-model`.

| Flag | Description | Default |
|---|---|---|
| `--no-seed` | Run without a seed file; bootstrap from the objective | `false` |
| `--evaluator-command <cmd...>` | Command evaluator (stdin and stdout JSON) | -- |
| `--evaluator-url <url>` | HTTP evaluator endpoint | -- |
| `--intake-json <json>` | Inline intake spec | -- |
| `--intake-file <path>` | Intake spec file | -- |
| `--evaluator-cwd <path>` | Working directory for a command evaluator | -- |
| `--objective <text>` | Optimization objective | -- |
| `--background <text>` | Extra domain context | -- |
| `--dataset <train.jsonl>` | Training dataset | -- |
| `--valset <val.jsonl>` | Validation dataset (requires `--dataset`) | -- |
| `--budget <int>` | Maximum evaluator calls | `100` |
| `--output, -o <file>` | Write the best artifact to a file | -- |
| `--model <model>` | Proposer model | `OPTIMIZE_ANYTHING_MODEL`, then `openai/gpt-5.6-sol` |
| `--proposer-backend api\|codex\|claude` | Proposal backend | `api` |
| `--judge-model <model>` | Built-in LLM judge model | -- |
| `--jev-model <model>` | TypeSafe Jev evaluator, such as `jev-latest` (needs `TYPESAFE_API_KEY`) | -- |
| `--judge-backend api\|codex\|claude` | Built-in judge backend | `api` |
| `--subscription-concurrency <int>` | Concurrent calls per subscription provider | `1` |
| `--no-api-fallback` | Forbid subscription-to-API fallback | `false` |
| `--openai-api-fallback-model <model>` | Same-vendor API fallback for Codex | -- |
| `--anthropic-api-fallback-model <model>` | Same-vendor API fallback for Claude | -- |
| `--judge-objective <text>` | Judge objective override | `--objective` |
| `--api-base <url>` | LiteLLM API base override | -- |
| `--diff` | Print a unified diff (seed vs best) to stderr | `false` |
| `--run-dir <path>` | Save run artifacts in a timestamped directory | -- |
| `--parallel` | Enable parallel evaluator calls | `true` |
| `--no-parallel` | Run evaluator calls serially | -- |
| `--workers <int>` | Maximum parallel workers | -- |
| `--proposals-per-iteration <int>` | Candidate mutations per iteration | `1` |
| `--cache` | Enable the evaluator cache | `false` |
| `--cache-from <run-dir>` | Copy a prior run's `fitness_cache` | -- |
| `--early-stop` | Enable plateau early stopping | on when budget > 30 |
| `--early-stop-window <int>` | Plateau window size | `10` |
| `--early-stop-threshold <float>` | Minimum improvement over the window | `0.005` |
| `--spec-file <path>` | Load TOML spec defaults | -- |
| `--task-model <model>` | Metadata forwarded to evaluators | -- |
| `--score-range unit\|any` | Score validation for command and HTTP evaluators | `unit` |

## Development

```bash
uv sync
uv run pytest
uv run python scripts/check.py --skip-smoke   # offline gate
```

[AGENTS.md](AGENTS.md) describes the repository layout, the quality gates, and the maintainer workflows (smoke gates, live gates, plugin regression, and the optimization observability benchmark).

## More documentation

- [install.md](install.md): install, update, remove, and verify
- [WALKTHROUGH.md](WALKTHROUGH.md): step-by-step first run
- [EXAMPLES.md](EXAMPLES.md): CLI examples
- [CONCEPTS.md](CONCEPTS.md): terms and modes
- [PROTOCOL.md](PROTOCOL.md): evaluator contract
- [evaluator-cookbook.md](evaluator-cookbook.md): evaluator recipes
- [CHANGELOG.md](CHANGELOG.md): release history

## License

[MIT](LICENSE)
