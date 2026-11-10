# Generate evaluator

`generate-evaluator` prints a ready-to-run evaluator script for a seed and objective. A user saves it and passes it to `optimize` or `score`.

## Sub-features

- `gen-judge` (default type): a Python script that calls the LLM judge through `optimize_anything.evaluator_runtime`.
- `gen-command`: a standalone bash script with heuristic scoring and no LLM.
- `gen-http`: a Python HTTP server evaluator.
- `gen-composite`: a Python script that combines heuristics with an LLM judge.
- `gen-dataset`: a dataset-aware template (`--dataset`) that reads `{"candidate", "example"}`.

## How to get to it (user POV)

- `uv run optimize-anything generate-evaluator <seed> --objective "…" [--evaluator-type judge|command|http|composite] [--model …] [--api-base …] > eval.<py|sh>`
- The plugin's `generate-evaluator` skill.

## Driving it with verifyctl + uv

Preconditions:

- Baseline from [README.md](./README.md). Set `G="$EVID/generate"`, then `mkdir -p "$G"`.

Steps:

- **Command type.** Run `uv run optimize-anything generate-evaluator "$EVID/work/seed.txt" --objective clarity --evaluator-type command > "$G/eval.sh"`. Line 1 is `#!/usr/bin/env bash`. Then run `echo '{"candidate":"hello"}' | bash "$G/eval.sh"`. Exit is 0, and stdout is JSON with a numeric `score` in [0,1].
- **Judge type.** Run `… --evaluator-type judge --model openai/verify-stub --api-base "$STUB_BASE" > "$G/judge_eval.py"`. Then run `echo '{"candidate":"hello"}' | uv run python "$G/judge_eval.py"`. Pass if:
  - `score` is 0.8.
  - `dimension_scores` has `correctness`, `clarity`, and `conciseness`.
  - `llm_provenance.prompt_contract_version` is `generated-evaluator-v1`.
  - There is no `error` key.
- **Composite type.** Run the same as the judge type with `--evaluator-type composite`. The output also has `hard_constraints_satisfied: true`.
- **HTTP type.** Run `… --evaluator-type http > "$G/http_eval.py"`. Start it on a free port, recording the PID. POST `{"candidate":"hello"}` and expect JSON with `score`. Kill the PID.
- **Use the generated file.** Pass `--evaluator-command bash eval.sh --evaluator-cwd "$G"` to the `optimize` command drive. Exit is 0, `summary.json` has numeric scores and no `error`, and `llm_provenance_summary.call_count` ≥ 1. Do not require `num_candidates` ≥ 2 here (see Gotchas).

## Gotchas

- The generated judge and composite scripts hardcode the `--model` and `--api-base` given at generation time. A script generated without `--api-base "$STUB_BASE"` calls a real provider when run (default `openai/gpt-5.6-luna`).
- Generated scripts that fail an LLM call print `{"score": 0.0, "error": "evaluator_failed", …}` and exit 0. Check `.error`.
- Run generated Python with `uv run python` so `optimize_anything.evaluator_runtime` imports.
- The generated command evaluator is a heuristic, and it scores the baseline seed 1.0. No proposal can beat that, so `num_candidates` stays 1 even though the proposer ran (`call_count` 3). This is the heuristic behaving as designed, not a stub bug.
- Verified 2026-11-10 (evidence `smoke_outputs/verify-20261110-035404-91741/generate/`): `gen-command` (generate, run, and use in optimize), `gen-judge`, and `gen-composite`. `gen-http` and `gen-dataset` are recipes that have not been run yet.
