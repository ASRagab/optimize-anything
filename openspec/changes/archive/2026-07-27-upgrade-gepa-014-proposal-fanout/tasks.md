## 1. Contract Tests

- [x] 1.1 Update dependency safety tests for GEPA 0.1.4 and the LiteLLM `>=1.83.0,<1.92` supported range, including the existing compromised-version exclusions.
- [x] 1.2 Add a real-package compatibility test that imports the GEPA production symbols and constructs `EngineConfig` with disabled output retention and `SameParentSampling`.
- [x] 1.3 Add CLI tests for the unchanged single-proposal default, explicit fan-out, explicit one, positive-integer validation, and `track_best_outputs = false`.
- [x] 1.4 Add spec-loader and CLI-precedence tests for `optimization.proposals_per_iteration`.
- [x] 1.5 Add a documentation contract test for the packaged optimization guide's GEPA 0.1.4 retention, fan-out, budget, and migration guidance.

## 2. Dependency Upgrade

- [x] 2.1 Update `pyproject.toml` to require `gepa>=0.1.4,<0.2.0` and constrain the direct LiteLLM dependency to `>=1.83.0,<1.92` while preserving exclusions.
- [x] 2.2 Run a package-scoped GEPA 0.1.4 lock dry run, regenerate `uv.lock`, and confirm the resolved GEPA version is 0.1.4 without unrelated package movement.

## 3. Runtime Configuration

- [x] 3.1 Add `--proposals-per-iteration` as a positive integer CLI option and normalize/apply the matching TOML optimization field with CLI precedence.
- [x] 3.2 Set `track_best_outputs=False` on every wrapper-built `EngineConfig`.
- [x] 3.3 Pass `SameParentSampling(n=N)` only when the effective proposal count is greater than one, leaving GEPA's default strategy in control otherwise.

## 4. Documentation

- [x] 4.1 Update `README.md` and `commands/optimize.md` with the proposal fan-out option, its distinction from evaluator workers, repeated-minibatch trade-off, final-iteration budget overshoot, and forward-only GEPA state migration note.
- [x] 4.2 Update `skills/optimization-guide/SKILL.md` with the same guidance and safe direct `EngineConfig` examples.

## 5. Verification

- [x] 5.1 Run the dependency safety, spec-loader, and CLI test modules and fix any regressions.
- [x] 5.2 Run `uv run pytest` and `uv run python scripts/check.py --skip-smoke`.
- [x] 5.3 Run `uv run optimize-anything optimize --help` and confirm the proposal fan-out guidance is present.
- [x] 5.4 Run `openspec validate upgrade-gepa-014-proposal-fanout --strict` and inspect the dependency diff for only intended metadata and lock changes.
- [x] 5.5 Run the documentation contract test, offline project gate, strict OpenSpec validation, and final diff checks after aligning the packaged skill.
