# Installation Guide

optimize-anything can be installed three ways. Each gives you different capabilities:

| Method | MCP tools in Claude Code | Skills + `/optimize` | Terminal CLI | Prerequisites |
|---|---|---|---|---|
| **Claude Code plugin** | Yes | Yes | No | [uv](https://docs.astral.sh/uv/), Python >= 3.10 |
| **CLI installer** | No | No | Yes | None (installs uv automatically) |
| **From source** | Via `uv run` | If used as plugin | Via `uv run` | uv, Python >= 3.10 |

> **Plugin vs CLI:** The plugin gives you MCP tools and skills *inside Claude Code*. The CLI gives you the `optimize-anything` command *in your terminal*. They are independent — install either or both.

---

## Claude Code Plugin (recommended for Claude Code users)

The plugin auto-discovers the MCP server, skills, and `/optimize` command. The MCP server self-bootstraps via `uv run` on first use — no manual dependency install needed.

**Prerequisite:** [uv](https://docs.astral.sh/uv/) and Python >= 3.10 must be installed on your system. The plugin's MCP server is launched via `uv --directory <plugin-root> run python -m optimize_anything.server`, which auto-installs dependencies into an isolated environment.

### Install

```bash
claude plugin add https://github.com/ASRagab/optimize-anything
```

Or from a local clone:

```bash
claude plugin add /path/to/optimize-anything
```

### What you get

- **MCP tools** — `optimize`, `explain`, `recommend_budget`, `generate_evaluator`
- **Skills** — `generate-evaluator` and `optimization-guide`
- **Command** — `/optimize` slash command

### Verify

In Claude Code, run `/optimize` or ask Claude to use the optimize tool.

### Uninstall

```bash
claude plugin remove optimize-anything
```

---

## CLI Installer (recommended for terminal use)

Installs `optimize-anything` as a global CLI command in `~/.local/bin/`. This does **not** install the Claude Code plugin — the CLI is a standalone tool.

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash
```

This will:
1. Install [uv](https://docs.astral.sh/uv/) if not already present
2. Run `uv tool install` to install `optimize-anything` in an isolated environment
3. Verify the installation

### Verify

```bash
optimize-anything --help
```

If the command is not found, add `~/.local/bin` to your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Uninstall

```bash
uv tool uninstall optimize-anything
```

Or via the installer:
```bash
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash -s -- --uninstall
```

---

## From Source (for development)

Clone and install in a local virtual environment. Use `uv run` to execute commands.

```bash
git clone https://github.com/ASRagab/optimize-anything.git
cd optimize-anything
uv sync
```

### Verify

```bash
uv run pytest              # Run tests
uv run optimize-anything --help   # Check CLI
```

### Use as plugin from source

If you've cloned the repo, you can also add it as a Claude Code plugin:
```bash
claude plugin add /path/to/optimize-anything
```

---

## Manual MCP Configuration (non-plugin)

If you're not using Claude Code's plugin system (e.g., Claude Desktop, other MCP clients), configure the MCP server manually.

**Prerequisite:** `uv` and Python >= 3.10 installed, and the repo cloned locally.

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

Edit `~/.config/Claude/claude_desktop_config.json` with the same structure.

### Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

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

Any stdio-compatible MCP client works:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/optimize-anything", "python", "-m", "optimize_anything.server"]
}
```

### Verify MCP

1. Restart the MCP client
2. Confirm the `optimize` tool appears in the tool listing
3. Test with:
   ```json
   {
     "seed": "hello world",
     "evaluator_command": ["bash", "-c", "echo '{\"score\": 1}'"],
     "max_metric_calls": 1
   }
   ```

### Uninstall MCP

Remove the `optimize-anything` entry from your MCP client config and restart the client.

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not installed | Run the CLI installer (installs uv) or install from https://docs.astral.sh/uv/ |
| `ANTHROPIC_API_KEY missing` | Env var not set | Export in shell or add `env` block to MCP config |
| `ModuleNotFoundError` | Dependencies not installed | Run `uv sync` in the project directory (source install) |
| Server starts but no tools | MCP config syntax error | Validate JSON: `jq . < config.json` |
| Tool call hangs | Evaluator not executable | Run `chmod +x evaluator.sh` |
| Plugin MCP fails to start | uv not on PATH | Ensure `uv` is installed and available in your shell's PATH |
