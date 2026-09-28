# 0.6.0 release verification

## Live Codex skill optimization

**Run date:** 2026-09-27 PDT (2026-09-28 UTC)  
**Decision:** Reject all generated candidates. No candidate changed the skill or `scores.json` during the run; a later release-review correction changed one skill example.

The post-packaging source of `skills/generate-evaluator/SKILL.md` scored **0.8876** with `evaluators/skill_clarity.sh` before the live run. Its SHA-256 was `36176f2956c44802031495bae173725c6843ec8d3b14391dbabcbf98deefa108`. The older `scores.json` entry records 0.8503; that historical value was not used as this run's baseline. The acceptance target was 0.9 plus the evaluator contract and plugin workflow checks.

Both runs used the direct CLI `optimize` path with `--proposer-backend codex`, `--no-api-fallback`, `--no-parallel`, one proposal per iteration, and the deterministic evaluator. Each requested six metric calls. `--evaluator-command bash evaluators/skill_clarity.sh` was the last flag. Raw prompts, candidate text, and run logs remain in ignored `integration_runs/release-0.6.0-u3/`.

| Run ID | Actual metric calls | Codex proposal calls | Finite proposal scores | Retained `num_candidates` | Best score |
|---|---:|---:|---|---:|---:|
| `94a607a28ce9408597ec49b8694be3e8` | 7 | 3 | 0.8275, 0.8728, 0.8473 | 1 | 0.8876 |
| `5e22321923c64eb98ac53d0ba6d6646a` | 7 | 3 | 0.8374, 0.8477, 0.8360 | 1 | 0.8876 |

The six proposals were distinct from the seed, with three distinct proposal texts per run. All six Codex calls reported `actual_backend=codex`, `auth_class=subscription`, and model `gpt-5.6-terra`; the backend plan disabled API fallback and reported no fallback cause or mixed backend. Total spend was **14 evaluator calls** and **6 Codex subscription calls** (57,914 reported tokens across the two runs). GEPA used one more evaluator call than each requested budget because it checks the budget between iterations. No billed API fallback was used.

`num_candidates=1` in each summary counts retained candidates, so it does not mean the run failed to evaluate proposals. The run logs record three evaluated proposals in each run. The best proposal scored 0.8728, a **-0.0148** delta from the frozen baseline; the retained best stayed at 0.8876, a **0.0** delta. The release plan's stricter `num_candidates > 1` verification condition was **not met**, and no candidate reached the 0.9 target. No candidate was applied, so candidate-specific Protocol v2, preflight, numeric score, evaluator-pattern, host/backend, no-fallback, and bundled-launcher acceptance checks were not reached. This is an explicit rejection under the 15-call cap, not an accepted optimization improvement.

Immediately after both runs, the skill still matched the frozen source byte for byte, so the applied optimization diff was empty. Release review later corrected the dataset-aware CLI example; the current skill has SHA-256 `dfbc4465dc5de7ca515520b65422039b08ea518e0396bbc7384b32e182c6e4e7` and scores 0.8875 with the same evaluator, 0.0001 below the frozen run seed. `scores.json` still has SHA-256 `ddfade5810c4323b38daede71a2ff10e9afb0e91df65b1c5c7d40038d177377a`; no score entries were changed.

## Premerge release-candidate checks

**Checked on:** 2026-09-27 PDT (2026-09-28 UTC). **Tested release-code commit:** `d9defd1ec5295223527b81fdf2c83ae5ef752a9c`. The full gate, focused contracts, Bash syntax, type check, and package build ran on that tree immediately before or after its commit. The earlier U2 clean-install check is identified separately below. Subsequent release-evidence edits need the final PR-head CI check; these local results do not claim it has passed.

| Gate | Status | Observed result |
|---|---|---|
| Version and lockfile | PASS | `uv lock` resolved 77 packages and changed the local project entry from 0.5.1 to 0.6.0. Python, Claude manifest and marketplace, and Codex manifest fields now read 0.6.0; the Codex marketplace resolves its version from the manifest. |
| Focused release contracts | PASS | `uv run pytest tests/test_prompt_plugin_contract.py tests/test_doc_contract.py tests/test_plugin_launcher.py`: 38 passed. The version-parity contract reads all active version fields; the installer test covers default Bash 3.2 and Codex paths. |
| Full project gate | PASS | `uv run python scripts/check.py`: 546 passed, 18 skipped; CLI smoke and all three tracked score baselines passed. Credentialed plugin regression was skipped because `--with-plugin` was not set. The reviewed skill's current deterministic score is 0.8875. |
| Type and shell checks | PASS | `uv run mypy src/optimize_anything`: no issues in 27 source files. `/bin/bash -n install.sh scripts/run-optimize-anything` and `git diff --check` passed. |
| Package build and wheel install | PASS | `uv build` made `optimize_anything-0.6.0.tar.gz` and `optimize_anything-0.6.0-py3-none-any.whl`. The wheel lists the CLI module, entry point, and 0.6.0 metadata. An isolated `uv tool run --from dist/optimize_anything-0.6.0-py3-none-any.whl optimize-anything --help` succeeded. |
| Plugin payload inspection | PASS | The 0.6.0 source archive lists both host manifests, the Claude marketplace and commands, the shared launcher, all four canonical skills, and the prompt skill's agent, reference, and evaluator resources. The wheel is the Python CLI package; plugin distribution uses the repository/source tree. |
| Clean host install (U2 result, reused) | PASS | A fresh copied plugin snapshot with no global CLI exposed four shared skills and nine Claude commands. Its bundled launcher ran `budget` with Codex SDK 0.156.0, generated a Codex/no-fallback evaluator, and passed child preflight. A separate isolated global install and Python 3.10.21 check passed after pinning the SDK to 0.156.0; U2 reported 56 focused tests passed. This check was not rerun during U4 package inspection. |
| Review and fixes | PASS | Compound Engineering review run `20260927-174849-e5d41434` completed with an independent Claude adversarial pass. Three validated findings were fixed: default Bash installer, dataset quick start, and bundled LiteLLM example/guard. The evaluator child's dependency flags were aligned. A platform limitation remains documented below. |
| PR head and post-merge gates | PENDING | Final PR-head CI results, merge SHA, main workflow, and tag/install results belong to the release operation. |

The plan's `num_candidates > 1` proxy is a failed check, not a publication gate: GEPA counts retained candidates there. The live logs instead show six distinct evaluated proposals with finite scores, actual Codex subscription provenance, and no API fallback. This satisfies the real-candidate part of R4. All scores were below the frozen baseline and the 0.9 acceptance target, so R5 rejected them; no optimization candidate changed the source or score history. The later CLI example correction is separate from that decision. No candidate improvement or cross-provider corroboration is claimed.

## Known audit findings and release disposition

- **GEPA evaluator cache identity (R4): follow-up, with an operating constraint.** `test_cache_fingerprint_uses_actual_route_without_exposing_input` covers the backend's safe fingerprint, but GEPA's evaluator `fitness_cache` key does not include the actual completion route after a subscription-to-API fallback. This affects opt-in `--cache`/`--cache-from` runs when an evaluator or judge can switch routes; it does not affect the default uncached path or the uncached Codex release run above. `install.md` now tells users to omit those cache flags for such runs. A route-aware cache policy or GEPA integration remains follow-up work; the audit's R4 status remains partial.
- **TOML table-over-scalar precedence (R6): follow-up.** One TOML document cannot define `model.proposer` as both a scalar and a table; standard parsing rejects it before precedence can apply. `test_scalar_table_model_conflict_names_both_keys` verifies the specific diagnostic, while existing CLI-over-spec tests verify the supported override path. Use one representation per role and a CLI flag for an override. Multi-file layering or new syntax requires a separate product decision; the audit's R6 status remains partial.
- **Plugin platforms without a Codex binary wheel: follow-up.** The bundled launcher selects the Codex extra for every plugin invocation. On an architecture without an `openai-codex-cli-bin` wheel, even API-only plugin commands cannot start. The release install check covers macOS arm64; other platforms remain untested. `install.md` directs API-only users on those platforms to the global CLI or source install without the Codex extra. A broader plugin runtime policy needs a separate compatibility decision.

The premerge evidence and changelog contain no credentials, account identity, raw prompts, or private candidate text. Detailed live artifacts remain in ignored `integration_runs/`; built packages and smoke outputs remain outside the committed release evidence.
