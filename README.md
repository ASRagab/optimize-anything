# optimize-anything

LLM-guided optimization for text artifacts using an iterative propose-evaluate-reflect loop with a bring-your-own evaluator.

## Overview

optimize-anything takes a seed artifact (prompt, code snippet, config, etc.), evaluates it against your custom scoring function, then uses an LLM to propose improvements. The loop runs until a budget is exhausted or a stop condition is met.

**Core loop:** seed -> evaluate -> propose mutation -> evaluate -> reflect -> repeat

Key features:
- **BYO evaluator** -- shell commands or HTTP endpoints
- **Powered by gepa** -- evolutionary search with LLM-guided mutations
- **MCP server** -- integrate directly with Claude Desktop or any MCP client
- **CLI** -- run optimizations from the terminal
- **Evaluator generator** -- auto-generate starter evaluator scripts

## Install

**Claude Code plugin** — MCP tools + skills + `/optimize` command inside Claude Code:

```bash
claude plugin add https://github.com/ASRagab/optimize-anything
```
> Requires [uv](https://docs.astral.sh/uv/) and Python >= 3.10. The MCP server auto-installs its dependencies on first use.

**Terminal CLI** — installs the `optimize-anything` command in your shell:

```bash
# One-liner (installs uv if needed):
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash

# Or directly with uv:
uv tool install git+https://github.com/ASRagab/optimize-anything
```
> Plugin and CLI are independent — install either or both.

**From source** (for development):

```bash
git clone https://github.com/ASRagab/optimize-anything.git && cd optimize-anything
uv sync
```

See [docs/install.md](docs/install.md) for manual MCP config, platform-specific setup, and troubleshooting.

## Quickstart

### CLI

```bash
# Create a seed file
echo "Write a haiku about the ocean" > seed.txt

# Create an evaluator (stdin JSON -> stdout JSON with score)
cat > eval.sh << 'EVAL'
#!/usr/bin/env bash
input=$(cat)
echo '{"score": 0.5}'
EVAL
chmod +x eval.sh

# Run optimization
ANTHROPIC_API_KEY=sk-... uv run optimize-anything optimize seed.txt \
  --evaluator-command bash eval.sh \
  --budget 10 \
  --output result.txt
```

The optimized artifact is written to `result.txt`. CLI stdout returns a canonical
JSON summary (`best_artifact`, `total_metric_calls`, `score_summary`,
`top_diagnostics`, `plateau_guidance`).

### MCP (Model Context Protocol)

Add to your MCP client config (see [docs/install.md](docs/install.md) for platform-specific paths):

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/optimize-anything", "python", "-m", "optimize_anything.server"],
      "env": { "ANTHROPIC_API_KEY": "sk-..." }
    }
  }
}
```

Then call the `optimize` tool:

```json
{
  "seed": "Write a haiku about the ocean",
  "evaluator_command": ["bash", "eval.sh"],
  "evaluator_cwd": "/absolute/path/to/your/project",
  "max_metric_calls": 10
}
```

## Evaluator Contract

Your evaluator receives JSON on stdin and must return JSON on stdout:

**Input (stdin):**
```json
{
  "candidate": "the text artifact being scored"
}
```

**Output (stdout):**
```json
{
  "score": 0.75,
  "length": 42,
  "notes": "optional diagnostic text"
}
```

- `score` (required): float, higher is better
- Any additional fields become side information fed back to gepa's reflection LM

See [docs/evaluator-cookbook.md](docs/evaluator-cookbook.md) for full recipes.

## CLI Commands

### optimize

```bash
uv run optimize-anything optimize <seed_file> [options]
```

| Flag | Description | Default |
|---|---|---|
| `seed_file` | Path to seed artifact file | (required) |
| `--evaluator-command <cmd...>` | Shell command evaluator | -- |
| `--evaluator-cwd <path>` | Working directory for evaluator command | current process cwd |
| `--evaluator-url <url>` | HTTP POST evaluator URL | -- |
| `--intake-json <json-string>` | Inline evaluator intake JSON (validated) | -- |
| `--intake-file <path>` | Path to evaluator intake JSON file (validated) | -- |
| `--objective <text>` | Natural language objective | -- |
| `--background <text>` | Domain knowledge/constraints | -- |
| `--budget <n>` | Max evaluator invocations | 100 |
| `--output, -o <file>` | Write best candidate to file | stdout |

If intake is provided, `execution_mode` is used to decide which evaluator source flag is required when neither `--evaluator-command` nor `--evaluator-url` is set. Explicit evaluator flags always win if both explicit flags and intake are supplied.

### explain

```bash
uv run optimize-anything explain <seed_file> [--objective <text>]
```

Preview what optimization would do for a given seed artifact.

### budget

```bash
uv run optimize-anything budget <seed_file>
```

Get a recommended evaluation budget based on the seed artifact length.

## MCP Tools

| Tool | Description |
|---|---|
| `optimize` | Run LLM-guided optimization with BYO evaluator |
| `explain` | Preview what optimization would do |
| `recommend_budget` | Get budget recommendations based on artifact size |
| `generate_evaluator` | Generate a starter evaluator script |
| `evaluator_intake` | Normalize/validate evaluator intake schema |

See [docs/mcp-protocol.md](docs/mcp-protocol.md) for full tool schemas.

## Architecture

```
src/optimize_anything/
  __init__.py              # Public API re-exports
  evaluators.py            # Command and HTTP evaluator factories
  evaluator_generator.py   # Generate evaluator scripts from seed + objective
  server.py                # FastMCP server with 5 tools
  cli.py                   # CLI entry point (argparse)
  __main__.py              # python -m support

commands/
  optimize.md              # /optimize command definition

skills/
  generate-evaluator/      # Evaluator generation skill
  optimization-guide/      # Optimization workflow guide

examples/
  evaluators/              # Sample evaluator scripts
  seeds/                   # Sample seed artifacts

docs/
  install.md               # Installation and MCP client setup
  evaluator-cookbook.md     # Guide to writing evaluators
  mcp-protocol.md          # MCP tool schemas and protocol docs
```

## Programmatic API

```python
from optimize_anything import optimize_anything, command_evaluator
from gepa.optimize_anything import GEPAConfig, EngineConfig

eval_fn = command_evaluator(["bash", "eval.sh"])
config = GEPAConfig(engine=EngineConfig(max_metric_calls=20))

result = optimize_anything(
    seed_candidate="initial text",
    evaluator=eval_fn,
    objective="maximize clarity",
    config=config,
)

print(result.best_candidate)
```

## Generating Evaluators

If you do not have an evaluator, optimize-anything can generate one:

```python
from optimize_anything.evaluator_generator import generate_evaluator_script

script = generate_evaluator_script(
    seed="Your seed artifact",
    objective="maximize clarity",
    evaluator_type="command",  # or "http"
)
```

This produces a bash script (or Python HTTP server) that you can customize.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ANTHROPIC_API_KEY missing` | Set `ANTHROPIC_API_KEY` in your environment |
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| `Seed file not found` | Check the seed file path is correct |
| `Evaluator command failed` | Verify evaluator outputs valid JSON to stdout and exits 0 |
| MCP server not responding | Check MCP config paths match your clone location |
| `Invalid JSON` from evaluator | Ensure evaluator writes only JSON to stdout (logs go to stderr) |

## Uninstall

**CLI** (`optimize-anything` command):

```bash
uv tool uninstall optimize-anything
```

**Plugin:**

```bash
claude plugin remove optimize-anything
```

## Links

- [Installation Guide](docs/install.md)
- [Evaluator Cookbook](docs/evaluator-cookbook.md)
- [MCP Protocol](docs/mcp-protocol.md)
- [Examples](examples/)
