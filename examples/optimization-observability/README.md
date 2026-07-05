# Optimization Observability Benchmark

This benchmark verifies that an optimization loop improved a useful project
artifact, not just that the CLI ran. The first benchmark targets
`skills/generate-evaluator/SKILL.md`, because better evaluator-generation
guidance should improve future optimize-anything workflows.

The benchmark never overwrites the tracked source artifact. `setup` copies the
seed into a work directory, and optimization writes candidate artifacts into a
run directory. Accepting a result is a separate review step.

## Run The Benchmark

Create a copied seed and print the exact run metadata:

```bash
uv run python scripts/optimization_observer.py setup
```

The JSON output includes:

- `seed_file`: copied seed to optimize
- `objective`: benchmark objective
- `constraints`: acceptance constraints
- `run_base_dir`: parent directory for optimizer run artifacts
- `training_evaluator_command`: deterministic training scorer
- `heldout_evaluator_command`: deterministic held-out scorer
- `optimize_command`: starter command for the optimization run

Run optimization with a small budget. Set `OPTIMIZE_ANYTHING_MODEL`, or add
`--model <litellm-model>` before `--evaluator-command`.

```bash
uv run optimize-anything optimize \
  integration_runs/optimization-observability/evaluator-generation-guidance/seed.md \
  --objective "Improve the evaluator-generation guidance so it helps maintainers create reliable evaluators with clear JSON contracts, runnable examples, diagnostic feedback, calibration guidance, and concise acceptance criteria." \
  --budget 6 \
  --run-dir integration_runs/optimization-observability/evaluator-generation-guidance/runs \
  --evaluator-command bash evaluators/evaluator_generation_training.sh
```

Generate the observation report for the created `run-*` directory:

```bash
uv run python scripts/optimization_observer.py report \
  --run-dir integration_runs/optimization-observability/evaluator-generation-guidance/runs/run-YYYYMMDD-HHMMSS \
  --benchmark examples/optimization-observability/evaluator-generation-benchmark.json \
  --strict
```

When `--benchmark` is provided, the report uses the benchmark's held-out
validation scorer automatically.

## Expected Report

The report JSON includes:

- `training.initial_score`, `training.best_score`, and `training.score_delta`
- `training.candidate_count` and `training.metric_calls`
- `training.diagnostics` from the optimizer summary
- `diff_summary.added`, `diff_summary.removed`, and a short diff preview
- `validation.seed_score`, `validation.best_score`, `validation.score_delta`
- `warnings` with actionable recommendations for weak evidence
- `accepted`: `true` only when training improvement and held-out validation pass
- `artifacts`: paths to `seed.txt`, `best_artifact.txt`, `summary.json`, and GEPA artifacts

## Acceptance Criteria

Accept an optimized artifact only when:

- training score improves by at least `meaningful_delta` from the benchmark config
- held-out validation improves by at least `validation_delta`
- candidate count is greater than one
- diagnostics are present and specific enough to explain the improvement
- the diff improves evaluator guidance without bloating or weakening the skill
- the tracked source file is updated manually after review

Do not accept a run solely because the training scorer improved. Treat the
observer report as evidence for review, not as an automatic source change.

## Troubleshooting

- `seed_only`: increase budget, confirm model credentials, and inspect GEPA artifacts.
- `missing_diagnostics`: return dimension scores or feedback fields from the scorer.
- `flat_scores`: sharpen the objective or make the scorer more discriminating.
- `insufficient_improvement`: rerun with a larger budget or improve scorer feedback.
- `heldout_regression`: inspect the diff for scorer gaming before accepting.
- `validation_not_run`: pass `--benchmark` or `--validation-command` to the report.
