# Planning tools

`intake`, `explain`, and `budget` help a user plan a run before spending evaluator calls. They are fully offline and make no LLM calls.

## Sub-features

- `intake-normalize`: normalizes an intake spec from flags, inline JSON, or a file, filling default `quality_dimensions`.
- `intake-reject`: rejects an invalid spec with a non-zero exit.
- `explain-plan`: prints a human-readable plan for a seed and objective.
- `budget-recommend`: prints a JSON budget recommendation from the seed's size.

## How to get to it (user POV)

- `uv run optimize-anything intake [--artifact-class …] [--execution-mode command|http] [--evaluation-pattern …] [--hard-constraint …] [--intake-json … | --intake-file …]`
- `uv run optimize-anything explain <seed> [--objective "…"]`
- `uv run optimize-anything budget <seed>`
- The plugin's `/optimize-anything:intake`, `/optimize-anything:explain`, and `/optimize-anything:budget` commands.

## Driving it with verifyctl + uv

Preconditions:

- Baseline from [README.md](./README.md). The stub is not needed. Set `PL="$EVID/planning"`, then `mkdir -p "$PL"`.

Steps:

- **Intake from flags.** Run `uv run optimize-anything intake --artifact-class prompt --execution-mode command --hard-constraint "no PII" > "$PL/intake.json"`. Pass if:
  - Exit is 0.
  - `jq -c '{artifact_class, execution_mode, evaluation_pattern, hard_constraints, dims: [.quality_dimensions[].name]}'` gives `{"artifact_class":"prompt","execution_mode":"command","evaluation_pattern":"judge","hard_constraints":["no PII"],"dims":["correctness","clarity","conciseness"]}`.
- **Intake rejection.** Run `uv run optimize-anything intake --intake-json '{"execution_mode":"carrier-pigeon"}'`. Exit is 1, and stderr is `Error: invalid intake spec: execution_mode must be one of: 'command', 'http'`.
- **Explain.** Run `uv run optimize-anything explain "$EVID/work/seed.txt" --objective clarity`. Stdout starts with `Seed: <N> chars` and `Objective: clarity`.
- **Budget.** Run `uv run optimize-anything budget "$EVID/work/seed.txt"`. Stdout is JSON with `recommended_budget` 100, `rationale` `"Medium artifact"`, and `seed_length` 129, which equals `wc -m` of the baseline seed. A seed of about 71 chars gives 50 and `"Short artifact"`.

## Gotchas

- `intake` fills default dimensions when none are given. Do not mistake the defaults for user input.
- `budget` depends only on seed length, not on the objective.
- Verified 2026-11-10 (evidence `smoke_outputs/verify-20261110-035404-91741/planning/`): all four sub-features.
