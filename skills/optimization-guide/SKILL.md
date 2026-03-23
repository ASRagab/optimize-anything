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

Three interfaces exist. Pick based on where your evaluator code lives:

| Your evaluator is... | Use this interface | Evaluator signature |
|---|---|---|
| Python code in the same project | **Python API** — pass a function to `optimize_anything()` | `def eval(candidate: str) -> float` or `-> tuple[float, dict]` |
| A standalone script/binary | **CLI command** — `--evaluator-command` | Reads `{"candidate": "..."}` from stdin, writes `{"score": float}` to stdout |
| A remote service | **HTTP endpoint** — `--evaluator-url` | POST `{"candidate": "..."}`, response `{"score": float}` |

**Prefer the Python API** when your evaluator is Python code. It bypasses all CLI overhead: no preflight timeout, no argparse conflicts, no subprocess timeout, no stdin/stdout protocol. Your evaluator is just a function:

```python
import gepa.optimize_anything as oa

def my_evaluator(candidate: str) -> tuple[float, dict]:
    score = run_my_scoring(candidate)
    oa.log("Details:", some_diagnostic)  # captured as ASI
    return score, {"feedback": "..."}

result = optimize_anything(
    seed_candidate=open("seed.txt").read(),
    evaluator=my_evaluator,
    objective="maximize quality",
    config=GEPAConfig(engine=EngineConfig(max_metric_calls=100)),
)
```

**Use CLI command** only when your evaluator is a separate process (different language, isolated environment, or shared team tooling). Wrap evaluator-specific flags in a shell script — do not pass them through `--evaluator-command`:

```bash
# evaluators/eval.sh (bakes in your evaluator's flags)
#!/bin/bash
cd "$(dirname "$0")/.."
exec python -m my_eval.scorer --subset-size 5 --temperature 0.0
```

```bash
optimize-anything optimize seed.txt --evaluator-command bash evaluators/eval.sh
```

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
    dataset=train_examples,
    valset=val_examples,
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

### 7. Interpret Results

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

## Preflight Behavior (CLI only)

When using `--evaluator-command`, the CLI runs a **preflight check** before optimization starts. It sends:

```json
{"_protocol_version": 2, "candidate": "__optimize_anything_preflight__"}
```

The preflight has a **10-second timeout**. If your evaluator makes slow API calls (LLM inference, database queries), it will timeout on the real evaluation pipeline. Two solutions:

1. **Detect the sentinel** in your evaluator and fast-return:
```python
payload = json.load(sys.stdin)
candidate = payload["candidate"]
if candidate == "__optimize_anything_preflight__":
    print(json.dumps({"score": 0.5}))
    sys.exit(0)
# ... actual evaluation below
```

2. **Use the Python API instead** — it has no preflight step at all.

### Command Evaluator Timeout

The `command_evaluator` has a default **30-second timeout per evaluation call** (not configurable via CLI). If your evaluator takes longer than 30s per call, use the Python API or the HTTP evaluator interface.