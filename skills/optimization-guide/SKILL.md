---
name: optimization-guide
description: >-
  Guide for running, configuring, and interpreting `optimize-anything` and `gepa`
  optimization workflows. Use when asked how to optimize a prompt, artifact, config,
  or skill, or when troubleshooting evaluator feedback, budget, or score interpretation.
---
## Resolve the bundled runtime

Locate this installed `SKILL.md`, then set:

```bash
OPTIMIZATION_GUIDE_SKILL_DIR="/absolute/path/to/skills/optimization-guide"
OPTIMIZE_ANYTHING_ROOT="$(cd "$OPTIMIZATION_GUIDE_SKILL_DIR/../.." && pwd)"
OPTIMIZE_ANYTHING_RUNNER="$OPTIMIZE_ANYTHING_ROOT/scripts/run-optimize-anything"
```

Use the runner for every CLI call; no global command is needed. It selects the
locked Codex SDK. For Codex subscription use, run `codex login`; source installs
need `uv sync --extra codex`, and global installs need `install.sh --codex`.
Pass `--no-api-fallback` to prevent billed fallback.

## Workflow

### 1. Prepare the Seed
Start with your best artifact.
1. Set `objective` if you have no seed, and let `gepa` bootstrap one from the description.
2. Use a dict like `{"system_prompt": "...", "examples": "..."}` for multi-component artifacts.

### 2. Create an Evaluator
Use the **generate-evaluator** skill to create one matched to your objective.

### 2b. Choose Your Evaluator Interface

1. Use the **Python API** for in-process Python evaluators. Pass a function that returns a score or `(score, diagnostics)`.
2. Use `--evaluator-command` for standalone scripts or binaries. Read `{"candidate":"..."}` from stdin and write `{"score":0.5}` to stdout.
3. Use `--evaluator-url` for remote services that accept request JSON and return score JSON.

Prefer the Python API. For command templates, use the **generate-evaluator** and **evaluator-patterns** skills.

**Command preflight:** The CLI sends `{"candidate":"__optimize_anything_preflight__"}` with protocol version 2. Return `{"score":0.5}` within 10 seconds. Normal calls time out after 30 seconds.

### 3. Choose Optimization Mode

1. Use single-task mode without a dataset for one artifact and evaluator.
2. Add `dataset` for cross-task transfer across training examples.
3. Add `valset` with `dataset` to test generalization on unseen examples.

### 4. Set Budget and Configuration

Run `"$OPTIMIZE_ANYTHING_RUNNER" budget seed.txt` for a starting budget.
Current defaults by seed length are 50 (<100 chars), 100 (<500), 200 (<2000),
and 300 otherwise. Adjust for cost and evaluator quality.

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

For API fan-out, pass `SameParentSampling(n=3)` from
`gepa.strategies.proposal_sampling` as `sampling_strategy`.

### 5. Run Optimization

If the workflow is executing inside Codex or Claude Code, reuse that host's
logged-in subscription explicitly:

```bash
# Codex host
"$OPTIMIZE_ANYTHING_RUNNER" optimize seed.txt --proposer-backend codex --judge-backend codex ...

# Claude Code host
"$OPTIMIZE_ANYTHING_RUNNER" optimize seed.txt --proposer-backend claude --judge-backend claude ...
```

Subscription calls default to one per provider. Announce the backend and
possible billed API fallback; use `--no-api-fallback` to prohibit it. Unknown
hosts omit backend flags and keep API defaults.

**Via CLI:**
```bash
"$OPTIMIZE_ANYTHING_RUNNER" optimize seed.txt --evaluator-command bash evaluators/eval.sh --budget 100 --objective "maximize clarity" -o result.txt
```

To request multiple mutations from the selected parent, add
`--proposals-per-iteration 3`. The equivalent spec setting is:

```toml
[optimization]
proposals_per_iteration = 3
```

The CLI value overrides the spec. Fan-out adds proposal and evaluation work;
`--workers` and `--parallel` govern evaluator concurrency. The final iteration
can exceed `--budget` because GEPA checks the limit between iterations.

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
"$OPTIMIZE_ANYTHING_RUNNER" optimize seed.txt \
  --evaluator-command bash evaluators/eval.sh \
  --budget 120 \
  --early-stop \
  --early-stop-window 10 \
  --early-stop-threshold 0.005
```

Notes:
1. `--early-stop` activates automatically above budget 30.
2. Tune window and threshold for noisy evaluators.
3. Check `early_stopped` and `stopped_at_iteration` in the result.

For cache reuse across runs, copy prior disk cache entries into a new run directory:

```bash
"$OPTIMIZE_ANYTHING_RUNNER" optimize seed.txt \
  --evaluator-command bash evaluators/eval.sh \
  --run-dir runs \
  --cache \
  --cache-from runs/run-20260303-120000
```

Notes:
1. `--cache-from` requires `--cache` and `--run-dir`.
2. It copies `fitness_cache/` from the prior run before optimization.
3. GEPA 0.1.4 can migrate older state forward; rollback to 0.1.1 may not load it.

### 7. Interpret Results

Expected output:
1. Inspect `best_candidate` — the optimized artifact.
2. Review `val_aggregate_scores` — score progression across iterations.
3. Check `total_metric_calls` — how many evaluator invocations were used.

Compare the best candidate with the seed and check that scores rise. Flat scores
suggest weak discrimination; oscillation suggests noise. If improvement is
small, refine the objective or evaluator before increasing budget.

## Tips

1. Start with budget 20-50 to check evaluator discrimination.
2. Return sub-scores, errors, and specific improvement hints to guide reflection.
3. Put constraints and audience in `objective` or `background`.
4. Pass `--evaluator-cwd` when evaluator scripts use relative paths.
