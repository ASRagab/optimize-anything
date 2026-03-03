---
name: evaluator-patterns
description: Complete runnable evaluator templates for verification, judge, simulation, and composite patterns
---

# evaluator-patterns

Use this skill when you need a production-shaped evaluator quickly.

## Common evaluator contract
- Read one JSON object from `stdin`: `{"candidate": "..."}`
- Write one JSON object to `stdout` on a single line: `{"score": <float>, ...}`
- Keep score in `0.0..1.0` unless your workflow opts into unrestricted range.

## Pattern 1: Verification
**When to use:** deterministic checks, format enforcement, policy gates.

**Template (`evaluators/verification_eval.sh`):**
```bash
#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
candidate="$(printf '%s' "$payload" | python -c 'import json,sys; print(json.load(sys.stdin).get("candidate", ""))')"

checks_total=3
checks_passed=0

if [[ "$candidate" == *"Objective:"* ]]; then
  checks_passed=$((checks_passed + 1))
fi
if [[ "$candidate" == *"Constraints:"* ]]; then
  checks_passed=$((checks_passed + 1))
fi
if [[ ${#candidate} -le 800 ]]; then
  checks_passed=$((checks_passed + 1))
fi

python - <<'PY' "$checks_passed" "$checks_total"
import json
import sys

passed = int(sys.argv[1])
total = int(sys.argv[2])
score = passed / total if total else 0.0
print(json.dumps({"score": score, "checks_passed": passed, "checks_total": total}, separators=(",", ":")))
PY
```

**Test it:**
```bash
echo '{"candidate":"Objective: improve clarity\nConstraints: <= 800 chars\nDraft text..."}' | bash evaluators/verification_eval.sh
```

## Pattern 2: Judge
**When to use:** rubric-based semantic scoring with an LLM judge.

**Template (`evaluators/judge_eval.py`):**
```python
#!/usr/bin/env python3
import json
import sys

from optimize_anything.llm_judge import llm_judge_evaluator


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = payload.get("candidate", "")

    eval_fn = llm_judge_evaluator(
        "Score this artifact for clarity, correctness, and actionability.",
        model="openai/gpt-4o-mini",
        quality_dimensions=[
            {"name": "clarity", "weight": 0.4},
            {"name": "correctness", "weight": 0.4},
            {"name": "actionability", "weight": 0.2},
        ],
    )

    try:
        score, side_info = eval_fn(candidate)
        out = {"score": float(score), **(side_info or {})}
    except Exception as exc:
        out = {"score": 0.0, "error": f"judge_failed: {exc}"}

    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"Write a short troubleshooting guide with clear steps."}' | python evaluators/judge_eval.py
```

## Pattern 3: Simulation
**When to use:** scenario-driven behavior evaluation (agents, SOPs, workflows).

**Template (`evaluators/simulation_eval.py`):**
```python
#!/usr/bin/env python3
import json
import sys


def score_scenarios(candidate: str) -> dict:
    scenarios = [
        ("asks_for_clarification", ["ask", "clarify"]),
        ("uses_safe_tooling", ["safe", "rollback"]),
        ("handles_failure", ["retry", "fallback"]),
    ]

    per_scenario = {}
    passed = 0
    text = candidate.lower()

    for name, required_tokens in scenarios:
        ok = all(token in text for token in required_tokens)
        per_scenario[name] = 1.0 if ok else 0.0
        if ok:
            passed += 1

    score = passed / len(scenarios) if scenarios else 0.0
    return {
        "score": score,
        "scenarios_passed": passed,
        "scenarios_total": len(scenarios),
        "scenario_scores": per_scenario,
    }


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = payload.get("candidate", "")
    print(json.dumps(score_scenarios(candidate), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"Ask clarifying questions first. Use safe steps with rollback. On failure, retry then fallback."}' | python evaluators/simulation_eval.py
```

## Pattern 4: Composite
**When to use:** combine hard constraints + semantic quality + scenario coverage.

**Template (`evaluators/composite_eval.py`):**
```python
#!/usr/bin/env python3
import json
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = payload.get("candidate", "")
    text = candidate.lower()

    hard_constraints = {
        "max_len_1200": len(candidate) <= 1200,
        "must_include_safety": "safety" in text,
    }
    failed_hard = [k for k, v in hard_constraints.items() if not v]

    if failed_hard:
        out = {
            "score": 0.0,
            "hard_constraints_satisfied": False,
            "failed_constraints": failed_hard,
        }
        print(json.dumps(out, separators=(",", ":")))
        return 0

    clarity = 1.0 if "step" in text else 0.5
    robustness = 1.0 if "fallback" in text else 0.4
    compliance = 1.0 if "constraint" in text else 0.5

    score = (0.4 * clarity) + (0.3 * robustness) + (0.3 * compliance)
    out = {
        "score": round(score, 6),
        "hard_constraints_satisfied": True,
        "clarity": clarity,
        "robustness": robustness,
        "compliance": compliance,
    }
    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"Safety first. Step-by-step plan with explicit constraint checks and fallback actions."}' | python evaluators/composite_eval.py
```
