---
name: quick
description: Zero-config one-shot optimization for fast improvements
---
Run a no-questions-asked fast optimization.

Use Claude Code's subscription explicitly with `--analysis-backend claude`,
`--proposer-backend claude`, and `--judge-backend claude`. Announce serialized
subscription use and possible same-vendor billed API fallback before running.

## Usage
`/optimize-anything:quick <file> "<objective>"`

## Behavior (do not ask follow-up questions)
1. Run analysis to discover dimensions:
   - Subscription mode: `"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" analyze <file> --analysis-backend claude --objective "<objective>"`
   - API mode: `"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" analyze <file> --judge-model openai/gpt-5.6-luna --objective "<objective>"`
   - If analyze fails, skip dimension discovery and run optimize with `--judge-model` directly using the objective as-is.
2. Run optimization using LLM judge with:
   - Subscription mode: `--proposer-backend claude --judge-backend claude` (omit API model strings)
   - API mode: `--judge-model openai/gpt-5.6-luna`
   - `--budget 50`
   - `--diff`
   - `--early-stop`
   - `--run-dir runs/`
   - Include the `--intake-json` returned by analyze when available.
3. Return:
   - Unified diff highlights
   - Score improvement (initial → best, delta)
   - Best artifact path/info and one concise next-step suggestion
