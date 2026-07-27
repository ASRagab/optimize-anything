## Context

`pyproject.toml` accepts GEPA 0.1 releases from 0.1.1 onward, but `uv.lock` and the active environment resolve 0.1.1. GEPA 0.1.4 is the current published PyPI/GitHub release. A package-scoped `uv lock --dry-run -P gepa==0.1.4` changes only GEPA, and a clean 0.1.4 environment successfully imports every GEPA symbol used by this project.

The upstream changes still affect the wrapper's contract. GEPA now retains best validation outputs by default, even though this project does not read them. GEPA 0.1.4 also replaces the short-lived `num_parallel_proposals` option with sampling and selection strategy objects. This project never used the removed option, so the dependency upgrade itself has no direct API break. The new `SameParentSampling` strategy can provide useful opt-in proposal diversity without changing existing runs.

GEPA's `full` extra caps LiteLLM below 1.92 because that release line lacks a complete wheel matrix for supported Python/platform combinations. This project depends on LiteLLM directly, so it must carry the equivalent compatibility bound itself.

## Goals / Non-Goals

**Goals:**

- Upgrade the resolved GEPA package from 0.1.1 to 0.1.4 without unrelated lockfile churn.
- Preserve current result-memory behavior and all existing CLI defaults.
- Expose a small, stable, opt-in proposal fan-out control through both CLI and TOML specs.
- Keep proposal fan-out distinct from evaluator-call parallelism.
- Keep the packaged optimization guide aligned with the upgraded runtime and direct GEPA configuration surface.
- Leave a real-package compatibility check that fails if the imported GEPA surface drifts.

**Non-Goals:**

- Do not adopt the removed `num_parallel_proposals` compatibility path.
- Do not add `batch_evaluator`; command and HTTP evaluator contracts remain singleton contracts.
- Do not expose custom reflection strategies, acceptance/selection strategies, new adapters, callbacks, experiment tracking, or reflection-cost accounting.
- Do not change result JSON, scoring, early stopping, evaluator transport, or default proposal count.
- Do not add full GEPA-state resume behavior; `--cache-from` continues copying only the fitness cache.

## Decisions

### Target the published package release

Set the project requirement to `gepa>=0.1.4,<0.2.0` and resolve 0.1.4 in `uv.lock`. Keep the release range rather than pinning Git `main`; the user selected the 0.1.4 release, and PyPI provides reproducible wheel and source artifacts for Python 3.10 through 3.14.

Use a package-scoped lock update and inspect the dependency diff. The verified dry run changes only GEPA 0.1.1 to 0.1.4.

Align the direct LiteLLM requirement with upstream's compatibility range: retain the current safe floor and compromised-version exclusions, and add `<1.92`. No LiteLLM lock change is expected because the project already resolves 1.83.0.

Alternative considered: install GEPA from the latest `main` commit. That would pull unreleased API and state changes beyond the requested release and make builds depend on a moving development branch.

### Preserve output-retention behavior explicitly

Pass `track_best_outputs=False` in `EngineConfig`. The canonical summary reads candidate scores and history but never reads `best_outputs_valset`, so enabling retention would add memory cost without adding user-visible output.

Alternative considered: accept GEPA's new default. This is unnecessary until the wrapper exposes retained per-example outputs.

### Add one proposal fan-out setting

Add `--proposals-per-iteration N` and `[optimization].proposals_per_iteration`. Both accept positive integers and default to one. CLI values take precedence over spec values using the existing spec-application pattern.

When `N > 1`, set `EngineConfig.sampling_strategy=SameParentSampling(n=N)`. When omitted or equal to one, do not pass a sampling strategy so GEPA's `SingleMutationSampling` default remains authoritative. Keep GEPA's default `AllImprovements` selection strategy.

`SameParentSampling` is the narrowest useful model for a generic artifact optimizer: it produces diverse mutations of the selected parent without adding a parent-selection policy to this CLI.

Alternative considered: expose all sampling and selection strategies. That would require a larger configuration vocabulary and policy guidance without evidence that users need the additional combinations.

### Keep proposal and evaluator concurrency independent

`--proposals-per-iteration` controls how many candidate mutations GEPA attempts in an iteration. `--workers` continues controlling concurrent singleton evaluator calls, and `--no-parallel` continues forcing those evaluations to run serially. No new conflict validation is needed between these settings because fan-out remains valid with serial evaluation.

Documentation must state that fan-out multiplies reflection and evaluation work. GEPA checks stop conditions between iterations, so an opted-in fan-out run can exceed `--budget` by the work already scheduled for the final iteration.

The packaged optimization guide must carry the same guidance, disable unused best-output retention in direct `EngineConfig` examples, and avoid presenting the metric-call budget as a hard upper bound.

### Verify the actual external contract

Update dependency safety assertions for GEPA 0.1.4 and LiteLLM `<1.92`. Add a small compatibility test that imports the GEPA symbols used by production code and constructs `EngineConfig` with `track_best_outputs=False` and `SameParentSampling`. Existing CLI tests continue covering argument/spec precedence and runtime wiring.

Add a documentation contract assertion for the packaged optimization guide so the GEPA 0.1.4 retention, fan-out, budget, and migration guidance cannot silently drift.

The implementation gate is the existing offline project check plus CLI help. A live model call is unnecessary because this change does not alter evaluator or model-provider behavior.

## Risks / Trade-offs

- Proposal fan-out can spend more calls than the nominal budget in the final iteration → Keep it opt-in, default to one, and document the upstream between-iteration stopping behavior.
- Large fan-out can reuse minibatches when the training set is small → Document the trade-off; do not invent a wrapper-specific cap that GEPA does not require.
- GEPA state written after the upgrade is not backward-compatible with 0.1.1 → Support forward migration only and document that rollback should not resume upgraded state.
- The LiteLLM upper bound can delay later LiteLLM features → Match GEPA's supported range now and lift the cap only after upstream restores platform coverage.
- A future GEPA 0.1 patch could drift despite the declared compatible range → Keep the real-package import/config smoke and lock an exact resolved version.

## Migration Plan

1. Update dependency metadata and run a package-scoped GEPA 0.1.4 lock refresh.
2. Add the explicit output-retention setting and proposal fan-out wiring.
3. Extend TOML normalization, CLI/spec precedence tests, compatibility tests, user documentation, and the packaged optimization guide.
4. Run the dependency tests, targeted CLI/spec tests, the offline project gate, and CLI help smoke.
5. Inspect the dependency diff and confirm only intended package metadata changed.

Rollback restores the prior dependency metadata and lockfile. Existing 0.1.4 run directories must not be resumed under 0.1.1; wrapper-created fitness-cache entries remain the only supported cross-run reuse path.

## Open Questions

None.
