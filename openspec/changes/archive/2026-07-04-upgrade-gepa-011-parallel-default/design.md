## Context

The project currently depends on unconstrained `gepa` and `litellm` in `pyproject.toml`, while `uv.lock` pins `gepa 0.1.0` and `litellm 1.81.14`. GEPA `0.1.1` changes `EngineConfig` defaults to parallel evaluation with default worker sizing, adds candidate tree visualization methods, writes richer run artifacts, and improves state persistence. LiteLLM `1.82.7` and `1.82.8` were compromised in a March 2026 supply-chain incident, so any dependency movement must explicitly resolve beyond those versions.

The CLI currently overrides GEPA's new default by always passing `parallel=args.parallel or (args.workers is not None)`. That means upgrading GEPA alone would not adopt parallel-by-default behavior. The implementation should make the behavior change explicit in this wrapper.

## Goals / Non-Goals

**Goals:**

- Upgrade the optimizer runtime to GEPA `0.1.1`.
- Ensure LiteLLM resolution cannot land on compromised versions.
- Make `optimize-anything optimize` parallel by default.
- Provide clear serial opt-outs for one-off CLI calls and repeatable spec files.
- Preserve existing `--parallel` invocations so scripts do not break.
- Keep dependency updates scoped and reviewable through package-targeted `uv` commands.

**Non-Goals:**

- Do not redesign the evaluator contract.
- Do not make command evaluators concurrency-safe automatically.
- Do not expose GEPA candidate tree visualization as a new CLI feature in this change.
- Do not change scoring semantics, early-stop thresholds, or result summary schema except where needed for run artifact documentation.

## Decisions

### Dependency Resolution

Use package-scoped `uv` upgrades rather than a global upgrade. The implementation should dry-run first, then update only GEPA and LiteLLM:

```bash
uv lock --dry-run -P gepa==0.1.1 -P litellm==1.83.0
uv lock -P gepa==0.1.1 -P litellm==1.83.0
```

The project metadata should express minimum safe constraints, including `gepa>=0.1.1,<0.2.0` and `litellm>=1.83.0,!=1.82.7,!=1.82.8`. The lockfile pins the exact resolved artifacts; the metadata prevents downstream or future lock refreshes from selecting affected LiteLLM versions.

Alternative considered: upgrade LiteLLM to latest during implementation. That gets newer fixes but broadens the change surface. The conservative default is `1.83.0`, the first post-incident safe release identified during exploration, unless implementation-time verification justifies a newer version.

### Parallel-by-Default CLI Model

Use a tri-state concurrency flag model:

- No CLI concurrency flag: parallel evaluation is enabled.
- `--parallel`: parallel evaluation is enabled, retained for compatibility and explicitness.
- `--no-parallel`: parallel evaluation is disabled.
- `--workers N`: parallel evaluation is enabled with `max_workers=N`.

This requires changing argparse so `args.parallel` can represent unspecified, true, or false instead of defaulting to `False`. The runtime builder can then compute the effective engine settings intentionally rather than relying on GEPA defaults by accident.

Alternative considered: remove the explicit `parallel=` argument and rely on GEPA defaults. That is simpler but loses a clean local policy layer and makes `--no-parallel` harder to express consistently.

### Spec File Concurrency

Spec files already parse `optimization.parallel` as a boolean. With parallel-by-default, `parallel = false` must become meaningful. The implementation should update spec application logic so optional boolean spec values can apply both true and false when the CLI did not explicitly set the corresponding option.

CLI flags continue to take precedence over spec file values. A CLI `--parallel` or `--no-parallel` should override `optimization.parallel`.

### Invalid Combinations

Reject `--no-parallel --workers N` because worker count has no effect in serial mode. A spec-file combination of `parallel = false` and `workers = N` should likewise fail unless a CLI flag overrides the spec value to parallel mode.

### Documentation and Tests

Documentation should state that optimization is now parallel by default and that command, HTTP, and LLM evaluators must tolerate concurrent calls. It should also show `--no-parallel` for evaluators that write shared temp files, depend on process-global state, or hit provider rate limits.

Tests should cover default parallel behavior, explicit serial opt-out, worker interactions, spec-file false handling, security constraints, and the targeted `uv` upgrade expectation.

## Risks / Trade-offs

- Non-concurrency-safe evaluators may fail or produce flaky scores -> Provide `--no-parallel`, document evaluator expectations, and add tests for the serial opt-out.
- Provider rate limits may be hit faster in LLM judge mode -> Document `--workers` for controlling concurrency and `--no-parallel` for strict serial calls.
- Existing scripts may assume serial execution without saying so -> Treat this as a deliberate behavior change and document it prominently.
- GEPA `0.1.1` creates additional run-dir artifacts -> Update docs/tests to avoid assuming the wrapper-created files are the only run artifacts.
- Lockfile update could accidentally move unrelated packages -> Use `uv lock -P` package-scoped commands and inspect the diff before accepting.

## Migration Plan

1. Update dependency constraints and regenerate `uv.lock` with package-scoped `uv` commands.
2. Update CLI parsing and spec-file application to support tri-state parallel settings.
3. Update runtime config construction and validation for default parallel behavior and conflicts.
4. Update tests and documentation.
5. Run the full project gate, including dependency safety checks and CLI smoke tests.

Rollback is straightforward: restore the previous lockfile and revert the CLI default to serial mode. Existing `--no-parallel` support can remain if already released because it is additive.

## Open Questions

- Should the lockfile use LiteLLM `1.83.0` for minimal change or the current latest safe version at implementation time? The conservative default is `1.83.0`.
- Should generated TOML examples start including `parallel = false` for known non-concurrency-safe evaluator examples?
