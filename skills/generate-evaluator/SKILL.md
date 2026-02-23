---
name: generate-evaluator
description: Generate an evaluator script for a text artifact, choosing the right scoring pattern for the objective
---
Generate an evaluator that scores candidate artifacts for optimization with gepa.
The evaluator is the most important piece — gepa's reflection LM uses your scores
AND diagnostic feedback to propose targeted improvements.

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

1. **Identify the artifact type** — prompt, code, config, skill, agent instruction?
2. **Choose the evaluator pattern** from above based on whether you have ground truth, need subjective judgment, or measure runtime behavior
3. **Define scoring dimensions** — what sub-scores matter? (accuracy, clarity, speed, etc.)
4. **Generate the evaluator** using the `generate_evaluator` tool as a starting point
5. **Add rich feedback** — include sub-scores, error messages, and improvement hints in the output
6. **Test the evaluator** with the seed artifact: `echo '{"candidate": "..."}' | bash evaluator.sh`
7. **Validate score range** — ensure the seed gets a middling score (0.3-0.7), not 0 or 1, so gepa has room to improve

## Common Mistakes

- Returning only a score with no diagnostic fields (gepa can't reflect effectively)
- Binary scoring (0 or 1) — use continuous scores so gepa can detect incremental improvement
- Writing logs to stdout instead of stderr (breaks JSON parsing)
- Evaluator that always returns high scores — leaves no room for optimization
