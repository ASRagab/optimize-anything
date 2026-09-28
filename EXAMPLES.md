# EXAMPLES

Illustrative CLI examples for optimize-anything v2. Replace seed, evaluator,
and dataset paths with your files. These commands assume the global CLI installer
from [install.md](install.md); use `uv run optimize-anything` from a source
checkout. The shown API models can incur provider charges. `--budget` counts
evaluator calls, not dollars, and an iteration can exceed the requested count.

## Result JSON shape (current contract)

An abbreviated optimization output has this structure:

```json
{
  "best_artifact": "...",
  "total_metric_calls": 42,
  "score_summary": {
    "initial": 0.41,
    "latest": 0.77,
    "best": 0.81,
    "delta_latest_vs_initial": 0.36,
    "delta_best_vs_initial": 0.4,
    "num_candidates": 14
  },
  "top_diagnostics": [
    {"name": "clarity", "value": 0.91},
    {"name": "constraint_adherence", "value": 0.84}
  ],
  "plateau_detected": false,
  "plateau_guidance": "No strong plateau detected. Continue iterating or tighten constraints to target specific gains."
}
```

> `top_diagnostics` is a **list of objects**, not a single object.

---

## 1) Command Evaluator (verification-style)

```bash
optimize-anything optimize parse_duration.py \
  --evaluator-command bash eval_tests.sh \
  --model openai/gpt-5.6-sol \
  --objective "Pass all duration parsing tests" \
  --budget 20
```

Sample output excerpt:

```json
{
  "score_summary": {"best": 1.0, "initial": 0.0, "num_candidates": 9},
  "top_diagnostics": [
    {"name": "passed", "value": 7},
    {"name": "total", "value": 7},
    {"name": "overall_score", "value": 1.0}
  ]
}
```

---

## 2) HTTP Evaluator

```bash
optimize-anything optimize error_template.txt \
  --evaluator-url http://localhost:8080/evaluate \
  --model openai/gpt-5.6-sol \
  --objective "Make API error messages clear and actionable" \
  --budget 15
```

---

## 3) LLM Judge Evaluator

```bash
optimize-anything optimize support_prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Improve clarity, constraints, and tone" \
  --model openai/gpt-5.6-sol \
  --budget 30
```

---

## 4) Multi-Task Optimization with Dataset (new)

```bash
optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Generalize across user intents" \
  --dataset data/train.jsonl \
  --model openai/gpt-5.6-sol \
  --budget 120 \
  --workers 6 \
  --cache --run-dir runs
```

Optimization runs evaluator calls in parallel by default. Use `--workers` to cap
concurrency, or `--no-parallel` when an evaluator writes shared temp files,
depends on process-global state, or must stay below strict provider rate limits.

With validation set:

```bash
optimize-anything optimize prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Generalize to unseen examples" \
  --dataset data/train.jsonl \
  --valset data/val.jsonl \
  --model openai/gpt-5.6-sol \
  --budget 150 \
  --cache --cache-from runs/run-20260303-120000 \
  --run-dir runs
```

---

## 5) Multi-Provider Validation (new)

```bash
optimize-anything validate runs/run-20260303-130000/best_artifact.txt \
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score clarity, correctness, and robustness" \
  --intake-file intake.json
```

Gemini uses LiteLLM's `gemini/` provider prefix.

Sample output excerpt:

```json
{
  "artifact_file": "runs/run-20260303-130000/best_artifact.txt",
  "objective": "Score clarity, correctness, and robustness",
  "providers": [
    {"provider": "openai/gpt-5.6-luna", "score": 0.82, "reasoning": "..."},
    {"provider": "anthropic/claude-sonnet-5", "score": 0.79, "reasoning": "..."},
    {"provider": "gemini/gemini-3.6-flash", "score": 0.81, "reasoning": "..."}
  ],
  "mean": 0.8066666667,
  "stddev": 0.0152752523,
  "min": 0.79,
  "max": 0.82
}
```

---

## 6) Seedless Optimization

```bash
optimize-anything optimize --no-seed \
  --objective "Draft a concise support policy prompt" \
  --model openai/gpt-5.6-sol \
  --judge-model openai/gpt-5.6-luna \
  --budget 25
```

`--no-seed` requires both `--objective` and `--model`.

---

## 7) Score-range any (unbounded scores)

```bash
optimize-anything optimize strategy.md \
  --evaluator-command bash eval_unbounded.sh \
  --model openai/gpt-5.6-sol \
  --objective "Maximize reward" \
  --score-range any \
  --budget 20
```

Use when your evaluator emits finite scores outside `[0,1]`.
