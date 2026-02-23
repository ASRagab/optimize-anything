# Evaluator Cookbook

An evaluator is a function that scores a candidate artifact. optimize-anything supports two evaluator types: **shell commands** and **HTTP endpoints**.

## Evaluator Contract

### Input

Your evaluator receives a JSON object on stdin (command) or as a POST body (HTTP):

```json
{
  "candidate": "the text being optimized",
  "example": null,
  "objective": "maximize clarity and conciseness",
  "background": "target audience is developers"
}
```

| Field | Type | Description |
|---|---|---|
| `candidate` | string \| object | The artifact being scored |
| `example` | any | Current dataset example (if using minibatch) |
| `objective` | string \| undefined | Natural language goal |
| `background` | string \| undefined | Domain context |

### Output

Return JSON on stdout (command) or as the response body (HTTP):

```json
{
  "score": 0.75,
  "sideInfo": {
    "readability": 0.8,
    "accuracy": 0.7,
    "log": "Good structure but could be more concise"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `score` | number | Yes | Overall score, higher is better |
| `sideInfo` | object | No | Diagnostics fed back to the LLM proposer |

**Shorthand:** Returning just a number (`0.75`) is equivalent to `{"score": 0.75}`.

`sideInfo` is powerful — the LLM proposer sees it and uses it to guide the next mutation. Include sub-scores, error messages, or improvement hints.

## Recipe 1: Shell Evaluator (Word Count)

Scores candidates by proximity to a target word count.

```bash
#!/bin/bash
# evaluators/word-count.sh
# Target: 50 words

read input
candidate=$(echo "$input" | jq -r '.candidate')
word_count=$(echo "$candidate" | wc -w | tr -d ' ')
target=50
diff=$((word_count - target))
if [ $diff -lt 0 ]; then diff=$((-diff)); fi
# Score: 1.0 when exactly 50 words, decreasing with distance
score=$(echo "scale=4; 1.0 / (1.0 + $diff / 10.0)" | bc)
echo "{\"score\": $score, \"sideInfo\": {\"wordCount\": $word_count, \"target\": $target}}"
```

**Usage:**
```bash
chmod +x evaluators/word-count.sh
bun run src/cli/index.ts optimize \
  --seed seed.txt \
  --evaluator-command "./evaluators/word-count.sh" \
  --objective "Write exactly 50 words about TypeScript" \
  --max-metric-calls 15
```

**Test your evaluator:**
```bash
echo '{"candidate":"hello world"}' | bash evaluators/word-count.sh
# Expected: {"score": 0.1724, "sideInfo": {"wordCount": 2, "target": 50}}
```

## Recipe 2: HTTP Evaluator (Bun Server)

An HTTP evaluator that scores JSON validity and schema compliance.

```typescript
// evaluators/json-validator.ts
const server = Bun.serve({
  port: 3456,
  async fetch(req) {
    const { candidate } = await req.json();

    let parsed: unknown;
    try {
      parsed = JSON.parse(candidate);
    } catch {
      return Response.json({
        score: 0,
        sideInfo: { error: "Invalid JSON", log: "Candidate is not valid JSON" },
      });
    }

    let score = 0.5; // Valid JSON baseline
    const sideInfo: Record<string, unknown> = { validJson: true };

    // Bonus for having expected keys
    if (typeof parsed === "object" && parsed !== null) {
      const keys = Object.keys(parsed);
      if (keys.includes("name")) { score += 0.15; sideInfo.hasName = true; }
      if (keys.includes("version")) { score += 0.15; sideInfo.hasVersion = true; }
      if (keys.includes("description")) { score += 0.2; sideInfo.hasDescription = true; }
    }

    return Response.json({ score, sideInfo });
  },
});

console.error(`JSON validator evaluator running on port ${server.port}`);
```

**Usage:**
```bash
# Terminal 1: start evaluator
bun run evaluators/json-validator.ts

# Terminal 2: run optimization
bun run src/cli/index.ts optimize \
  --seed seed.json \
  --evaluator-url "http://localhost:3456" \
  --objective "Generate a valid package.json" \
  --max-metric-calls 10
```

**Test your evaluator:**
```bash
curl -X POST http://localhost:3456 \
  -H "Content-Type: application/json" \
  -d '{"candidate": "{\"name\": \"test\"}"}'
# Expected: {"score": 0.65, "sideInfo": {"validJson": true, "hasName": true}}
```

## Evaluator Factories

optimize-anything provides two factory functions for programmatic use:

```typescript
import { createCommandEvaluator, createHttpEvaluator } from "optimize-anything";

// Shell evaluator with 30s timeout
const cmdEval = createCommandEvaluator("./eval.sh", { timeoutMs: 30000 });

// HTTP evaluator with custom headers
const httpEval = createHttpEvaluator("http://localhost:3456", {
  timeoutMs: 10000,
  headers: { "Authorization": "Bearer token" },
});
```

## Timeout Behavior

- **Command evaluators:** The child process is killed when the timeout fires. The evaluation throws an error.
- **HTTP evaluators:** The fetch request is aborted. The evaluation throws an error.
- **Default:** No timeout. Set one to prevent runaway evaluators from blocking the loop.

The optimizer catches evaluation errors and logs them via the event system. A failed evaluation does not crash the run — it skips that candidate.

## Error Handling

| Evaluator behavior | Result |
|---|---|
| Exit code != 0 (command) | Error thrown, candidate skipped |
| Non-200 response (HTTP) | Error thrown, candidate skipped |
| Invalid JSON output | Error thrown, candidate skipped |
| Score is not a finite number | Error thrown, candidate skipped |
| Timeout exceeded | Error thrown, candidate skipped |

**Best practice:** Write diagnostics to stderr (command) or log them in `sideInfo` (both). Never write non-JSON to stdout in a command evaluator.

## Tips

1. **Start simple.** A 5-line bash evaluator that returns a constant score is a valid starting point.
2. **Use `sideInfo` liberally.** The more feedback you give the proposer, the better mutations it generates.
3. **Test evaluators independently** before plugging into optimize-anything.
4. **Set `maxMetricCalls`** to prevent runaway costs. Each call invokes your evaluator once.
5. **Make evaluators deterministic** when possible — same input should produce same score for reproducible runs.
