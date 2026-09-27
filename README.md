# optimize-anything

LLM-guided optimization for text artifacts using an iterative propose-evaluate-reflect loop with a bring-your-own evaluator.

## Quickstart (v2)

```bash
# 1) Install
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash

# 2) Create a seed artifact
echo "Write a concise support prompt" > seed.txt

# 3) Optimize with the built-in LLM judge
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

CLI stdout returns a JSON summary — see [Result Contract](#result-contract) for the full shape.

### Model defaults

The proposer defaults to `openai/gpt-5.6-sol` after checking `--model` and `OPTIMIZE_ANYTHING_MODEL`. Generated judge and composite evaluators default to `openai/gpt-5.6-luna`. LLM judge calls use each provider's sampling defaults unless an explicit temperature is supplied.

### LLM API authentication

Export the API key for every provider selected by `--model`, `--judge-model`,
or `--providers` before launching the CLI or plugin host:

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

The default proposer and judge require `OPENAI_API_KEY`. Multi-provider
validation requires each selected provider's key; Gemini also accepts
`GOOGLE_API_KEY`. Claude Code or Codex login is separate from provider API
authentication. Plugin installation does not store credentials, so export keys
before launching the host and restart it after changes. `--api-base` changes the
endpoint but does not select a provider or its credentials. Do not commit API
keys or `.env` files.

## How It Works

optimize-anything runs a GEPA (Guided Evolutionary Prompt Algorithm) loop: propose → evaluate → reflect, repeating until budget is exhausted or early stopping kicks in.

```
seed.txt ──► [Propose] ──► candidates
                 ▲               │
                 │           [Evaluate]
             [Reflect] ◄──── scores + diagnostics
```

1. **Propose** — The optimizer generates candidate artifacts from your seed (or from scratch in seedless mode).
2. **Evaluate** — Each candidate is scored by your evaluator. Three evaluator types are supported: a **command evaluator** (any executable that reads JSON on stdin and writes a score on stdout), an **HTTP evaluator** (a service that accepts POST requests), or a built-in **LLM judge** (no evaluator script required — just pass `--judge-model`).
3. **Reflect** — Scores and diagnostics feed back into the next proposal round. The loop continues, progressively improving the artifact toward your objective.

The evaluator is the only thing you bring. Everything else — proposal strategy, reflection, early stopping, caching, parallelism — is handled by the optimizer.

## Runtime Modes

### Dataset / Valset modes

Use `--dataset` for multi-task optimization (one evaluator call per example). Add `--valset` for generalization validation.

```bash
optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Generalize across customer request types" \
  --dataset data/train.jsonl \
  --valset data/val.jsonl \
  --model openai/gpt-5.6-sol \
  --budget 120 --workers 6 --cache --run-dir runs
```

### Multi-provider validation

Cross-check one artifact with multiple judge providers:

```bash
optimize-anything validate result.txt \
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score clarity, constraints, and robustness" \
  --intake-file intake.json
```

Gemini uses LiteLLM's `gemini/` provider prefix.

### Seedless mode

No seed file required; GEPA bootstraps from objective.

```bash
optimize-anything optimize --no-seed \
  --objective "Draft a concise, testable API prompt" \
  --model openai/gpt-5.6-sol \
  --judge-model openai/gpt-5.6-luna
```

`--no-seed` requires both `--objective` and `--model`.

### Early stopping and cache reuse

- Early stop is auto-enabled when `--budget > 30` (or force with `--early-stop`)
- Reuse prior evaluator cache with `--cache-from` (requires `--cache` + `--run-dir`)
- Evaluator calls run in parallel by default; pass `--no-parallel` for evaluators
  that write shared temp files, depend on process-global state, or need strict
  provider rate-limit control.
- `--proposals-per-iteration N` asks GEPA to generate `N` mutations from the
  selected parent each iteration. It is independent of `--workers`, which only
  controls concurrent evaluator calls, and defaults to one proposal.

Proposal fan-out increases reflection and evaluation work. Small training sets
may reuse the same minibatch across proposals, and GEPA checks the metric-call
budget between iterations, so the final iteration can exceed `--budget` after
its work has been scheduled.

GEPA 0.1.4 can migrate older run state forward. State written by 0.1.4 is not
expected to load under 0.1.1 after a rollback; `--cache-from` remains limited
to copying the prior fitness cache.

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash eval.sh \
  --model openai/gpt-5.6-sol \
  --budget 150 \
  --cache --cache-from runs/run-20260303-120000 \
  --run-dir runs \
  --early-stop --early-stop-window 12 --early-stop-threshold 0.003
```

### Score range options

For command/HTTP evaluators:
- `--score-range unit` (default): enforce score in `[0, 1]`
- `--score-range any`: allow any finite float

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash eval.sh \
  --model openai/gpt-5.6-sol \
  --score-range any
```

### Optimization observability benchmark

Use the maintainer benchmark when you want evidence that an optimization loop
improved a useful artifact and was not just a seed-only or scorer-gaming run.

```bash
uv run python scripts/optimization_observer.py setup
uv run python scripts/optimization_observer.py report \
  --run-dir integration_runs/optimization-observability/evaluator-generation-guidance/runs/run-YYYYMMDD-HHMMSS \
  --benchmark examples/optimization-observability/evaluator-generation-benchmark.json \
  --strict
```

See `examples/optimization-observability/README.md` for the full benchmark
commands, expected report fields, acceptance criteria, and troubleshooting.

## CLI Subcommands

- `optimize`
- `generate-evaluator`
- `intake`
- `explain`
- `budget`
- `score`
- `analyze`
- `validate`

## Codex and Claude subscription backends

Local Codex and Claude Code logins can power proposer and built-in evaluator
roles without API keys. Selection is explicit; omitting backend flags preserves
the existing LiteLLM API behavior.

```bash
# Install the pinned Codex SDK adapter, then authenticate with ChatGPT.
uv sync --extra codex
codex login

# Codex subscription: proposer plus built-in judge.
optimize-anything optimize seed.txt \
  --proposer-backend codex --judge-backend codex \
  --objective "Improve clarity"

# Claude Code subscription. Install/sign in to the claude CLI first.
optimize-anything optimize seed.txt \
  --proposer-backend claude --judge-backend claude \
  --objective "Improve clarity"
```

Subscription calls are serialized per provider by default. The CLI may switch
an eligible failure to a same-vendor API only when a matching key and fallback
model are available, and prints a billing warning first. Use
`--no-api-fallback` to prohibit that switch. Claude support is local-only and
experimental; neither adapter initiates login or copies credential contents.

Single-role commands use `--analysis-backend` (`analyze`) or
`--judge-backend` (`score`). `validate --providers` also accepts `codex`,
`codex:<model>`, `claude`, and `claude:<model>`. Structured TOML uses role
tables such as:

```toml
[model.proposer]
backend = "codex"
api_fallback = false

[model.judge]
backend = "claude"
api_fallback_model = "anthropic/claude-sonnet-5"
```

Rollout notes (details in [install.md](install.md#optional-local-subscription-backends)):

- **Supported versions:** `openai-codex>=0.156.0,<0.157.0` via
  `uv sync --extra codex`; Claude Code 2.1.278 or newer; macOS local
  machines only. Tested 2026-09-26 with openai-codex 0.156.0, Codex CLI
  0.155.1, and Claude Code 2.1.283 on macOS 26.6.2.
- **Claude scope:** experimental, opt-in, and local-only. Not supported for
  hosted services, CI, or shared daemons; subscription use through a
  third-party tool carries a provider-policy risk separate from technical
  support.
- **Billing and fallback:** only `backend_unavailable`, `authentication`,
  `rate_limit`, and `quota_exceeded` can fall back; `timeout`, `cancelled`,
  `invalid_response`, and `configuration` never do. Fallback stays with the
  same vendor, needs its key plus `--openai-api-fallback-model` /
  `--anthropic-api-fallback-model` (or a same-vendor role model), warns before
  dispatch, and opens a sticky per-role circuit for the rest of the run.
- **Data handling:** each call runs in an empty temporary workspace with no
  repository context, user instructions, tools, or MCP servers; prompts go
  over stdin or the SDK request body. Output records content-free
  `llm_provenance` (backend, model, auth class, usage, fallback reason), never
  account identity or secrets. Coordination state is a private run-scoped temp
  directory removed when the run ends.
- **Preflight and concurrency:** subscription roles are preflighted once and
  `optimize` prints a `Backend plan:` line. `--subscription-concurrency`
  defaults to `1`; other values print a warning.
- **Disable or remove:** omit the backend flags and TOML role tables to return
  to API defaults, run `uv sync` without `--extra codex` to drop the SDK, and
  use the plugin removal commands in [install.md](install.md).

Opt-in live gates consume local subscription quota:

```bash
OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1 \
  uv run pytest tests/test_subscription_live.py
```

The separate `OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE` gate bills the OpenAI
and Anthropic API accounts behind `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`:

```bash
OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1 \
  uv run pytest tests/test_api_fallback_live.py
```

## Agent Plugins

The Claude Code plugin and Codex plugin share the same `skills/` tree and
bundled locked runtime. Plugin users need `uv` and Python 3.10 or newer, but do
not need a global `optimize-anything` command. The standalone CLI remains a
separate installation choice.

### Prompt Optimization Workflow

Claude Code users invoke `$optimize-prompt`; Codex users invoke the namespaced
`$optimize-anything:optimize-prompt`. Both accept prompt text, a standalone
file, an embedded prompt region, or a list of independent prompt files.

| Evidence mode | Evaluation | What it proves |
|---|---|---|
| **Fast mode** | Scores the prompt text for clarity, constraints, and task fitness | Prompt-quality evidence only |
| **Rigorous mode** | Runs the candidate on representative inputs, then scores task outputs | Task-performance evidence for the tested examples |
| **Composite mode** | Runs deterministic hard constraints before the rigorous judge | No subjective score can override a failed gate |

Rigorous datasets use JSONL records with `input`, optional `expected`,
`criteria`, and `hard_constraints`. See
[`prompt-execution-dataset.md`](skills/optimize-prompt/references/prompt-execution-dataset.md)
for representative examples, the default system-prompt adapter, custom adapter
guidance, and expected cost controls. Use explicit proposer, target, and judge
models; bound calls with a small dataset, budget, and early stopping.

The workflow captures the baseline and writes search output to a temporary or
run directory. It accepts only a positive comparable score delta with all hard
constraints satisfied, plus required held-out acceptance in rigorous mode.
Independent prompt files receive separate decisions. Coupled components require
an explicit structured-candidate adapter and are not optimized as unrelated
files.

Inline example:

```text
$optimize-prompt Improve this prompt in fast mode and return the accepted result:
"Summarize this."
```

The response includes the complete accepted prompt, evidence mode, and score
delta; it does not write a repository file.

Embedded repository example:

```text
$optimize-prompt Optimize SYSTEM_PROMPT in src/agent.py with the examples in
evals/prompt.jsonl. Apply it only if held-out acceptance passes.
```

The workflow optimizes a captured copy, replaces only `SYSTEM_PROMPT`, preserves
the source representation, and runs the cheapest relevant parse or targeted
test. Rejected candidates leave the file unchanged.

### Plugin Regression Workflow

Use the regression harness when you want to verify that Claude can actually invoke the plugin correctly end-to-end, not merely that the CLI itself still works.

```bash
# Direct plugin regression run
uv run python scripts/plugin_regression.py

# Full repo validation including plugin regression
uv run python scripts/check.py --with-plugin
```

Requirements:
- `claude` CLI installed and authenticated
- `OPENAI_API_KEY` set in the shell that launches the command
- `ANTHROPIC_API_KEY` for `validate` or the full scenario set

The harness runs existing CLI scenarios plus bounded prompt inline-return and
repository-apply scenarios. `--dry-run` verifies prompt and artifact wiring
without credentials or model calls.

### Claude Code Plugin

```bash
/plugin marketplace add ASRagab/optimize-anything
/plugin install optimize-anything@optimize-anything
```

For a local clone, replace the repository name in the first command with its
absolute path. Restart Claude Code after installation or update, then invoke
`$optimize-prompt` or an existing slash command.

### Codex Plugin

```bash
codex plugin marketplace add ASRagab/optimize-anything
codex plugin add optimize-anything@optimize-anything
```

For local development, pass the clone path to `codex plugin marketplace add`.
Start a new Codex thread after install or update, then invoke
`$optimize-anything:optimize-prompt` so skill discovery refreshes.
See [install.md](install.md) for update, removal, verification, and the optional
standalone CLI path.

### Slash Commands

| Command | Description |
|---------|-------------|
| `/optimize-anything:optimize` | Guided optimization workflow — walks you through mode selection, evaluator setup, execution, and results |
| `/optimize-anything:quick` | Zero-config one-shot optimization. Just provide a file and objective. |
| `/optimize-anything:analyze` | Discover quality dimensions for an artifact and objective |
| `/optimize-anything:score` | Score a single artifact without optimization |
| `/optimize-anything:validate` | Cross-validate with multiple LLM judges |
| `/optimize-anything:compare` | Side-by-side comparison of two artifacts |
| `/optimize-anything:budget` | Get a budget recommendation for your artifact |
| `/optimize-anything:explain` | Preview the optimization plan without running it |
| `/optimize-anything:intake` | Normalize and validate an intake specification |

### Skills

Both plugins include four skills that the host can invoke:

- **optimize-prompt** — Build the rubric, choose fast or rigorous evidence, optimize outside the source, and return or safely apply an accepted prompt
- **optimization-guide** — Full workflow walkthrough covering modes, configuration, budget, and result interpretation
- **generate-evaluator** — Choose the right evaluator pattern (judge, command, composite) and generate a script
- **evaluator-patterns** — Library of ready-to-use evaluator templates for prompts, code, docs, and agent instructions

### Typical Plugin Workflow

```
/optimize-anything:analyze prompt.txt --objective "Score clarity"
  → discovers quality dimensions

/optimize-anything:quick prompt.txt "improve clarity and specificity"
  → runs analyze + optimize with sensible defaults, shows diff

/optimize-anything:validate result.txt --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash
  → cross-checks the result with multiple judges
```

## Reference

### Result Contract

CLI stdout returns a JSON summary with these fields:

- `best_artifact`
- `total_metric_calls`
- `score_summary` (`initial`, `latest`, `best`, deltas, `num_candidates`)
- `top_diagnostics` (**list** of `{name, value}`)
- `plateau_detected`, `plateau_guidance`
- optional `evaluator_failure_signal`
- optional `early_stopped`, `stopped_at_iteration`
- `budget_utilization` (`requested`, `evaluator_calls`, `candidates_accepted`, `efficiency`)

### Evaluator Protocol (v2)

Evaluator input payload (stdin JSON for command mode, POST JSON for HTTP mode):

```json
{"_protocol_version": 2, "candidate": "...", "example": {...}, "task_model": "..."}
```

- `candidate` is required
- `_protocol_version`, `example`, and `task_model` are optional/additive
- legacy evaluators that only read `candidate` remain compatible

Evaluator output payload:

```json
{"score": 0.75, "notes": "optional diagnostics"}
```

- `score` is required
- additional keys are treated as side-info

### Intake

Intake is optional structured guidance you pass to the optimizer to shape how evaluation works. Instead of relying solely on an `--objective` string, intake lets you declare quality dimensions, hard constraints, evaluation patterns, and execution preferences — giving you finer control over what "better" means for your artifact.

Use intake when your evaluation criteria are multi-dimensional, when you need to enforce hard constraints, or when you want consistent evaluation behavior across runs.

Pass it inline or from a file:

```bash
# Inline
optimize-anything optimize seed.txt \
  --intake-json '{"quality_dimensions": ["clarity", "specificity"], "hard_constraints": ["max 100 words"]}' \
  --judge-model openai/gpt-5.6-luna

# From file
optimize-anything optimize seed.txt \
  --intake-file intake.json \
  --judge-model openai/gpt-5.6-luna
```

`optimize-anything intake` normalizes and validates these keys:

- `artifact_class`
- `quality_dimensions`
- `hard_constraints`
- `evaluation_pattern`
- `execution_mode`
- `evaluator_cwd`

### `optimize` flags (complete)

Exactly one evaluator source is required: `--evaluator-command` OR `--evaluator-url` OR a built-in judge selected by `--judge-model`/`--judge-backend`.

| Flag | Description | Default |
|---|---|---|
| `--no-seed` | Run without seed file; bootstrap from objective | `false` |
| `--evaluator-command <cmd...>` | Command evaluator (stdin/stdout JSON) | -- |
| `--evaluator-url <url>` | HTTP evaluator endpoint | -- |
| `--intake-json <json>` | Inline intake spec | -- |
| `--intake-file <path>` | Intake spec file | -- |
| `--evaluator-cwd <path>` | Working dir for command evaluator | -- |
| `--objective <text>` | Optimization objective | -- |
| `--background <text>` | Extra domain context | -- |
| `--dataset <train.jsonl>` | Training dataset JSONL | -- |
| `--valset <val.jsonl>` | Validation dataset JSONL (requires `--dataset`) | -- |
| `--budget <int>` | Max evaluator calls | `100` |
| `--output, -o <file>` | Write best artifact to file | -- |
| `--model <model>` | Proposer model (or env fallback) | `OPTIMIZE_ANYTHING_MODEL`, then `openai/gpt-5.6-sol` |
| `--proposer-backend api\|codex\|claude` | Proposal backend | `api` |
| `--judge-model <model>` | Built-in LLM judge evaluator model | -- |
| `--judge-backend api\|codex\|claude` | Built-in judge backend | `api` |
| `--subscription-concurrency <int>` | Concurrent calls allowed per subscription provider | `1` |
| `--no-api-fallback` | Prohibit subscription-to-API fallback | `false` |
| `--openai-api-fallback-model <model>` | Same-vendor API fallback for Codex | -- |
| `--anthropic-api-fallback-model <model>` | Same-vendor API fallback for Claude | -- |
| `--judge-objective <text>` | Judge objective override | falls back to `--objective` |
| `--api-base <url>` | Override LiteLLM API base | -- |
| `--diff` | Print unified diff (seed vs best) to stderr | `false` |
| `--run-dir <path>` | Save run artifacts in timestamped run dir | -- |
| `--parallel` | Explicitly enable parallel evaluator calls | `true` |
| `--no-parallel` | Run evaluator calls serially | -- |
| `--workers <int>` | Max workers for parallel evaluation | -- |
| `--proposals-per-iteration <int>` | Candidate mutations per iteration; independent of evaluator workers | `1` |
| `--cache` | Enable evaluator cache | `false` |
| `--cache-from <run-dir>` | Copy prior `fitness_cache` into new run | -- |
| `--early-stop` | Enable plateau early stop | auto on when budget > 30 |
| `--early-stop-window <int>` | Plateau window size | `10` |
| `--early-stop-threshold <float>` | Min improvement required over window | `0.005` |
| `--spec-file <path>` | Load TOML spec defaults | -- |
| `--task-model <model>` | Optional metadata forwarded to evaluators | -- |
| `--score-range unit\|any` | Score validation mode for cmd/http | `unit` |

## Learn More

- [EXAMPLES.md](EXAMPLES.md)
- [WALKTHROUGH.md](WALKTHROUGH.md)
- [CONCEPTS.md](CONCEPTS.md)
- [PROTOCOL.md](PROTOCOL.md)
