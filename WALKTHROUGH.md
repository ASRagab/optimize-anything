# Walkthrough: Optimizing a Skill File

Step-by-step guide from zero to a complete optimization cycle. For concept definitions, see [CONCEPTS.md](CONCEPTS.md).

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) installed
- An API key for your LLM provider (e.g., `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)

## Step 1: Install

```bash
# From source (recommended for this walkthrough):
git clone https://github.com/ASRagab/optimize-anything.git
cd optimize-anything
uv sync
```

Or install the CLI tool:

```bash
uv tool install git+https://github.com/ASRagab/optimize-anything
```

## Step 2: Create a Seed Artifact

Write your first draft. This is the starting point gepa will evolve.

```bash
cat > skills/my-skill/SKILL.md << 'EOF'
# My Skill

This skill helps users do a task. It provides guidance and examples.

## Steps

1. Do the first thing
2. Do the second thing
3. Check the results
EOF
```

## Step 3: Write an Evaluator

Generate a starter evaluator from your seed and objective:

```bash
uv run optimize-anything generate-evaluator \
    skills/my-skill/SKILL.md \
    --objective "Score clarity, actionability, and specificity" \
    > evaluators/my_eval.sh

chmod +x evaluators/my_eval.sh
```

## Step 4: Test the Evaluator

Verify it produces valid JSON with a `score` field:

```bash
echo '{"candidate": "test content"}' | bash evaluators/my_eval.sh
# Expected: {"score": 0.xx, "feedback": [...]}
```

## Step 5: Score the Seed

Get a baseline score for your artifact:

```bash
uv run optimize-anything score skills/my-skill/SKILL.md \
    --evaluator-command bash evaluators/my_eval.sh
```

## Step 6: Run Optimization (GREEN Phase)

Use gepa to propose and score improvements:

```bash
uv run optimize-anything optimize skills/my-skill/SKILL.md \
    --evaluator-command bash evaluators/my_eval.sh \
    --model openai/gpt-4o-mini \
    --budget 15 \
    --objective "Improve clarity and specificity" \
    --run-dir runs/ \
    --diff
```

The `--diff` flag shows what changed. Results are saved under `runs/`.

## Step 7: Validate with LLM Judge (RED Phase)

Score the optimized artifact with an independent LLM judge:

```bash
uv run optimize-anything score runs/run-<TIMESTAMP>/best_artifact.txt \
    --judge-model openai/gpt-4o-mini \
    --objective "Score clarity, actionability, specificity"
```

## Step 8: Accept or Iterate

**If improved:**

```bash
cp runs/run-<TIMESTAMP>/best_artifact.txt skills/my-skill/SKILL.md
uv run python scripts/score_check.py --update
```

**If flat:** Adjust the `--objective` with more specific guidance and re-run Step 6.

## Step 9: Run Full Cycle with live_integration.py

The orchestrator script combines GREEN and RED phases with structured JSON output:

```bash
# GREEN: optimize
uv run python scripts/live_integration.py \
    --phase green \
    --artifact skills/my-skill/SKILL.md \
    --model openai/gpt-4o-mini \
    --budget 15 \
    --objective "Improve clarity and specificity" \
    --run-dir integration_runs \
    --evaluator-command bash evaluators/my_eval.sh

# RED: validate with multiple providers
uv run python scripts/live_integration.py \
    --phase red \
    --artifact integration_runs/run-<TIMESTAMP>/best_artifact.txt \
    --objective "Score skill quality" \
    --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5-20250929 \
    --baseline 0.85 \
    --evaluator-command bash evaluators/my_eval.sh
```

**Important:** Place `--evaluator-command` as the last flag (it consumes all remaining arguments).

## Common Issues

| Problem | Fix |
|---------|-----|
| No proposals generated | Pass `--model` explicitly (gepa default may be unavailable) |
| Evaluator preflight failed | Use `bash evaluators/script.sh` not `evaluators/script.sh` |
| LLM returned malformed JSON | Anthropic wraps JSON in code fences (handled automatically) |
| Score didn't improve | Try a more capable model (`gpt-4o` or `claude-sonnet-4-5`) or increase `--budget` |
| `--model` flag ignored | Ensure `--evaluator-command` is the LAST flag in the command |
