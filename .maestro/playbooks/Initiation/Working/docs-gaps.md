---
type: analysis
title: Phase 04 Documentation Gap Inventory (U8)
created: 2026-09-26
tags:
  - docs
  - subscription-backends
  - u8
related:
  - '[[Phase-04-Rollout-Documentation]]'
  - '[[Subscription-Live-Evidence-2026-09-26]]'
---

# Phase 04 Documentation Gap Inventory

Scope for the Phase 04 edits. Built from term counts (`codex`, `claude`,
`subscription`, `fallback`, `--proposer-backend`, `--judge-backend`,
`--analysis-backend`, `evaluator_runtime`) plus targeted topic greps
(`workspace`, `provenance`, `circuit`, `quota_exceeded`, `macOS`, `policy`,
`coordination`, `preflight`, `concurrency`, `0.156`, `2.1.278`).

## DoD topics

1. **Versions** – supported versions / platform
2. **Claude scope** – experimental, local-only, opt-in, policy caveat
3. **Billing/fallback** – `--no-api-fallback`, fallback categories, same-vendor, sticky circuit, warning, fallback-model flags
4. **Data handling** – empty workspace, no repo context/tools/MCP, stdin prompts, provenance (no identity/secrets), run-scoped coordination state
5. **Disable/removal** – omit flags / drop TOML role tables, `uv sync` without `--extra codex`, plugin removal

Plus task-2 extra: **Preflight/concurrency** (backend-plan output, `--subscription-concurrency` default 1 + override warning).

## Facts to use (verified)

| Fact | Source |
|---|---|
| `openai-codex>=0.156.0,<0.157.0` | `pyproject.toml` `[project.optional-dependencies] codex` |
| Tested: openai-codex 0.156.0, codex-cli 0.155.1, claude CLI 2.1.283, macOS 26.6.2 arm64, Python 3.12.14 | `docs/verification/subscription-live-evidence-2026-09-26.md` |
| Claude Code minimum 2.1.278 | `install.md` (already stated) |
| `RUNTIME_CONTRACT_VERSION = 1`; metadata key `min_runtime_contract_version` | `src/optimize_anything/evaluator_runtime.py:15`, `evaluator_generator.py:677,698` |
| Runtime errors: `incompatible_runtime`, `runtime_unavailable`, `runtime_backend_unavailable` | `evaluator_runtime.py:52,111`, `evaluator_generator.py:709` |
| **generate-evaluator flag is `--judge-backend {api,codex,claude}`, NOT `--backend`** | `uv run optimize-anything generate-evaluator --help` |
| `llm_provenance` emitted by `llm_judge.py`, `evaluator_runtime.py`, `cli_optimize.py`; documented nowhere | grep |

## Per-file coverage

| File | Versions | Claude scope | Billing/fallback | Data handling | Disable/removal | Preflight/concurrency | Notes |
|---|---|---|---|---|---|---|---|
| `README.md` (§ "Codex and Claude subscription backends", L181-237; flags table L457-464) | MISSING (no pin, no tested versions, no macOS) | PARTIAL ("local-only and experimental"; no opt-in/hosted/CI/policy caveat) | PARTIAL (`--no-api-fallback`, same-vendor, billing warning; flags in table; MISSING category lists, sticky circuit) | MISSING (no workspace/tools/MCP/provenance/coordination) | MISSING (only "omitting flags preserves API behavior") | PARTIAL ("serialized per provider"; flag in table; MISSING override warning, preflight/backend plan) | Live-gate commands already present L224-237 – keep. |
| `install.md` (§ "Optional local subscription backends", L3-22) | PARTIAL (2.1.278 min; MISSING SDK pin range, tested versions, macOS) | MISSING | MISSING (fallback=0) | PARTIAL (no tokens in config; private temp Codex home; Claude env overrides stripped; fail closed. MISSING empty workspace, no repo context/tools/MCP, stdin, provenance, coordination) | PARTIAL (plugin uninstall/remove commands L61-62, L88-90 present; MISSING API-default return, `uv sync` without extra) | MISSING | Keep existing text; append. |
| `evaluator-cookbook.md` | – | – | – | – | – | – | Zero mentions. Needs R13 section (§7 "Auto-generating Evaluators" L382 is natural neighbor). Use `--judge-backend`, not `--backend`. |
| `PROTOCOL.md` | – | – | – | – | – | – | No `llm_provenance`. §1.5 "Evaluator output contract (unchanged)" – check only for contradiction; do not expand unless it contradicts. |
| `CONCEPTS.md` | – | – | – | – | – | – | No mentions. Not in Phase 04 edit scope. |
| `SKILL.md` (root) | – | n/a | PARTIAL (serialized, same-vendor fallback, `--no-api-fallback`) | – | – | PARTIAL | Host routing L35-46 correct (codex/claude, no inference for unknown host). Leave. |
| `docs/smoke-gates.md` | – | – | – | – | – | – | No subscription gates. Task 5 adds. Format: `##` sections with bash blocks + "What it does" bullets. |
| `docs/release-checklist.md` | – | – | – | – | – | – | codex appears only as reviewer name. Task 5 adds rows to "Required Evidence Index" table (`Item \| Status \| Command \| Evidence Artifact \| Notes`). |
| `skills/optimization-guide/SKILL.md` | – | – | PARTIAL | – | – | PARTIAL (1 concurrent/provider) | Host routing L68-82 correct incl. unknown-host API default. Leave. |
| `skills/generate-evaluator/SKILL.md` | – | – | – | – | – | – | L53-54 documents `--judge-backend` per host. Correct. |
| `skills/evaluator-patterns/SKILL.md` | – | – | – | – | – | – | No backend mention; deterministic templates. Consider no change unless it shows LLM-judge generation invocations. |
| `skills/optimize-prompt/SKILL.md` | – | – | – | – | – | – | No backend mention; contract-tested by `test_prompt_plugin_contract.py`. Review in task 4 but touch carefully. |
| `commands/optimize.md`, `commands/quick.md` | – | – | mention fallback | – | – | serialized | Claude Code-only surface (Codex plugin has no commands per `install.md` table) → `claude` only is correct. |
| `commands/analyze.md`, `score.md`, `compare.md` | – | – | mention fallback | – | – | – | Document both codex/claude. |
| `commands/validate.md` | – | – | mention fallback | – | – | – | Documents reserved `codex`/`claude` selectors. |
| `commands/budget.md`, `explain.md`, `intake.md` | – | – | – | – | – | – | No LLM backend role; no change expected. |
| `.codex-plugin/plugin.json` | – | – | – | – | – | – | Only points at shared `./skills/`; no separate Codex docs. |

## Contract-checked strings (must not break)

- `tests/test_doc_contract.py` (README.md + CLAUDE.md combined): intake fields, result keys, `--intake-json/--intake-file/--evaluator-cwd`, `validate`; must NOT contain `optimize_anything.server`, `tests/test_server.py`. `skills/optimization-guide/SKILL.md` must contain `--proposals-per-iteration`, `proposals_per_iteration`, `SameParentSampling`, `track_best_outputs=False`, `--workers`, `final iteration`, `GEPA 0.1.1`. Every `commands/*.md` needs `name`/`description` frontmatter; expected command/skill sets fixed.
- `tests/test_plugin_regression.py`: exercises `scripts/plugin_regression.py` prompts only; no backend-flag doc assertions. Fixture `tests/fixtures/optimize_prompt_workflow.json`.
- `tests/test_prompt_plugin_contract.py`: commands must use bundled launcher (`${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything`); `install.md` must contain `$optimize-anything:optimize-prompt`; prompt workflow docs cover both hosts.
- `tests/test_model_defaults.py`: README, PROTOCOL, `evaluator-cookbook.md`, `commands/{analyze,quick,score,validate}.md`, generator/evaluator-patterns skills must not contain stale models (`openai/gpt-4o`, `anthropic/claude-sonnet-4-*`, `gemini-2.0-flash`, ...); README must show `openai/gpt-5.6-luna`, `anthropic/claude-sonnet-5`, `gemini/gemini-3.6-flash`.

## Edit scope (derived)

- **Task 2**: append to `install.md` § subscription and `README.md` § subscription: versions table, Claude scope/policy caveat, fallback category lists + sticky circuit, data handling, disable/removal, preflight + concurrency warning. Do not rewrite existing paragraphs.
- **Task 3**: new cookbook section (runtime contract v1, `--judge-backend`, standalone deterministic evaluators, unchanged JSON score contract, runtime error codes). PROTOCOL.md: only fix if it contradicts `llm_provenance`; currently silent, so likely no change. **Playbook says `--backend codex|claude`; real flag is `--judge-backend` – document the real flag.**
- **Task 4**: host docs look aligned; likely no-op except optional unknown-host API-default note in command docs. Verify facts in the gap table before editing.
- **Task 5**: add gate section to `docs/smoke-gates.md` and evidence rows to `docs/release-checklist.md`.
