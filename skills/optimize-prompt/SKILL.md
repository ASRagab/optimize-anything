---
name: optimize-prompt
description: Optimize an inline prompt, standalone prompt file, embedded prompt region, or independent prompt batch with optimize-anything; use when a prompt needs rubric construction, measured iteration, safe acceptance, or targeted repository application.
---

# Optimize a Prompt

Improve prompt text with the existing `optimize-anything` runtime. Keep source
files unchanged until a candidate passes the selected evidence contract.

## Resolve the bundled runtime

Locate this `SKILL.md`, then derive these paths from its installed location:

```bash
OPTIMIZE_PROMPT_SKILL_DIR="/absolute/path/to/skills/optimize-prompt"
OPTIMIZE_ANYTHING_ROOT="$(cd "$OPTIMIZE_PROMPT_SKILL_DIR/../.." && pwd)"
OPTIMIZE_ANYTHING_RUNNER="$OPTIMIZE_ANYTHING_ROOT/scripts/run-optimize-anything"
```

Invoke every CLI subcommand through `$OPTIMIZE_ANYTHING_RUNNER`. Do not assume
a global `optimize-anything` executable exists. The launcher requires `uv` and
Python 3.10 or newer; model-backed modes also require the relevant credentials.

## 1. Capture the source and destination

Classify the request before optimizing:

- **Inline:** capture the exact delimited prompt and return an accepted result
  in the conversation. Do not create a repository destination.
- **Standalone file:** capture the full file as the seed and record the path as
  the possible destination.
- **Embedded region:** capture only the named string, symbol, or exact region.
  Record its delimiters, indentation, escaping, and surrounding source needed
  for a targeted replacement.
- **Independent batch:** create one run and acceptance decision per file. Reuse
  the evaluation contract only where the objective and constraints match.

If more than one source is plausible, ask the user to identify it. If prompt
components must evolve together, do not optimize them independently. Require an
explicit structured-candidate adapter or report that joint optimization is not
supported by this workflow.

Copy the captured baseline into a temporary directory. Never use a repository
source file as `--output` or modify it during search.

## 2. Establish the evaluation contract

Record these values before optimization:

1. Objective and target task.
2. Weighted quality dimensions.
3. Machine-checkable hard constraints.
4. Fast, rigorous, or composite evidence mode.
5. Proposer model and budget.
6. Judge model or evaluator command.
7. Target task model and representative examples for rigorous modes.
8. Optional held-out set and minimum acceptance delta.

Infer values from the prompt, surrounding code, schemas, tests, and the user's
request when they are clear. Ask only when the target task, required output
contract, non-negotiable constraint, model, or spend limit would change the
evaluation.

Use the bundled runner to compose existing analysis and intake behavior:

```bash
"$OPTIMIZE_ANYTHING_RUNNER" analyze "$SEED_FILE" \
  --judge-model "$JUDGE_MODEL" --objective "$OBJECTIVE"
"$OPTIMIZE_ANYTHING_RUNNER" intake --intake-file "$INTAKE_FILE"
```

Save the `intake_json` returned by `analyze`, review its dimensions and hard
constraints, then normalize it with `intake`. Add deterministic checks for
placeholders, delimiters, schemas, required phrases, token ceilings, or project
tests when the repository exposes them.

## 3. Choose what the evidence proves

### Fast mode

Use fast mode for quick polish or when representative task examples are not
available. Score prompt clarity, specificity, constraint expression, and
apparent task fitness with the built-in prompt-text judge.

```bash
"$OPTIMIZE_ANYTHING_RUNNER" score "$SEED_FILE" \
  --judge-model "$JUDGE_MODEL" --objective "$OBJECTIVE" \
  --intake-file "$INTAKE_FILE"
"$OPTIMIZE_ANYTHING_RUNNER" optimize "$SEED_FILE" \
  --judge-model "$JUDGE_MODEL" --objective "$OBJECTIVE" \
  --intake-file "$INTAKE_FILE" --model "$PROPOSER_MODEL" \
  --budget "$BUDGET" --output "$CANDIDATE_FILE" --diff \
  --run-dir "$RUNS_DIR" --early-stop
"$OPTIMIZE_ANYTHING_RUNNER" score "$CANDIDATE_FILE" \
  --judge-model "$JUDGE_MODEL" --objective "$OBJECTIVE" \
  --intake-file "$INTAKE_FILE"
```

Use identical scoring arguments for baseline and candidate. Label every result
as **prompt-quality evidence**. Never claim that downstream task performance
improved from fast-mode scores alone.

When provider agreement is part of acceptance, run `validate` on both files
with the same provider list, objective, and intake. Report the score comparison,
unified diff, and any provider-specific regression; do not accept on aggregate
gain alone when a declared provider threshold fails.

### Rigorous mode

Use rigorous mode when representative inputs and a target model are available,
or when the user requests task-performance evidence. Read
[`references/prompt-execution-dataset.md`](references/prompt-execution-dataset.md),
build training JSONL, and build a separate held-out JSONL when required.

Use the bundled Protocol v2 evaluator. Put `--evaluator-command` last because it
captures all remaining command arguments:

```bash
JUDGE_MODEL="$JUDGE_MODEL" "$OPTIMIZE_ANYTHING_RUNNER" optimize "$SEED_FILE" \
  --objective "$OBJECTIVE" --intake-file "$INTAKE_FILE" \
  --dataset "$TRAIN_JSONL" --valset "$HELD_OUT_JSONL" \
  --task-model "$TASK_MODEL" --model "$PROPOSER_MODEL" \
  --budget "$BUDGET" --output "$CANDIDATE_FILE" --diff \
  --run-dir "$RUNS_DIR" --early-stop --evaluator-cwd "$WORK_DIR" \
  --evaluator-command uv run --project "$OPTIMIZE_ANYTHING_ROOT" --locked \
  python "$OPTIMIZE_PROMPT_SKILL_DIR/scripts/prompt_execution_evaluator.py"
```

Omit `--valset` only when held-out acceptance is not part of the declared
contract. The default adapter treats the candidate as a system prompt and
`example.input` as the user input. For another prompt shape, copy the evaluator
into the temporary work directory and change only its target-message adapter;
keep Protocol v2, preflight, hard gates, failure scores, and judge isolation.

### Composite mode

Use the rigorous evaluator with `example.hard_constraints`. Deterministic gates
run before subjective judging. A failed gate returns zero and remains
authoritative even if wording quality appears high.

## 4. Compare and accept

Keep the run directory's captured seed, best artifact, summary, diagnostics,
and diff. Compare the baseline and candidate under the same evaluator, dataset,
models, intake, and constraints.

Accept only when all declared rules pass:

- Score delta is positive and meets any configured minimum.
- Every hard constraint passes.
- Rigorous training evidence improves.
- Required held-out evidence meets its threshold and does not regress.
- Model or evaluator failures are not represented as improvement.

Reject train-only gains that fail held-out acceptance. Preserve the candidate
and diagnostics in the run directory, leave the source unchanged, and report
the next evaluator or prompt issue to address.

## 5. Deliver an accepted result

- **Inline:** return the complete prompt with the mode and score delta.
- **Standalone file:** when application was requested, confirm the file still
  matches the captured baseline, then replace only its contents.
- **Embedded region:** confirm the recorded region still matches the baseline,
  then replace only that region while preserving syntax, delimiters, escaping,
  indentation, and unrelated code.
- **Independent batch:** report baseline score, candidate score, delta,
  acceptance, run directory, and destination for every file.

After a repository edit, run the cheapest relevant parse, schema, import,
targeted test, lint, or type check. If it fails, repair the targeted region or
restore its captured baseline before returning. Never leave unrelated changes
or a known-broken source file.

On missing credentials, rate limits, target failures, judge failures, invalid
responses, or launcher prerequisites, report the failing stage and preserved
run artifacts. Do not modify the source prompt.
