## Context

`optimize-anything` has several verification surfaces today:

- `scripts/smoke_harness.py` proves the CLI can run and produce contract-shaped output, but its evaluator is a toy length proxy.
- `scripts/score_check.py` protects accepted artifacts from score regression, including `skills/generate-evaluator/SKILL.md`.
- `scripts/live_integration.py` already models GREEN optimization and RED scoring phases, but it is more of an experiment helper than a clear observability workflow.
- `optimize-anything optimize --run-dir` persists `seed.txt`, `best_artifact.txt`, `summary.json`, and GEPA runtime artifacts.

The missing piece is a repeatable, realistic workflow that answers: "Did the optimizer explore useful candidates and improve something we actually care about?"

## Goals / Non-Goals

**Goals:**

- Provide a realistic benchmark centered on a project-relevant text artifact, initially evaluator-generation guidance.
- Preserve source artifacts during optimization; acceptance remains a separate review step.
- Use deterministic training scoring for repeatability.
- Add held-out validation so improvements are not accepted solely because they satisfy the training scorer.
- Produce a compact observation report with enough loop telemetry to debug ineffective optimization.
- Document commands and acceptance criteria for maintainers.

**Non-Goals:**

- Do not replace GEPA's internal telemetry or candidate tree artifacts.
- Do not require live LLM/provider credentials for the default deterministic benchmark path.
- Do not automatically commit or overwrite optimized artifacts.
- Do not redesign the evaluator protocol.
- Do not make broad changes to `score_check.py` unless the benchmark needs a small reusable helper.

## Decisions

### Benchmark Artifact

Use evaluator-generation guidance as the first benchmark target. It is already useful to this project, already appears in `scores.json`, and has a clear product purpose: better evaluator guidance should improve optimization outcomes for future users.

Implementation should avoid optimizing the tracked file in place. A setup step can copy `skills/generate-evaluator/SKILL.md` into a run input directory, or the benchmark can pass the original as a seed while writing optimized output to a run directory.

Alternative considered: use the smoke harness launch blurb. That is cheaper, but it does not prove real product usefulness and encourages superficial improvements.

### Training Scorer

Use a deterministic scorer for the primary benchmark so it can run in CI and local development without model credentials. The scorer should emit:

- `score`
- dimension scores, such as contract completeness, runnable examples, feedback quality, calibration guidance, and conciseness
- concise feedback strings that GEPA can use for reflection

The existing `evaluators/skill_clarity.sh` may be reused if it is sufficient, but implementation should be willing to add a more benchmark-specific scorer if the existing rubric is too easy to game.

Alternative considered: use only an LLM judge. That is semantically attractive, but it introduces cost, provider variance, and credential requirements into the default effectiveness check.

### Held-Out Validation

Acceptance should require a second view of quality. The default held-out check can be deterministic if it measures different dimensions than the training scorer. An optional LLM or multi-provider judge path can provide stronger semantic validation when credentials are available.

The observation report should distinguish:

- training improvement: optimizer beat the deterministic scorer
- validation acceptance: held-out check agrees the artifact is better enough to consider

This prevents a run from being called successful when it only learned to satisfy shallow scorer features.

### Observation Report

Prefer deriving the report from existing outputs:

- CLI summary JSON for initial/best scores, candidate count, metric calls, diagnostics, and plateau guidance
- persisted run directory for seed, best artifact, and GEPA artifacts
- text diff between seed and best artifact for reviewability
- optional held-out validation JSON for acceptance

The implementation can live in one of two shapes:

1. Extend `scripts/live_integration.py` with a named realistic benchmark/report mode.
2. Add a small dedicated script such as `scripts/optimization_observer.py` if separating benchmark/report logic keeps `live_integration.py` simpler.

A new public CLI command should be avoided unless the script proves broadly useful. This change is primarily a maintainer-facing verification workflow.

### Ineffective Run Detection

The report should explicitly flag weak evidence:

- no candidate beyond the seed
- missing score summary or diagnostics
- best score equal to or below initial score
- improvement below a meaningful threshold
- held-out validation regression

These flags should not necessarily make every run exit non-zero. For CI-style gates, implementation can add a strict mode or threshold argument that returns non-zero when effectiveness evidence is insufficient.

## Risks / Trade-offs

- Deterministic scorers can be gamed -> Use held-out validation and inspect diffs before accepting artifacts.
- Benchmark-specific scripts can become stale -> Keep the benchmark close to existing scorer assets and document ownership.
- Live LLM validation can be noisy or unavailable -> Make it optional; keep deterministic validation as the default path.
- Too much telemetry can obscure the decision -> Produce a compact report first, with paths to deeper GEPA artifacts for inspection.
- Source artifact optimization can accidentally overwrite reviewed docs -> Always write to run directories or copies until maintainers explicitly accept a result.

## Migration Plan

1. Add benchmark assets and report logic without changing existing source artifact behavior.
2. Add tests around deterministic scorer output, observation report fields, and ineffective-run detection.
3. Document the maintainer workflow.
4. Optionally wire the benchmark into `scripts/check.py` only after it is stable and cheap enough.

Rollback is straightforward: remove the benchmark assets and report script/docs. Existing optimization and scoring commands continue to work.

## Open Questions

- Should the first benchmark optimize `skills/generate-evaluator/SKILL.md` directly from the tracked file, or should it use a dedicated copied seed under `examples/`?
- Should strict effectiveness thresholds be hardcoded for the benchmark or configurable by command-line flags?
- Should optional semantic validation use `optimize-anything validate`, `score --judge-model`, or the existing `live_integration.py --phase red` path?
