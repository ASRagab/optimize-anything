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

*Pending: Step 5 negative auth tests*

## Isolation and leakage assertions

*Pending: Step 7 artifact scan*

## Verdict

*Pending: All gates*
