## Why

The project is locked to GEPA 0.1.1 while 0.1.4 is the current published release. The upgrade should preserve existing CLI behavior across GEPA's changed defaults and make its stable multi-proposal strategy available without increasing cost or concurrency for existing runs.

## What Changes

- Require and lock GEPA 0.1.4 within the compatible 0.1 release line.
- Align the direct LiteLLM constraint with GEPA 0.1.4's supported `<1.92` range while retaining the existing compromised-version exclusions.
- Explicitly disable GEPA's new `track_best_outputs` default because the wrapper does not consume retained validation outputs.
- Add an opt-in `--proposals-per-iteration N` setting, with matching TOML spec support, that maps values above one to GEPA's `SameParentSampling(n=N)` strategy.
- Keep one proposal per iteration as the default and leave evaluator parallelism controlled independently by `--parallel`, `--no-parallel`, and `--workers`.
- Validate proposal counts and document that fan-out increases reflection/evaluation work and can overshoot the metric-call budget by up to the final iteration.
- Align the packaged optimization guide with the new retention default, proposal fan-out controls, budget behavior, and state migration guidance.
- Add dependency, runtime-wiring, spec, and compatibility checks for the upgraded API.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `optimization-runtime`: Raise the supported GEPA floor, preserve output-retention behavior, and add opt-in proposal fan-out for optimization runs.

## Impact

- Dependencies: `pyproject.toml` and `uv.lock`.
- Runtime configuration: `src/optimize_anything/cli.py` and `src/optimize_anything/cli_optimize.py`.
- Repeatable specs: `src/optimize_anything/spec_loader.py` and example/spec documentation.
- Tests: dependency safety, real GEPA import/config compatibility, CLI wiring, spec precedence, input validation, unchanged defaults, and packaged-skill guidance.
- Documentation: README, command guidance, the packaged optimization guide, and the distinction between evaluator workers and proposal fan-out.
- Existing GEPA run state can migrate forward to the newer schema, but state written by the upgraded runtime is not expected to load under GEPA 0.1.1.
