---
name: generate-evaluator
description: >-
  Create or write an evaluator script for scoring text artifacts, prompts, or configs
  during gepa optimization. Use when asked to build, scaffold, or generate an evaluator,
  scoring function, or judge for optimize-anything.
---

## Objective
Generate an evaluator that scores candidate artifacts for optimization with gepa. The evaluator is crucial — gepa's reflection LM uses your scores AND diagnostic feedback to propose targeted improvements.

## Intake Questions (Ask First)

Before generating any evaluator, ask these:

1. What exact artifact are we optimizing (e.g., prompt text, skill markdown, docs)?
2. What does success look like? Identify the top 3 quality criteria.
3. What hard constraints must never be violated?
4. Should scoring be conducted with deterministic checks, LLM-as-judge, or a composite approach?
5. Specify the directory from which evaluator commands will run (`project-path` for relative files/tools).

## Evaluator Contract

- **Input:** JSON on stdin (command) or POST body (HTTP): 
  ```json
  {"candidate": "<text>"}``` 
- **Output:** JSON on stdout or response body: 
  ```json
  {"score": <float>, ...}``` 
- Ensure the score is a float; the higher, the better.
- Any fields beyond `score` contribute to **Actionable Side Information (ASI)** — gepa's reflection LM reads them to guide subsequent mutations.

## The Key Principle

**Rich feedback drives better optimization.** An evaluator that delivers only 
```json
{"score": 0.3}``` provides minimal guidance. Instead, aim for a response like 
```json
{"score": 0.3, "errors": ["missing output format"], "strengths": ["good structure"], "suggestion": "add explicit JSON output instructions"}```, offering specific guidance for the next mutation.

## Choose an Evaluator Pattern

### 1. Verification-Based (ground truth exists)
Best for: structured extraction, QA, code correctness, config validation.

```bash
#!/usr/bin/env bash
# Compare candidate output against expected result
input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
# Run the candidate through your system and compare to ground truth
result=$(echo "$candidate" | my-test-harness --expected expected.json)
echo "$result"  # Expected output: {"score": 0.85, "passed": 17, "failed": 3, "failures": ["test_edge_case"]}
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
    echo '{"score": 0.0, "error": "'"$result"'"}'
else
    runtime=$(echo "$result" | grep -oP 'runtime: \K[\d.]+')
    echo "{\"score\": $(python3 -c "print(round(1.0 / (1.0 + $runtime), 4))"), \"runtime_ms\": $runtime}"
fi
```

### 4. Composite (multiple criteria)
Best for: any artifact where quality has multiple dimensions.

Return sub-scores as extra fields for insight:
```json
{"score": 0.72, "accuracy": 0.9, "speed": 0.6, "readability": 0.65, "feedback": "Fast but hard to read."}
```

## Steps

1. **Identify artifact type** — prompt, code, config, skill, agent instruction.
2. **Ask intake questions** and finalize scoring criteria before coding.
3. **Choose evaluator pattern** from options above.
4. **Define scoring dimensions** — include sub-scores and a weighted total score.
5. **Generate evaluator** using the `generate-evaluator` CLI subcommand as a starter template.
6. **Add rich feedback** — include errors, strengths, and specific suggestions for improvement.
7. **Test evaluator**: run 
   ```bash
   echo '{"candidate": "..."}' | bash evaluator.sh
   ``` 
8. **Validate score range** — typical seed scores should be in the range of (0.3 to 0.7).

## Reusable Rubric Blueprints

Select a blueprint based on the artifact type, then customize names and weights accordingly:

### A) Instructional Content

Recommended dimensions:
- `clarity` — Is the wording unambiguous?
- `coverage` — Are key steps and edge cases included?
- `actionability` — Are outputs directly usable?
- `safety` — Does it avoid risky or misleading guidance?

Example weighted score:
```python
score = 0.35 * clarity + 0.30 * coverage + 0.25 * actionability + 0.10 * safety
```

### B) Prompts / Skills / Agent Instructions

Recommended dimensions:
- `goal_alignment` — Do the instructions drive the intended behavior?
- `constraint_adherence` — Do they respect hard rules and boundaries?
- `robustness` — Do they manage ambiguity and edge cases?
- `specificity` — Are the directives clear and not vague?

Example weighted score:
```python
score = 0.35 * goal_alignment + 0.30 * constraint_adherence + 0.20 * robustness + 0.15 * specificity
```

### C) Executable/Analytical Artifacts

Recommended dimensions:
- `correctness` — Is the output valid and logically sound?
- `efficiency` — Does it avoid unnecessary costs/run-time overhead?
- `validation` — Are checks and failure handling included?
- `maintainability` — Is the output understandable and structured?

Example weighted score:
```python
score = 0.40 * correctness + 0.25 * efficiency + 0.20 * validation + 0.15 * maintainability
```

## Common Mistakes

- Returning only a score without diagnostic fields (gepa cannot reflect effectively).
- Using binary scoring (0 or 1) — opt for continuous scores to enable incremental improvement detection.
- Writing logs to stdout instead of stderr (this disrupts JSON parsing).
- Creating evaluators that always return high scores — leaving no scope for optimization.