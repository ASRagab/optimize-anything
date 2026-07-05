## 1. Benchmark Assets

- [x] 1.1 Choose the first realistic seed artifact and document why it is useful to optimize.
- [x] 1.2 Add benchmark setup that uses a copied seed or explicit output path so tracked source artifacts are not overwritten.
- [x] 1.3 Define the benchmark objective and acceptance constraints in a reusable file or documented command.

## 2. Training Scorer

- [x] 2.1 Review `evaluators/skill_clarity.sh` against the benchmark objective and identify any missing dimensions.
- [x] 2.2 Add or update a deterministic benchmark scorer that returns `score` plus actionable dimension diagnostics.
- [x] 2.3 Add tests that verify the scorer accepts valid evaluator payloads and rejects malformed or non-discriminating output paths appropriately.

## 3. Observation Report

- [x] 3.1 Add report logic that reads optimization summary/run-dir outputs and extracts initial score, best score, score delta, candidate count, metric calls, diagnostics, diff summary, and artifact paths.
- [x] 3.2 Add ineffective-run detection for seed-only runs, missing diagnostics, flat scores, and improvements below the meaningful threshold.
- [x] 3.3 Add tests for successful, insufficient-improvement, and seed-only observation reports.

## 4. Held-Out Validation

- [x] 4.1 Add a held-out validation path using a different deterministic rubric or an optional judge/multi-provider scoring command.
- [x] 4.2 Ensure validation output records pass/fail status, threshold, score, and discrepancy details when training improvement and validation disagree.
- [x] 4.3 Add tests showing scorer-gaming or held-out regression prevents acceptance.

## 5. Documentation

- [x] 5.1 Document the realistic optimization benchmark commands and expected output.
- [x] 5.2 Document acceptance criteria for reviewing and accepting an optimized artifact.
- [x] 5.3 Document troubleshooting guidance for ineffective optimization runs.

## 6. Verification

- [x] 6.1 Run focused tests for the benchmark scorer, report logic, and held-out validation.
- [x] 6.2 Run `uv run pytest`.
- [x] 6.3 Run `uv run python scripts/check.py --skip-smoke`.
- [x] 6.4 Run the realistic benchmark with a small budget and record the observation report outcome. Budget 1 report was accepted=false with missing_diagnostics, seed_only, flat_scores, insufficient_improvement, seed_and_best_identical, and heldout_validation_failed warnings.
- [x] 6.5 Validate this OpenSpec change with `openspec validate observe-realistic-optimization-loop --json`.
