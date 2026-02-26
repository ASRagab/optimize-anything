# Examples

Complete worked examples for each evaluator type and evaluation pattern.

For basic usage, see the [README quickstart](README.md#quickstart).

---

## HTTP Evaluator — API Endpoint Scoring

**What we're optimizing:** A REST API error message template. The goal is to make error
messages clear, accurate, and actionable for API consumers.

**Artifact** (`error_template.txt`):

```
Error {status_code}: {message}. Please check the documentation for details.
```

**The evaluator** (`evaluator_server.py`):

A Python HTTP server that scores error message templates on three dimensions:

```python
#!/usr/bin/env python3
"""HTTP evaluator for API error message quality."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class ErrorEvaluator(BaseHTTPRequestHandler):
    def do_GET(self):
        self._respond(200, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        candidate = body["candidate"]

        # Clarity: does it explain what went wrong?
        clarity = 0.0
        if any(w in candidate.lower() for w in ["error", "failed", "invalid"]):
            clarity += 0.3
        if any(w in candidate.lower() for w in ["because", "reason", "due to"]):
            clarity += 0.4
        if "?" not in candidate:  # errors shouldn't be questions
            clarity += 0.3

        # Actionability: does it tell the user what to do?
        action = 0.0
        if any(w in candidate.lower() for w in ["try", "check", "verify", "ensure"]):
            action += 0.5
        if any(w in candidate.lower() for w in ["example", "e.g.", "such as"]):
            action += 0.3
        if any(w in candidate.lower() for w in ["docs", "documentation", "reference"]):
            action += 0.2

        # Conciseness: penalize overly long messages
        words = len(candidate.split())
        conciseness = 1.0 if words <= 30 else max(0.2, 1.0 - (words - 30) / 50)

        score = round(0.4 * clarity + 0.4 * action + 0.2 * conciseness, 4)
        self._respond(200, {
            "score": score,
            "clarity": round(clarity, 2),
            "actionability": round(action, 2),
            "conciseness": round(conciseness, 2),
        })

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass

if __name__ == "__main__":
    HTTPServer(("localhost", 8080), ErrorEvaluator).serve_forever()
```

**Run it:**

```bash
# Terminal 1: start the evaluator server
python evaluator_server.py &

# Terminal 2: optimize
optimize-anything optimize error_template.txt \
  --evaluator-url http://localhost:8080 \
  --model openai/gpt-5.1 \
  --budget 15 \
  --objective "Make API error messages clear, actionable, and concise"
```

**Sample output:**

```json
{
  "score_summary": {"best": 0.82, "initial": 0.34, "num_candidates": 12},
  "top_diagnostics": {"clarity": 0.9, "actionability": 0.85, "conciseness": 0.65}
}
```

**When to use:** HTTP evaluators are ideal when your scoring logic needs state
(databases, ML models), runs in a different language, or is already deployed as
a service. Use the built-in `scripts/evaluator_http_server.py` to wrap any
command evaluator behind HTTP without writing a server from scratch.

---

## Verification Pattern — Test Suite as Evaluator

**What we're optimizing:** A Python function that parses duration strings like
`"2h30m"` into total seconds. The evaluator runs a test suite against the
candidate and scores based on how many tests pass.

**Artifact** (`parse_duration.py`):

```python
def parse_duration(s):
    """Parse a duration string (e.g., '2h30m') into total seconds."""
    return 0  # initial stub
```

**The evaluator** (`eval_tests.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Write candidate to a temp file
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

python3 -c "
import json, sys
candidate = json.load(sys.stdin)['candidate']
with open('$tmpdir/parse_duration.py', 'w') as f:
    f.write(candidate)
"

# Run tests against the candidate
cat > "$tmpdir/test_parse.py" << 'TESTS'
import sys; sys.path.insert(0, ".")
from parse_duration import parse_duration

CASES = [
    ("30s", 30),
    ("5m", 300),
    ("2h", 7200),
    ("1h30m", 5400),
    ("2h30m15s", 9015),
    ("0s", 0),
    ("100m", 6000),
]

passed = 0
failed = []
for input_str, expected in CASES:
    try:
        result = parse_duration(input_str)
        if result == expected:
            passed += 1
        else:
            failed.append(f"{input_str}: got {result}, expected {expected}")
    except Exception as e:
        failed.append(f"{input_str}: {type(e).__name__}: {e}")

import json
print(json.dumps({
    "score": round(passed / len(CASES), 4),
    "passed": passed,
    "total": len(CASES),
    "failures": failed[:5],
}))
TESTS

cd "$tmpdir" && python3 test_parse.py
```

**Run it:**

```bash
optimize-anything optimize parse_duration.py \
  --evaluator-command bash eval_tests.sh \
  --model openai/gpt-5.1 \
  --budget 20 \
  --objective "Implement parse_duration to handle h/m/s duration strings"
```

**Sample output:**

```json
{
  "score_summary": {"best": 1.0, "initial": 0.0, "num_candidates": 8},
  "top_diagnostics": {"passed": 7, "total": 7, "failures": []}
}
```

**When to use:** Verification evaluators are ideal when correctness is
well-defined by a test suite. The score is the pass ratio, giving the optimizer
a clear gradient to follow. Works especially well for code generation,
data transformation functions, and format conversion tasks.

---

## Simulation Pattern — Multi-Scenario Scoring

**What we're optimizing:** A system prompt for a customer support chatbot. The
evaluator tests the prompt against multiple simulated customer scenarios and
averages the scores.

**Artifact** (`support_prompt.txt`):

```
You are a helpful customer support agent. Answer questions about our product.
```

**The evaluator** (`eval_scenarios.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json, sys, re

candidate = json.load(sys.stdin)["candidate"]
candidate_lower = candidate.lower()

# Simulated scenarios with scoring criteria
SCENARIOS = [
    {
        "name": "angry_customer",
        "weight": 0.25,
        "signals": {
            "empathy": ["sorry", "understand", "frustrat", "apologize", "hear you"],
            "de_escalation": ["help", "resolve", "solution", "let me", "happy to"],
        },
    },
    {
        "name": "refund_request",
        "weight": 0.25,
        "signals": {
            "policy_awareness": ["policy", "refund", "return", "within", "days"],
            "process_clarity": ["step", "process", "follow", "submit", "form"],
        },
    },
    {
        "name": "technical_issue",
        "weight": 0.20,
        "signals": {
            "troubleshooting": ["try", "restart", "clear", "update", "check"],
            "escalation_path": ["team", "engineer", "escalat", "specialist", "ticket"],
        },
    },
    {
        "name": "general_inquiry",
        "weight": 0.15,
        "signals": {
            "helpfulness": ["help", "assist", "happy to", "glad", "of course"],
            "knowledge": ["product", "feature", "documentation", "guide", "faq"],
        },
    },
    {
        "name": "out_of_scope",
        "weight": 0.15,
        "signals": {
            "boundaries": ["scope", "able to", "cannot", "outside", "specialist"],
            "redirection": ["suggest", "recommend", "contact", "visit", "refer"],
        },
    },
]

scenario_scores = {}
feedback = []

for scenario in SCENARIOS:
    hits = 0
    total = 0
    for category, keywords in scenario["signals"].items():
        total += len(keywords)
        matched = sum(1 for kw in keywords if kw in candidate_lower)
        hits += matched

    raw = min(1.0, hits / max(1, total * 0.4))  # 40% coverage = full score
    scenario_scores[scenario["name"]] = round(raw, 4)

    if raw < 0.5:
        feedback.append(f"{scenario['name']}: add guidance for this scenario")

weighted = sum(
    scenario_scores[s["name"]] * s["weight"] for s in SCENARIOS
)

print(json.dumps({
    "score": round(weighted, 4),
    "scenario_scores": scenario_scores,
    "feedback": feedback,
}))
PY
```

**Run it:**

```bash
optimize-anything optimize support_prompt.txt \
  --evaluator-command bash eval_scenarios.sh \
  --model openai/gpt-5.1 \
  --budget 15 \
  --objective "Create a comprehensive support chatbot system prompt"
```

**Sample output:**

```json
{
  "score_summary": {"best": 0.78, "initial": 0.12, "num_candidates": 11},
  "top_diagnostics": {
    "scenario_scores": {
      "angry_customer": 0.9, "refund_request": 0.75,
      "technical_issue": 0.8, "general_inquiry": 0.7, "out_of_scope": 0.6
    },
    "feedback": ["out_of_scope: add guidance for this scenario"]
  }
}
```

**When to use:** Simulation evaluators are ideal when quality depends on
performance across diverse conditions. Each scenario tests a different aspect
of the artifact, and the weighted average gives the optimizer a multi-faceted
gradient. Works well for prompts, configs, and decision-making templates.

---

## Composite Pattern — Combined Evaluators

**What we're optimizing:** CLI help text for a developer tool. The evaluator
combines three independent scoring signals into a single weighted score.

**Artifact** (`help_text.txt`):

```
Usage: mytool [options] <file>

A tool for processing files.
```

**The evaluator** (`eval_composite.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json, sys, re, math

candidate = json.load(sys.stdin)["candidate"]
lines = candidate.split("\n")
candidate_lower = candidate.lower()

# --- Signal 1: Readability (weight 0.35) ---
# Measures: line length distribution, section breaks, formatting
long_lines = sum(1 for l in lines if len(l) > 80)
total_lines = max(1, len(lines))
line_length_score = max(0, 1.0 - long_lines / total_lines)

has_sections = bool(re.search(r"^(#{1,3}\s|[A-Z][A-Z ]+:)", candidate, re.MULTILINE))
has_examples = "example" in candidate_lower or "```" in candidate
has_blank_lines = "\n\n" in candidate

readability = (
    0.4 * line_length_score
    + 0.3 * (1.0 if has_sections else 0.0)
    + 0.2 * (1.0 if has_examples else 0.0)
    + 0.1 * (1.0 if has_blank_lines else 0.0)
)

# --- Signal 2: Completeness (weight 0.40) ---
# Check for essential CLI help components
components = {
    "usage_line": bool(re.search(r"usage:", candidate_lower)),
    "description": len(candidate) > 50,
    "options": bool(re.search(r"(--\w+|options|flags)", candidate_lower)),
    "examples": has_examples,
    "version_or_help": bool(re.search(r"(--help|--version|-h|-v)", candidate)),
}
completeness = sum(components.values()) / len(components)

missing = [k for k, v in components.items() if not v]

# --- Signal 3: Conciseness (weight 0.25) ---
# Penalize extremes: too short is unhelpful, too long is overwhelming
char_count = len(candidate)
if char_count < 100:
    conciseness = char_count / 100
elif char_count <= 2000:
    conciseness = 1.0
elif char_count <= 4000:
    conciseness = max(0.3, 1.0 - (char_count - 2000) / 3000)
else:
    conciseness = 0.2

# --- Composite score ---
score = round(0.35 * readability + 0.40 * completeness + 0.25 * conciseness, 4)

print(json.dumps({
    "score": score,
    "readability": round(readability, 4),
    "completeness": round(completeness, 4),
    "conciseness": round(conciseness, 4),
    "missing_components": missing,
    "char_count": char_count,
}))
PY
```

**Run it:**

```bash
optimize-anything optimize help_text.txt \
  --evaluator-command bash eval_composite.sh \
  --model openai/gpt-5.1 \
  --budget 15 \
  --objective "Create comprehensive, readable CLI help text"
```

**Sample output:**

```json
{
  "score_summary": {"best": 0.87, "initial": 0.31, "num_candidates": 10},
  "top_diagnostics": {
    "readability": 0.85, "completeness": 0.8, "conciseness": 1.0,
    "missing_components": ["version_or_help"],
    "char_count": 890
  }
}
```

**When to use:** Composite evaluators are ideal when quality has multiple
independent dimensions that each need their own scoring logic. The weighted
combination gives the optimizer rich diagnostic feedback through the side
information fields, helping gepa's reflection LM make targeted improvements.
Works well for documentation, configs, and any artifact with multiple quality
axes.

---

## Tips

- **Start simple.** Begin with a basic evaluator and add dimensions as you learn what matters.
- **Return diagnostics.** Every field beyond `score` becomes feedback for the optimizer's reflection step.
- **Use `score` to pre-test.** Run `optimize-anything score artifact.txt --evaluator-command bash eval.sh` before optimizing to verify your evaluator works.
- **Use `analyze` for LLM judges.** Run `optimize-anything analyze artifact.txt --judge-model ... --objective ...` to discover quality dimensions before optimizing.
