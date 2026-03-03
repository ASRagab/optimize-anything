---
name: evaluator-patterns
description: Complete runnable evaluator templates for prompt, code, documentation, and agent-instructions artifacts
---

# evaluator-patterns

Use this skill to generate evaluator scripts that follow the optimize-anything command evaluator contract.

## Evaluator I/O contract (all patterns)
- Read one JSON object from stdin: `{"candidate": "..."}`
- Write one JSON object to stdout on a single line: `{"score": <float>, ...diagnostics...}`
- Return a numeric `score` (recommended in `0.0..1.0`)

---

## Pattern 1: Prompt / Instruction evaluator (LLM judge via LiteLLM)

Use when the candidate is a prompt or instruction text and you want rubric-based semantic scoring.

**Template: `eval_prompt.py`**
```python
#!/usr/bin/env python3
import json
import os
import sys

from litellm import completion


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = str(payload.get("candidate", ""))

    dimensions = [
        {"name": "clarity", "weight": 0.35, "guide": "Clear, specific, easy to follow"},
        {"name": "constraint_following", "weight": 0.35, "guide": "Respects constraints and boundaries"},
        {"name": "task_fitness", "weight": 0.30, "guide": "Likely to produce desired outputs"},
    ]

    system_prompt = (
        "You are a strict evaluator. Return ONLY valid JSON with keys: "
        "score, reasoning, and one numeric key per dimension name in [0,1]."
    )

    rubric_lines = "\n".join(
        f"- {d['name']} (weight {d['weight']}): {d['guide']}" for d in dimensions
    )

    user_prompt = f"""
Objective: Evaluate this prompt/instruction candidate.

Dimensions:
{rubric_lines}

Candidate:
{candidate}

Return JSON exactly like:
{{
  "score": 0.0,
  "reasoning": "brief reason",
  "clarity": 0.0,
  "constraint_following": 0.0,
  "task_fitness": 0.0
}}
""".strip()

    model = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")

    try:
        resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        parsed = json.loads(content)
    except Exception as exc:
        print(json.dumps({"score": 0.0, "error": f"judge_call_failed: {exc}"}, separators=(",", ":")))
        return 0

    # Normalize output defensively.
    out = {"reasoning": str(parsed.get("reasoning", ""))}
    weighted = 0.0
    total_w = 0.0
    for d in dimensions:
        name = d["name"]
        w = float(d["weight"])
        raw = float(parsed.get(name, 0.0))
        val = clamp01(raw)
        out[name] = val
        weighted += val * w
        total_w += w

    score = clamp01(float(parsed.get("score", weighted / total_w if total_w else 0.0)))
    out["score"] = score
    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"You are a careful coding assistant. Ask one clarifying question if needed, then provide concise steps."}' | python3 eval_prompt.py
```

---

## Pattern 2: Code evaluator (Bash test-suite pass ratio)

Use when the candidate is code to be validated by tests.

**Template: `evaluator.sh`**
```bash
#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
candidate="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("candidate",""))')"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# Example: write candidate code under test.
printf '%s' "$candidate" > "$workdir/candidate.py"

# Example mini test suite (replace with your real tests / project command).
cat > "$workdir/test_candidate.py" <<'PY'
from candidate import *


def test_nonempty():
    # Replace with real assertions against candidate behavior.
    assert True


def test_importable():
    assert callable(globals().get("__loader__", lambda: True)) or True
PY

set +e
pytest_out="$(cd "$workdir" && python3 -m pytest -q 2>&1)"
pytest_rc=$?
set -e

# Parse pass/total from pytest summary conservatively.
# Handles lines like: "2 passed in ..." or "1 failed, 3 passed in ..."
passed="$(printf '%s\n' "$pytest_out" | python3 - <<'PY'
import re, sys
text = sys.stdin.read()
m = re.search(r'(\d+)\s+passed', text)
print(int(m.group(1)) if m else 0)
PY
)"
failed="$(printf '%s\n' "$pytest_out" | python3 - <<'PY'
import re, sys
text = sys.stdin.read()
m = re.search(r'(\d+)\s+failed', text)
print(int(m.group(1)) if m else 0)
PY
)"

total=$((passed + failed))
if [ "$total" -eq 0 ]; then
  score="0.0"
else
  score="$(python3 - <<PY
p = $passed
n = $total
print(p / n)
PY
)"
fi

python3 - <<PY
import json
print(json.dumps({
  "score": float("$score"),
  "passed": int("$passed"),
  "failed": int("$failed"),
  "total": int("$total"),
  "pytest_rc": int("$pytest_rc")
}, separators=(",", ":")))
PY
```

**Test it:**
```bash
echo '{"candidate":"def add(a, b):\n    return a + b\n"}' | bash evaluator.sh
```

---

## Pattern 3: Documentation evaluator (heuristic readability/completeness/structure)

Use when candidate text is docs, guides, specs, or tutorials.

**Template: `eval_docs.py`**
```python
#!/usr/bin/env python3
import json
import re
import sys


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = str(payload.get("candidate", ""))
    text = candidate.strip()

    words = re.findall(r"\w+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_sentence_len = (len(words) / len(sentences)) if sentences else 100.0

    readability = clamp01(1.0 - max(0.0, (avg_sentence_len - 20.0) / 40.0))

    required_sections = ["overview", "usage", "examples", "limitations"]
    lowered = text.lower()
    present = sum(1 for s in required_sections if s in lowered)
    completeness = present / len(required_sections)

    has_headings = 1.0 if re.search(r"^#{1,3}\s+", text, flags=re.MULTILINE) else 0.0
    has_bullets = 1.0 if re.search(r"^\s*[-*]\s+", text, flags=re.MULTILINE) else 0.0
    has_code = 1.0 if "```" in text else 0.0
    structure = (has_headings + has_bullets + has_code) / 3.0

    score = clamp01(0.4 * readability + 0.35 * completeness + 0.25 * structure)

    out = {
        "score": score,
        "readability": readability,
        "completeness": completeness,
        "structure": structure,
        "avg_sentence_len": avg_sentence_len,
        "sections_present": present,
        "sections_required": len(required_sections),
    }
    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"# Overview\nThis guide explains setup.\n## Usage\n- Step 1\n- Step 2\n## Examples\n```bash\nrun it\n```\n## Limitations\nNeeds API key."}' | python3 eval_docs.py
```

---

## Pattern 4: Agent-instructions evaluator (multi-scenario simulation)

Use when candidate text is an agent/system prompt, runbook, or behavior policy.

**Template: `eval_agent.py`**
```python
#!/usr/bin/env python3
import json
import sys


def scenario_score(text: str, required_signals: list[str]) -> float:
    hits = sum(1 for s in required_signals if s in text)
    return hits / len(required_signals) if required_signals else 0.0


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = str(payload.get("candidate", "")).lower()

    scenarios = {
        "ambiguous_request": ["clarifying question", "assumption"],
        "tool_failure": ["retry", "fallback", "error message"],
        "safety_sensitive_action": ["ask approval", "impact", "rollback"],
        "completion_reporting": ["summary", "next steps"],
    }

    per_scenario = {
        name: scenario_score(candidate, signals)
        for name, signals in scenarios.items()
    }

    score = sum(per_scenario.values()) / len(per_scenario) if per_scenario else 0.0

    out = {
        "score": score,
        "scenario_scores": per_scenario,
        "scenarios_total": len(scenarios),
        "scenarios_meeting_bar": sum(1 for v in per_scenario.values() if v >= 0.75),
    }
    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Test it:**
```bash
echo '{"candidate":"If request is unclear, ask a clarifying question and state assumption. On tool failure, retry once, provide fallback, and include error message. For risky actions, ask approval with impact and rollback. End with summary and next steps."}' | python3 eval_agent.py
```
