---
name: optimize
description: Guided optimization workflow with mode selection and evaluator setup
---
Run optimization using a deterministic, guided workflow.

## Step 1: Identify the artifact
- If the user provided a file argument, use it directly.
- Otherwise ask: **"What file should I optimize?"**
- Confirm the path exists before running commands.

## Step 2: Choose optimization mode
Present these options and ask the user to choose one unless they already specified dataset/valset context.

- **Quick (default)**
  - Best for: fast iterations on prompts, docs, skill instructions
  - Typical config: single-task, LLM judge, budget 50
- **Thorough**
  - Best for: higher-confidence optimization on important artifacts
  - Typical config: single-task, run analyze first, budget 150+
- **Multi-task**
  - Best for: one artifact that must work across many examples
  - Requires: `--dataset <train.jsonl>`
- **Generalization**
  - Best for: transfer to unseen examples, avoid overfitting
  - Requires: `--dataset <train.jsonl> --valset <val.jsonl>`

## Step 3: Evaluator setup
- If evaluator is already specified, proceed.
- If no evaluator is specified:
  1. Run `analyze` first:
     - `optimize-anything analyze <file> --judge-model <model> --objective "<objective>"`
  2. Fallback if analyze fails:
     - Continue without `--intake-json` and note: `analyze failed; using direct judge fallback`.
  3. Ask: **"Should we use LLM judge directly, or do you want a custom evaluator?"**
  4. If custom evaluator is needed, invoke evaluator generation workflow.
  5. If LLM judge is acceptable, use `--judge-model` in optimize.

## Step 4: Build and run the optimize command
Construct the command from selected mode and user inputs.
Always include:
- `--objective "..."`
- `--diff`
- `--run-dir runs/`
- `--early-stop`

Mode guidance:
- Quick: `--budget 50`
- Thorough: `--budget 150` (or user-specified)
- Multi-task: include `--dataset`
- Generalization: include `--dataset` and `--valset`

Fallback text to include when analysis fails:
- `Analysis failed, so optimization will run with --judge-model and objective only (no intake dimensions).`

For larger budgets (especially >50), suggest `--parallel` (and optionally `--workers`) when evaluator setup can support concurrency.

## Step 5: Present results clearly
After completion, provide:
1. **Diff summary** (seed vs optimized)
2. **Score improvement** (initial → best, with delta)
3. **Per-dimension diagnostics** (if available)
4. **Next-step recommendation** based on outcome:
   - Plateaued: suggest richer evaluator diagnostics/composite constraints
   - Improved: suggest accept or iterate with higher budget
   - Need confidence check: suggest multi-provider validation via `/optimize-anything:validate`
