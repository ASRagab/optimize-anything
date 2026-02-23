# MCP Protocol

> Protocol documentation for the optimize-anything MCP server.

## Transport: stdio

The server uses FastMCP with stdio transport. Clients communicate over stdin/stdout using the MCP protocol.

## Starting the Server

```bash
uv run python -m optimize_anything.server
```

Or via the CLI entry point:

```bash
uv run optimize-anything serve  # if serve subcommand is added
```

## Available Tools

### 1. optimize

Run LLM-guided optimization on a text artifact.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `seed` | string | Yes | -- | The seed text artifact to optimize |
| `evaluator_command` | list[str] | No | null | Shell command for evaluation |
| `evaluator_url` | string | No | null | HTTP POST endpoint for evaluation |
| `objective` | string | No | null | Natural language optimization goal |
| `background` | string | No | null | Domain knowledge and constraints |
| `max_metric_calls` | int | No | 100 | Maximum evaluator invocations |

Requires either `evaluator_command` or `evaluator_url`.

**Returns:** JSON string with `best_candidate`, `total_metric_calls`, and `val_scores`.

**Example:**
```json
{
  "seed": "You are a helpful assistant.",
  "evaluator_command": ["bash", "eval.sh"],
  "objective": "maximize helpfulness and clarity",
  "max_metric_calls": 50
}
```

### 2. explain

Preview what optimization would do for a given artifact without running it.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `seed` | string | Yes | -- | The seed text artifact |
| `objective` | string | No | null | Natural language optimization goal |

**Returns:** Human-readable explanation of the optimization plan.

### 3. recommend_budget

Get a recommended evaluation budget based on artifact characteristics.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `seed` | string | Yes | -- | The seed text artifact |
| `evaluator_type` | string | No | "command" | Type of evaluator ("command" or "http") |

**Returns:** JSON with `recommended_budget`, `rationale`, `seed_length`, and `evaluator_type`.

**Budget recommendations:**

| Seed length | Budget | Rationale |
|---|---|---|
| < 100 chars | 50 | Short artifact -- fewer mutations needed |
| 100-499 chars | 100 | Medium artifact -- moderate exploration |
| 500-1999 chars | 200 | Long artifact -- more exploration needed |
| >= 2000 chars | 300 | Very long artifact -- extensive exploration |

### 4. generate_evaluator

Generate an evaluator script for a given artifact and objective.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `seed` | string | Yes | -- | The seed text artifact |
| `objective` | string | Yes | -- | What to optimize for |
| `evaluator_type` | string | No | "command" | "command" for bash, "http" for Python server |

**Returns:** The generated script content as a string.

## Rules

### 1. stdout: protocol only

All protocol communication happens over stdout. No debug output, logging, or non-protocol data should be written to stdout.

### 2. stderr: diagnostics and logs

All diagnostic output -- debug logs, warnings, progress info -- goes to stderr.

### 3. Error handling

Tool errors are returned as JSON strings with an `error` field. The server does not crash on evaluation failures.

## MCP Client Configuration

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/optimize-anything", "python", "-m", "optimize_anything.server"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

## Error Codes

Tool-level errors are returned within the tool response as JSON. Protocol-level errors follow standard MCP/JSON-RPC conventions.
