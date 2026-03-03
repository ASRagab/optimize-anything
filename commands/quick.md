---
name: quick
description: Zero-config one-shot optimization for fast improvements
---
Run a no-questions-asked fast optimization.

## Usage
`/optimize-anything:quick <file> "<objective>"`

## Behavior (do not ask follow-up questions)
1. Run analysis to discover dimensions:
   - `optimize-anything analyze <file> --judge-model openai/gpt-4o-mini --objective "<objective>"`
   - If analyze fails, skip dimension discovery and run optimize with `--judge-model` directly using the objective as-is.
2. Run optimization using LLM judge with:
   - `--judge-model openai/gpt-4o-mini`
   - `--budget 50`
   - `--diff`
   - `--early-stop`
   - `--run-dir runs/`
   - Include the `--intake-json` returned by analyze when available.
3. Return:
   - Unified diff highlights
   - Score improvement (initial → best, delta)
   - Best artifact path/info and one concise next-step suggestion
