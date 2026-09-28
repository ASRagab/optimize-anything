---
name: generate-evaluator
description: >-
  Create or write an evaluator script for scoring text artifacts, prompts, or configs
  during gepa optimization. Use when asked to build, scaffold, or generate an evaluator,
  scoring function, or judge for optimize-anything.
---

## Objective
Generate an evaluator that scores candidate artifacts for optimization with gepa. Include diagnostic feedback so reflections can improve weak dimensions.

## Resolve the bundled runtime

Locate this `SKILL.md` in the installed plugin, then set:

```bash
GENERATE_EVALUATOR_SKILL_DIR="/absolute/path/to/skills/generate-evaluator"
OPTIMIZE_ANYTHING_ROOT="$(cd "$GENERATE_EVALUATOR_SKILL_DIR/../.." && pwd)"
OPTIMIZE_ANYTHING_RUNNER="$OPTIMIZE_ANYTHING_ROOT/scripts/run-optimize-anything"
```

Use `$OPTIMIZE_ANYTHING_RUNNER` for every CLI call. The plugin does not require a
global `optimize-anything` command. For Codex subscription judging, run
`codex login` first; the launcher installs the locked `codex` SDK extra. In a
source checkout use `uv sync --extra codex`; a global CLI needs the SDK in its
tool environment. Use `--no-api-fallback` to prevent billed API fallback.

## Evaluator Contract
- Input JSON on stdin (`--evaluator-command`) or HTTP POST body (`--evaluator-url`)
- Default payload: `{"candidate": "<text>"}`
- Dataset-aware payload (`--dataset`): `{"candidate": "<text>", "example": {...}}`
- Output JSON must include `score` (float, usually in `[0,1]`), plus optional side-info fields.
- **Preflight detection** (command evaluators only): The CLI sends `"__optimize_anything_preflight__"` as the candidate text before optimization starts. Your evaluator should detect this and return immediately:
  ```python
  if candidate == "__optimize_anything_preflight__":
      print(json.dumps({"score": 0.5}))
      sys.exit(0)
  ```
  This avoids the 10-second preflight timeout for evaluators that make slow API calls.

## Choose an Evaluator Pattern

### 1) Judge (default)
`generate-evaluator` now defaults to `--evaluator-type judge`.
- Generates a Python litellm-based evaluator.
- Best for subjective quality scoring (clarity, tone, instruction quality).
- Supports `response_format={"type": "json_object"}` and includes dimension scores.

### 2) Command
`--evaluator-type command`
- Generates a bash evaluator scaffold.
- Best for deterministic local checks and CI/offline workflows.

### 3) HTTP
`--evaluator-type http`
- Generates a Python HTTP server evaluator scaffold.
- Useful when evaluator needs to run as a service.

### 4) Composite
`--evaluator-type composite`
- Generates a Python evaluator with:
  1. hard deterministic constraints (fast gate), then
  2. LLM judge scoring only if constraints pass.
- Constraint failure returns `score: 0.0`.

## Generation Flags
- `--evaluator-type judge|command|http|composite`
- `--model <litellm-model>`: hardcodes judge model into judge/composite scripts.
- `--judge-backend api|codex|claude`: configures the installed evaluator runtime.
- In Codex use `--judge-backend codex`; in Claude Code use `--judge-backend claude`.
  Unknown hosts omit it and keep the API default (`api`).
  Add `--no-api-fallback` when billed API fallback is not acceptable.
- `--dataset`: generate dataset-aware templates that read `example` and show how to use it in scoring.
- `--intake-json` / `--intake-file`: embed rubric/quality dimensions.

## Quick Start

Generate a judge evaluator and test it:

```bash
# Generate
"$OPTIMIZE_ANYTHING_RUNNER" generate-evaluator seed.txt \
  --objective "Score clarity and specificity" \
  --model openai/gpt-5.6-luna > eval_judge.py

# Test it
echo '{"candidate":"Your artifact text here"}' | \
  uv run --project "$OPTIMIZE_ANYTHING_ROOT" --locked --no-dev --extra codex python eval_judge.py
```

This returns JSON like:

```json
{"score": 0.82, "reasoning": "Clear structure but lacks examples", "clarity": 0.9, "specificity": 0.7}
```

For dataset-aware evaluators:

```bash
"$OPTIMIZE_ANYTHING_RUNNER" generate-evaluator seed.txt \
  --objective "Score correctness" \
  --dataset > eval_dataset.py

echo '{"candidate":"text","example":{"input":"q","expected":"a"}}' | \
  uv run --project "$OPTIMIZE_ANYTHING_ROOT" --locked --no-dev --extra codex python eval_dataset.py
```

`generate-evaluator --dataset` selects the dataset-aware template. Pass the JSONL file later to `optimize --dataset examples.jsonl`.

## Workflow
1. Clarify artifact + objective + hard constraints.
2. Pick evaluator pattern (judge default, composite for safety gates).
3. Run generator to scaffold.
4. Customize scoring logic and side-info fields.
5. Test with stdin payloads. You should see JSON with `score` plus diagnostic fields.
6. Validate score range: a good seed should score between 0.3-0.7. If above 0.85, the evaluator lacks discrimination.
7. Test preflight: `echo '{"candidate":"__optimize_anything_preflight__"}' | python3 your_evaluator.py` — should return `{"score": 0.5}` instantly.
