## Why

The project can prove that optimization commands run, but it does not yet give a realistic, repeatable way to observe whether an optimization loop made a useful artifact better. We need a workflow that shows score movement, candidate exploration, evaluator feedback quality, and held-out validation on an artifact this project actually wants to improve.

## What Changes

- Add a realistic optimization effectiveness benchmark built around a useful text artifact, starting with evaluator-generation guidance.
- Add or extend scorer assets so the benchmark includes both deterministic training feedback and a held-out quality check that discourages scorer gaming.
- Add an observation workflow that records and summarizes the optimization loop: initial score, best score, score delta, candidate count, metric calls, top diagnostics, diff summary, and run-dir locations.
- Add warnings or failure states for ineffective runs such as seed-only optimization, flat scores, missing diagnostics, or no meaningful improvement.
- Document how maintainers run the benchmark, inspect the run, and decide whether an optimized artifact should be accepted.

## Capabilities

### New Capabilities

- `optimization-observability`: Defines realistic optimization benchmark inputs, scorer expectations, loop telemetry, effectiveness checks, and acceptance evidence for optimized text artifacts.

### Modified Capabilities

- None.

## Impact

- Affected scripts: likely `scripts/live_integration.py`, `scripts/score_check.py`, or a new focused observation/report script.
- Affected CLI/runtime surfaces: `optimize-anything optimize --run-dir` output contract and any command used to summarize a saved run.
- Affected assets: benchmark seed artifact, scorer/rubric files, expected output examples, and documentation.
- Affected tests: unit tests for scoring/report logic and integration-style tests using deterministic mock evaluators.
