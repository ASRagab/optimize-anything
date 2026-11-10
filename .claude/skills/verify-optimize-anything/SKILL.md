---
name: verify-optimize-anything
description: Drive the optimize-anything CLI (optimize, score, analyze, validate, generate-evaluator, intake, explain, budget) the way a user would and capture proof. Use this to confirm a change works in the real CLI, not only in pytest. It runs offline against a local OpenAI-compatible stub by default. Real providers run only on opt-in.
---

# Verify optimize-anything

optimize-anything is a Python CLI (`uv run optimize-anything <subcommand>`). There is no server to keep alive. Each drive is one CLI process. The LLM calls (proposer, judge, analyze, validate) go to a local stub (`scripts/fake_llm.py`) through the production `--api-base` flag. That stub is the only mock: `--api-base` is the boundary the CLI already exposes for other OpenAI-compatible hosts.

Everything below runs from the repo root. `$SK` means `.claude/skills/verify-optimize-anything`.

## Hard rules

- **No paid calls without the user's approval.** If provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …) are in the environment, any LLM command without `--api-base "$STUB_BASE"` can bill a real account. So can a `*_BASE_URL` env var that points at a proxy. Pass `--api-base "$STUB_BASE"` and `--no-api-fallback` to every LLM-touching command. `doctor` shows which keys are set and where the base URLs point.
- **No `--proposer-backend`, `--judge-backend`, or `--analysis-backend` set to `claude` or `codex` without approval.** Those spawn the `claude` and `codex` CLIs on the user's subscription. They ignore `--api-base`.
- **Exit code 0 proves nothing by itself.** LLM failures often degrade silently:
  - `optimize` exits 1 with `Error: all N proposer call(s) failed` when every proposer call fails (fixed 2026-11-10). If only some proposer calls fail, it still exits 0, and so does a run where the proposer worked but nothing improved. Check `num_candidates` and `call_count`.
  - `score`, `validate`, and generated judge evaluators exit 0 with `"score": 0.0` and an `"error"` key.
  Always assert on the JSON fields and the stub request log.
- Each run gets its own evidence dir. Never reuse a `--run-dir` from another run (see Gotchas).

## Launch

Install deps once: `uv sync` (add `--extra codex` only if you are explicitly verifying the codex backend).

Start one isolated instance. This creates the evidence dir, starts the stub on a free port, and copies the marker evaluator in:

```bash
$SK/scripts/verifyctl.sh start
# EVID=/…/smoke_outputs/verify-<utc-ts>-<pid>
# STUB_BASE=http://127.0.0.1:<port>/v1
```

Ready means `start` printed both lines and `doctor` (below) prints `doctor=PASS`. In later commands, set `EVID=<printed path>` literally and read the base URL with `STUB_BASE=$(cat "$EVID/stub/base")`. Some agent shells block `eval`, so `start` prints plain lines and does not print `export` lines.

Instances are independent: each has its own port, PID, and `$EVID`. Parallel runs are safe as long as each uses its own `$EVID`.

Layout of `$EVID`:

- `stub/requests.jsonl` holds every request the stub got: method, path, status, and body. Bodies have no headers or keys.
- `stub/port`, `stub/pid`, `stub/base` hold live-instance state. `stop` removes `port` and `pid`.
- `work/` holds inputs: the seed, plus `marker_eval.sh` (copied from `$SK/scripts/`).
- `<feature>/` holds the proof for each drive. You create it.

## Doctor

Read-only. Run it first, and again whenever something looks off:

```bash
$SK/scripts/verifyctl.sh doctor "$EVID"
```

It reports the git HEAD and dirty count, the package version, whether `optimize-anything --help` runs, and whether the stub PID is alive *and* answering `/health` with that same PID (so the port is ours). It also prints the hosts of the base-URL env vars and the set/unset state of each API key. It never prints values. Any `FAIL` or `DOWN` means: stop, then `start` a fresh instance. Do not drive it.

## Drive

Write every proof under `$EVID/<feature>/`. Prefer `--run-dir` and `-o` outputs over parsing stdout. `optimize` stdout starts with GEPA progress lines (`Iteration 0: …`), so it is not pure JSON.

The canonical drive is `optimize` with a command evaluator and the stub proposer:

```bash
O="$EVID/optimize-command"; mkdir -p "$O"
printf 'You are a writing assistant. Improve this blurb while preserving facts:\nOur launch is Monday and the beta has room for 20 teams.\n' > "$EVID/work/seed.txt"
CMD=(uv run optimize-anything optimize "$EVID/work/seed.txt"
  --evaluator-command bash marker_eval.sh --evaluator-cwd "$EVID/work"
  --model openai/verify-stub --api-base "$STUB_BASE" --no-api-fallback
  --budget 6 --run-dir "$O/runs" -o "$O/best.txt")
printf '%q ' "${CMD[@]}" > "$O/command.txt"
VERIFY_EVAL_LOG="$O/evaluator_payloads.jsonl" "${CMD[@]}" > "$O/stdout.log" 2> "$O/stderr.log"; echo "exit=$?" > "$O/exit_code.txt"
```

Pass only if all of these hold:

- `exit=0`.
- `jq '.score_summary' "$O"/runs/run-*/summary.json` shows `best` 0.9 > `initial` 0.2, and `num_candidates` ≥ 2.
- `jq '.llm_provenance_summary.call_count' …/summary.json` is ≥ 1.
- `"$O/best.txt"` contains `VERIFY-MARKER-7f3a`.
- `jq -c '{path,status}' "$EVID/stub/requests.jsonl"` shows `/v1/chat/completions` with status 200.
- There are no 404 rows. A 404 means LiteLLM changed route. Fix the stub; do not ignore it.

How the stub answers (`$SK/scripts/fake_llm.py`):

- **Proposer prompts.** These ask for "``` blocks". The stub returns the text from the prompt's first ``` block with `VERIFY-MARKER-7f3a` appended. `marker_eval.sh` scores that 0.9 and anything else 0.2, so improvement is visible and deterministic.
- **Judge, analyze, and validate prompts.** The stub returns JSON with exactly the keys the prompt asks for, because the judge schema rejects extra keys. Those keys are `score` 0.8, `reasoning`, one key per `- <dim> (weight=…)` line, `hard_constraints_satisfied` when constraints are listed, or `{"dimensions": [...]}` for analyze's second call.

The feature map gives per-subcommand recipes: [features/README.md](features/README.md).

## Evidence

Proof lives in `$EVID` under `smoke_outputs/`. That dir is gitignored, so it survives cleanup and does not dirty `git status`. A complete proof for a drive has:

- `command.txt` (the exact argv), `stdout.log`, `stderr.log`, and `exit_code.txt`.
- The resulting state: `runs/run-*/summary.json`, `best_artifact.txt`, `candidates.json`, the `-o` output file, and generated evaluator files.
- The side-effect trail: `stub/requests.jsonl` (the LLM calls made) and `evaluator_payloads.jsonl` (the payloads the evaluator saw, protocol v2).

Proof standards:

- Drive the real CLI entry point (`uv run optimize-anything …`). Do not call internal functions or run pytest as a substitute.
- Assert on the resulting state, not on a success line. "Optimization complete." prints even when no proposal was made.
- When you claim a side effect (run dir written, cache reused, file generated), `ls` or `cat` it into the proof.
- Report each mapped entry point you skipped. Do not count a skipped path as covered by another path.

## Cleanup

```bash
$SK/scripts/verifyctl.sh stop "$EVID"
ls "$EVID"   # evidence must still be here
```

`stop` kills only the PID in `$EVID/stub/pid`. Never `pkill -f fake_llm` or kill by name: another agent's instance may be running. If you started `scripts/evaluator_http_server.py`, kill the `$!` PID you recorded for it. Run `stop` after failed attempts too. To discard evidence, the user deletes `smoke_outputs/verify-*` themselves.

## Live providers (opt-in only)

Only with explicit user approval, because it bills. Drop `--api-base` and use real models, such as `--model openai/gpt-5.6-sol` and `--judge-model openai/gpt-5.6-luna`.

Before any live call:

- If `doctor` shows `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, or `GEMINI_API_BASE_URL` pointing at a local proxy, run every command under `env -u OPENAI_BASE_URL -u ANTHROPIC_BASE_URL -u GEMINI_API_BASE_URL`. LiteLLM honors those vars, so otherwise calls route through the proxy.
- Keep paid keys in a `chmod 600` env file outside the repo, and load them only into the child: `env -u ANTHROPIC_API_KEY uv run --env-file <file> …`. Existing env values win over the file, so unset any stale key first.
- Check each key and model with a free models request, printing status codes only:
  - OpenAI: `GET https://api.openai.com/v1/models/<id>`
  - Anthropic: `GET https://api.anthropic.com/v1/models/<id>`
  - Gemini: `GET https://generativelanguage.googleapis.com/v1beta/models/<id>`, with the key in the `x-goog-api-key` header

  A 200 proves the key works for listing models, not that the account can bill.
- Never print raw LiteLLM exception text. Gemini errors embed `?key=<GEMINI_API_KEY>` in the URL, nested inside the exception's `__cause__` chain. Send outputs to files, show only selected JSON fields, mask `sk-ant-…` and `key=…` patterns, and finish with a key-match count over the evidence dir (counts only).

Live run 2026-11-10:

- OpenAI: `optimize` with `openai/gpt-5.6-sol` worked. Score went from 0.2 to 0.9; the real proposer read the evaluator's feedback and added the marker line itself, in 2 calls. `score` and `analyze` with `openai/gpt-5.6-luna` worked.
- Anthropic: `score`, `analyze`, and `validate` with `anthropic/claude-sonnet-5` worked. `optimize` with the Sonnet proposer made 3 calls and produced 3 real rewrites, each evaluated. None added the marker line, so all 3 were rejected and best stayed 0.2. The proposer path works. The marker check depends on the model: GPT-5.6-sol follows the evaluator's "add the line" feedback, and Sonnet does not.
- Gemini: `models/<id>` returned 200, but `generateContent` failed with `402 Payment Required` (no billing on the account), which LiteLLM reports as `APIConnectionError`. That run exposed the `validate` miscount bug (`successful: 2, failed: 0`). After the fix, `validate` reports `successful: 1, failed: 1` and averages only the working provider.
- For a live `optimize` proof, do not require the marker. Assert all of these instead:
  - `call_count` ≥ 1, with `actual_model` equal to the requested model.
  - `run_log.txt` has `Proposed new text` lines.
  - `evaluator_payloads.jsonl` has candidates that differ from the seed.
- When a provider fails, `validate` prints LiteLLM's "Give Feedback" banner to stdout before the JSON. Parse from the first line that starts with `{`.

Still unverified live:

- An accepted Anthropic `optimize` candidate. The proposer ran, but GEPA accepted none of its rewrites.
- A successful Gemini call.
- The `claude` and `codex` subscription backends.
- The Jev evaluator (`--jev-model`, needs `TYPESAFE_API_KEY`).

## Helpers

All are executable. Run them from the repo root.

- `$SK/scripts/verifyctl.sh start | doctor "$EVID" | stop "$EVID"` handles lifecycle.
- `$SK/scripts/fake_llm.py --state-dir <dir>` is the stub. `verifyctl.sh start` runs it with `.venv/bin/python`, so you never call it directly.
- `$SK/scripts/marker_eval.sh` is the command-protocol evaluator: JSON in on stdin, `{"score","reasoning"}` out. It logs payloads to `$VERIFY_EVAL_LOG` when that is set.

## Gotchas

- `--run-dir X` creates `X/run-<UTC seconds>`. Two runs in the same second share that dir, and the second prints `Loading gepa state from run dir` and *resumes* the first. Give every run its own `--run-dir` parent.
- Budget 1 only evaluates the seed. Use budget ≥ 4 for a proposal to happen. Early stop auto-enables above budget 30.
- Some agent sandboxes block `python3 -c` and `eval` in the agent shell. Use the shipped helper files and `jq`. Evaluator subprocesses are not affected.
- `.claude/skills/` is tracked in git (`.gitignore` has `.claude/*` plus `!.claude/skills/`). Other `.claude/` files, such as `settings.local.json`, stay ignored.
