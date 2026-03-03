---
name: generate-evaluator
description: >-
  Create or write an evaluator script for scoring text artifacts, prompts, or configs
  during gepa optimization. Use when asked to build, scaffold, or generate an evaluator,
  scoring function, or judge for optimize-anything.
---

## Objective
Generate an evaluator that scores candidate artifacts for optimization with gepa. Include diagnostic feedback so reflections can improve weak dimensions.

## Evaluator Contract
- Input JSON on stdin (`--evaluator-command`) or HTTP POST body (`--evaluator-url`)
- Default payload: `{"candidate": "<text>"}`
- Dataset-aware payload (`--dataset`): `{"candidate": "<text>", "example": {...}}`
- Output JSON must include `score` (float, usually in `[0,1]`), plus optional side-info fields.

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
- `--dataset`: generate dataset-aware templates that read `example` and show how to use it in scoring.
- `--intake-json` / `--intake-file`: embed rubric/quality dimensions.

## Quick Start

Generate a judge evaluator and test it:

```bash
# Generate
optimize-anything generate-evaluator seed.txt \
  --objective "Score clarity and specificity" \
  --model openai/gpt-4o-mini > eval_judge.py

# Test it
echo '{"candidate":"Your artifact text here"}' | python3 eval_judge.py
```

This returns JSON like:

```json
{"score": 0.82, "reasoning": "Clear structure but lacks examples", "clarity": 0.9, "specificity": 0.7}
```

For dataset-aware evaluators:

```bash
optimize-anything generate-evaluator seed.txt \
  --objective "Score correctness" \
  --dataset examples.jsonl > eval_dataset.py

echo '{"candidate":"text","example":{"input":"q","expected":"a"}}' | python3 eval_dataset.py
```

## Workflow
1. Clarify artifact + objective + hard constraints.
2. Pick evaluator pattern (judge default, composite for safety gates).
3. Run generator to scaffold.
4. Customize scoring logic and side-info fields.
5. Test with stdin payloads. You should see JSON with `score` plus diagnostic fields.
6. Validate score range: a good seed should score between 0.3-0.7. If above 0.85, the evaluator lacks discrimination.
