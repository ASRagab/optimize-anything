# Installation Guide

## Optional local subscription backends

The plugin launcher selects the locked `codex` SDK extra automatically. To
reuse a Codex login made through ChatGPT, authenticate with the provider CLI:

```bash
codex login
codex login status
```

For a source checkout, install the optional SDK in that project environment:

```bash
uv sync --extra codex
```

For a global CLI install, pass `--codex` to `install.sh`; this installs SDK
version 0.156.0 required by the adapter in the isolated uv tool environment.
The default global install keeps LiteLLM/API behavior.

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
| **Codex plugin** | Yes | No | Bundled, locked project with `codex` extra | uv, Python >= 3.10; `codex login` for subscription use |
| **CLI installer** | No | No | Global `optimize-anything` | None; installer adds uv |
| **From source** | Local checkout | No | `uv run` | uv, Python >= 3.10 |

The Claude Code plugin and Codex plugin discover the same `skills/` tree. Their
launcher runs the repository project with the locked `codex` extra, so neither
plugin requires a separately installed global CLI. Generated evaluator child
processes use that same project environment. The CLI installer does not install
either plugin.

### Supported versions

| Component | Requirement | Tested (2026-09-26) |
|---|---|---|
| `openai-codex` Python SDK | Exactly 0.156.0 (the `codex` extra and adapter) | 0.156.0 |
| Codex CLI | Any CLI that can `codex login` with ChatGPT | 0.155.1 |
| Claude Code (`claude`) | 2.1.278 or newer, `claude.ai` first-party auth | 2.1.283 |
| Platform | macOS, local machine only | macOS 26.6.2 arm64, Python 3.12.14 |

Other platforms, hosted runners, and newer SDK releases are untested; the
adapters fail closed rather than guessing when a required control is missing.

### Experimental Claude scope

Claude subscription support is experimental, opt-in, and local-only. It is not
supported for hosted services, CI, shared daemons, or any setup where one
login serves other people. Using a Claude subscription through a third-party
tool carries a provider-policy risk that is separate from whether it works
technically; review Anthropic's current terms before relying on it. The
adapter never starts a login flow, extracts tokens, or reuses a host
conversation.

### Billing and API fallback

Subscription backends never switch to an API silently. A failure can move a
role to the same-vendor API only when all of these hold:

- the failure category is `backend_unavailable`, `authentication`,
  `rate_limit`, or `quota_exceeded`;
- a same-vendor fallback model is set (`--openai-api-fallback-model` for Codex,
  `--anthropic-api-fallback-model` for Claude, a role table's
  `api_fallback_model`, or a same-vendor role model such as `openai/...` for
  Codex);
- the matching key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) is present;
- `--no-api-fallback` (or `api_fallback = false` in the role table) is not set.

`timeout`, `cancelled`, `invalid_response`, and `configuration` failures never
fall back; they fail the call. Codex only falls back to `openai/` models and
Claude only to `anthropic/` models.

The first eligible failure opens a sticky circuit for that role (for example
`proposer` or `judge`) and prints a warning to stderr before the API request is
dispatched:

```text
Warning: judge switched from claude to API model anthropic/claude-sonnet-5 after rate_limit; API billing may apply.
```

The role stays on the API for the rest of the run, including generated
evaluator child processes; other roles keep their own circuits. Pass
`--no-api-fallback` to make every subscription failure terminal.

When an evaluator or judge can switch from a subscription backend to API
fallback, omit `--cache` and `--cache-from`. GEPA's evaluator cache key does
not include the route actually used for each completion, so a cached score
could be reused after that route changes.

### Data handling

- Each request runs in a new, empty temporary workspace that is deleted
  afterwards. No repository files, project instructions (`AGENTS.md`,
  `CLAUDE.md`), or user settings are loaded.
- Tools are disabled: Codex runs read-only with approvals denied, shell/patch
  tools off, no MCP servers, and web search disabled; Claude runs with
  `--tools ""`, an empty strict MCP config, slash commands disabled, and no
  session persistence.
- Prompts reach Claude on stdin and Codex through the SDK request body, never
  as command-line arguments.
- Each call records content-free provenance: role, requested/actual backend and
  model, auth class and source (for example `chatgpt`), timing, retry count,
  token usage, contract versions, and any fallback source and reason. Optimize
  output includes these as `llm_provenance` alongside `backend_plan`. Account
  identity, email, prompts, and secrets are never recorded.
- Cross-process coordination state (provider slots, role circuits, provenance
  events) lives in a private (`0700`) `optimize-anything-run-*` directory under
  the system temp dir, is bound to one run ID, and is removed when the run
  ends.

### Preflight and concurrency

Selected subscription roles are preflighted once before any model request:
Claude checks version, flags, and auth class; Codex checks SDK version,
isolation controls, and the saved login. A failed preflight stops the run
unless an eligible, ready fallback is configured. Then `optimize` prints the
resolved plan to stderr, for example:

```text
Backend plan: {"api_fallback": true, "custom_api_base": false, "judge": {"backend": "claude", "model": null}, "proposer": {"backend": "claude", "model": null}, "subscription_concurrency": 1}
```

`--subscription-concurrency` defaults to `1`, so calls to each subscription
provider are serialized across the whole run, including evaluator
subprocesses. Any other value prints a warning such as
`Warning: codex subscription concurrency set to 2.`

### Disable or remove

- Return to API defaults by omitting `--proposer-backend`, `--judge-backend`,
  and `--analysis-backend` (or passing `api`), and removing `backend` entries
  from `[model.proposer]` / `[model.judge]` tables in TOML spec files.
- In a source checkout, drop the Codex SDK with a plain `uv sync` (without
  `--extra codex`). The plugin launcher reinstalls it on the next invocation.
- Remove the plugins with the `claude plugin uninstall` and
  `codex plugin remove` commands below. Provider logins belong to the provider
  CLIs; use `codex logout` or `claude auth logout` if you also want to sign
  out.

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
through `.codex-plugin/plugin.json`. The launcher installs the locked Codex SDK
extra on first use. Run `codex login` before choosing a Codex subscription
backend. Use `--no-api-fallback` to make missing auth or SDK failures terminal
without a billed API request.

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

To include Codex subscription support in the CLI tool environment:

```bash
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash -s -- --codex
codex login
```

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
prerequisites, and runs `uv run --project <checkout> --locked --no-dev --extra codex`.

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
| `Install the Codex backend` or `Codex SDK 0.156.0 is required` | Source or global CLI lacks the Codex extra, or has the wrong SDK version | Run `uv sync --extra codex` from source or reinstall the global CLI with `install.sh --codex` |
| Codex authentication failure | No usable ChatGPT login is saved | Run `codex login`, then `codex login status`; add `--no-api-fallback` when API billing is not acceptable |
| Model credential error | Selected proposer, task, or judge model is not authenticated | Export that provider's credential before launching the host |
| Skill is not visible | Host loaded the prior plugin snapshot | Reinstall/update, then start a new thread or session |
| Evaluator command fails | Script path or working directory is wrong | Set `--evaluator-cwd` and run the evaluator preflight payload manually |
| `Error: --output must be a file path` | Output points to a directory | Use a candidate file in a temporary or run directory |
