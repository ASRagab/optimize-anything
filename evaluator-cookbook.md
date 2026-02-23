# Evaluator Cookbook

An evaluator is a function that scores a candidate artifact. optimize-anything supports two evaluator types: **shell commands** and **HTTP endpoints**.

## Evaluator Contract

### Input

Your evaluator receives a JSON object on stdin (command) or as a POST body (HTTP):

```json
{
  "candidate": "the text being optimized"
}
```

| Field | Type | Description |
|---|---|---|
| `candidate` | string | The artifact being scored |

> **Note:** The `objective` and `background` strings are passed to gepa's reflection LM, not to your evaluator. Your evaluator only sees the candidate text.

### Output

Return JSON on stdout (command) or as the response body (HTTP):

```json
{
  "score": 0.75,
  "readability": 0.8,
  "accuracy": 0.7,
  "notes": "Good structure but could be more concise"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `score` | number | Yes | Overall score, higher is better |
| *(any other keys)* | any | No | Side information fed to gepa's reflection LM |

All fields beyond `score` become side information that gepa's reflection LM uses to guide the next mutation. Include sub-scores, error messages, or improvement hints.

## Recipe 1: Shell Evaluator (Word Count)

Scores candidates by proximity to a target word count.

```bash
#!/usr/bin/env bash
# evaluators/word-count.sh
# Target: 50 words

input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
word_count=$(echo "$candidate" | wc -w | tr -d ' ')
target=50
diff=$((word_count - target))
if [ $diff -lt 0 ]; then diff=$((-diff)); fi
# Score: 1.0 when exactly 50 words, decreasing with distance
score=$(python3 -c "print(round(1.0 / (1.0 + $diff / 10.0), 4))")
echo "{\"score\": $score, \"wordCount\": $word_count, \"target\": $target}"
```

**Usage:**
```bash
chmod +x evaluators/word-count.sh
uv run optimize-anything optimize seed.txt \
  --evaluator-command bash evaluators/word-count.sh \
  --objective "Write exactly 50 words about Python" \
  --budget 15
```

**Test your evaluator:**
```bash
echo '{"candidate":"hello world"}' | bash evaluators/word-count.sh
# Expected: {"score": 0.1724, "wordCount": 2, "target": 50}
```

## Recipe 2: HTTP Evaluator (Python Server)

An HTTP evaluator that scores JSON validity and schema compliance.

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

**Usage:**
```bash
# Terminal 1: start evaluator
python3 evaluators/json_validator.py

# Terminal 2: run optimization
uv run optimize-anything optimize seed.json \
  --evaluator-url "http://localhost:3456" \
  --objective "Generate a valid package.json" \
  --budget 10
```

**Test your evaluator:**
```bash
curl -X POST http://localhost:3456 \
  -H "Content-Type: application/json" \
  -d '{"candidate": "{\"name\": \"test\"}"}'
# Expected: {"score": 0.65, "validJson": true, "hasName": true}
```

## Auto-generating Evaluators

optimize-anything can generate a starter evaluator for you:

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

Or use the MCP tool:
```json
{
  "tool": "generate_evaluator",
  "arguments": {
    "seed": "Your seed text",
    "objective": "maximize clarity",
    "evaluator_type": "command"
  }
}
```

The generated evaluator is a starting point. Customize the scoring logic to match your specific objective.

## Evaluator Factories

optimize-anything provides two factory functions for programmatic use:

```python
from optimize_anything.evaluators import command_evaluator, http_evaluator

# Shell evaluator
cmd_eval = command_evaluator(["bash", "eval.sh"])

# HTTP evaluator
http_eval = http_evaluator("http://localhost:3456")
```

## Error Handling

| Evaluator behavior | Result |
|---|---|
| Exit code != 0 (command) | Returns `score: 0.0` with error side info |
| Non-200 response (HTTP) | Returns `score: 0.0` with error side info |
| Invalid JSON output | Returns `score: 0.0` with error side info |
| Score is missing/non-numeric/non-finite | Returns `score: 0.0` with error side info |
| Timeout exceeded | Returns `score: 0.0` with error side info |

**Best practice:** Write diagnostics to stderr (command) or include them as extra keys in the JSON output (both). Never write non-JSON to stdout in a command evaluator.

## Tips

1. **Start simple.** A 5-line bash evaluator that returns a constant score is a valid starting point.
2. **Include diagnostic fields liberally.** The more feedback you give gepa's reflection LM (as extra JSON keys), the better mutations it generates.
3. **Test evaluators independently** before plugging into optimize-anything.
4. **Set `--budget`** to prevent runaway costs. Each call invokes your evaluator once.
5. **Make evaluators deterministic** when possible -- same input should produce same score for reproducible runs.
