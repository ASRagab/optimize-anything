# Installation Guide

## Prerequisites

| Requirement | Minimum | Check |
|---|---|---|
| Python | >= 3.10 | `python3 --version` |
| uv | >= 0.4 | `uv --version` |
| ANTHROPIC_API_KEY | Set in env | `echo $ANTHROPIC_API_KEY` |

## Install from Source

```bash
git clone <repo-url>
cd optimize-anything
uv sync
```

### Verify Installation

```bash
# Run tests
uv run pytest

# Check CLI
uv run optimize-anything --help
```

Both commands should complete without errors.

## MCP Client Configuration

### Claude Desktop (macOS)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/optimize-anything", "python", "-m", "optimize_anything.server"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Claude Desktop (Linux)

Edit `~/.config/Claude/claude_desktop_config.json` with the same structure as above.

### Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json` with the same structure, using Windows paths:

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\Users\\you\\optimize-anything", "python", "-m", "optimize_anything.server"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Other MCP Clients

Any MCP client that supports stdio transport can use optimize-anything. The server uses FastMCP and communicates over stdin/stdout.

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/optimize-anything", "python", "-m", "optimize_anything.server"]
}
```

## Verification Checklist

After configuring your MCP client:

1. **Restart the MCP client** to pick up config changes
2. **Check tool listing** -- the `optimize` tool should appear
3. **Test with a simple call:**
   ```json
   {
     "seed": "hello world",
     "evaluator_command": ["bash", "-c", "echo '{\"score\": 1}'"],
     "max_metric_calls": 1
   }
   ```
4. **Expected result:** a JSON response with `best_candidate`, `total_metric_calls`, and `val_scores`

## Common Setup Errors

| Error | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not installed | Install from https://docs.astral.sh/uv/ |
| `ANTHROPIC_API_KEY missing` | Env var not passed through | Add `env` block to MCP config |
| `ModuleNotFoundError` | Dependencies not installed | Run `uv sync` in the project directory |
| Server starts but no tools | Config syntax error | Validate JSON with `jq . < config.json` |
| Tool call hangs | Evaluator script not executable | Run `chmod +x evaluator.sh` |

## Uninstall / Rollback

1. Remove the `optimize-anything` entry from your MCP client config file
2. Restart the MCP client
3. Optionally delete the cloned repository: `rm -rf optimize-anything`

No global packages or system-level changes are made during installation.
