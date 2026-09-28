# Smoke Gates

Repeatable smoke checks for `RB-009` and `RB-010`.

## Prerequisites
- Dependencies installed: `uv sync`
- `OPENAI_API_KEY` for the default `openai/gpt-5.6-sol` proposer, or set `OPTIMIZE_ANYTHING_MODEL` and provide that model's API credential

## Run Smoke Harness (RB-009)

One command:

```bash
uv run python scripts/smoke_harness.py --budget 1
```

What it does:
- Creates a temporary seed file and temporary evaluator command script.
- Runs CLI optimize smoke (`optimize_anything.cli` path) with a temporary command evaluator.
- Asserts that the CLI summary has a non-empty `best_artifact`, positive `total_metric_calls`, `top_diagnostics`, and `score_summary`.
- Runs `generate-evaluator` and checks that it emits a script with a shebang.
- Runs `intake` and checks that its JSON includes `execution_mode`.
- Saves logs/artifacts under `smoke_outputs/smoke-<timestamp>/` by default.
- Exits non-zero on any assertion failure.

Use a custom output directory:

```bash
uv run python scripts/smoke_harness.py --budget 1 --output-dir /tmp/opt-anything-smoke
```

## Run Consecutive Smoke Gate (RB-010)

One command:

```bash
uv run python scripts/consecutive_smoke_gate.py --budget 1
```

What it does:
- Runs `scripts/smoke_harness.py` twice consecutively.
- Prints concise summary fields:
  - `pass1`
  - `pass2`
  - `overall`
- Exits non-zero if either pass fails.
- Saves gate logs and per-pass outputs under `smoke_outputs/consecutive-<timestamp>/` by default.

Use a custom output directory:

```bash
uv run python scripts/consecutive_smoke_gate.py --budget 1 --output-dir /tmp/opt-anything-consecutive
```

## Subscription Live Gates (opt-in)

These gates exercise the Codex and Claude subscription backends against real
local logins. They are marked `pytest.mark.integration` and skip unless their
environment variable is set to `1`, so default CI and `uv run pytest` never
spend subscription quota or bill an API account. Run them on macOS with a saved
Codex login (`uv sync --extra codex`) and Claude Code 2.1.278 or newer.

| Gate | Opt-in variable | Spends | Test file |
|---|---|---|---|
| Subscription live (plan steps 8-10) | `OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1` | Local Codex / Claude subscription quota | `tests/test_subscription_live.py` |
| Paid API fallback (plan step 11) | `OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1` | OpenAI and Anthropic API accounts (billed) | `tests/test_api_fallback_live.py` |

### Subscription live gate

Invalid API-key sentinels prove the run cannot silently fall back to a paid
key. Run each provider separately:

```bash
OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1 OPENAI_API_KEY=deliberately-invalid-live-gate ANTHROPIC_API_KEY=deliberately-invalid-live-gate uv run pytest tests/test_subscription_live.py -k codex -v -s
OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1 OPENAI_API_KEY=deliberately-invalid-live-gate ANTHROPIC_API_KEY=deliberately-invalid-live-gate uv run pytest tests/test_subscription_live.py -k claude -v -s
```

Each covers structured completion, a seedless budget-1 proposer optimize, and a
generated judge evaluator. After both pass, run one built-in judge canary per
provider:

```bash
OPENAI_API_KEY=deliberately-invalid-live-gate ANTHROPIC_API_KEY=deliberately-invalid-live-gate uv run optimize-anything score examples/seeds/sample_seed.txt --judge-backend codex --no-api-fallback --objective "Score clarity"
OPENAI_API_KEY=deliberately-invalid-live-gate ANTHROPIC_API_KEY=deliberately-invalid-live-gate uv run optimize-anything score examples/seeds/sample_seed.txt --judge-backend claude --no-api-fallback --objective "Score clarity"
```

The score JSON must carry `llm_provenance` with `actual_backend` matching the
provider, `auth_class=subscription`, and no `fallback_source` /
`fallback_reason` keys (those appear only when API fallback ran).

### Paid API fallback gate

This gate bills real API calls. A fake subscription adapter forces an eligible
failure so the real `FallbackBackend` and `LiteLLMBackend` run. Keep
`ANTHROPIC_API_KEY` out of your shell and pass it through an env file (outside
the repo, mode 600). Unset `ANTHROPIC_BASE_URL` so LiteLLM reaches
`https://api.anthropic.com` directly instead of a local proxy:

```bash
env -u ANTHROPIC_BASE_URL OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1 \
  uv run --env-file "$HOME/.config/optimize-anything/paid-fallback.env" \
  pytest tests/test_api_fallback_live.py -v -s
```

It asserts same-vendor fallback, the billing warning before dispatch, the sticky
per-role circuit, and zero API calls under `--no-api-fallback`.

### Evidence to record

Every live run records, without account identity, secrets, or artifact prompts:

- Versions: uv, Python, `openai-codex`, Codex CLI, Claude Code CLI (and pytest / litellm for the paid gate)
- OS and architecture
- Auth class and auth source per provider
- Requested and actual backend and model
- Whether fallback ran (`fallback_source` / `fallback_reason`) and `retry_count`; for the paid gate, fallback model, billed call count, and token usage
- Isolation assertions: no secret or identity leakage in retained files, coordination state, or cache keys; Claude child with tools and MCP disabled and a scrubbed environment
- Key scan result over logs and the report
- Pass/fail per gate

Latest evidence: [[Subscription-Live-Evidence-2026-09-26]]
(`docs/verification/subscription-live-evidence-2026-09-26.md`).
