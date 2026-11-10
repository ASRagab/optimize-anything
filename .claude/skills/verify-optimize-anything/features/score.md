# Score

`score` evaluates one artifact once, without optimizing, and prints the evaluator's JSON (`score`, `reasoning`, side info, and LLM provenance for judges).

## Sub-features

- `score-command`: score with a command evaluator.
- `score-judge`: score with the built-in LLM judge (`--judge-model --objective`).
- `score-judge-dims`: judge scoring with an intake that has `quality_dimensions` and `hard_constraints`, giving a weighted score and per-dimension keys.
- `score-http`: score with an HTTP evaluator (`--evaluator-url`).

## How to get to it (user POV)

- `uv run optimize-anything score <artifact> --evaluator-command … [--evaluator-cwd …]`
- `uv run optimize-anything score <artifact> --judge-model <model> --objective "…" [--intake-json … | --intake-file …]`
- The plugin's `/optimize-anything:score` command.

## Driving it with verifyctl + uv

Preconditions:

- Baseline from [README.md](./README.md).

Steps:

- **Command evaluator.** Run `uv run optimize-anything score "$EVID/work/seed.txt" --evaluator-command bash marker_eval.sh --evaluator-cwd "$EVID/work" > "$EVID/score/command.json"`. Exit is 0, and the output is `{"score": 0.2, "reasoning": "marker absent; …"}`. Append the marker line to a copy of the seed and score that copy instead. The score becomes 0.9.
- **Judge.** Run `uv run optimize-anything score "$EVID/work/seed.txt" --judge-model openai/verify-stub --objective "clarity" --api-base "$STUB_BASE" --no-api-fallback`. Pass if:
  - `.score` is 0.8.
  - `.error` is absent or null.
  - `.llm_provenance.actual_backend` is `api`.
  - `requests.jsonl` gains one 200 row.
- **Judge with dimensions.** Add `--intake-json '{"quality_dimensions":[{"name":"clarity","weight":0.7},{"name":"brevity","weight":0.3}],"hard_constraints":["keep facts"]}'`. The output has `clarity` 0.8, `brevity` 0.8, `hard_constraints_satisfied: true`, `score` ≈ 0.8, and no `error`.
- **HTTP.** Start `scripts/evaluator_http_server.py` as in [optimize.md](./optimize.md) `opt-http`. Then run `score … --evaluator-url http://127.0.0.1:P/`. The output matches the command-evaluator result.

## Gotchas

- When the judge LLM fails (bad route, schema mismatch, dead endpoint), `score` exits 0 and prints `"score": 0.0` with an `"error"` key such as `LLM call failed: InvalidResponse: provider response did not satisfy output schema`. Check `.error`, not the exit code.
- The judge validates replies against a strict schema. Extra keys fail it. If you change the judge prompt's "Required JSON Output" section, re-check `fake_llm.py`'s key extraction.
- `--judge-model` cannot be combined with `--evaluator-command` or `--evaluator-url`. Pick exactly one source.
- With dimensions, `score` is the weighted aggregate as a float such as 0.7999999…, not exactly 0.8. Compare with a tolerance (`jq '.score > 0.79 and .score < 0.81'`).
- Verified 2026-11-10 (evidence `smoke_outputs/verify-20261110-035404-91741/score/`): `score-command`, `score-judge`, and `score-judge-dims`. `score-http` is a recipe that has not been run yet.
