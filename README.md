# optimize-anything

LLM-guided optimization for text artifacts using an iterative propose-evaluate-reflect loop with a bring-your-own evaluator.

## Quickstart (v2)

```bash
# 1) Install
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash

# 2) Create a seed artifact
echo "Write a concise support prompt" > seed.txt

# 3) Generate a starter evaluator (default: judge/python template)
optimize-anything generate-evaluator seed.txt \
  --objective "Score clarity, actionability, and specificity" \
  > eval.py

# 4) Optimize
optimize-anything optimize seed.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Improve clarity and specificity" \
  --model openai/gpt-4o-mini \
  --budget 20 \
  --parallel --workers 4 \
  --cache \
  --run-dir runs \
  --output result.txt
```

CLI stdout returns a JSON summary using the current result contract:
- `best_artifact`
- `total_metric_calls`
- `score_summary` (`initial`, `latest`, `best`, deltas, `num_candidates`)
- `top_diagnostics` (**list** of `{name, value}`)
- `plateau_detected`, `plateau_guidance`
- optional `evaluator_failure_signal`
- optional `early_stopped`, `stopped_at_iteration`

## Evaluator Contract (Protocol v2)

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

## v2 Runtime Modes

### Intake schema keys

`optimize-anything intake` normalizes these keys:
- `artifact_class`
- `quality_dimensions`
- `hard_constraints`
- `evaluation_pattern`
- `execution_mode`
- `evaluator_cwd`

### Dataset / Valset modes

Use `--dataset` for multi-task optimization (one evaluator call per example). Add `--valset` for generalization validation.

```bash
optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Generalize across customer request types" \
  --dataset data/train.jsonl \
  --valset data/val.jsonl \
  --model openai/gpt-4o-mini \
  --budget 120 --parallel --workers 6 --cache --run-dir runs
```

### Multi-provider validation

Cross-check one artifact with multiple judge providers:

```bash
optimize-anything validate result.txt \
  --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5 google/gemini-2.0-flash \
  --objective "Score clarity, constraints, and robustness" \
  --intake-file intake.json
```

### Seedless mode

No seed file required; GEPA bootstraps from objective.

```bash
optimize-anything optimize --no-seed \
  --objective "Draft a concise, testable API prompt" \
  --model openai/gpt-4o-mini \
  --judge-model openai/gpt-4o-mini
```

`--no-seed` requires both `--objective` and `--model`.

### Early stopping and cache reuse

- Early stop is auto-enabled when `--budget > 30` (or force with `--early-stop`)
- Reuse prior evaluator cache with `--cache-from` (requires `--cache` + `--run-dir`)

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash eval.sh \
  --model openai/gpt-4o-mini \
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
  --model openai/gpt-4o-mini \
  --score-range any
```

## CLI Subcommands

- `optimize`
- `generate-evaluator`
- `intake`
- `explain`
- `budget`
- `score`
- `analyze`
- `validate`

## `optimize` flags (complete)

Exactly one evaluator source is required: `--evaluator-command` OR `--evaluator-url` OR `--judge-model`.

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
| `--model <model>` | Proposer model (or env fallback) | `OPTIMIZE_ANYTHING_MODEL` |
| `--judge-model <model>` | Built-in LLM judge evaluator model | -- |
| `--judge-objective <text>` | Judge objective override | falls back to `--objective` |
| `--api-base <url>` | Override LiteLLM API base | -- |
| `--diff` | Print unified diff (seed vs best) to stderr | `false` |
| `--run-dir <path>` | Save run artifacts in timestamped run dir | -- |
| `--parallel` | Enable parallel evaluator calls | `false` |
| `--workers <int>` | Max workers for parallel evaluation | -- |
| `--cache` | Enable evaluator cache | `false` |
| `--cache-from <run-dir>` | Copy prior `fitness_cache` into new run | -- |
| `--early-stop` | Enable plateau early stop | auto on when budget > 30 |
| `--early-stop-window <int>` | Plateau window size | `10` |
| `--early-stop-threshold <float>` | Min improvement required over window | `0.005` |
| `--spec-file <path>` | Load TOML spec defaults | -- |
| `--task-model <model>` | Optional metadata forwarded to evaluators | -- |
| `--score-range unit|any` | Score validation mode for cmd/http | `unit` |

## Learn More

- [EXAMPLES.md](EXAMPLES.md)
- [WALKTHROUGH.md](WALKTHROUGH.md)
- [CONCEPTS.md](CONCEPTS.md)
- [PROTOCOL.md](PROTOCOL.md)
