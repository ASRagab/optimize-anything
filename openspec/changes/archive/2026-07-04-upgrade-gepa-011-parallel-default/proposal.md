## Why

GEPA `0.1.1` adds useful runtime improvements, including parallel evaluation by default, richer run artifacts, candidate tree visualization, and safer state persistence. This project should adopt the upgrade intentionally while avoiding the LiteLLM versions compromised in the March 2026 supply-chain incident.

## What Changes

- Upgrade the project to GEPA `0.1.1`.
- Constrain LiteLLM resolution so dependency updates land on versions after the compromised `1.82.7` and `1.82.8` releases.
- Change `optimize-anything optimize` to run evaluator calls in parallel by default.
- Add a `--no-parallel` opt-out for evaluators that are not concurrency-safe.
- Preserve `--parallel` as an accepted explicit enable flag for compatibility with existing scripts.
- Reject conflicting concurrency options such as `--no-parallel --workers`.
- Update tests and documentation to describe the new default and concurrency expectations.

## Capabilities

### New Capabilities

- `optimization-runtime`: Defines optimizer dependency safety, default evaluation parallelism, and user-facing controls for evaluator concurrency.

### Modified Capabilities

- None.

## Impact

- Dependencies: `pyproject.toml`, `uv.lock`.
- CLI behavior: `optimize-anything optimize` defaults to parallel GEPA engine execution.
- CLI options: add `--no-parallel` while keeping `--parallel`.
- Tests: engine configuration wiring, flag validation, dependency safety checks, and documentation contract tests.
- Documentation: README, command docs, examples, and any run-dir/concurrency guidance.
- Runtime risk: command/HTTP/LLM evaluators may need concurrency-safe file access, rate-limit handling, or explicit `--no-parallel`.
