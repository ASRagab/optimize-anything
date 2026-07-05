## 1. Dependency Upgrade Safety

- [x] 1.1 Update `pyproject.toml` dependency constraints for `gepa>=0.1.1,<0.2.0` and `litellm>=1.83.0,!=1.82.7,!=1.82.8`.
- [x] 1.2 Run a package-scoped dry run with `uv lock --dry-run -P gepa==0.1.1 -P litellm==1.83.0` and inspect the planned package changes.
- [x] 1.3 Regenerate `uv.lock` with package-scoped `uv lock -P gepa==0.1.1 -P litellm==1.83.0`.
- [x] 1.4 Add or update a dependency safety test/check that fails if `uv.lock` resolves LiteLLM to `1.82.7` or `1.82.8`.

## 2. CLI Concurrency Model

- [x] 2.1 Change optimize argparse wiring so `--parallel` and `--no-parallel` write a tri-state concurrency value instead of defaulting to `False`.
- [x] 2.2 Update `_build_optimize_runtime` to configure `EngineConfig.parallel=True` by default, `False` for explicit serial mode, and `True` when `--workers` is present.
- [x] 2.3 Ensure `EngineConfig.max_workers` is passed only when a worker count is explicitly provided.
- [x] 2.4 Add validation errors for `--no-parallel --workers` and equivalent spec-file conflicts.

## 3. Spec File Concurrency

- [x] 3.1 Update spec application logic so `optimization.parallel = false` applies when no CLI concurrency flag overrides it.
- [x] 3.2 Preserve CLI precedence so explicit `--parallel`, `--no-parallel`, or `--workers` overrides `optimization.parallel`.
- [x] 3.3 Add tests for `parallel = false`, `parallel = true`, and CLI-overrides-spec behavior.

## 4. Tests and Documentation

- [x] 4.1 Update engine config wiring tests for default parallel mode, explicit `--parallel`, `--no-parallel`, and `--workers`.
- [x] 4.2 Update run-dir/documentation tests to allow GEPA `0.1.1` additional artifacts such as logs, candidate JSON, or candidate tree HTML.
- [x] 4.3 Update README, command docs, and examples to state that optimization is parallel by default.
- [x] 4.4 Document when users should pass `--no-parallel`, including shared temp files, process-global state, and provider rate limits.

## 5. Verification

- [x] 5.1 Run `uv run pytest`.
- [x] 5.2 Run `uv run python scripts/check.py --skip-smoke`.
- [x] 5.3 Run `uv run optimize-anything optimize --help` and confirm both `--parallel` and `--no-parallel` are documented.
- [x] 5.4 Inspect `git diff -- pyproject.toml uv.lock` and confirm no unrelated dependency churn.
