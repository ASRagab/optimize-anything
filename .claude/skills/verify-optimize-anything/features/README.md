# optimize-anything verification map

This directory is the maintained source for verifying the user-facing behavior of the optimize-anything CLI. Read this index first, then use the matching feature file as the recipe. Launch, doctor, evidence, and cleanup rules live in [../SKILL.md](../SKILL.md).

## Baseline preconditions

- `uv sync` has run, and `uv run optimize-anything --help` exits 0.
- `.claude/skills/verify-optimize-anything/scripts/verifyctl.sh start` printed `EVID=…` and `STUB_BASE=…`.
- `verifyctl.sh doctor "$EVID"` printed `doctor=PASS`.
- `$EVID/work/seed.txt` holds the two-line blurb seed from SKILL.md, and `$EVID/work/marker_eval.sh` exists.
- Every LLM-touching command carries `--api-base "$STUB_BASE" --no-api-fallback`. Without it, the command can bill a real provider.
- Never drive an instance this run did not start.

## Driving conventions

- Run from the repo root as `uv run optimize-anything <subcommand> …`.
- Use `openai/verify-stub` as the model string. Any `openai/<name>` works, because the stub ignores the name.
- Write each feature's proof to `$EVID/<feature-id>/`: `command.txt`, `stdout.log`, `stderr.log`, `exit_code.txt`, plus the state files named in the recipe.
- Use `jq` for assertions. `python3 -c` is blocked in the agent shell.
- After each LLM-touching step, check `jq -c '{path,status}' "$EVID/stub/requests.jsonl" | sort | uniq -c`. Expect `/v1/chat/completions` with 200 and no 404.

## Proof and skip reporting

- Proof is the command, its exit code, the resulting JSON or state, and the side-effect trail (`stub/requests.jsonl`, run-dir files, generated files).
- An `"error"` key or `score: 0.0` from an LLM-backed command is a failure, even with exit 0.
- Report an entry point you could not reach with the command you tried and the unmet precondition.
- Live-provider paths (`claude`/`codex` backends, `--jev-model`, real models) count as skipped unless the user approved a paid run.

## Feature entry contract

Each feature file has an H1, one paragraph, then these four H2s in order: `Sub-features`, `How to get to it (user POV)`, `Driving it with verifyctl + uv`, and `Gotchas`.

## Features

- [Optimize](./optimize.md) covers seeded and seedless optimize with command, HTTP, and judge evaluators; run-dir persistence; and the cache.
- [Score](./score.md) covers one-shot scoring with command and judge evaluators, including dimensioned intake.
- [Generate evaluator](./generate-evaluator.md) covers the judge, command, http, and composite evaluator scripts, and running them.
- [Analyze and validate](./analyze-validate.md) covers dimension discovery and multi-provider judge validation.
- [Planning tools](./planning.md) covers `intake`, `explain`, and `budget`. These are offline, with no LLM.
