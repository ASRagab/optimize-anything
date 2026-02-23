# optimize-anything

LLM-guided optimization for text artifacts using an iterative propose-evaluate-reflect loop with a bring-your-own evaluator.

## Overview

optimize-anything takes a seed artifact (prompt, code snippet, config, etc.), evaluates it against your custom scoring function, then uses an LLM to propose improvements. The loop runs until a budget is exhausted or a stop condition is met.

**Core loop:** seed -> evaluate -> propose mutation -> evaluate -> reflect -> repeat

Key features:
- **BYO evaluator** — shell commands or HTTP endpoints
- **Pareto frontier** — tracks non-dominated candidates across multiple metrics
- **Deterministic** — seeded selection for reproducible runs
- **Resumable** — persist and resume runs from disk
- **MCP server** — integrate directly with Claude Desktop or any MCP client

## Prerequisites

- [Bun](https://bun.sh) >= 1.0
- An `ANTHROPIC_API_KEY` environment variable
- An evaluator (shell script or HTTP server) that scores candidates

## Quickstart

### CLI

```bash
# Clone and install
git clone <repo-url> && cd optimize-anything
bun install

# Create a seed file
echo "Write a haiku about the ocean" > seed.txt

# Create an evaluator (stdin JSON -> stdout JSON with score)
cat > eval.sh << 'EVAL'
#!/bin/bash
read input
echo '{"score": 0.5}'
EVAL
chmod +x eval.sh

# Run optimization
ANTHROPIC_API_KEY=sk-... bun run src/cli/index.ts optimize \
  --seed seed.txt \
  --evaluator-command "./eval.sh" \
  --max-metric-calls 10 \
  --output result.txt
```

The optimized artifact is written to `result.txt`. A full run log is saved to `./runs/<timestamp>/result.json`.

### MCP (Model Context Protocol)

Add to your MCP client config (see [docs/install.md](docs/install.md) for platform-specific paths):

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "bun",
      "args": ["run", "/path/to/optimize-anything/src/mcp/server.ts"],
      "env": { "ANTHROPIC_API_KEY": "sk-..." }
    }
  }
}
```

Then call the `optimize` tool:

```json
{
  "seedCandidate": "Write a haiku about the ocean",
  "evaluatorCommand": "./eval.sh",
  "maxMetricCalls": 10
}
```

## Evaluator Contract

Your evaluator receives JSON on stdin and must return JSON on stdout:

**Input (stdin):**
```json
{
  "candidate": "the text artifact being scored",
  "objective": "optional objective string",
  "background": "optional domain context"
}
```

**Output (stdout):**
```json
{
  "score": 0.75,
  "sideInfo": {
    "readability": 0.8,
    "accuracy": 0.7,
    "log": "optional diagnostic text"
  }
}
```

- `score` (required): float, higher is better
- `sideInfo` (optional): diagnostics fed back to the LLM proposer

Returning just a number also works: `0.75`

See [docs/evaluator-cookbook.md](docs/evaluator-cookbook.md) for full recipes.

## CLI Flags

| Flag | Description | Default |
|---|---|---|
| `--seed <file>` | Path to seed artifact file | (required unless `--objective`) |
| `--evaluator-command <cmd>` | Shell command evaluator | — |
| `--evaluator-url <url>` | HTTP POST evaluator URL | — |
| `--objective <text>` | Natural language objective | — |
| `--background <text>` | Domain knowledge/constraints | — |
| `--max-metric-calls <n>` | Max evaluator invocations | 20 |
| `--output <file>` | Write best candidate to file | stdout |
| `--run-dir <dir>` | Directory for run artifacts | `./runs/<timestamp>` |

## MCP Tool Arguments

| Argument | Type | Description |
|---|---|---|
| `seedCandidate` | string | Initial text to optimize |
| `evaluatorCommand` | string | Shell command evaluator |
| `evaluatorUrl` | string | HTTP POST evaluator URL |
| `objective` | string | Natural language objective |
| `background` | string | Domain knowledge/constraints |
| `maxMetricCalls` | number | Max evaluator calls (default: 20) |

Requires either `evaluatorCommand` or `evaluatorUrl`, plus either `seedCandidate` or `objective`.

## Architecture

```
src/
  core/
    optimizer.ts    # Main optimization loop
    proposer.ts     # LLM prompt builder for mutations
    reflector.ts    # Post-evaluation reflection
    evaluate.ts     # Candidate evaluation with caching
    evaluator.ts    # Command and HTTP evaluator factories
    candidate-selector.ts  # Frontier-based selection
    pareto.ts       # Pareto dominance computation
    state.ts        # Run state management
    persistence.ts  # Save/load run state
    events.ts       # Event emitter for lifecycle hooks
    stop-conditions.ts  # Configurable stopping criteria
    llm.ts          # Anthropic API adapter
    asi.ts          # Eval result normalization + hashing
  mcp/
    server.ts       # JSON-RPC stdio MCP server
    schema.ts       # MCP tool schema definition
  cli/
    index.ts        # CLI entry point
  types.ts          # Shared type definitions
  index.ts          # Public API exports
```

## Programmatic API

```typescript
import { optimizeAnything, createCommandEvaluator, AnthropicModel } from "optimize-anything";

const result = await optimizeAnything({
  seedCandidate: "initial text",
  evaluator: createCommandEvaluator("./eval.sh"),
  model: new AnthropicModel({ apiKey: "sk-...", model: "claude-sonnet-4-20250514", maxTokens: 1024 }),
  objective: "maximize clarity",
  config: {
    engine: { maxMetricCalls: 20 },
    tracking: { runDir: "./my-run" },
  },
});

console.log(result.bestCandidate, result.bestScore);
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ANTHROPIC_API_KEY missing` | Set `ANTHROPIC_API_KEY` in your environment |
| `Seed file not found` | Check `--seed` path is correct |
| `Evaluator command failed` | Verify evaluator outputs valid JSON to stdout and exits 0 |
| MCP server not responding | Check MCP config paths match your clone location |
| `Invalid JSON` from evaluator | Ensure evaluator writes only JSON to stdout (logs go to stderr) |

## Links

- [Installation Guide](docs/install.md)
- [Evaluator Cookbook](docs/evaluator-cookbook.md)
- [MCP Protocol Policy](docs/mcp-protocol.md)
- [Examples](examples/)
