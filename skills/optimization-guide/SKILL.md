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

### 3. Choose Optimization Mode

**Single-task** (no dataset) — optimize one artifact against one evaluator:
```json
{"seed": "...", "evaluator_command": ["bash", "evaluators/eval.sh"]}
```

**Multi-task** (with dataset) — optimize across multiple examples for cross-task transfer:
```python
result = optimize_anything(
    seed_candidate="...",
    evaluator=eval_fn,
    dataset=[{"input": "q1", "expected": "a1"}, ...],
)
```

**Generalization** (train + validation split) — ensure the artifact transfers to unseen examples:
```python
result = optimize_anything(
    seed_candidate="...",
    evaluator=eval_fn,
    dataset=`train_examples`,
    valset=`val_examples`,
)
```

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
    ),
)
```

### 5. Run Optimization

**Via CLI:**
```bash
optimize-anything optimize seed.txt --evaluator-command bash evaluators/eval.sh --budget 100 --objective "maximize clarity" -o result.txt
```

**Via Python API:**
```python
from optimize_anything import optimize_anything, command_evaluator
from gepa.optimize_anything import GEPAConfig, EngineConfig

result = optimize_anything(
    seed_candidate=open("seed.txt").read(),
    evaluator=command_evaluator(["bash", "evaluators/eval.sh"]),
    objective="maximize clarity",
    config=GEPAConfig(engine=EngineConfig(max_metric_calls=100)),
)
print(result.best_candidate)
```

### 6. Interpret Results

The result contains:
1. Inspect `best_candidate` — the optimized artifact.
2. Review `val_aggregate_scores` — score progression across iterations.
3. Check `total_metric_calls` — how many evaluator invocations were used.

**Signs of a good run:**
1. Confirm scores trend upward over iterations.
2. Verify `total_metric_calls` < `budget` (converged early).
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