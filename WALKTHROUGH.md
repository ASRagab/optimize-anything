# WALKTHROUGH

Step-by-step v2 workflow for optimize-anything.

## Prerequisites

- Python 3.10+
- `uv`
- API key(s) for any LLM providers you plan to use

## Step 1: Install

```bash
git clone https://github.com/ASRagab/optimize-anything.git
cd optimize-anything
uv sync
```

## Step 2: Create a seed artifact

```bash
cat > seed.txt << 'EOF'
You are a support assistant. Help users quickly.
EOF
```

## Step 3: Generate an evaluator (default is judge/Python)

`generate-evaluator` now defaults to `--evaluator-type judge` (Python template), not bash command mode.

```bash
uv run optimize-anything generate-evaluator \
  seed.txt \
  --objective "Score clarity, actionability, and specificity" \
  > evaluators/eval.py
```

If you want a bash scaffold explicitly:

```bash
uv run optimize-anything generate-evaluator \
  seed.txt \
  --objective "Score clarity, actionability, and specificity" \
  --evaluator-type command \
  > evaluators/eval.sh
chmod +x evaluators/eval.sh
```

## Step 4: Test evaluator contract

```bash
echo '{"_protocol_version":2,"candidate":"test"}' | python evaluators/eval.py
# expected: JSON with required "score"
```

## Step 5: Baseline score

```bash
uv run optimize-anything score seed.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score clarity and constraints"
```

## Step 6: Optimize

```bash
uv run optimize-anything optimize seed.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Improve clarity and specificity" \
  --model openai/gpt-4o-mini \
  --budget 40 \
  --cache --run-dir runs --diff
```

Notes:
- `--early-stop` can be set manually.
- It is **auto-enabled when budget > 30**.

## Step 7: Validate optimized output (single judge)

```bash
uv run optimize-anything score runs/run-<TIMESTAMP>/best_artifact.txt \
  --judge-model anthropic/claude-sonnet-4-5 \
  --objective "Score clarity, constraints, and usefulness"
```

## Step 8: Validate with multiple providers (new `validate` flow)

```bash
uv run optimize-anything validate runs/run-<TIMESTAMP>/best_artifact.txt \
  --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5 google/gemini-2.0-flash \
  --objective "Score clarity, constraints, and robustness"
```

## Step 9: Iterate (dataset/generalization optional)

For multi-task optimization:

```bash
uv run optimize-anything optimize seed.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Generalize across support scenarios" \
  --dataset data/train.jsonl --valset data/val.jsonl \
  --model openai/gpt-4o-mini \
  --budget 120 --cache --run-dir runs
```

## Step 9.5: Speed up with parallel workers

For expensive evaluators, add parallel execution:

```bash
uv run optimize-anything optimize seed.txt \
  --evaluator-command bash evaluators/eval.sh \
  --objective "Improve quality" \
  --model openai/gpt-4o-mini \
  --budget 100 \
  --parallel --workers 8
```

## Step 10: Accept or rerun

If improved, copy best artifact back into source. Otherwise adjust objective/intake and rerun.

## Common issues

| Problem | Fix |
|---|---|
| Missing API key when using judge evaluator | Set provider API key env vars (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) |
| `--no-seed` failed | `--no-seed` requires both `--objective` and `--model` |
| Evaluator preflight failed | Ensure evaluator prints valid JSON with `score`; logs go to stderr |
| `--valset` rejected | `--valset` requires `--dataset` |
| Cache reuse failed | `--cache-from` requires `--cache` and `--run-dir` |
