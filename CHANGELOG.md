# Changelog

## v0.3.0 - 2026-03-03

### Features
- Hardened `validate` command to tolerate per-provider failures.
- `validate` now returns per-provider results with explicit failure records:
  - `{"provider": "...", "score": null, "error": "..."}` for failed providers.
- Aggregate stats (`mean`, `stddev`, `min`, `max`) are computed from successful providers only.
- Validation output now includes summary counts for successful and failed providers.
- Reworked `skills/evaluator-patterns/SKILL.md` into four complete runnable evaluator templates:
  - verification
  - judge
  - simulation
  - composite
- Updated command guidance docs with explicit analyze-failure fallback text:
  - `commands/optimize.md` (Step 3 and Step 4)
  - `commands/quick.md` (analyze-fails fallback)
- Expanded contract tests to guard docs/command metadata and concept coverage.

### Breaking Changes
- `validate` output now includes a structured `summary` object and `results` list.
- `validate` may return exit code `1` when all providers fail, even though JSON results are still emitted.
- Aggregates in `validate` can be `null` when no provider succeeds.

### Migration Notes
- Consumers of `validate` output should read provider entries from `results` (or `providers` alias) and check:
  - `summary.successful`
  - `summary.failed`
- Handle nullable aggregate fields (`mean`, `stddev`, `min`, `max`) for all-failure runs.
- For strict pipelines, treat exit code `1` with parseable JSON output as a recoverable "all providers failed" condition and branch on `summary.successful == 0`.
