---
name: evaluator-patterns
description: Reusable evaluator templates for common artifact types
---

# evaluator-patterns

Use this skill when you need a fast, proven evaluator shape for a specific artifact type.

## Pattern 1: Prompt / Instruction Artifacts
**When to use:** Prompts, system messages, task instructions, policy prompts.

**Expected score range:** 0.0-1.0 (unit)

**Diagnostic fields:** `clarity`, `constraint_adherence`, `robustness`, `reasoning`

**Example evaluator (LLM judge):**
```python
from optimize_anything.llm_judge import llm_judge_evaluator

eval_fn = llm_judge_evaluator(
    "Maximize clarity while strictly following constraints.",
    model="openai/gpt-4o-mini",
    quality_dimensions=[
        {"name": "clarity", "weight": 0.4},
        {"name": "constraint_adherence", "weight": 0.4},
        {"name": "robustness", "weight": 0.2},
    ],
)
```

## Pattern 2: Code Artifacts (Test-Suite Verification)
**When to use:** Code snippets, scripts, or patches where correctness is validated by tests.

**Expected score range:** 0.0-1.0

**Diagnostic fields:** `tests_passed`, `tests_failed`, `lint_ok`, `failure_summary`

**Example evaluator (command):**
```bash
#!/usr/bin/env bash
set -euo pipefail
payload=$(cat)
candidate=$(echo "$payload" | python -c 'import json,sys; print(json.load(sys.stdin)["candidate"])')
printf "%s" "$candidate" > candidate.py
if uv run pytest -q >/tmp/test.out 2>/tmp/test.err; then
  echo '{"score": 1.0, "tests_passed": true, "tests_failed": 0}'
else
  echo '{"score": 0.0, "tests_passed": false, "tests_failed": 1, "failure_summary": "tests failed"}'
fi
```

## Pattern 3: Documentation Artifacts
**When to use:** READMEs, guides, runbooks, internal docs.

**Expected score range:** 0.0-1.0

**Diagnostic fields:** `completeness`, `accuracy`, `readability`, `actionability`, `reasoning`

**Example evaluator (LLM judge):**
```python
from optimize_anything.llm_judge import llm_judge_evaluator

eval_fn = llm_judge_evaluator(
    "Score docs for completeness, factual accuracy, readability, and actionability.",
    model="openai/gpt-4o-mini",
    quality_dimensions=[
        {"name": "completeness", "weight": 0.3},
        {"name": "accuracy", "weight": 0.3},
        {"name": "readability", "weight": 0.2},
        {"name": "actionability", "weight": 0.2},
    ],
)
```

## Pattern 4: Agent Instructions (Scenario Simulation)
**When to use:** Agent policies, SOPs, behavior playbooks, instruction hierarchies.

**Expected score range:** 0.0-1.0

**Diagnostic fields:** `policy_alignment`, `ambiguity_resistance`, `tool_use_safety`, `scenario_coverage`

**Example evaluator (composite):**
```python
import json
from optimize_anything.llm_judge import llm_judge_evaluator

judge = llm_judge_evaluator(
    "Score instruction quality under realistic scenarios.",
    model="openai/gpt-4o-mini",
    quality_dimensions=[
        {"name": "policy_alignment", "weight": 0.4},
        {"name": "ambiguity_resistance", "weight": 0.2},
        {"name": "tool_use_safety", "weight": 0.2},
        {"name": "scenario_coverage", "weight": 0.2},
    ],
)

def evaluator(candidate: str):
    required_tokens = ["Safety", "Ask first", "Rollback"]
    missing = [t for t in required_tokens if t not in candidate]
    if missing:
        return 0.0, {"hard_constraints_satisfied": False, "missing_required_sections": missing}
    return judge(candidate)
```
