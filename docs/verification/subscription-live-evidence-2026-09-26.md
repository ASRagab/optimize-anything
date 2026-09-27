---
type: report
title: Subscription Live Gate Evidence 2026-09-26
created: 2026-09-26
tags:
  - subscription-backends
  - live-gate
  - codex
  - claude
  - evidence
related:
  - "[[Subscription-Backends-U1-U7-Completion-Audit]]"
---

## Verdict

### Gates

| Gate | Result | Notes |
|------|--------|-------|
| Codex structured completion | PASS | auth_class=subscription, fallback=false |
| Codex budget-1 proposer | PASS | auth_class=subscription, fallback=false |
| Codex generated evaluator | PASS | auth_class=subscription, fallback=false |
| Claude structured completion | PASS | auth_class=subscription, fallback=false |
| Claude budget-1 proposer | PASS | auth_class=subscription, fallback=false |
| Claude generated evaluator | PASS | auth_class=subscription, fallback=false |
| Codex judge canary | PASS | auth_class=subscription, fallback=false |
| Claude judge canary | PASS | auth_class=subscription, fallback=false |
| Leak scan | PASS | No secrets, identity, or leakage in 17 retained files |
| Negative cases (fakes) | PASS | All 5 expected scenarios pass: auth rejection, timeout, invalid response |

### Required Fields Summary

- **Versions**: uv 0.12.5, Python 3.12.14, openai-codex 0.156.0, codex-cli 0.155.1, claude CLI 2.1.283 (meets minimum 2.1.278)
- **OS**: macOS 26.6.2 (Build 25G83), Darwin 25.6.0 aarch64
- **Auth Class**: Codex: subscription (ChatGPT), Claude: subscription (claude_subscription)
- **Requested/Actual Models**: Codex: gpt-5.6-terra (confirmed in all runs), Claude: claude (confirmed in all runs)
- **Isolation Assertions**: No secret leakage, no identity leakage, no objective text in cache/coordination state, Claude child process with all tools/MCP disabled, environment variables scrubbed

### Summary

All subscription live gates pass. Both Codex and Claude complete requests using saved subscriptions (ChatGPT and Claude subscription respectively) with no API fallback. No leaked secrets, tokens, account identity, or objectives in retained artifacts or coordination state. Claude child process runs with all tools and MCP disabled, parent environment variables scrubbed, and safe mode enforced.

## Environment

| Field | Value |
|-------|-------|
| OS | macOS 26.6.2 (Build 25G83) |
| Unikernel | Darwin 25.6.0 aarch64 |
| uv version | 0.12.5 (aarch64-apple-darwin) |
| Python version | 3.12.14 |
| openai-codex version | 0.156.0 |
| codex-cli version | 0.155.1 |
| claude CLI version | 2.1.283 (meets minimum 2.1.278) |
| Codex auth class | ChatGPT (subscription) |
| Claude auth class | subscription |
| Claude auth source | claude_subscription |

## Codex

**Structured Completion Test**: PASS
- Requested backend: codex, Actual backend: codex
- Actual model: gpt-5.6-terra
- Auth class: subscription, Auth source: chatgpt
- Fallback used: false

**Seedless Budget-1 Proposer Test**: PASS
- Requested backend: codex, Actual backend: codex
- Actual model: gpt-5.6-terra
- Auth class: subscription, Auth source: chatgpt
- Fallback used: false

**Generated Judge Evaluator Test**: PASS
- Requested backend: codex, Actual backend: codex
- Actual model: gpt-5.6-terra
- Auth class: subscription, Auth source: chatgpt
- Fallback used: false

**Explicit CLI Optimize Run**: PASS
- Command: `optimize --no-seed --objective "Write a concise friendly greeting." --budget 1 --proposer-backend codex --no-api-fallback`
- Requested backend: codex, Actual backend: codex
- Actual model: gpt-5.6-terra
- Auth class: subscription, Auth source: chatgpt
- Fallback used: false (retry_count: 0)
- Wall time: 3.75 seconds
- Input tokens: 6788, Output tokens: 14, Total tokens: 6802
- Run directory: `.maestro/playbooks/Initiation/Working/live-codex/run-20260927-050159`
- Generated artifact: "Hello! Nice to meet you."

## Claude

**Structured Completion Test**: PASS
- Requested backend: claude, Actual backend: claude
- Auth class: subscription, Auth source: claude_subscription
- Fallback used: false

**Seedless Budget-1 Proposer Test**: PASS
- Requested backend: claude, Actual backend: claude
- Auth class: subscription, Auth source: claude_subscription
- Fallback used: false

**Generated Judge Evaluator Test**: PASS
- Requested backend: claude, Actual backend: claude
- Auth class: subscription, Auth source: claude_subscription
- Fallback used: false

**Explicit CLI Optimize Run**: PASS
- Command: `optimize --no-seed --objective "Write a concise friendly greeting." --budget 1 --proposer-backend claude --no-api-fallback`
- Requested backend: claude, Actual backend: claude
- Auth class: subscription, Auth source: claude_subscription
- Fallback used: false (retry_count: 0)
- Wall time: 2.40 seconds
- Input tokens: 2, Output tokens: 27, Total tokens: 29
- Run directory: `.maestro/playbooks/Initiation/Working/live-claude/run-20260927-050352`
- Generated artifact: "Hi there! It's great to see you. I hope your day is going well!"

## Judge canaries

**Codex Judge Canary**: PASS
- Command: `score examples/seeds/sample_seed.txt --judge-backend codex --no-api-fallback --objective "Score clarity"`
- Score: 1.0
- Requested backend: codex, Actual backend: codex
- Actual model: gpt-5.6-terra
- Role: score (judge)
- Auth class: subscription, Auth source: chatgpt
- Fallback used: false (retry_count: 0)
- Wall time: 4.15 seconds
- Input tokens: 6909, Output tokens: 29, Total tokens: 6938

**Claude Judge Canary**: PASS
- Command: `score examples/seeds/sample_seed.txt --judge-backend claude --no-api-fallback --objective "Score clarity"`
- Score: 0.8
- Requested backend: claude, Actual backend: claude
- Role: score (judge)
- Auth class: subscription, Auth source: claude_subscription
- Fallback used: false (retry_count: 0)
- Wall time: 3.82 seconds
- Input tokens: 2, Output tokens: 196, Total tokens: 198

## Negative cases (fakes)

**API-key/Auth rejection tests:**
- test_codex_backend.py::test_api_key_auth_is_rejected_before_thread_dispatch - PASS
  - Expected behavior: API-key auth type rejected before thread dispatch
  - Result: AuthenticationError raised, no thread created
- test_claude_backend.py::test_external_schema_ref_is_rejected_before_completion - PASS
  - Expected behavior: External schema refs blocked before completion
  - Result: ConfigurationError raised, no process call made
- test_claude_backend.py::test_external_dynamic_schema_ref_is_rejected_before_completion - PASS
  - Expected behavior: Dynamic schema refs blocked before completion
  - Result: ConfigurationError raised, no process call made

**Fallback and invalid result tests:**
- test_llm_fallback.py::test_no_fallback_for_ambiguous_or_invalid_result[error0] - PASS (Timeout)
  - Expected behavior: No fallback to API on timeout
  - Result: Timeout raised, API not called
- test_llm_fallback.py::test_no_fallback_for_ambiguous_or_invalid_result[error1] - PASS (InvalidResponse)
  - Expected behavior: No fallback to API on invalid response
  - Result: InvalidResponse raised, API not called

**Coverage verification:**
All expected scenarios from plan U4/U5 test lists are covered by existing fake tests:
- U4: ChatGPT/API-key distinction, structured output validation, timeout cleanup
- U5: Subscription auth requirement, sentinel scrubbing, timeout termination
- Fallback: Invalid result handling, timeout blocking, auth error blocking

## Isolation and leakage assertions

**Artifact scan results:** Scanned 17 files across `Working/live-codex/` (8 files) and `Working/live-claude/` (9 files) for secret/identity leakage.

| Pattern | Hits | Locations | Status |
|---------|------|-----------|--------|
| `deliberately-invalid-live-gate` | 0 | - | PASS |
| OpenAI/Anthropic secret-key token prefix | 0 | - | PASS |
| Email patterns (@) | 0 | - | PASS |
| `account` word | 0 | - | PASS |
| Objective text in structured files | 0 | - | PASS |
| `CLAUDECODE` variable | 0 | - | PASS |

**Claude isolation verification:** Claude child process argv construction verified in `tests/test_claude_backend.py`:
- `--safe-mode` ✓ (line 273)
- `--tools ""` (empty tools list) ✓ (line 273)
- `--disable-slash-commands` ✓ (line 274)
- `--strict-mcp-config --mcp-config <path>` with `{"mcpServers":{}}` ✓ (lines 268-271, 275)
- `--no-session-persistence` ✓ (line 276)
- `--permission-mode dontAsk --permission-prompts none` ✓ (lines 276-277)
- Environment scrubbing: `CLAUDECODE`, `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, paid-auth env vars removed ✓ (`_subscription_env()`, test line 66)

**Assertion confirmed:** No tools, MCP servers, or slash commands available in Claude subscription child process. Paid-auth environment variables scrubbed before execution.

## Paid API fallback (step 11)

Verification Contract step 11 proves the conservative same-vendor API fallback end-to-end with real paid keys. The gate is `tests/test_api_fallback_live.py`. It is marked `pytest.mark.integration` and skipped unless `OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1`, so default CI (`pytest -m "not integration"`) and the Phase 02 flag (`OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1`) never bill an API account. All values below come from the `[paid-fallback]` lines in `.maestro/playbooks/Initiation/Working/live-fallback/pytest.log`, the only full run, unless marked as asserted.

### Verdict

| Gate | Result | Notes |
|------|--------|-------|
| Codex eligible failure, OpenAI API fallback | PASS | `openai/gpt-5.6-luna`, auth_class=api, sticky judge circuit, 3 billed calls |
| Claude eligible failure, Anthropic API fallback | PASS | `anthropic/claude-sonnet-5`, auth_class=api, sticky judge circuit, 3 billed calls |
| Codex `--no-api-fallback` | PASS | `BackendUnavailable` raised, 0 API calls, no billing warning |
| Claude `--no-api-fallback` | PASS | `BackendUnavailable` raised, 0 API calls, no billing warning |
| Key scan | PASS | 0 hits for either real key value, key-shaped strings, or the bare key prefix in the logs and this report |

Result: `4 passed in 7.79s`, exit 0, on the only full run. No code changed.

### Run conditions

```bash
env -u ANTHROPIC_BASE_URL OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE=1 \
  uv run --env-file "$HOME/.config/optimize-anything/paid-fallback.env" \
  pytest tests/test_api_fallback_live.py -v -s 2>&1 \
  | tee .maestro/playbooks/Initiation/Working/live-fallback/pytest.log
```

| Field | Value |
|-------|-------|
| When | 2026-09-26 23:27 PDT. Provenance timestamps read 2026-09-27T06:27:36Z to 06:27:42Z because they are UTC; it is the same run. |
| Versions | Python 3.12.14, pytest 9.0.2, litellm 1.83.0, uv 0.12.5, macOS 26.6.2 (Darwin 25.6.0 aarch64) |
| Key delivery | `OPENAI_API_KEY` came from this agent's Maestro per-agent env. `ANTHROPIC_API_KEY` reached only the pytest child, through `uv run --env-file` (file outside the repo, mode 600). It was never in the agent's own env, so the agent's own Claude Code turns stayed on the subscription. |
| Anthropic routing | The agent inherits `ANTHROPIC_BASE_URL=http://127.0.0.1:4444` (the local lean-ctx proxy), and LiteLLM would otherwise use it. `env -u ANTHROPIC_BASE_URL` removed it, and a pre-check through the same child path resolved `AnthropicModelInfo.get_api_base()` to `https://api.anthropic.com`. The Anthropic leg went direct, not through the proxy. |
| Key validity pre-check | Free model lookups (`GET /v1/models/gpt-5.6-luna` on OpenAI, `GET /v1/models/claude-sonnet-5` on Anthropic) returned `200 200` before any billed call. |
| Subscription auth | Present and untouched. A test-only fake subscription adapter forces the eligible failure: its `preflight()` passes and its `complete()` raises `BackendUnavailable("forced subscription failure")`. It is injected at the factory seam, so the real `resolve_backend_spec`, `create_backend`, `FallbackBackend`, `RunCoordinator`, and `LiteLLMBackend` run. |
| API leg | The real `LiteLLMBackend`, subclassed only to record each dispatch (model, order, and stderr so far) before it calls `super().complete()`. The calls were real and billed, and they reported real usage. |
| Fallback models | Pinned in the test, because fallback has no project default and billing stays opt-in: `openai/gpt-5.6-luna` (`DEFAULT_EVALUATOR_MODEL`) for codex and `anthropic/claude-sonnet-5` for claude. Every spec sets both vendors' fallback flags, so spec resolution itself has to keep the same vendor. |

### Per-vendor results (eligible failure)

Each eligible case builds a `judge` backend and a `score` backend from the same spec on one `RunCoordinator`, then sends three requests: judge, judge, score.

| Field | Codex | Claude |
|-------|-------|--------|
| Vendor | OpenAI | Anthropic |
| Requested backend | `codex` | `claude` |
| Actual backend | `api` (3 of 3 calls) | `api` (3 of 3 calls) |
| Fallback model dispatched | `openai/gpt-5.6-luna` | `anthropic/claude-sonnet-5` |
| Actual model (provenance, reported without the provider prefix) | `gpt-5.6-luna` | `claude-sonnet-5` |
| `auth_class` | `api` | `api` |
| `auth_source` | `openai_api` | `anthropic_api` |
| `fallback_source` / `fallback_reason` | `codex` / `backend_unavailable` | `claude` / `backend_unavailable` |
| `retry_count` / `mixed_backend` | 0 / false | 0 / false |
| Billing warning before dispatch (judge, judge, score) | `[true, false, true]` | `[true, false, true]` |
| Dispatch timeline | `[sub judge, api, api, sub score, api]` | `[sub judge, api, api, sub score, api]` |
| Usage, input / output / total tokens | 39 / 12 / 51 (13 / 4 / 17 per call) | 48 / 12 / 60 (16 / 4 / 20 per call) |
| Per-call duration | 1.08 s, 0.84 s, 1.15 s | 1.57 s, 1.13 s, 1.10 s |

The codebase has no `fallback_used` field. The equivalent was asserted on all 3 results per vendor: `result.fallback` is non-null, with `source_backend=<provider>` and `reason=backend_unavailable`. Coordinator events carry the same facts as `fallback_source` and `fallback_reason`.

### Billing warning before dispatch

`FallbackBackend._warn` prints `Warning: <role> switched from <provider> to API model <model> after <reason>; API billing may apply.` to stderr (`fallback.py:145-146`). It prints only when a role's circuit opens. The test captures stderr with `capsys`, so the warning text itself is not in `pytest.log`.

The ordering proof comes from the recording wrapper. Inside each API `complete()` call, before `super().complete()` dispatches, the wrapper snapshots the stderr written since the previous snapshot. `billing_warning_before_dispatch` records whether each snapshot contains `API billing may apply`:

1. Dispatch 1 (judge, circuit opens): `true`. The warning came before the first billed call.
2. Dispatch 2 (judge, circuit already open): `false`. A sticky role does not warn again.
3. Dispatch 3 (score, its own circuit opens): `true`. A new role warns again before its first billed call.

The test also asserts, without printing, that snapshot 1 contains `judge switched from <provider> to API model <model>` and snapshot 3 contains `score switched from <provider> to API model <model>`.

### Sticky role circuit

The shared `RunCoordinator` keys circuits by subscription backend and role. Both vendors produced the same dispatch timeline:

1. `subscription judge`: the fake adapter raises `BackendUnavailable`, the judge circuit opens, and the warning prints.
2. `api <model>`: the same judge request completes on the same vendor's API.
3. `api <model>`: the second judge request skips the subscription attempt entirely. There is no `subscription judge` entry before it, so it went straight to API.
4. `subscription score`: a different role still tries the subscription first. The judge failure did not open its circuit.
5. `api <model>`: the score request falls back after its own eligible failure.

Coordinator events match the timeline. Each vendor has 3 events, with roles `judge, judge, score`, and each event has `requested_backend=<provider>`, `actual_backend=api`, `auth_class=api`, and `fallback_source=<provider>`.

### `--no-api-fallback` zero-call proof

`test_no_api_fallback_raises_typed_error_without_api_calls[codex|claude]` resolves the same spec with `no_api_fallback=True` and applies the same forced subscription failure. The real key stays exported, so only the flag can explain zero API calls. The log lines are `[paid-fallback] codex {"events": [], "timeline": [["subscription", "judge"]]}` and the same line for `claude`.

- `BackendUnavailable` is raised, and its message matches `forced subscription failure`. This is the typed error from the subscription leg, not an API error.
- The timeline is `[subscription judge]`: exactly one subscription attempt and no API dispatch through the recording wrapper.
- The coordinator has `events=[]`: no provenance event of any kind, so no `api` event.
- No `API billing may apply` text appears on stderr.

Billed calls: 0 per vendor.

### Assertions

All 4 cases passed under `-x`, so every assertion held. Observed values are printed in `pytest.log`. Asserted values were checked in-process but not printed.

| Assertion | Codex | Claude | Evidence |
|-----------|-------|--------|----------|
| The vendor's API key is present before any call | PASS | PASS | asserted (`_require_key`) |
| Judge and score backends pass preflight (`ready=True`) | PASS | PASS | asserted |
| Timeline `[sub judge, api, api, sub score, api]`: fallback, sticky same-role skip, and a new role tries the subscription first | PASS | PASS | observed |
| Snapshot 1 contains `judge switched from <provider> to API model <model>` | PASS | PASS | asserted |
| Billing warning before dispatch 1 and absent before dispatch 2 | PASS | PASS | observed (`[true, false, ...]`) |
| Snapshot 3 contains `score switched from <provider> to API model <model>` | PASS | PASS | asserted; the warning is observed as `true` at index 2 |
| Each result has `requested_backend=<provider>`, `actual_backend=api`, `auth_class=api` | PASS | PASS | asserted on results; observed on events |
| Each result's `auth_source` is the same vendor's API (`openai_api` / `anthropic_api`) | PASS | PASS | asserted on results; observed on events |
| Each result's `fallback` is non-null, with `source_backend=<provider>` and `reason=backend_unavailable` (stands in for `fallback_used=true`) | PASS | PASS | asserted on results; observed on events as `fallback_source` / `fallback_reason` |
| Each result has non-empty text and non-zero `usage.total_tokens` | PASS | PASS | asserted; usage observed |
| Coordinator events are roles `judge, judge, score`, each with `(<provider>, api, api)` and `fallback_source=<provider>` | PASS | PASS | observed |
| `--no-api-fallback`: preflight ready | PASS | PASS | asserted |
| `--no-api-fallback`: `BackendUnavailable` matching `forced subscription failure` | PASS | PASS | asserted |
| `--no-api-fallback`: timeline `[sub judge]`, zero API dispatches | PASS | PASS | observed |
| `--no-api-fallback`: `events == []` | PASS | PASS | observed |
| `--no-api-fallback`: no billing warning on stderr | PASS | PASS | asserted |

### Token usage and billing

| Scope | Billed calls | Input | Output | Total tokens |
|-------|--------------|-------|--------|--------------|
| Codex, `openai/gpt-5.6-luna` | 3 | 39 | 12 | 51 |
| Claude, `anthropic/claude-sonnet-5` | 3 | 48 | 12 | 60 |
| `--no-api-fallback`, both vendors | 0 | 0 | 0 | 0 |
| Evidence run total | 6 | 87 | 24 | 111 |

These figures are each case's `provenance.usage`, aggregated from the coordinator events.

One earlier failed attempt also billed 3 OpenAI calls (51 tokens). In that attempt the `claude` case failed at its first API dispatch with `AuthenticationError`, and it billed 0 Anthropic calls. A free model lookup then showed that Anthropic rejected the previous key with `401 authentication_error`. Counting that attempt, the live gate billed 6 OpenAI calls and 3 Anthropic calls in total. That attempt is not used as evidence here, and its log is kept apart from `pytest.log`.

### Key scan

This scan ran after the section was written. It covered the three logs in `.maestro/playbooks/Initiation/Working/live-fallback/` (`pytest.log` and the two failed-attempt logs) and this report. It checked three patterns:

- the exact values of both real keys, read from the agent env and the key file into a process substitution and never printed or written to disk;
- a key-shaped regex: the OpenAI/Anthropic secret-key prefix, an optional `ant-`, then 20 or more key characters;
- the bare secret-key prefix alone.

| Pattern | Logs (3 files) | This report | Status |
|---------|----------------|-------------|--------|
| Exact real key values (OpenAI, Anthropic) | 0 | 0 | PASS |
| Key-shaped string | 0 | 0 | PASS |
| Bare secret-key prefix | 0 | 0 | PASS |

The logs hold only content-free observations: roles, backends, models, auth classes, usage, and timestamps. `Working/` is not committed.
