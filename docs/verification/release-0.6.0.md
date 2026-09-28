# 0.6.0 release verification

## Live Codex skill optimization

**Run date:** 2026-09-27 PDT (2026-09-28 UTC)  
**Decision:** Reject all generated candidates. The skill and `scores.json` remain unchanged.

The post-packaging source of `skills/generate-evaluator/SKILL.md` scored **0.8876** with `evaluators/skill_clarity.sh` before the live run. Its SHA-256 was `36176f2956c44802031495bae173725c6843ec8d3b14391dbabcbf98deefa108`. The older `scores.json` entry records 0.8503; that historical value was not used as this run's baseline. The acceptance target was 0.9 plus the evaluator contract and plugin workflow checks.

Both runs used the direct CLI `optimize` path with `--proposer-backend codex`, `--no-api-fallback`, `--no-parallel`, one proposal per iteration, and the deterministic evaluator. Each requested six metric calls. `--evaluator-command bash evaluators/skill_clarity.sh` was the last flag. Raw prompts, candidate text, and run logs remain in ignored `integration_runs/release-0.6.0-u3/`.

| Run ID | Actual metric calls | Codex proposal calls | Finite proposal scores | Retained `num_candidates` | Best score |
|---|---:|---:|---|---:|---:|
| `94a607a28ce9408597ec49b8694be3e8` | 7 | 3 | 0.8275, 0.8728, 0.8473 | 1 | 0.8876 |
| `5e22321923c64eb98ac53d0ba6d6646a` | 7 | 3 | 0.8374, 0.8477, 0.8360 | 1 | 0.8876 |

The six proposals were distinct from the seed, with three distinct proposal texts per run. All six Codex calls reported `actual_backend=codex`, `auth_class=subscription`, and model `gpt-5.6-terra`; the backend plan disabled API fallback and reported no fallback cause or mixed backend. Total spend was **14 evaluator calls** and **6 Codex subscription calls** (57,914 reported tokens across the two runs). GEPA used one more evaluator call than each requested budget because it checks the budget between iterations. No billed API fallback was used.

`num_candidates=1` in each summary counts retained candidates, so it does not mean the run failed to evaluate proposals. The run logs record three evaluated proposals in each run. The best proposal scored 0.8728, a **-0.0148** delta from the frozen baseline; the retained best stayed at 0.8876, a **0.0** delta. The release plan's stricter `num_candidates > 1` verification condition was **not met**, and no candidate reached the 0.9 target. No candidate was applied, so candidate-specific Protocol v2, preflight, numeric score, evaluator-pattern, host/backend, no-fallback, and bundled-launcher acceptance checks were not reached. This is an explicit rejection under the 15-call cap, not an accepted optimization improvement.

After both runs, the skill still matched the frozen source byte for byte, so the applied skill diff is empty. `scores.json` still had SHA-256 `ddfade5810c4323b38daede71a2ff10e9afb0e91df65b1c5c7d40038d177377a`; no other score entries were changed.
