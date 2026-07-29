## 1. Contract Tests and Fixtures

- [x] 1.1 Extend plugin and documentation contract tests to require `skills/optimize-prompt/SKILL.md`, its bundled resources, valid Claude and Codex manifests, a Codex marketplace entry, and aligned release versions.
- [x] 1.2 Add launcher tests that prove the bundled CLI runs from a relocated plugin root without a global `optimize-anything` executable and fails clearly when `uv` or Python prerequisites are unavailable.
- [x] 1.3 Add offline prompt-execution evaluator tests for preflight, representative-example scoring, deterministic hard-gate failure, target-model failure, judge failure, invalid responses, and evaluator-directed candidate text.
- [x] 1.4 Add deterministic workflow fixtures that cover inline return, standalone-file application, embedded-region application with syntax preservation, rejected-candidate no-op behavior, independent batch reporting, and coupled-component refusal.

## 2. Prompt Optimization Skill

- [x] 2.1 Create `skills/optimize-prompt/SKILL.md` with specific triggering metadata and routing for inline prompts, standalone files, embedded prompt regions, and independent prompt batches.
- [x] 2.2 Implement the fast-mode instructions by composing existing analysis, intake, optimize, compare, diff, persistence, and validation behavior while labeling the result as prompt-quality evidence.
- [x] 2.3 Add a bundled prompt-execution evaluator template and default dataset adapter for a candidate system prompt plus `example.input`, optional expected output, criteria, and hard constraints using the existing Protocol v2 fields.
- [x] 2.4 Implement rigorous and composite-mode instructions that construct or adapt the evaluator, execute representative examples on the target model, run held-out acceptance when configured, and keep deterministic gates authoritative.
- [x] 2.5 Implement temporary-output, comparable baseline/candidate scoring, acceptance, inline return, targeted repository application, relevant post-edit checks, failure recovery, and per-file batch reporting instructions.

## 3. Bundled Runtime and Cross-Client Packaging

- [x] 3.1 Add one self-locating launcher that runs the locked repository project with `uv` and emits actionable prerequisite errors without modifying source artifacts.
- [x] 3.2 Route every packaged Claude command that invokes `optimize-anything` through the canonical launcher while preserving command behavior and names.
- [x] 3.3 Add `.codex-plugin/plugin.json` pointing to the canonical `skills/` tree and add `.agents/plugins/marketplace.json` with local and Git-backed repository installation metadata supported by the current Codex plugin contract.
- [x] 3.4 Update the Claude marketplace metadata, Python package metadata, Codex metadata, changelog, and contract tests to one next release version.

## 4. Documentation and Examples

- [x] 4.1 Update `README.md`, `install.md`, the root skill overview, and relevant command guidance with separate Claude plugin, Codex plugin, and optional standalone CLI installation and invocation paths.
- [x] 4.2 Document fast versus rigorous evidence, representative JSONL examples, default and custom prompt adapters, hard constraints, expected cost controls, acceptance rules, and independent-versus-coupled multi-prompt behavior.
- [x] 4.3 Add concise worked examples for returning an inline optimized prompt and safely replacing a prompt embedded in a repository file.

## 5. Verification

- [x] 5.1 Run the new targeted contract, launcher, evaluator, and workflow tests and fix every failure.
- [x] 5.2 Run `uv run python scripts/check.py --skip-smoke`, `claude plugin validate --strict .`, the available Codex plugin/package validator, and local skill-discovery checks for both hosts; confirm the worktree contains only intended changes.
- [x] 5.3 Extend the optional credentialed plugin regression with bounded inline-return and repository-apply scenarios, verify its dry-run and artifact wiring offline, and run paid live scenarios only when credentials and explicit spend authorization are available.
