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
| `sk-` token prefix | 0 | - | PASS |
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
