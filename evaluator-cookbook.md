# Evaluator Cookbook

An evaluator is a function that **scores a candidate artifact**. `optimize-anything` supports three types: **shell commands**, **HTTP endpoints**, and **LLM judges**.

---

## 1. Evaluator Contract

### Input

Your evaluator must read a JSON object from **stdin** (command) or as a **POST body** (HTTP):

```json
{
  "candidate": "the text being optimized"
}
```

| Field       | Type   | Description                  |
|------------|--------|------------------------------|
| `candidate`| string | The artifact being evaluated |

> **Note:** The `objective` and `background` strings are **not** passed to your evaluator — only to gepa's reflection LM. Your evaluator only sees the `candidate`.

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

## 5. Auto-generating Evaluators

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

## 6. Evaluator Factories (Python API)

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

## 7. Error Handling

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

## 8. Tips

1. **Start simple.** Create a minimal evaluator that returns a constant score first to verify JSON I/O works, then add real logic incrementally.
2. **Always return rich diagnostics.** Include sub-scores (`length`, `violations`), booleans (`hasIntro`), and `improvementSuggestions`. This produces more targeted mutations because gepa’s reflection LM uses these fields to guide the next proposal.
3. **Test evaluators independently** before plugging into optimize-anything. Run `echo ‘{"candidate":"test"}’ | bash evaluators/your-evaluator.sh` to verify JSON parsing and catch logic errors early.
4. **Set `--budget`** to cap evaluator calls. You should never run without a budget — this prevents unexpectedly long or expensive runs.
5. **Favor determinism.** Avoid random seeds and time-based behavior — same input must produce same score for reproducible, debuggable runs.