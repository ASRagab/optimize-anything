# Examples

Runnable examples for optimize-anything.

## Shell Evaluator (echo-score)

Scores candidates by length. No external dependencies.

```bash
# Test the evaluator directly
echo '{"candidate":"hello world"}' | bash examples/evaluators/echo-score.sh
# Output: {"score": 0.0521, "sideInfo": {"length": 11}}

# Run optimization (requires ANTHROPIC_API_KEY)
bun run src/cli/index.ts optimize \
  --seed examples/seeds/sample-seed.txt \
  --evaluator-command "bash examples/evaluators/echo-score.sh" \
  --max-metric-calls 5 \
  --output /tmp/optimized.txt

cat /tmp/optimized.txt
```

## HTTP Evaluator (word-count target)

Scores candidates by proximity to 50 words.

```bash
# Terminal 1: start the evaluator server
bun run examples/evaluators/http-evaluator.ts

# Terminal 2: test it
curl -X POST http://localhost:3456 \
  -H "Content-Type: application/json" \
  -d '{"candidate": "hello world"}'
# Output: {"score": 0.17241379310344826, "sideInfo": {"wordCount": 2, "target": 50, "diff": 48}}

# Terminal 2: run optimization
bun run src/cli/index.ts optimize \
  --seed examples/seeds/sample-seed.txt \
  --evaluator-url http://localhost:3456 \
  --objective "Write about TypeScript in exactly 50 words" \
  --max-metric-calls 10 \
  --output /tmp/optimized.txt
```

## Output Artifacts

After a CLI run with `--run-dir`, the directory contains:

- `state.json` — full run state (all candidates, scores, frontier)
- `result.json` — final result with best candidate and events

You can inspect results with:

```bash
cat runs/*/result.json | jq '.bestScore, .totalMetricCalls'
```

## Writing Your Own Evaluator

See [docs/evaluator-cookbook.md](../docs/evaluator-cookbook.md) for the full contract and more recipes.
