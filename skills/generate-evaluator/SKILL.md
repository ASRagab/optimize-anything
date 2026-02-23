---
name: generate-evaluator
description: Generate an evaluator script for a text artifact, choosing the right scoring pattern for the objective
---
Generate an evaluator that scores candidate artifacts for optimization with gepa.
The evaluator is the most important piece — gepa's reflection LM uses your scores
AND diagnostic feedback to propose targeted improvements.

## Intake Questions (Ask First)

Before generating any evaluator, ask these:

1. What exact artifact are we optimizing (prompt text, skill markdown, docs, etc.)?
2. What does success look like (top 3 quality criteria)?
3. What hard constraints must never be violated?
4. Should scoring be deterministic checks, LLM-as-judge, or a composite?
5. Where should evaluator commands run from (project path for relative files/tools)?

## Evaluator Contract

- **Input:** JSON on stdin (command) or POST body (HTTP): `{"candidate": "<text>"}`
- **Output:** JSON on stdout or response body: `{"score": <float>, ...}`
- Score must be a float, higher is better
- All fields beyond `score` become **Actionable Side Information (ASI)** — gepa's reflection LM reads them to guide mutations

## The Key Principle

**Rich feedback drives better optimization.** An evaluator returning just `{"score": 0.3}` gives gepa almost nothing to reflect on. An evaluator returning `{"score": 0.3, "errors": ["missing output format"], "strengths": ["good structure"], "suggestion": "add explicit JSON output instructions"}` gives gepa precise guidance for the next mutation.

## Choose an Evaluator Pattern

### 1. Verification-Based (ground truth exists)
Best for: structured extraction, QA, code correctness, config validation.

```bash
#!/usr/bin/env bash
# Compare candidate output against expected result
input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
# Run the candidate through your system, compare to ground truth
result=$(echo "$candidate" | my-test-harness --expected expected.json)
echo "$result"  # {"score": 0.85, "passed": 17, "failed": 3, "failures": ["test_edge_case"]}
```

### 2. LLM-as-Judge (subjective quality)
Best for: prompt quality, writing style, persona authenticity, instruction clarity.

```python
#!/usr/bin/env python3
import json, sys, os
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

Return JSON: {{"score": <float>, "clarity": <float>, "completeness": <float>, "conciseness": <float>, "feedback": "<specific improvement suggestions>"}}"""
    }],
)
print(response.choices[0].message.content)
```

### 3. Simulation-Based (runtime measurement)
Best for: code performance, API latency, resource usage, compilation success.

```bash
#!/usr/bin/env bash
input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
# Write candidate to temp file, run benchmark
echo "$candidate" > /tmp/candidate.py
result=$(python3 /tmp/candidate.py 2>&1)
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "{\"score\": 0.0, \"error\": \"$result\"}"
else
    runtime=$(echo "$result" | grep -oP 'runtime: \K[\d.]+')
    echo "{\"score\": $(python3 -c "print(round(1.0 / (1.0 + $runtime), 4))"), \"runtime_ms\": $runtime}"
fi
```

### 4. Composite (multiple criteria)
Best for: any artifact where quality has multiple dimensions.

Return sub-scores as extra fields — gepa sees them all:
```json
{"score": 0.72, "accuracy": 0.9, "speed": 0.6, "readability": 0.65, "feedback": "Fast but hard to read"}
```

## Steps

1. **Identify artifact type** — prompt, code, config, skill, agent instruction.
2. **Ask intake questions** and lock scoring criteria before coding.
3. **Choose evaluator pattern** from above.
4. **Define scoring dimensions** (include sub-scores and a weighted total score).
5. **Generate evaluator** using the `generate-evaluator` CLI subcommand as a starter.
6. **Add rich feedback** — include errors, strengths, and specific suggestions.
7. **Test evaluator**: `echo '{"candidate": "..."}' | bash evaluator.sh`
8. **Validate score range** — seed should usually score in the middle (0.3-0.7).

## Reusable Rubric Blueprints

Choose a blueprint based on artifact type, then adapt names/weights:

### A) Instructional Content

Recommended dimensions:
- `clarity` — wording is unambiguous
- `coverage` — key steps/edge cases are included
- `actionability` — outputs are directly usable
- `safety` — avoids risky or misleading guidance

Example weighted score:
`score = 0.35*clarity + 0.30*coverage + 0.25*actionability + 0.10*safety`

### B) Prompts / Skills / Agent Instructions

Recommended dimensions:
- `goal_alignment` — instructions drive intended behavior
- `constraint_adherence` — respects hard rules and boundaries
- `robustness` — handles ambiguity and edge cases
- `specificity` — avoids vague directives

Example weighted score:
`score = 0.35*goal_alignment + 0.30*constraint_adherence + 0.20*robustness + 0.15*specificity`

### C) Executable/Analytical Artifacts

Recommended dimensions:
- `correctness` — output is valid and logically sound
- `efficiency` — avoids unnecessary cost/runtime overhead
- `validation` — includes checks and failure handling
- `maintainability` — understandable, structured output

Example weighted score:
`score = 0.40*correctness + 0.25*efficiency + 0.20*validation + 0.15*maintainability`

## Common Mistakes

- Returning only a score with no diagnostic fields (gepa can't reflect effectively)
- Binary scoring (0 or 1) — use continuous scores so gepa can detect incremental improvement
- Writing logs to stdout instead of stderr (breaks JSON parsing)
- Evaluator that always returns high scores — leaves no room for optimization
