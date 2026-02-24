# Concepts

Core concepts for understanding optimize-anything. For a hands-on tutorial, see [WALKTHROUGH.md](WALKTHROUGH.md).

## Artifact

The text being optimized. Can be a prompt, config, skill file, evaluator script, or any text where quality can be scored. Passed as a file path to the CLI.

## Evaluator

A function that scores an artifact candidate. Returns `{"score": <float>, ...}`. Three runtime modes:

- **Command** (`--evaluator-command`): shell script receiving JSON on stdin
- **HTTP** (`--evaluator-url`): endpoint receiving POST JSON
- **LLM judge** (`--judge-model`): litellm-backed model scoring against an objective

## Evaluator Protocol

- **Input:** `{"candidate": "<text>"}` via stdin (command) or POST body (HTTP)
- **Output:** JSON with required `score` key (0.0-1.0) and optional diagnostic keys
- Diagnostic keys become "Actionable Side Information" for gepa's reflection LM

## Evaluation Pattern vs Execution Mode

Two independent axes:

| Concept | What it answers | Values |
|---------|----------------|--------|
| `execution_mode` | How the evaluator runs (transport) | `command`, `http` |
| `evaluation_pattern` | What scoring strategy it implements (intent) | `verification`, `judge`, `simulation`, `composite` |

A verification evaluator can run as a command or HTTP endpoint. These are never conflated.

## gepa

The optimization engine. Runs propose/evaluate/reflect cycles to improve artifacts. Uses a proposer LLM to generate candidates and an evaluator to score them. Configure with `--model` (proposer) and `--budget` (max evaluator calls).

## Intake Specification

Schema describing what the evaluator expects: quality dimensions (with weights), hard constraints, evaluation pattern, and execution mode. Normalized by `intake.py`. Provide via `--intake-json` or `--intake-file`.

## Quality Dimensions

Named scoring axes (e.g., "clarity", "conciseness") with float weights that sum to 1.0. Used by the LLM judge for dimension-weighted scoring and by intake normalization.

## Hard Constraints

Boolean pass/fail conditions. If any constraint is violated, the LLM judge forces the score to 0.0 regardless of other dimensions.

## RED-GREEN-OBSERVER Cycle

An iterative optimization workflow orchestrated by `scripts/live_integration.py`:

- **GREEN:** Run gepa to optimize an artifact (proposer generates, evaluator scores)
- **RED:** Validate the result with multi-provider scoring (command + LLM judges)
- **OBSERVER:** Read the score matrix and decide: continue, adjust objective, or stop

## Score Baselines

Tracked in `scores.json`. The `score_check.py` script ensures artifacts don't regress below their baselines. Use `--update` to raise baselines after improvements.

## Spec File

A TOML file (`--spec-file`) that bundles optimization parameters (artifact path, evaluator, budget, objective) for repeatable runs. Loaded by `spec_loader.py`.
