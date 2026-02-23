---
name: optimization-guide
description: Guide for running optimizations with optimize-anything, covering modes, configuration, and interpretation
---
End-to-end guide for optimizing text artifacts with optimize-anything and gepa.

## Workflow

### 1. Prepare the Seed
Start with your current best version of the artifact. gepa evolves from here.
- If you have no seed, set `objective` and gepa bootstraps one from the description
- For multi-component artifacts (e.g., system prompt + few-shot examples), use a dict: `{"system_prompt": "...", "examples": "..."}`

### 2. Create an Evaluator
Use the **generate-evaluator** skill to create one matched to your objective. The evaluator is the most critical piece — gepa's optimization quality is bounded by your evaluator's feedback quality.

### 3. Choose Optimization Mode

**Single-task** (no dataset) — optimize one artifact against one evaluator:
```json
{"seed": "...", "evaluator_command": ["bash", "eval.sh"]}
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
    dataset=train_examples,
    valset=val_examples,
)
```

### 4. Set Budget and Configuration

Use `recommend_budget` for a starting point, then adjust:

| Seed length | Recommended budget | Rationale |
|---|---|---|
| < 100 chars | 50 | Short artifact, fewer mutations needed |
| 100-499 | 100 | Moderate exploration |
| 500-1999 | 200 | More search space to cover |
| 2000+ | 300 | Extensive exploration recommended |

Configuration options via `GEPAConfig`:
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

**Via MCP tool:**
```json
{"seed": "...", "evaluator_command": ["bash", "eval.sh"], "evaluator_cwd": "/absolute/path/to/project", "objective": "maximize clarity", "max_metric_calls": 100}
```

**Via CLI:**
```bash
optimize-anything optimize seed.txt --evaluator-command bash eval.sh --budget 100 --objective "maximize clarity" -o result.txt
```

**Via Python API:**
```python
from optimize_anything import optimize_anything, command_evaluator
from gepa.optimize_anything import GEPAConfig, EngineConfig

result = optimize_anything(
    seed_candidate=open("seed.txt").read(),
    evaluator=command_evaluator(["bash", "eval.sh"]),
    objective="maximize clarity",
    config=GEPAConfig(engine=EngineConfig(max_metric_calls=100)),
)
print(result.best_candidate)
```

### 6. Interpret Results

The result contains:
- `best_candidate` — the optimized artifact
- `val_aggregate_scores` — score progression across iterations
- `total_metric_calls` — how many evaluator invocations were used

**Signs of a good run:**
- Scores trend upward over iterations
- Total metric calls < budget (converged early)
- Best candidate clearly differs from seed in targeted ways

**Signs of problems:**
- Scores flat from start — evaluator may not be discriminating enough
- Scores oscillate — evaluator may be noisy or non-deterministic
- Best score barely above seed — try richer feedback in evaluator, increase budget, or refine objective

## Tips

- **Start small:** Run with budget 20-50 first to validate your evaluator works and scores change meaningfully
- **Rich feedback wins:** Include sub-scores, error messages, and specific improvement hints in evaluator output — this is what drives gepa's reflection
- **Objective matters:** The `objective` string is injected into gepa's reflection prompt. Be specific: "maximize JSON extraction accuracy while keeping responses under 100 tokens" beats "make it better"
- **Background provides context:** Use `background` for domain knowledge, constraints, or strategies: "Target audience is non-technical users. Never use jargon."
- **Iterate on the evaluator:** If optimization results are poor, improve the evaluator before increasing budget
- **Set evaluator working directory in plugin flows:** when evaluator commands use repo-relative files or scripts, pass `evaluator_cwd` as an absolute project path
