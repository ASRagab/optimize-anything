# Optimize

`optimize` evolves a text artifact. GEPA asks the proposer LLM for candidate rewrites, scores each candidate with the user's evaluator, and returns the best one. It can write the result to a file and persist the run to a run dir.

## Sub-features

- `opt-command`: optimize with a command evaluator (`--evaluator-command`, JSON on stdin and stdout).
- `opt-http`: optimize with an HTTP evaluator (`--evaluator-url`).
- `opt-judge`: optimize with the built-in LLM judge (`--judge-model`).
- `opt-no-seed`: bootstrap without a seed file (`--no-seed --objective …`).
- `opt-run-dir`: persist the run (`--run-dir`) with summary, candidates, and best artifact.
- `opt-cache`: reuse evaluator results from an earlier run (`--cache --cache-from <run-dir>`).
- `opt-diff`: print a seed-vs-best unified diff to stderr (`--diff`).

## How to get to it (user POV)

- `uv run optimize-anything optimize <seed> --evaluator-command … | --evaluator-url … | --judge-model … [--model …]`
- `uv run optimize-anything optimize --no-seed --objective "…" --model … <evaluator>`
- The plugin's `/optimize-anything:optimize` and `/optimize-anything:quick` commands, which wrap the same CLI.
- `--spec-file <toml>` supplies the same flags from a file.

## Driving it with verifyctl + uv

Preconditions:

- Baseline from [README.md](./README.md). `$EVID/work/seed.txt` does not contain `VERIFY-MARKER-7f3a`.
- Set `STUB_BASE=$(cat "$EVID/stub/base")`.

Steps:

- **Command evaluator (`opt-command`).** Run the canonical drive in SKILL.md with `O="$EVID/optimize-command"`. Pass if:
  - `jq '.score_summary' "$O"/runs/run-*/summary.json` shows `initial` 0.2, `best` 0.9, and `num_candidates` ≥ 2.
  - `.llm_provenance_summary.call_count` ≥ 1.
  - `"$O/best.txt"` ends with `VERIFY-MARKER-7f3a`.
  - `$O/evaluator_payloads.jsonl` rows carry `"_protocol_version": 2` and a `candidate`.
- **Run dir contents (`opt-run-dir`).** Run `ls "$O"/runs/run-*/`. It lists `summary.json`, `best_artifact.txt`, `seed.txt`, `candidates.json`, `run_log.json`, and `gepa_state.bin`. `best_artifact.txt` matches `$O/best.txt`.
- **Diff (`opt-diff`).** Repeat the command drive with `--diff` and a new `O="$EVID/optimize-diff"`. `stderr.log` contains a unified diff whose `+` line is `VERIFY-MARKER-7f3a`.
- **HTTP evaluator (`opt-http`).**
  1. Pick a free port P.
  2. Start the evaluator: `(cd "$EVID/work" && uv run python ../../../scripts/evaluator_http_server.py --port P --evaluator-command bash marker_eval.sh) > "$EVID/http_eval.log" 2>&1 &`. Record `$!` into `$EVID/http_eval.pid`.
  3. Wait until `curl -fsS http://127.0.0.1:P/` returns `{"status": "ok"}`.
  4. Run the command drive with `--evaluator-url http://127.0.0.1:P/` in place of `--evaluator-command … --evaluator-cwd …`, with `O="$EVID/optimize-http"`.
  5. Apply the same pass checks as `opt-command`.
  6. Kill the recorded PID afterwards.
- **LLM judge (`opt-judge`).** Replace the evaluator flags with `--judge-model openai/verify-stub --objective "clarity"`. The stub judge scores every candidate 0.8, so do not expect improvement. Pass if:
  - Exit is 0.
  - `summary.json` shows `score_summary.initial` 0.8.
  - `backend_plan.judge.model` is `openai/verify-stub`.
  - The stub log has both judge requests (`response_format` `json_object`) and proposer requests.
- **No seed (`opt-no-seed`).** Run `uv run optimize-anything optimize --no-seed --objective "Write a one-line product blurb" --model openai/verify-stub --api-base "$STUB_BASE" --no-api-fallback --evaluator-command bash marker_eval.sh --evaluator-cwd "$EVID/work" --budget 6 --run-dir "$EVID/optimize-noseed/runs" -o "$EVID/optimize-noseed/best.txt"`. Pass if exit is 0, `best.txt` is non-empty, and `requests.jsonl` shows the bootstrap call.
- **Cache (`opt-cache`).** Run the command drive with `--cache` into `O1`. Then run it again with `--cache --cache-from "$O1"/runs/run-*` and `--run-dir "$O2/runs"`. Pass if `"$O2"/runs/run-*/fitness_cache/` exists and is non-empty, and `$O2/evaluator_payloads.jsonl` has fewer rows than the first run's.

## Gotchas

- A dead or misrouted proposer makes `optimize` exit 1, printing `Error: all N proposer call(s)` and the cause. The run dir and `-o` file are still written, holding the unchanged seed. This was fixed 2026-11-10; before that it exited 0. Evidence is in `smoke_outputs/verify-20261110-041330-14886/optimize-dead/`. Partial proposer failures still exit 0, so check `num_candidates` and `call_count`, not only the exit code.
- `--run-dir` names the subdir by UTC second. Two runs in the same second share it, and the second resumes the first (`Loading gepa state from run dir`). Give each drive its own parent dir.
- Budget 1 only evaluates the seed. Use budget 6.
- Do not parse `stdout.log` as JSON, because GEPA progress lines come first. Read `summary.json`.
- Without `--model`, the proposer falls back to `OPTIMIZE_ANYTHING_MODEL`, then to `openai/gpt-5.6-sol`. That is a real, billed model. Always pass `--model openai/verify-stub` and `--api-base`.
- `scripts/evaluator_http_server.py` defaults to port 8234. Pass `--port` so parallel runs do not collide.
- The first evaluator payload is a preflight probe (`candidate` starts with `__optimize_anything_preflight_`). Skip it when counting real evaluations in `evaluator_payloads.jsonl`.
- Verified 2026-11-10 (evidence `smoke_outputs/verify-20261110-035202-89994/optimize-command/`): `opt-command` and `opt-run-dir`. The other sub-features are recipes that have not been run yet. Promote each one to verified after a run proves it.
