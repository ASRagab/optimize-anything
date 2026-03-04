# Evaluator Cookbook

An evaluator is a function that **scores a candidate artifact**. `optimize-anything` supports three types: **shell commands**, **HTTP endpoints**, and **LLM judges**.

---

## 1. Evaluator Contract

### Input (Protocol v2)

Your evaluator reads a JSON object from **stdin** (command) or as a **POST body** (HTTP). As of v0.3.0, the payload follows **Protocol v2**:

```json
{
  "_protocol_version": 2,
  "candidate": "the text being optimized",
  "example": {"input": "...", "expected": "..."},
  "task_model": "openai/gpt-4o-mini"
}
```

| Field                | Type    | Required | Description                                                                 |
|----------------------|---------|----------|-----------------------------------------------------------------------------|
| `candidate`          | string  | **Yes**  | The artifact being evaluated                                                |
| `_protocol_version`  | integer | No       | Protocol version marker; value is `2` for v2 payloads                       |
| `example`            | object  | No       | One dataset record from `--dataset`; present only in dataset-backed modes   |
| `task_model`         | string  | No       | Identifies the model being optimized for; passed via `--task-model` flag    |

> **Backward compatibility:** v1 evaluators that only read `candidate` still work. New fields are optional and must be safely ignored if unused.

> **Note:** The `objective` and `background` strings are **not** passed to your evaluator — only to gepa's reflection LM. Your evaluator only sees the fields above.

#### When is `example` present?

The `example` field is populated **per-call** when using `--dataset` mode. Each evaluator invocation receives one dataset record bound to `example`. Use it to score the candidate against the expected behavior for that specific example. Without `--dataset`, `example` is omitted from the payload.

#### Command evaluators: `OPTIMIZE_ANYTHING_TASK_MODEL`

For shell-command evaluators, `task_model` is also available as an environment variable:

```bash
echo "$OPTIMIZE_ANYTHING_TASK_MODEL"   # e.g. openai/gpt-4o-mini
```

### Output

Return a JSON object to **stdout** (command) or as the **response body** (HTTP):

```json
{
  "score": 0.75,
  "readability": 0.8,
  "accuracy": 0.7,
  "notes": "Good structure but could be more concise"
}
```

| Field          | Type   | Required | Description                                      |
|----------------|--------|----------|--------------------------------------------------|
| `score`        | number | Yes      | Overall score, higher is better                  |
| *(other keys)* | any    | No       | Side information consumed by gepa's reflection LM |

All fields beyond `score` become **rich feedback** that gepa's reflection LM uses to steer future mutations. You should always include sub-scores, booleans, and improvement hints as extra JSON keys.

---

## 2. Recipe: Shell Evaluator (Word Count)

Start with a working shell script, then adapt the scoring logic. This recipe **scores candidates by proximity to a target word count**.

> **Protocol v2 note:** Your script will receive the full v2 payload. If you only need `candidate`, your existing parsing logic works unchanged — extra fields are just ignored.

```bash
#!/usr/bin/env bash
# evaluators/word-count.sh
# Target: 50 words

set -euo pipefail

input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys, json; print(json.load(sys.stdin)['candidate'])")
word_count=$(echo "$candidate" | wc -w | tr -d ' ')
target=50
diff=$((word_count - target))
if [ $diff -lt 0 ]; then diff=$((-diff)); fi
score=$(python3 -c "print(round(1.0 / (1.0 + $diff / 10.0), 4))")
echo "{\"score\": $score, \"wordCount\": $word_count, \"target\": $target}"
```

**Run it:**
```bash
chmod +x evaluators/word-count.sh
uv run optimize-anything optimize seed.txt \
  --evaluator-command bash evaluators/word-count.sh \
  --objective "Write exactly 50 words about Python" \
  --budget 15
```

**Test it independently:**
```bash
echo '{"candidate":"hello world"}' | bash evaluators/word-count.sh
```
Expected output: `{"score": 0.1724, "wordCount": 2, "target": 50}`

Outcome: The optimizer repeatedly calls your script, adjusting the text toward 50 words. You should always test independently first — this produces immediate feedback on JSON parsing before running a full optimization.

---

## 3. Recipe: HTTP Evaluator (Python Server)

Use an HTTP evaluator when you need a long-running service, access to external systems, or evaluations in any language. This example **scores JSON validity and schema compliance**.

> **Protocol v2 note:** Your handler will receive the full v2 payload. Reading only `data.get("candidate", "")` is safe — `example` and `task_model` are simply unused.

```python
#!/usr/bin/env python3
"""evaluators/json_validator.py"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        data = json.loads(body)
        candidate = data.get("candidate", "")

        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            result = {"score": 0, "error": "Invalid JSON"}
        else:
            score = 0.5  # Valid JSON baseline
            side_info = {"validJson": True}
            if isinstance(parsed, dict):
                if "name" in parsed:
                    score += 0.15
                    side_info["hasName"] = True
                if "version" in parsed:
                    score += 0.15
                    side_info["hasVersion"] = True
                if "description" in parsed:
                    score += 0.2
                    side_info["hasDescription"] = True
            result = {"score": score, **side_info}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


if __name__ == "__main__":
    server = HTTPServer(("localhost", 3456), Handler)
    print("JSON validator evaluator running on port 3456", flush=True)
    server.serve_forever()
```

**Run it:**
```bash
python3 evaluators/json_validator.py                     # Terminal 1
uv run optimize-anything optimize seed.json \            # Terminal 2
  --evaluator-url "http://localhost:3456" \
  --objective "Generate a valid package.json" --budget 10
```

**Test it independently:**
```bash
curl -X POST http://localhost:3456 \
  -H "Content-Type: application/json" \
  -d '{"candidate": "{\"name\": \"test\"}"}'
```
Expected output: `{"score": 0.65, "validJson": true, "hasName": true}`

Outcome: The optimizer calls your endpoint for each candidate, moving toward valid JSON with the desired schema.

---

## 4. Recipe: LLM Judge (No Script Required)

Use an LLM judge when you want to score text qualitatively (clarity, style, persuasiveness) without writing an evaluator script. You specify a judge model via `--judge-model` and an objective; the model returns a score plus reasoning.

**Score a single artifact:**
```bash
uv run optimize-anything score my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score clarity and persuasiveness"
```

**Optimize with an LLM judge:**
```bash
uv run optimize-anything optimize my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Maximize clarity and persuasiveness" \
  --budget 15
```

**Discover quality dimensions, then optimize:**
```bash
uv run optimize-anything analyze my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Quality"
```

Outcome: The `analyze` command returns named dimensions (e.g., clarity, specificity, tone). Use them with explicit weights and hard constraints:

```bash
uv run optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Maximize quality" \
  --intake-json '{
    "quality_dimensions": [
      {"name": "clarity", "weight": 0.6},
      {"name": "accuracy", "weight": 0.4}
    ],
    "hard_constraints": [
      "must be under 200 words"
    ]
  }'
```

Outcome: The judge enforces hard constraints and optimizes a weighted combination of named dimensions. You must use `--judge-model` exclusively — it cannot combine with `--evaluator-command` or `--evaluator-url`.

---

## 5. Recipe: Dataset-Aware Evaluator

Use this when you're running with `--dataset` and want your evaluator to score the candidate **against the specific example** it should handle. The `example` field gives you the full dataset record for each evaluation call.

This recipe scores whether a candidate prompt **correctly handles a user intent** from the dataset.

```python
#!/usr/bin/env python3
"""evaluators/intent_match.py
Scores a candidate prompt by simulating it on a dataset example and checking
whether the output satisfies the expected intent.

Dataset record format (JSONL):
  {"input": "user message", "expected_intent": "book_flight", "expected_keywords": ["flight", "airline"]}
"""
import json
import os
import sys

from litellm import completion


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def main() -> int:
    payload = json.load(sys.stdin)
    candidate = str(payload.get("candidate", ""))
    example = payload.get("example", {})

    if not example:
        # No dataset mode: score as a generic prompt quality check
        result = {"score": 0.5, "note": "no_example_provided"}
        print(json.dumps(result, separators=(",", ":")))
        return 0

    user_input = example.get("input", "")
    expected_intent = example.get("expected_intent", "")
    expected_keywords = example.get("expected_keywords", [])

    if not user_input:
        print(json.dumps({"score": 0.0, "error": "example missing input field"}, separators=(",", ":")))
        return 0

    # Simulate running the candidate prompt against this example's input
    model = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")
    try:
        resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": candidate},
                {"role": "user", "content": user_input},
            ],
            temperature=0,
            max_tokens=256,
        )
        output = resp.choices[0].message.content or ""
    except Exception as exc:
        print(json.dumps({"score": 0.0, "error": f"llm_call_failed: {exc}"}, separators=(",", ":")))
        return 0

    # Score 1: keyword coverage
    output_lower = output.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in output_lower)
    keyword_score = clamp01(hits / len(expected_keywords)) if expected_keywords else 0.5

    # Score 2: intent signal (simple heuristic — replace with your logic)
    intent_score = clamp01(1.0 if expected_intent.lower() in output_lower else 0.3)

    score = clamp01(0.6 * keyword_score + 0.4 * intent_score)

    result = {
        "score": score,
        "keyword_score": keyword_score,
        "intent_score": intent_score,
        "keywords_hit": hits,
        "keywords_total": len(expected_keywords),
        "expected_intent": expected_intent,
    }
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Dataset file (`dataset.jsonl`):**
```jsonl
{"input": "I need to fly from NYC to London next week", "expected_intent": "book_flight", "expected_keywords": ["flight", "airline", "departure", "destination"]}
{"input": "What hotels are near the Eiffel Tower?", "expected_intent": "find_hotel", "expected_keywords": ["hotel", "accommodation", "Paris", "nearby"]}
```

**Run it:**
```bash
uv run optimize-anything optimize seed-prompt.txt \
  --evaluator-command python3 evaluators/intent_match.py \
  --dataset dataset.jsonl \
  --objective "Optimize a travel assistant prompt that correctly handles user intents" \
  --budget 20
```

**Test it independently (with example):**
```bash
echo '{
  "candidate": "You are a helpful travel assistant. Identify the user intent and respond accordingly.",
  "example": {"input": "Book me a flight to Paris", "expected_intent": "book_flight", "expected_keywords": ["flight", "airline"]}
}' | python3 evaluators/intent_match.py
```

Outcome: Each evaluator call scores the candidate prompt against one dataset example. The optimizer improves the prompt's ability to handle all intents in the dataset, not just the average case.

---

## 6. Recipe: Composite Evaluator

Use a composite evaluator when a single scoring strategy isn't enough. This recipe combines **fast heuristic checks** (no LLM calls) with a **slower LLM judge call**, blending them into one score.

The pattern: run cheap checks first, short-circuit on clear failures, call the LLM only when needed.

```python
#!/usr/bin/env python3
"""evaluators/composite_eval.py
Combines heuristic checks with an LLM judge.

Strategy:
  - 40%: length and structural heuristics (fast, no LLM)
  - 60%: LLM rubric judge (semantic quality)

Short-circuits: if heuristics score < 0.2, skip the LLM call entirely.
"""
import json
import os
import re
import sys

from litellm import completion


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ── Heuristic scorer ───────────────────────────────────────────────────────────

def heuristic_score(candidate: str) -> tuple[float, dict]:
    """Fast structural checks. Returns (score, side_info)."""
    text = candidate.strip()
    side: dict = {}

    # Word count: penalize < 20 or > 500 words
    words = re.findall(r"\w+", text)
    wc = len(words)
    if wc < 20:
        length_score = wc / 20.0
    elif wc > 500:
        length_score = max(0.0, 1.0 - (wc - 500) / 500.0)
    else:
        length_score = 1.0
    side["word_count"] = wc
    side["length_score"] = round(length_score, 4)

    # Structure: headings, bullets, code blocks
    has_heading = bool(re.search(r"^#{1,3}\s+", text, re.MULTILINE))
    has_bullets = bool(re.search(r"^\s*[-*]\s+", text, re.MULTILINE))
    has_code = "```" in text
    structure_score = (int(has_heading) + int(has_bullets) + int(has_code)) / 3.0
    side["has_heading"] = has_heading
    side["has_bullets"] = has_bullets
    side["has_code"] = has_code
    side["structure_score"] = round(structure_score, 4)

    score = clamp01(0.6 * length_score + 0.4 * structure_score)
    return score, side


# ── LLM judge ─────────────────────────────────────────────────────────────────

def llm_judge_score(candidate: str, model: str) -> tuple[float, dict]:
    """Rubric-based LLM score. Returns (score, side_info)."""
    system = (
        "You are a strict evaluator. Return ONLY valid JSON with keys: "
        "score (0-1), clarity (0-1), completeness (0-1), reasoning (string)."
    )
    user = f"""Rate this text on clarity and completeness.

Text:
{candidate}

Return JSON:
{{"score": 0.0, "clarity": 0.0, "completeness": 0.0, "reasoning": "brief"}}"""

    try:
        resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        return 0.0, {"llm_error": str(exc)}

    llm_score = clamp01(float(parsed.get("score", 0.0)))
    return llm_score, {
        "llm_score": llm_score,
        "clarity": clamp01(float(parsed.get("clarity", 0.0))),
        "completeness": clamp01(float(parsed.get("completeness", 0.0))),
        "reasoning": str(parsed.get("reasoning", "")),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    payload = json.load(sys.stdin)
    candidate = str(payload.get("candidate", ""))
    model = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")

    h_score, h_side = heuristic_score(candidate)
    side: dict = {"heuristic_score": round(h_score, 4), **h_side}

    # Short-circuit: skip LLM on clear structural failures
    if h_score < 0.2:
        final = clamp01(0.4 * h_score)
        side["llm_skipped"] = True
        side["skip_reason"] = "heuristic_below_threshold"
        print(json.dumps({"score": round(final, 4), **side}, separators=(",", ":")))
        return 0

    l_score, l_side = llm_judge_score(candidate, model)
    side.update(l_side)
    side["llm_skipped"] = False

    # Blend: 40% heuristics, 60% LLM
    final = clamp01(0.4 * h_score + 0.6 * l_score)
    print(json.dumps({"score": round(final, 4), **side}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Run it:**
```bash
uv run optimize-anything optimize seed.md \
  --evaluator-command python3 evaluators/composite_eval.py \
  --objective "Produce a clear, well-structured explanation" \
  --budget 20
```

**Test it independently:**
```bash
echo '{"candidate":"# Overview\nThis guide explains how to set up the project.\n- Install deps\n- Run tests\n\n```bash\nnpm install\n```"}' \
  | python3 evaluators/composite_eval.py
```

Outcome: Structurally poor candidates (< 0.2 heuristic score) are penalized immediately without burning LLM calls. Good candidates get full semantic scoring. The blend rewards both structure and quality.

**Adapt the weights to your task:**
- High-volume runs → increase heuristic weight (cheaper)
- Subtle quality tasks → increase LLM weight (more accurate)
- Add more heuristic dimensions: vocabulary diversity, prohibited patterns, required phrases

---

## 7. Auto-generating Evaluators

Run the generator to produce a **starting script** that you can then edit and customize.

**Python API:**
```python
from optimize_anything.evaluator_generator import generate_evaluator_script

script = generate_evaluator_script(
    seed="Your seed artifact text",
    objective="maximize clarity",
    evaluator_type="command",  # or "http"
)
with open("evaluator.sh", "w") as f:
    f.write(script)
```

**CLI:**
```bash
uv run optimize-anything generate-evaluator seed.txt --objective "maximize clarity"
```

Outcome: You get a starter script tailored to your seed and objective. Edit scoring logic to match your real constraints.

---

## 8. Evaluator Factories (Python API)

Call the built-in factories when you need to invoke evaluators **programmatically** from Python.

```python
from optimize_anything.evaluators import command_evaluator, http_evaluator

# Shell evaluator
cmd_eval = command_evaluator(["bash", "eval.sh"])

# HTTP evaluator
http_eval = http_evaluator("http://localhost:3456")
```

Outcome: Call `cmd_eval(candidate_text)` or `http_eval(candidate_text)` to receive a `(score, side_info)` tuple.

---

## 9. Score Range

By default, `optimize-anything` expects scores in `[0.0, 1.0]`. If your evaluator naturally produces values outside this range, use `--score-range any`.

| Mode                    | Valid score values           | When to use                                                   |
|-------------------------|------------------------------|---------------------------------------------------------------|
| `--score-range unit`    | `[0.0, 1.0]` (default)       | Most evaluators: probabilities, ratios, rubric averages       |
| `--score-range any`     | Any finite float             | Reward functions, penalty scores, raw test counts, custom metrics |

**Examples of `any`-range evaluators:**
- A test runner returning raw pass count (e.g., `42` out of 100)
- A penalty function that returns negative scores for violations
- A reward model returning logit-scaled outputs (e.g., `-2.3` to `+4.7`)
- A business metric like revenue delta (could be negative)

**Run with `--score-range any`:**
```bash
uv run optimize-anything optimize seed.txt \
  --evaluator-command python3 evaluators/reward_fn.py \
  --objective "Maximize task reward" \
  --score-range any \
  --budget 20
```

> **Note:** In `any` mode, `NaN` and `±Inf` are still invalid and treated as errors. The score just isn't clamped to `[0,1]`. LLM judge scores are always clamped to `[0,1]` regardless of `--score-range`.

---

## 10. Task-Model Awareness

The `--task-model` flag identifies the model your prompt will ultimately run on. Evaluators can read this to **adapt scoring logic** based on the target model — useful when different models have different strengths, context limits, or quirks.

**How to access `task_model` in your evaluator:**

In Python (reads from v2 payload):
```python
payload = json.load(sys.stdin)
task_model = payload.get("task_model", "")   # e.g. "openai/gpt-4o-mini"
```

In Bash (reads from environment variable):
```bash
task_model="${OPTIMIZE_ANYTHING_TASK_MODEL:-}"
```

**Example: adjusting length target per model:**
```python
payload = json.load(sys.stdin)
candidate = payload.get("candidate", "")
task_model = payload.get("task_model", "")

# Smaller models benefit from shorter, more explicit prompts
if "mini" in task_model or "flash" in task_model:
    target_words = 80
else:
    target_words = 150

# ... score based on target_words ...
```

**Pass `--task-model` at runtime:**
```bash
uv run optimize-anything optimize prompt.txt \
  --evaluator-command python3 evaluators/my_eval.py \
  --task-model openai/gpt-4o-mini \
  --objective "Optimize for the target model" \
  --budget 15
```

> `task_model` is informational metadata — it doesn't control which model runs the optimization. That's still determined by `--propose-model` and `--reflect-model`. Use `task_model` purely to steer your evaluator's scoring logic.

---

## 11. Error Handling

Never let your evaluator crash the optimization run. `optimize-anything` standardizes failure modes:

| Evaluator behavior                 | Outcome in optimizer                                           |
|------------------------------------|----------------------------------------------------------------|
| Non-zero exit code (command)      | Uses `score: 0.0` + error side info                            |
| Non-200 response (HTTP)           | Uses `score: 0.0` + error side info                            |
| Invalid JSON output               | Uses `score: 0.0` + error side info                            |
| Missing / non-numeric / NaN score | Uses `score: 0.0` + error side info                            |
| Timeout exceeded                  | Uses `score: 0.0` + timeout side info                          |

**Do:**

- Write diagnostics to **stderr** for command evaluators
- Include diagnostics as **extra JSON keys** in your response (for both command and HTTP)
- Ensure `stdout` (command) or response body (HTTP) contains **only JSON**

**Do not:**

- Print logs, banners, or non-JSON text to **stdout** in a command evaluator
- Return partial or malformed JSON

Outcome: The optimizer always receives a valid score, even when your evaluator encounters errors.

---

## 12. Tips

1. **Start simple.** Create a minimal evaluator that returns a constant score first to verify JSON I/O works, then add real logic incrementally.
2. **Always return rich diagnostics.** Include sub-scores (`length`, `violations`), booleans (`hasIntro`), and `improvementSuggestions`. This produces more targeted mutations because gepa's reflection LM uses these fields to guide the next proposal.
3. **Test evaluators independently** before plugging into optimize-anything. Run `echo '{"candidate":"test"}' | bash evaluators/your-evaluator.sh` to verify JSON parsing and catch logic errors early.
4. **Set `--budget`** to cap evaluator calls. You should never run without a budget — this prevents unexpectedly long or expensive runs.
5. **Favor determinism.** Avoid random seeds and time-based behavior — same input must produce same score for reproducible, debuggable runs.
6. **Use `--score-range any` intentionally.** The default `unit` range catches accidental out-of-bounds scores. Only switch to `any` when your metric genuinely lives outside `[0,1]`.
7. **Read `example` defensively.** Always guard `example = payload.get("example", {})` — the field is absent when not in dataset mode. Your evaluator must handle both cases.
8. **Composite > single-strategy for production.** Heuristic checks are fast and free; LLM calls are slow and cost money. A composite evaluator with a short-circuit threshold gives you the best of both.
