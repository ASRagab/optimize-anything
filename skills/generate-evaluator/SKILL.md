---
name: generate-evaluator
description: >-
  Create or write an evaluator script for scoring text artifacts, prompts, or configs
  during gepa optimization. Use when asked to build, scaffold, or generate an evaluator,
  scoring function, or judge for optimize-anything.
---

## Objective
Generate an evaluator that scores candidate artifacts for optimization with gepa. You should always include diagnostic feedback — gepa's reflection LM uses your scores AND side-info fields to propose targeted improvements. This produces a working evaluator script that you can run immediately with `optimize-anything score`.

## Intake Questions (Ask First)

Before generating any evaluator, ask these:

1. What exact artifact are we optimizing (e.g., prompt text, skill markdown, docs)?
2. What does success look like? Identify the top 3 quality criteria.
3. What hard constraints must never be violated?
4. Should scoring be conducted with deterministic checks, LLM-as-judge, or a composite approach?
5. Specify the directory from which evaluator commands will run (`project-path` for relative files/tools).

## Evaluator Contract

- **Input:** JSON on stdin (`--evaluator-command`) or POST body (`--evaluator-url`):
  ```json
  {"candidate": "<text>"}
  ```
- **Output:** JSON on stdout or response body:
  ```json
  {"score": <float>, ...}
  ```
- Score must be a float in `[0.0, 1.0]`; higher is better. Out-of-range scores are clamped to `0.0`.
- Any fields beyond `score` become **Actionable Side Information (ASI)** — gepa's `ReflectionConfig` reads them to propose targeted improvements.

## The Key Principle

**Rich feedback drives better optimization.** An evaluator returning only `{"score": 0.3}` gives minimal guidance. Aim for `{"score": 0.3, "errors": ["missing output format"], "strengths": ["good structure"], "suggestion": "add JSON output instructions"}` — specific feedback for the next mutation.

## Choose an Evaluator Pattern

### 1. Verification-Based (ground truth exists)
Best for: structured extraction, QA, code correctness, config validation.

```bash
#!/usr/bin/env bash
input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
result=$(echo "$candidate" | my-test-harness --expected expected.json)
echo "$result"  # Returns: {"score": 0.85, "passed": 17, "failed": 3, "failures": ["test_edge_case"]}
```

### 2. LLM-as-Judge (subjective quality)
Best for: prompt quality, writing style, persona authenticity, instruction clarity.

```python
#!/usr/bin/env python3
import json, sys
from litellm import completion

data = json.load(sys.stdin)
candidate = data["candidate"]

response = completion(
    model="openai/gpt-4o-mini",
    messages=[{
        "role": "user",
        "content": f"""Rate this system prompt on a 0-1 scale across these dimensions:
- clarity: Is it unambiguous?
- completeness: Does it cover edge cases?
- conciseness: Is it free of redundancy?

Prompt to evaluate:
{candidate}

Return JSON: {{{{"score": <float>, "clarity": <float>, "completeness": <float>, "conciseness": <float>, "feedback": "<specific improvement suggestions>"}}}"""
    }],
)
print(response.choices[0].message.content)
```

### 3. Simulation-Based (runtime measurement)
Best for: code performance, API latency, compilation success. Run the candidate, measure runtime/exit code, and convert to a 0–1 score (e.g., `score = 1.0 / (1.0 + runtime_seconds)`).

### 4. Composite (multiple criteria)
Best for: any artifact where quality has multiple dimensions.

Return sub-scores as extra fields for insight:
```json
{"score": 0.72, "accuracy": 0.9, "speed": 0.6, "readability": 0.65, "feedback": "Fast but hard to read."}
```

## Workflow Steps

1. **Identify artifact type** — prompt, code, config, skill, agent instruction.
2. **Ask intake questions** and finalize scoring criteria before coding. You must always do this step first.
3. **Choose evaluator pattern** from the guide above. Avoid mixing patterns unless building a composite.
4. **Define scoring dimensions** — always include sub-scores and a weighted total score.
5. **Generate evaluator** using the `generate-evaluator` CLI subcommand as a starter template. This returns a scaffold you should customize.
6. **Add rich feedback** — include errors, strengths, and specific suggestions. Never return a bare score without diagnostics.
7. **Test evaluator** — run `echo '{"candidate": "..."}' | bash evaluator.sh` and verify the result contains valid JSON with a `score` field.
8. **Validate score range** — a good seed score lands between 0.3–0.7. If the seed scores above 0.85, the evaluator lacks discrimination; if below 0.2, criteria are too strict. Always check this before starting optimization.

## Rubric Blueprints

Select a blueprint for your artifact type, then customize dimension names and weights:

| Artifact Type | Dimensions (weight) | Example |
|---|---|---|
| **Instructional** | `clarity`(.35) `coverage`(.30) `actionability`(.25) `safety`(.10) | Docs, tutorials, READMEs |
| **Prompts/Skills** | `goal_alignment`(.35) `constraint_adherence`(.30) `robustness`(.20) `specificity`(.15) | System prompts, SKILL.md |
| **Executable** | `correctness`(.40) `efficiency`(.25) `validation`(.20) `maintainability`(.15) | Scripts, configs, pipelines |

Compute the weighted total: `score = w1*d1 + w2*d2 + ...` and return each dimension as a side-info field. The result gives gepa's reflection LM the granularity required to target weak areas. You should never omit dimension fields from the output.

## Common Mistakes

- Returning only `{"score": 0.3}` without diagnostic fields — gepa's reflection LM cannot target improvements without ASI.
- Using binary scoring (`0` or `1`) — continuous scores let `optimize_anything` detect incremental gains.
- Writing logs to stdout instead of stderr — this corrupts the JSON that `_parse_evaluator_result()` expects.
- Seed scores above 0.85 — the evaluator lacks room to differentiate; optimization stalls.