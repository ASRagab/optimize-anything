# Installation Guide

optimize-anything can be installed three ways. Each gives you different capabilities:

| Method | Skills + `/optimize` | Terminal CLI | Prerequisites |
|---|---|---|---|
| **Claude Code plugin** | Yes | No | [uv](https://docs.astral.sh/uv/), Python >= 3.10 |
| **CLI installer** | No | Yes | None (installs uv automatically) |
| **From source** | If used as plugin | Via `uv run` | uv, Python >= 3.10 |

> **Plugin vs CLI:** The plugin gives you skills *inside Claude Code*. The CLI gives you the `optimize-anything` command *in your terminal*. They are independent -- install either or both.

---

## Claude Code Plugin (recommended for Claude Code users)

The plugin auto-discovers skills and the `/optimize` command.

**Prerequisite:** [uv](https://docs.astral.sh/uv/) and Python >= 3.10 must be installed on your system.

### Install

```bash
claude plugin add https://github.com/ASRagab/optimize-anything
```

Or from a local clone:

```bash
claude plugin add /path/to/optimize-anything
```

### What you get

- **Skills** — `generate-evaluator` and `optimization-guide`
- **Command** — `/optimize` slash command

### Verify

In Claude Code, run `/optimize` or ask Claude to use the optimization-guide skill.

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

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not installed | Run the CLI installer (installs uv) or install from https://docs.astral.sh/uv/ |
| `ANTHROPIC_API_KEY missing` | Env var not set | Export in shell or add `env` block to MCP config |
| `ModuleNotFoundError` | Dependencies not installed | Run `uv sync` in the project directory (source install) |
| Evaluator command fails repeatedly | Script path/cwd mismatch | Use `artifacts/eval.sh` directly or set `--evaluator-cwd` correctly, then validate with `echo '{"candidate":"test"}' | <command>` |
| `Error: --output must be a file path` | Passed directory to CLI output | Use a file path like `artifacts/result.txt` instead of `artifacts/` |
| Plugin not working | uv not on PATH | Ensure `uv` is installed and available in your shell's PATH |
