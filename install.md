# Installation Guide

## Optional local subscription backends

The default install keeps LiteLLM/API behavior. To reuse a Codex login made
through ChatGPT, install the pinned optional SDK and log in with the provider's
CLI:

```bash
uv sync --extra codex
codex login
codex login status
```

Claude subscription support uses the locally installed `claude` executable;
install Claude Code and run `claude auth login`. The adapter requires Claude
Code 2.1.278 or newer and verifies `claude.ai` first-party authentication.

Neither backend accepts tokens in optimize-anything configuration. Codex uses
a private temporary home linked to the provider-owned saved auth file; Claude
runs with API/cloud environment overrides removed. Both fail closed if the
required isolation or auth class cannot be verified.

Choose the host integration or standalone runtime you need:

| Method | Skills | Slash commands | Runtime | Prerequisites |
|---|---|---|---|---|
| **Claude Code plugin** | Yes | Yes | Bundled, locked project | uv, Python >= 3.10 |
| **Codex plugin** | Yes | No | Bundled, locked project | uv, Python >= 3.10 |
| **CLI installer** | No | No | Global `optimize-anything` | None; installer adds uv |
| **From source** | Local checkout | No | `uv run` | uv, Python >= 3.10 |

The Claude Code plugin and Codex plugin discover the same `skills/` tree. Their
launcher runs the repository project directly, so neither plugin requires a
separately installed global CLI. The CLI installer does not install either
plugin.

## Claude Code Plugin

Add the Git marketplace and install:

```bash
/plugin marketplace add ASRagab/optimize-anything
/plugin install optimize-anything@optimize-anything
```

For a local clone:

```bash
/plugin marketplace add /absolute/path/to/optimize-anything
/plugin install optimize-anything@optimize-anything
```

Restart Claude Code, then invoke `$optimize-prompt` or an existing
`/optimize-anything:*` command. The packaged command instructions and skill use
`scripts/run-optimize-anything` automatically.

Update or remove:

```bash
claude plugin update optimize-anything@optimize-anything
claude plugin uninstall optimize-anything@optimize-anything
```

## Codex Plugin

Add the Git marketplace and install:

```bash
codex plugin marketplace add ASRagab/optimize-anything
codex plugin add optimize-anything@optimize-anything
```

For a local clone:

```bash
codex plugin marketplace add /absolute/path/to/optimize-anything
codex plugin add optimize-anything@optimize-anything
```

Start a new Codex thread, then invoke `$optimize-anything:optimize-prompt`.
Codex namespaces plugin skills and discovers the canonical `skills/` tree
through `.codex-plugin/plugin.json`.

Update the Git marketplace and reinstall the plugin, or remove it:

```bash
codex plugin marketplace upgrade optimize-anything
codex plugin add optimize-anything@optimize-anything
codex plugin remove optimize-anything@optimize-anything
```

For local marketplaces, edits are visible after reinstalling the plugin and
starting a new thread; no Git marketplace upgrade is needed.

## CLI Installer

Use this path for a global terminal command without agent skills:

```bash
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash
optimize-anything --help
```

The installer places the command in `~/.local/bin/`. If that directory is not
on `PATH`, add it in the shell that will run the CLI.

Remove it with:

```bash
uv tool uninstall optimize-anything
```

## From Source

```bash
git clone https://github.com/ASRagab/optimize-anything.git
cd optimize-anything
uv sync
uv run pytest
uv run optimize-anything --help
```

The plugin-equivalent launcher is available at
`scripts/run-optimize-anything`. It resolves this checkout, verifies the
prerequisites, and runs `uv run --project <checkout> --locked`.

## Verify Prompt Optimization

After installing either plugin, start a new host session and use its skill
name:

```text
# Claude Code
$optimize-prompt Improve this prompt in fast mode and return the accepted result:
"Summarize this."

# Codex
$optimize-anything:optimize-prompt Improve this prompt in fast mode and return the accepted result:
"Summarize this."
```

Fast mode returns prompt-quality evidence. Rigorous mode additionally requires
representative JSONL examples, a target model, a judge model, and explicit cost
controls; see the prompt workflow in [README.md](README.md).

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `uv: command not found` | Plugin runtime prerequisite missing | Install uv from https://docs.astral.sh/uv/ |
| `Python 3.10 or newer is required` | No supported interpreter is available | Run `uv python install 3.10` |
| Model credential error | Selected proposer, task, or judge model is not authenticated | Export that provider's credential before launching the host |
| Skill is not visible | Host loaded the prior plugin snapshot | Reinstall/update, then start a new thread or session |
| Evaluator command fails | Script path or working directory is wrong | Set `--evaluator-cwd` and run the evaluator preflight payload manually |
| `Error: --output must be a file path` | Output points to a directory | Use a candidate file in a temporary or run directory |
