---
name: optimization-guide
description: >-
  Guide for running, configuring, and interpreting `optimize-anything` and `gepa`
  optimization workflows. Use when asked how to optimize a prompt, artifact, config,
  or skill, or when troubleshooting evaluator feedback, budget, or score interpretation.
---
End-to-end guide for optimizing text artifacts with `optimize-anything` and `gepa`.

## Workflow

### 1. Prepare the Seed
Start with your current best version of the artifact. `gepa` evolves from here.
1. Set `objective` if you have no seed, and let `gepa` bootstrap one from the description.
2. Use a dict like `{"system_prompt": "...", "examples": "..."}` for multi-component artifacts (e.g., `system_prompt` + few-shot examples).

### 2. Create an Evaluator
Use the **generate-evaluator** skill to create one matched to your objective. The evaluator is the most critical piece—`gepa`'s optimization quality is bounded by your evaluator's feedback quality.

### 2b. Choose Your Evaluator Interface

1. Use the **Python API** for in-process Python evaluators. Pass a function that returns a score or `(score, diagnostics)`.
2. Use `--evaluator-command` for standalone scripts or binaries. Read `{"candidate":"..."}` from stdin and write `{"score":0.5}` to stdout.
3. Use `--evaluator-url` for remote services that accept request JSON and return score JSON.

Prefer the Python API. For command templates, use the **generate-evaluator** and **evaluator-patterns** skills.

**Command preflight and timeouts:** Before optimization, the CLI sends `{"_protocol_version":2,"candidate":"__optimize_anything_preflight__"}` and waits 10 seconds. Detect that sentinel and immediately return `{"score":0.5}`. Normal command evaluations time out after 30 seconds; use the Python API for slower work.

### 3. Choose Optimization Mode

1. Use single-task mode without a dataset for one artifact and evaluator.
2. Add `dataset` for cross-task transfer across training examples.
3. Add `valset` with `dataset` to test generalization on unseen examples.

### 4. Set Budget and Configuration

Use the `budget` subcommand for a starting point, then adjust:

| Seed length | Recommended budget | Rationale |
|---|---|---|
| < 100 chars | 50 | Short artifact, fewer mutations needed |
| 100-499 | 100 | Moderate exploration |
| 500-1999 | 200 | More search space to cover |
| 2000+ | 300 | Extensive exploration recommended |

Configure options via `GEPAConfig`:
```python
from gepa.optimize_anything import GEPAConfig, EngineConfig

config = GEPAConfig(
    engine=EngineConfig(
        max_metric_calls=150,     # Budget
        parallel=True,            # Parallel evaluation
        max_workers=8,            # Worker count
        track_best_outputs=False,
    ),
)
```

For direct API fan-out, import `SameParentSampling` from
`gepa.strategies.proposal_sampling` and pass
`sampling_strategy=SameParentSampling(n=3)`. Omit the strategy for the default
single proposal.

### 5. Run Optimization

If the workflow is executing inside Codex or Claude Code, reuse that host's
logged-in subscription explicitly:

```bash
# Codex host
optimize-anything optimize seed.txt --proposer-backend codex --judge-backend codex ...

# Claude Code host
optimize-anything optimize seed.txt --proposer-backend claude --judge-backend claude ...
```

Subscription calls default to one concurrent call per provider. Announce the
backend and possible billed API fallback before execution; add
`--no-api-fallback` to prohibit it. Unknown hosts omit backend flags and keep
the API defaults.

**Via CLI:**
```bash
optimize-anything optimize seed.txt --evaluator-command bash evaluators/eval.sh --budget 100 --objective "maximize clarity" -o result.txt
```

To request multiple mutations from the selected parent, add
`--proposals-per-iteration 3`. The equivalent spec setting is:

```toml
[optimization]
proposals_per_iteration = 3
```

An explicit CLI value overrides the spec. Proposal fan-out is independent of
`--workers`, `--parallel`, and `--no-parallel`, which control evaluator-call
concurrency. Fan-out increases reflection and evaluation work, small datasets
may reuse a minibatch across proposals, and the final iteration can exceed
`--budget` because GEPA checks the limit between iterations.

**Via Python API:**
```python
from optimize_anything import optimize_anything, command_evaluator
from gepa.optimize_anything import GEPAConfig, EngineConfig

result = optimize_anything(
    seed_candidate=open("seed.txt").read(),
    evaluator=command_evaluator(["bash", "evaluators/eval.sh"]),
    objective="maximize clarity",
    config=GEPAConfig(
        engine=EngineConfig(max_metric_calls=100, track_best_outputs=False)
    ),
)
print(result.best_candidate)
```

### 6. Early Stopping and Cache Reuse

Use plateau-based early stopping to avoid wasting budget after convergence:

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash evaluators/eval.sh \
  --budget 120 \
  --early-stop \
  --early-stop-window 10 \
  --early-stop-threshold 0.005
```

Notes:
1. `--early-stop` is auto-enabled when `--budget > 30`.
2. Tune `--early-stop-window` and `--early-stop-threshold` for noisier evaluators.
3. CLI output includes `early_stopped` and `stopped_at_iteration` when a run exits early.

For cache reuse across runs, copy prior disk cache entries into a new run directory:

```bash
optimize-anything optimize seed.txt \
  --evaluator-command bash evaluators/eval.sh \
  --run-dir runs \
  --cache \
  --cache-from runs/run-20260303-120000
```

Notes:
1. `--cache-from` requires `--cache` and `--run-dir`.
2. `--cache-from` copies `fitness_cache/` from the previous run before optimization starts.
3. GEPA 0.1.4 can migrate older run state forward, but its state is not expected to load under GEPA 0.1.1 after a rollback.

### 7. Interpret Results

Expected output:
1. Inspect `best_candidate` — the optimized artifact.
2. Review `val_aggregate_scores` — score progression across iterations.
3. Check `total_metric_calls` — how many evaluator invocations were used.

**Signs of a good run:**
1. You should see scores trend upward over iterations.
2. Compare `total_metric_calls` with `budget`; the final iteration can overshoot the budget, especially with proposal fan-out.
3. Compare `best_candidate` against `seed.txt` or in-memory seed to see targeted differences.

**Signs of problems:**
1. Detect flat scores from start — evaluator may not be discriminating enough.
2. Notice oscillating scores — evaluator may be noisy or non-deterministic.
3. Investigate runs where best score barely beats `seed` — add richer feedback, increase `budget`, or refine `objective`.

## Tips

1. Start small: Run with `budget` 20-50 first to validate your evaluator on `seed.txt` and confirm that scores change meaningfully.
2. Provide rich feedback: Include sub-scores, error messages, and specific improvement hints in evaluator output — this drives `gepa`'s reflection.
3. Clarify the objective: Set the `objective` string that is injected into `gepa`'s reflection prompt and specify constraints like token limits or format requirements.
4. Add background context: Use `background` for domain knowledge, constraints, or strategies such as "Target audience is non-technical users. Never use jargon."
5. Iterate on the evaluator: Improve the evaluator before increasing `budget` if optimization results on `seed.txt` are poor.
6. Set evaluator working directory: Pass `evaluator_cwd` as an absolute project path next to `seed.txt` and `evaluators/eval.sh` when `evaluators/eval.sh` or other evaluator commands use repo-relative files or scripts.
