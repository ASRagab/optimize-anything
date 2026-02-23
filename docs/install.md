# Installation Guide

## Prerequisites

| Requirement | Minimum | Check |
|---|---|---|
| Python | >= 3.10 | `python3 --version` |
| ANTHROPIC_API_KEY | Set in env | `echo $ANTHROPIC_API_KEY` |

> **Note:** `uv` is installed automatically by the installer if not present.

## Quick Install (recommended)

One command — installs `uv` if needed, then `optimize-anything` as a global CLI:

```bash
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash
```

After installation, `optimize-anything` is available globally:

```bash
optimize-anything --help
```

## Manual Install

If you already have [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/ASRagab/optimize-anything
```

## Install from Source (for development)

```bash
git clone <repo-url>
cd optimize-anything
uv sync
```

### Verify Source Installation

```bash
# Run tests
uv run pytest

# Check CLI
uv run optimize-anything --help
```

Both commands should complete without errors.

## Uninstall CLI

```bash
uv tool uninstall optimize-anything
```

## Claude Code Plugin

optimize-anything is a Claude Code plugin. When installed as a plugin, Claude Code auto-discovers the MCP server, skills, and commands.

### Install as Plugin

```bash
claude plugin add /path/to/optimize-anything
```

Or from a git URL:

```bash
claude plugin add https://github.com/ASRagab/optimize-anything
```

This gives you:
- **MCP tools** — `optimize`, `explain`, `recommend_budget`, `generate_evaluator` available in Claude Code
- **Skills** — `generate-evaluator` and `optimization-guide` for guided workflows
- **Command** — `/optimize` slash command

### Verify Plugin

In Claude Code, run:
```
/optimize
```

Or ask Claude to use the optimize tool directly.

### Uninstall Plugin

```bash
claude plugin remove optimize-anything
```

## MCP Client Configuration (non-plugin)

If you're not using Claude Code's plugin system, configure the MCP server manually.

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

Any MCP client that supports stdio transport can use optimize-anything:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/optimize-anything", "python", "-m", "optimize_anything.server"]
}
```

## Verification Checklist

After configuring your MCP client or installing the plugin:

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
| `uv: command not found` | uv not installed | Run the install script or install from https://docs.astral.sh/uv/ |
| `ANTHROPIC_API_KEY missing` | Env var not passed through | Add `env` block to MCP config |
| `ModuleNotFoundError` | Dependencies not installed | Run `uv sync` in the project directory |
| Server starts but no tools | Config syntax error | Validate JSON with `jq . < config.json` |
| Tool call hangs | Evaluator script not executable | Run `chmod +x evaluator.sh` |

## Uninstall

**CLI (global):**
```bash
uv tool uninstall optimize-anything
```

**Claude Code plugin:**
```bash
claude plugin remove optimize-anything
```

**Manual MCP config:**
1. Remove the `optimize-anything` entry from your MCP client config
2. Restart the MCP client

**Source clone:**
```bash
rm -rf optimize-anything
```
