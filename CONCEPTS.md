# CONCEPTS

Core concepts for optimize-anything v2.

## Artifact

The text being optimized (prompt, config, docs, code, etc.).

## Evaluator

A scorer that returns JSON with required `score` plus optional diagnostics.
Runtime options:
- Command (`--evaluator-command`)
- HTTP (`--evaluator-url`)
- LLM Judge (`--judge-model`)

## Evaluator Protocol v2

Evaluator input is additive and backward-compatible:

```json
{"_protocol_version": 2, "candidate": "...", "example": {...}, "task_model": "..."}
```

- `candidate` required
- `_protocol_version`, `example`, and `task_model` optional
- Existing evaluators that only consume `candidate` still work

Evaluator output (unchanged):

```json
{"score": 0.73, "reasoning": "..."}
```

## Multi-task mode

Enabled by `--dataset`. Each candidate is evaluated across dataset examples (`example` payload populated per call).

## Generalization mode

Enabled by `--dataset` + `--valset`. Train set drives optimization; valset is used for out-of-sample validation aggregate.

## Early Stopping

Plateau-based termination of optimization before full budget is spent.
- Enable manually with `--early-stop`
- Auto-enabled when `--budget > 30`
- Tuned by `--early-stop-window` and `--early-stop-threshold`

## Cache Reuse

Evaluator results can be cached (`--cache`) and warm-started from a previous run via `--cache-from <run-dir>`.
This reduces repeated evaluator work across similar reruns.

## Seedless Mode

`--no-seed` runs optimization without an input seed file.
Requires both:
- `--objective`
- `--model`

## Score Range

Controls validation rules for command/HTTP evaluator scores:
- `unit` (default): score must be finite and within `[0,1]`
- `any`: score must be finite float (unbounded)

## Task Model metadata

`--task-model` is optional metadata forwarded into protocol payload and (for command evaluators) environment variables. It identifies the model context being optimized for.

## Intake Specification

Optional structured evaluator guidance (`--intake-json` / `--intake-file`) including:
- `artifact_class`
- `quality_dimensions`
- `hard_constraints`
- `evaluation_pattern`
- `execution_mode`
- `evaluator_cwd`

## Evaluation Pattern vs Execution Mode

These are independent axes:

| Concept | Purpose | Values |
|---|---|---|
| `execution_mode` | Transport/runtime | `command`, `http` |
| `evaluation_pattern` | Scoring strategy intent | `verification`, `judge`, `simulation`, `composite` |

## Result contract

`optimize` returns a normalized summary including:
- `best_artifact`
- `total_metric_calls`
- `score_summary`
- `top_diagnostics` (list of `{name, value}`)
- `plateau_detected`, `plateau_guidance`
- optional `evaluator_failure_signal`
- optional `early_stopped`, `stopped_at_iteration`
