# Analyze and validate

`analyze` scores an artifact and then asks the LLM for 4–6 quality dimensions. It prints `suggested_dimensions` and an `intake_json` that can feed `optimize`. `validate` scores one artifact with two or more judge providers and reports the mean, stddev, min, and max.

## Sub-features

- `analyze-dims`: two LLM calls (score, then dimension discovery) that produce `suggested_dimensions` and `intake_json`.
- `analyze-to-optimize`: feed `intake_json` into `optimize --intake-json`.
- `validate-multi`: judge scoring per provider, plus summary stats.
- `validate-intake`: validation with `--intake-file` dimensions.

## How to get to it (user POV)

- `uv run optimize-anything analyze <artifact> --judge-model <model> --objective "…"`
- `uv run optimize-anything validate <artifact> --providers <m1> <m2> [...] --objective "…" [--intake-file …]`
- The plugin's `/optimize-anything:analyze` and `/optimize-anything:validate` commands.

## Driving it with verifyctl + uv

Preconditions:

- Baseline from [README.md](./README.md). Set `A="$EVID/analyze"`, then `mkdir -p "$A"`.

Steps:

- **Analyze.** Run `uv run optimize-anything analyze "$EVID/work/seed.txt" --judge-model openai/verify-stub --objective clarity --api-base "$STUB_BASE" --no-api-fallback > "$A/analyze.json"`. Pass if:
  - Exit is 0.
  - `jq '.current_score'` is 0.8.
  - `jq '[.suggested_dimensions[].name]'` is `["clarity","concision"]`.
  - `.intake_json` parses as JSON with `quality_dimensions`.
  - `requests.jsonl` gains two 200 rows.
- **Analyze into optimize.** Run the optimize command drive with `--intake-json "$(jq -r .intake_json "$A/analyze.json")"`. The run completes with `num_candidates` ≥ 2.
- **Validate.** Run `uv run optimize-anything validate "$EVID/work/seed.txt" --providers openai/verify-stub openai/verify-stub-2 --objective clarity --api-base "$STUB_BASE" --no-api-fallback > "$A/validate.json"`. Pass if:
  - `jq '.summary'` is `{"successful":2,"failed":0,"mean":0.8,"stddev":0.0,"min":0.8,"max":0.8}`.
  - Each entry in `.providers[]` has `llm_provenance.actual_model` equal to its own model name.

## Gotchas

- `analyze` exits 1 on an LLM failure, and prints `Error: Scoring LLM call failed: …` to stderr. `validate` exits 0 and records each failure inside `results[]` with `score: null` and an `error`, and the failure counts in `.summary.failed`. Before the 2026-11-10 fix, a failed judge call counted as successful and its 0.0 entered `mean`. Assert both `.summary.failed` and that every successful `.providers[].error` is null, so that bug cannot come back unnoticed.
- `validate` with mixed provider prefixes (`anthropic/…`, `gemini/…`) and one `--api-base` sends every provider to the stub. A real cross-provider run needs approval and no `--api-base`.
- The stub gives every provider the same score, so `stddev` 0.0 is expected here. It is not evidence of real agreement between providers.
- Verified 2026-11-10 (evidence `smoke_outputs/verify-20261110-035404-91741/analyze/`): `analyze-dims` and `validate-multi`. `analyze-to-optimize` and `validate-intake` are recipes that have not been run yet.
