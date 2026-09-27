---
type: report
title: Subscription Backends U1-U7 Completion Audit
created: 2026-09-26
tags: [subscription-backends, audit, verification]
related: ['[[Subscription-Live-Evidence]]']
---

# Subscription Backends U1-U7 Completion Audit

This report audits units U1-U7 of `docs/plans/2026-09-22-1841-feature-subscription-backends-plan.md` against:

- the plan's requirements R1-R14 (plan:42-55);
- each unit's "Test scenarios" (plan:187, :201, :215, :229, :243, :257, :271);
- the design spec `docs/superpowers/specs/2026-08-01-codex-claude-subscription-backends-design.md`.

**Scope and references**

- **Audited commit:** `0b0a99562e657d173b32c94f1f27062669e7b794` on `feat/codex-claude-subscription`.
  - `src/` is identical to `origin/main` at `70e1fdf2905a1f44b5b447eaa027f5ecfb6dbcef`, because PR #6 merged the backends.
  - PR #7 is still open: https://github.com/ASRagab/optimize-anything/pull/7
- **Live evidence:** Verification Contract steps 8-11 (the opt-in subscription and paid-fallback gates) are recorded in `docs/verification/subscription-live-evidence-2026-09-26.md`.
  - This audit covers code and offline tests only.
  - Offline gate results for steps 1-7 go under "Offline Gate Results" (Phase-01 Tasks 3-5).
- **Paths:**
  - Source paths are relative to `src/optimize_anything/`.
  - Line numbers refer to the audited commit.
  - Test references are pytest node IDs, confirmed with `uv run pytest --collect-only -q -o addopts="" tests/`.

**Status rule**

- `covered`: the behavior is implemented, and every element named in the R-text either has an offline test or is guaranteed by the code's structure (cited).
- `partial`: the behavior is implemented, but an element named in the R-text or in the owning unit's plan test scenarios has no test, or is only partly implemented.
- `gap`: the behavior is missing, or the code contradicts it.

## Requirement Matrix

| R-ID | Unit(s) | Implementing symbol(s) | Covering test(s) | Status | Notes |
|---|---|---|---|---|---|
| R1 | U4, U6 | `llm_backends/codex_backend.py:82` `CodexSdkBackend` (`_client` :110 blanks `OPENAI_API_KEY`/`CODEX_API_KEY`)<br>`llm_backends/factory.py:25` `resolve_backend_spec`, `:55` `create_backend`, `:113` `BackendLanguageModel`<br>`cli_optimize.py:202` `_configured_optimization_backends` (proposer :246, judge :251)<br>`cli_tools.py:365` `_completion_backend` (score/analyze), `:310` `_validate_provider`<br>`llm_judge.py:94` `llm_judge_evaluator`, `:325` `analyze_for_dimensions`<br>`evaluator_runtime.py:32` `run_generated_evaluator` | `tests/test_codex_backend.py::test_chatgpt_account_and_ephemeral_private_turn`<br>`tests/test_llm_factory.py::test_backend_language_model_adapts_gepa_prompt_lists`<br>`tests/test_evaluator_runtime.py::test_runtime_scores_json_lines_and_forwards_role_config_and_examples`<br>opt-in: `tests/test_subscription_live.py::test_saved_subscription_structured_completion[codex]`, `::test_saved_subscription_seedless_budget_one[codex]`, `::test_generated_evaluator_uses_saved_subscription[codex]` | partial | Fakes cover the proposer and generated-evaluator roles offline. No offline test sends the judge, analysis, score or validation role through a subscription backend: every `tests/test_llm_judge.py` unit case patches `litellm.completion`. The live structured gate uses only `role="validation"`. |
| R2 | U5, U6 | `llm_backends/claude_backend.py:180` `ClaudeCliBackend` (`_subscription_env` :91 strips `ANTHROPIC_*` and cloud overrides)<br>Role wiring is the same as R1 | `tests/test_claude_backend.py::test_preflight_requires_claude_subscription_under_scrubbed_env`, `::test_schema_and_user_content_stay_off_argv_and_are_locally_validated`<br>`tests/test_llm_factory.py::test_backend_language_model_adapts_gepa_prompt_lists`<br>`tests/test_evaluator_runtime.py::test_runtime_scores_json_lines_and_forwards_role_config_and_examples`<br>opt-in: the `[claude]` variants of the three `tests/test_subscription_live.py` tests | partial | Same role-wiring gap as R1. |
| R3 | U4, U5 | `llm_backends/codex_backend.py:121` `_prepare_private_home` (symlinks the saved `auth.json` into a private `CODEX_HOME` without reading it; refuses a missing or symlinked source)<br>`:127` `_check_account` (reads the auth type through the SDK `account()` call)<br>`llm_backends/claude_backend.py:213` `preflight` (runs `claude auth status` only)<br>`:60` `_BLOCKED_ENV_NAMES`, `:70` `_BLOCKED_ENV_PREFIXES`, `:91` `_subscription_env`<br>Config surface: `spec_loader.py:157` `_normalize_model_role` accepts only `backend`/`model`/`api_fallback`/`api_fallback_model`; `cli.py:24` `_add_subscription_options` has no token options | `tests/test_claude_backend.py::test_scrubber_covers_paid_auth_and_keeps_saved_login_location`, `::test_preflight_requires_claude_subscription_under_scrubbed_env`<br>`tests/test_codex_backend.py::test_chatgpt_account_and_ephemeral_private_turn` | partial | Neither adapter invokes a login command; remediation is error text only. Untested: that Codex links rather than copies `auth.json`; that Codex refuses a missing or symlinked `auth.json`; the Claude `loggedIn: false` path. |
| R4 | U1, U3, U4, U5, U6 | `llm_backends/base.py:105` `CompletionResult`, `:98` `FallbackRecord`<br>`llm_backends/provenance.py:13` `completion_event`<br>`llm_backends/coordination.py:25` `_EVENT_KEYS`, `:31` `_SAFE_VALUE`, `:220` `record_event`<br>`llm_backends/factory.py:90` `_CoordinatedBackend` (event at :109)<br>`llm_backends/fallback.py:100` `complete` (:133), `:150` `_complete_fallback` (:169)<br>`cli_optimize.py:142` `summary["llm_provenance"]`<br>`evaluator_runtime.py:105`<br>`llm_judge.py:154`, `:413` | `tests/test_llm_backend_contract.py::test_contract_values_are_immutable`, `::test_litellm_text_preserves_existing_kwargs_and_provenance`, `::test_cache_fingerprint_uses_actual_route_without_exposing_input`<br>`tests/test_llm_fallback.py::test_fallback_provenance_is_shared_with_child_coordinator`<br>`tests/test_llm_coordination.py::test_role_circuits_and_child_provenance_are_shared` | partial | Subscription results carry the full field set. API-backend roles are returned unwrapped (`factory.py:62-63`), so they never reach `events.jsonl` or `summary["llm_provenance"]`. The API proposer passes a model string to GEPA (`cli_optimize.py:243`) and produces no `CompletionResult` at all; design:255 requires a `LiteLLMBackend` callable instead. `call_id` is whitelisted but never passed. `cache_fingerprint` and `aggregate_provenance` have no production caller. |
| R5 | U1, U2, U6 | `llm_backends/factory.py:25` `resolve_backend_spec`; `:62-63` (`api` returns a bare `LiteLLMBackend`)<br>`llm_backends/litellm_backend.py:158` `LiteLLMBackend`, `:183` `complete`<br>`cli_optimize.py:243` (the API proposer keeps the GEPA model string)<br>`spec_loader.py:157` (a string role becomes `backend="api"`)<br>`cli_tools.py:90` (`args.judge_backend or "api"`)<br>`llm_judge.py:112` (default `LiteLLMBackend`)<br>`evaluator_generator.py:45` (API keeps the legacy templates) | `tests/test_llm_backend_contract.py::test_litellm_text_preserves_existing_kwargs_and_provenance`<br>`tests/test_llm_judge.py::TestLlmJudgeEvaluatorUnit::test_model_string_passed_through`, `::test_api_base_passed_when_set`, `::test_temperature_passed_through_to_litellm`, `::test_default_temperature_is_omitted_from_litellm`<br>`tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_command_evaluator_is_bash`, `::test_http_evaluator_is_python`<br>`tests/test_spec_loader.py::TestLoadSpec::test_structured_subscription_model_roles`<br>the pre-branch `tests/test_cli.py` suite, which uses no backend flags | covered | The pre-existing API-path suites run unchanged without backend flags. Any R13 fix must preserve R5; `evaluator_runtime._resolve_backend` already defaults to `backend="api"` (`evaluator_runtime.py:22`). |
| R6 | U2, U6 | `cli.py:24` `_add_subscription_options` (`--subscription-concurrency` default 1, `--no-api-fallback`, `--openai-api-fallback-model`, `--anthropic-api-fallback-model`)<br>`cli.py:94` `--proposer-backend`; `:108`, `:235`, `:312` `--judge-backend`; `:394` `--analysis-backend`<br>`spec_loader.py:146` `_normalize_model_section`, `:157` `_normalize_model_role`<br>`cli_optimize.py:496` `_apply_spec_to_args`, `:218` `role_spec`, `:180-185` concurrency | `tests/test_spec_loader.py::TestLoadSpec::test_structured_subscription_model_roles`<br>`tests/test_llm_factory.py::test_resolve_subscription_fallback_is_same_vendor_and_explicit`, `::test_no_api_fallback_overrides_resolvable_model`<br>`tests/test_llm_coordination.py::test_provider_override_allows_exactly_two_slots` | partial | TOML parsing and the factory are tested. No offline test parses the new CLI flags or checks that CLI flags override TOML. A TOML scalar/table conflict fails inside `tomllib` without naming the keys. TOML has no concurrency key; the design treats concurrency as a CLI option only (design:305, :321-338). |
| R7 | U2, U7 | Host instructions: `SKILL.md:37-41` ("Do not infer a backend in the Python runtime or for an unknown host"), `skills/generate-evaluator/SKILL.md:54`, `commands/analyze.md:5-7`, `commands/compare.md:5-7`, `commands/optimize.md:11-12`, `commands/quick.md:7-8`, `commands/score.md:5`; `.codex-plugin/plugin.json` shares the skills<br>Core has no host detection. The only `os.environ` reads are the model default, the coordination handoff (`llm_backends/coordination.py:21-22`), fallback readiness (`llm_backends/fallback.py:36-38`) and the Claude scrub. | `tests/test_prompt_plugin_contract.py::test_prompt_workflow_documentation_covers_both_hosts_and_evidence_modes` (doc terms only)<br>`tests/test_plugin_regression.py::test_claude_host_regression_uses_bounded_model` (model and budget only) | partial | No fixture checks the flags each host emits: `codex` flags for the Codex host, `claude` flags for the Claude host, and none for an unknown host (U7 scenario). Host non-inference is shown by inspection, not by a test. |
| R8 | U1, U4, U5 | Codex, in `llm_backends/codex_backend.py`: `:38` `_ISOLATION_OVERRIDES` (project docs, web search and tool features off; `model_max_output_tokens=8192`); `:36-37` `_MAX_OUTPUT_BYTES`/`_MAX_PROMPT_BYTES`; `:110` `_client` (temp `cwd`, private `CODEX_HOME`); `:148` `complete` (prompt through `thread.turn`)<br>Claude, in `llm_backends/claude_backend.py`: `:49` `_REQUIRED_FLAGS`; `:40` `_TRANSPORT_SCHEMA`; `:121` `_run_bounded`; `:241` `complete` (list argv with `--safe-mode`; prompt and user schema on stdin)<br>`llm_backends/schema.py:8` `score_output_schema`, `:32` `reject_external_refs`<br>`llm_backends/litellm_backend.py:183` (local schema validation) | `tests/test_codex_backend.py::test_chatgpt_account_and_ephemeral_private_turn`, `::test_structured_output_is_validated_locally`, `::test_timeout_interrupts_and_cleans_up`<br>`tests/test_claude_backend.py::test_schema_and_user_content_stay_off_argv_and_are_locally_validated`, `::test_original_schema_rejects_transport_valid_value`, `::test_timeout_is_typed_and_private_workspace_is_removed`, `::test_real_process_runner_bounds_output_and_terminates_on_timeout`, `::test_external_schema_ref_is_rejected_before_completion`, `::test_external_dynamic_schema_ref_is_rejected_before_completion`<br>`tests/test_llm_backend_contract.py::test_litellm_schema_is_validated_locally`, `::test_litellm_rejects_unsupported_schema_before_dispatch` | partial | The Claude argv-leak test checks schema property names and enum values but not `const` values. The Codex prompt and output byte caps are untested. Of the Codex overrides, only `features.shell_tool=false` is asserted. No test checks that the prompt stays out of logs. |
| R9 | U3, U4, U5, U6, U7 | `llm_backends/coordination.py:53` `RunCoordinator`:<br>• `create` :77 (private 0700 directory; warns when capacity != 1)<br>• `try_acquire_slot` :153 and `slot` :166 (fcntl locks)<br>• `exported_environment` :123, `attach` :103, `from_environment` :110 (`OPTIMIZE_ANYTHING_COORDINATION_DIR`/`_ID`, :21-22)<br>`llm_backends/factory.py:90` `_CoordinatedBackend`; `:66` `from_environment` for children<br>`cli_optimize.py:180-185` (always creates the run coordinator with per-provider capacity) | `tests/test_llm_coordination.py::test_provider_capacity_one_across_processes`, `::test_provider_override_allows_exactly_two_slots`, `::test_role_circuits_and_child_provenance_are_shared`<br>`tests/test_llm_fallback.py::test_queued_call_rechecks_circuit_after_acquiring_slot`, `::test_fallback_provenance_is_shared_with_child_coordinator` | partial | The environment handoff to a generated-evaluator child has no end-to-end test. The override warning is not asserted. There is no crashed-child test. |
| R10 | U5 | `llm_backends/claude_backend.py`:<br>• `:60` `_BLOCKED_ENV_NAMES` (includes `CLAUDECODE`), `:70` `_BLOCKED_ENV_PREFIXES`, `:91` `_subscription_env`; every child runs with `env=self._env()` (:205)<br>• `:213` `preflight`: `--version` must be at least `_MIN_VERSION` (:37); `--help` flag check; `auth status` must show `loggedIn`, `authMethod=="claude.ai"` and `apiProvider=="firstParty"` (:235-238)<br>• `:241` `complete` (`--safe-mode`, no `--bare`) | `tests/test_claude_backend.py::test_preflight_requires_claude_subscription_under_scrubbed_env` (accepts `claude.ai`, rejects `authMethod="apiKey"`, asserts `CLAUDECODE` is removed)<br>`::test_scrubber_covers_paid_auth_and_keeps_saved_login_location`<br>`::test_schema_and_user_content_stay_off_argv_and_are_locally_validated` (asserts `--safe-mode` is present and `--bare` absent, :82) | partial | Untested rejections: `apiProvider != "firstParty"` (cloud auth), `loggedIn: false`, a missing executable, an old version, and missing flags. |
| R11 | U4 | `llm_backends/codex_backend.py`:<br>• `:127` `_check_account` (accepts only `chatgpt`)<br>• `:99` `_module`: pin `_SDK_VERSION` (:35); requires `Codex`, `CodexConfig`, `Sandbox`, `ApprovalMode`, `Sandbox.read_only` and `ApprovalMode.deny_all`<br>• `:65` `_sdk` (missing-extra remediation), `:135` `preflight`<br>• `:148` `complete` (fresh temp workspace and private home per call) | `tests/test_codex_backend.py::test_chatgpt_account_and_ephemeral_private_turn`, `::test_api_key_auth_is_rejected_before_thread_dispatch`, `::test_version_mismatch_fails_closed` | partial | Of `_module`'s fail-closed branches, only the version mismatch is tested. |
| R12 | U2, U3, U4, U5, U6 | `llm_backends/fallback.py`:<br>• `:30` `_ELIGIBLE`<br>• `:33` `fallback_ready` (checks that `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` are present, :36-38)<br>• `:45` `FallbackBackend`, `:70` `_same_vendor`, `:89` `preflight`, `:100` `complete`, `:143` `_warn`, `:150` `_complete_fallback`<br>`llm_backends/coordination.py:189` `circuit_reason`, `:197` `open_circuit`<br>`llm_backends/factory.py:25` `resolve_backend_spec` | `tests/test_llm_fallback.py::test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api`, `::test_no_fallback_for_ambiguous_or_invalid_result[error0]` (Timeout), `::test_no_fallback_for_ambiguous_or_invalid_result[error1]` (InvalidResponse), `::test_no_fallback_to_other_vendor_or_without_readiness`, `::test_preflight_failure_routes_first_request_directly_to_api`, `::test_queued_call_rechecks_circuit_after_acquiring_slot`<br>`tests/test_llm_factory.py::test_resolve_subscription_fallback_is_same_vendor_and_explicit`, `::test_no_api_fallback_overrides_resolvable_model`<br>opt-in: `tests/test_api_fallback_live.py::test_eligible_failure_uses_same_vendor_api_with_sticky_role_circuit`, `::test_no_api_fallback_raises_typed_error_without_api_calls` | partial | `Cancelled` and `ConfigurationError` have no no-fallback test. `RateLimitError` and `QuotaExceeded` are never exercised. The tests don't prove the warning comes before dispatch. Every test injects `fallback_ready=lambda: True`, so neither the real `fallback_ready` nor the not-ready path is tested. |
| R13 | U3, U7 | `evaluator_runtime.py:15` `RUNTIME_CONTRACT_VERSION`, `:32` `run_generated_evaluator`<br>`evaluator_generator.py:12` `generate_evaluator_script`, `:45` routing gate, `:657` `_generate_runtime_evaluator`<br>**Contradicting:** `evaluator_generator.py:435` `_generate_judge_evaluator` emits `from litellm import completion, validate_environment` (:452); `:547` `_generate_composite_evaluator` embeds that template (:558) | `tests/test_evaluator_generator.py::test_generated_wrapper_runs_json_lines_through_installed_runtime`, `::test_generated_wrapper_reports_missing_installed_runtime`<br>`tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_judge_evaluator_contains_runtime_config_and_objective` (asserts no `litellm`, :184), `::test_subscription_composite_evaluator_has_constraints_and_judge` (:322), `::test_judge_evaluator_embeds_backend_and_fallback_configuration`, `::test_command_evaluator_is_bash`, `::test_http_evaluator_is_python`<br>`tests/test_evaluator_runtime.py::test_runtime_reports_incompatible_contract_and_invalid_json_as_score_lines`, `::test_runtime_scores_json_lines_and_forwards_role_config_and_examples`, `::test_composite_constraints_short_circuit_without_backend_call`, `::test_preflight_probe_does_not_call_backend`, `::test_dimension_name_cannot_replace_canonical_score`<br>**Contradicting test:** `tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_default_is_judge` asserts `"from litellm import completion" in script` (:177) | gap | Only `--judge-backend codex\|claude` routes through the runtime. The default (`api`) judge and composite scripts still embed LiteLLM, which contradicts R13, the U7 scenario and design:93, :273 and :533. `evaluator-cookbook.md:408` documents the contradicting behavior. Deterministic templates and the JSON-lines contract are intact. |
| R14 | U3, U5, U7 | `pyproject.toml:49` `integration` marker<br>`.github/workflows/ci.yml:35` `uv run pytest -v -m "not integration"`<br>`tests/test_subscription_live.py:16`: skipped unless `OPTIMIZE_ANYTHING_RUN_SUBSCRIPTION_LIVE=1`<br>`tests/test_api_fallback_live.py:55`: skipped unless `OPTIMIZE_ANYTHING_RUN_PAID_FALLBACK_LIVE` is set<br>`llm_backends/coordination.py:25` `_EVENT_KEYS` whitelist and `:31` `_SAFE_VALUE`, so no identity or prompt field can be recorded | opt-in:<br>• `tests/test_subscription_live.py::test_saved_subscription_structured_completion`, `::test_saved_subscription_seedless_budget_one`, `::test_generated_evaluator_uses_saved_subscription`<br>• `tests/test_api_fallback_live.py::test_eligible_failure_uses_same_vendor_api_with_sticky_role_circuit`, `::test_no_api_fallback_raises_typed_error_without_api_calls`<br>offline: `tests/test_llm_backend_contract.py::test_cache_fingerprint_uses_actual_route_without_exposing_input`, `::test_provider_error_does_not_expose_provider_message` | covered | The default CI job deselects `integration`. The paid judge-matrix job (`ci.yml:43-87`) predates this feature: `ci.yml` last changed in `b41adeb` on 2026-02-27, before the first backend commit `9ddfe82` on 2026-09-22. |

## Test Scenario Coverage by Unit

Every "Test scenarios" bullet in the plan is checked against the actual test names. `NO TEST` marks a scenario with no test at all; `partial` marks one only partly tested.

### U1: Shared completion contract and API compatibility (plan:187)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Existing API calls retain kwargs and parsing | tested | `tests/test_llm_backend_contract.py::test_litellm_text_preserves_existing_kwargs_and_provenance` |
| JSON and text completions succeed | tested | `::test_litellm_text_preserves_existing_kwargs_and_provenance`, `::test_litellm_schema_is_validated_locally` |
| Unsupported controls fail before dispatch | tested | `::test_litellm_rejects_unsupported_schema_before_dispatch` |
| Malformed schema output maps to `InvalidResponse` | tested | `::test_litellm_schema_is_validated_locally`; `tests/test_codex_backend.py::test_structured_output_is_validated_locally` |
| Provider exceptions map to typed errors without secrets | tested | `::test_provider_error_does_not_expose_provider_message` |

### U2: Configuration, CLI, TOML, and backend plan (plan:201)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Omitted flags remain API | tested | `tests/test_spec_loader.py::TestLoadSpec::test_structured_subscription_model_roles` (a string role becomes `api`); `tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_default_is_judge`; the unchanged `tests/test_cli.py` |
| CLI overrides table | NO TEST | |
| Table overrides legacy scalar | not expressible | TOML rejects `proposer = "..."` and `[model.proposer]` in the same file |
| Scalar/table conflicts name keys | NO TEST, and not met | `tomllib` raises `Cannot overwrite a value (at line 3, column 13)` with no key names |
| Command/HTTP evaluators reject judge backend | NO TEST | |
| Subscription selectors parse before model strings | NO TEST | |
| Custom API base reaches fallback without exposing credentials | NO TEST | |

### U3: Run coordination, fallback, provenance, and result contract (plan:215)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Provider capacity one across processes | tested | `tests/test_llm_coordination.py::test_provider_capacity_one_across_processes` |
| Override permits exactly N | tested | `::test_provider_override_allows_exactly_two_slots` |
| Independent role circuits | tested | `::test_role_circuits_and_child_provenance_are_shared`; `tests/test_llm_fallback.py::test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api` |
| One eligible failure prevents later subscription attempts for that role | tested | `tests/test_llm_fallback.py::test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api`, `::test_queued_call_rechecks_circuit_after_acquiring_slot` |
| Timeout/cancellation/invalid response never fallback | partial | `::test_no_fallback_for_ambiguous_or_invalid_result[error0]` and `[error1]`; `Cancelled` is missing |
| Warning precedes API call | partial | Tests assert the warning appears, not that it comes first |
| Crashed child cannot poison a new run | NO TEST | |
| Secrets/prompts never enter state or cache keys | partial | `tests/test_llm_backend_contract.py::test_cache_fingerprint_uses_actual_route_without_exposing_input` tests a helper that production code never calls (see R4) |

### U4: Codex SDK adapter (plan:229)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Missing extra remediation | NO TEST | |
| ChatGPT accepted / API-key auth rejected | tested | `tests/test_codex_backend.py::test_chatgpt_account_and_ephemeral_private_turn`, `::test_api_key_auth_is_rejected_before_thread_dispatch` |
| Fresh workspace/thread | tested | `::test_chatgpt_account_and_ephemeral_private_turn` |
| Prompt absent from argv/logs | partial | The adapter builds no argv (the prompt goes to `thread.turn`); logs are not asserted |
| Unsupported isolation capability blocks | partial | `::test_version_mismatch_fails_closed` covers only the version branch |
| Schema success/failure | partial | Failure: `::test_structured_output_is_validated_locally`. Success: NO TEST |
| Timeout cancellation/cleanup | tested | `::test_timeout_interrupts_and_cleans_up` |
| Live structured completion and budget-1 proposer run | opt-in | `tests/test_subscription_live.py::test_saved_subscription_structured_completion[codex]`, `::test_saved_subscription_seedless_budget_one[codex]` |

### U5: Claude CLI adapter (plan:243)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Missing/old CLI remediation | NO TEST | |
| `claude.ai` accepted and API/cloud auth rejected | partial | `tests/test_claude_backend.py::test_preflight_requires_claude_subscription_under_scrubbed_env` accepts `claude.ai` and rejects `authMethod="apiKey"`. Rejecting cloud auth (`apiProvider`) has NO TEST |
| Sentinel API key scrubbed | tested | `::test_scrubber_covers_paid_auth_and_keeps_saved_login_location`, `::test_preflight_requires_claude_subscription_under_scrubbed_env` |
| Prompt/candidate absent from argv | tested | `::test_schema_and_user_content_stay_off_argv_and_are_locally_validated` |
| Sentinels in schema property names, enum values, and const values absent from argv | partial | Property names and enum values are tested; `const` has NO TEST |
| Required saved-login environment retained | tested | `::test_scrubber_covers_paid_auth_and_keeps_saved_login_location` |
| Static-schema result adaptation and original-schema validation | tested | `::test_schema_and_user_content_stay_off_argv_and_are_locally_validated`, `::test_original_schema_rejects_transport_valid_value` |
| Output/exit/error mapping | partial | The output bound is tested in `::test_real_process_runner_bounds_output_and_terminates_on_timeout`. Nonzero-exit and error-result mapping have NO TEST |
| Timeout termination/cleanup | tested | `::test_timeout_is_typed_and_private_workspace_is_removed`, `::test_real_process_runner_bounds_output_and_terminates_on_timeout` |
| Live structured completion and seedless budget-1 proposer run | opt-in | `tests/test_subscription_live.py::test_saved_subscription_structured_completion[claude]`, `::test_saved_subscription_seedless_budget_one[claude]` |

### U6: Proposer and built-in role migration (plan:257)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| API regression | tested | The pre-existing `tests/test_llm_judge.py` and `tests/test_cli.py` suites; `tests/test_llm_backend_contract.py::test_litellm_text_preserves_existing_kwargs_and_provenance` |
| Codex/Claude callable proposal | tested | `tests/test_llm_factory.py::test_backend_language_model_adapts_gepa_prompt_lists` (fake backend) |
| Structured judge/analysis/score | NO TEST | No test runs these through a subscription backend |
| Mixed role backends | NO TEST | |
| Independent fallback | partial | Tested at the backend level only (`tests/test_llm_fallback.py::test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api`), not through the CLI roles |
| Validation provider mix | NO TEST | |
| Every role contributes provenance | NO TEST | Not met for API roles (see R4) |

### U7: Generated evaluator runtime and host skills (plan:271)

| Scenario | Result | Test(s) or reason |
|---|---|---|
| Generated wrappers contain no LiteLLM import | partial | Subscription wrappers are tested (`tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_judge_evaluator_contains_runtime_config_and_objective`, `::test_subscription_composite_evaluator_has_constraints_and_judge`). The default API judge/composite violate the scenario, and `::test_default_is_judge` asserts the violation |
| Missing/incompatible runtime is actionable | tested | `tests/test_evaluator_generator.py::test_generated_wrapper_reports_missing_installed_runtime`; `tests/test_evaluator_runtime.py::test_runtime_reports_incompatible_contract_and_invalid_json_as_score_lines` |
| JSON-lines score contract holds | tested | `tests/test_evaluator_generator.py::test_generated_wrapper_runs_json_lines_through_installed_runtime` (monkeypatched `_resolve_backend`, :111); `tests/test_evaluator_runtime.py::test_runtime_scores_json_lines_and_forwards_role_config_and_examples`, `::test_dimension_name_cannot_replace_canonical_score` |
| Child respects provider slot/circuit | NO TEST | No test covers the environment handoff |
| Codex/Claude/unknown-host fixtures emit correct flags | NO TEST | |
| Command/HTTP paths remain unchanged | tested | `tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_command_evaluator_is_bash`, `::test_http_evaluator_is_python`, `::test_objective_with_quotes_is_safe_in_command_script`, `::test_objective_with_quotes_is_safe_in_http_script` |

## Gaps

Each item lists the missing behavior for one `gap` or `partial` row.

- **Code** means a source change is required.
- **Test** means the behavior exists but no offline test covers it.

### R13 (gap): default API judge/composite scripts still embed LiteLLM

- **Code.** `evaluator_generator.py:45` routes only `backend != "api"` to `_generate_runtime_evaluator` (:657).
  - The default `api` judge template, `_generate_judge_evaluator` (:435), writes `from litellm import completion, validate_environment` (:452).
  - The composite template, `_generate_composite_evaluator` (:547), embeds the judge template (:558).
  - This violates R13, the U7 scenario "Generated wrappers contain no LiteLLM import" (plan:271), and design:93, :273 and :533 ("generated judge/composite wrappers contain no direct LiteLLM call").
- **Conflict (surfaced, not blended).** Two artifacts assert the opposite:
  - `evaluator-cookbook.md:408` ("With the default `--judge-backend api`, `judge` and `composite` scripts stay standalone LiteLLM scripts");
  - `tests/test_evaluator_generator.py::TestGenerateEvaluatorScript::test_default_is_judge` (:177).

  The plan, the design and this playbook's Task 2 all count the embedded import as an R13 violation, and the plan and design are the source of truth, so they win. Update the cookbook paragraph and `test_default_is_judge` in the same fix.
- **R5 is preserved by the fix path.** `evaluator_runtime._resolve_backend` (:16-29) already defaults to `backend="api"` and builds a `LiteLLMBackend` through `create_backend`. Routing `api` scripts through the runtime therefore keeps LiteLLM as the transport.

### R1 / R2 (partial): subscription judge, analysis, score and validation roles are untested offline

- **Test.** No offline test sends these roles through a Codex or Claude backend:
  - `cli_tools._completion_backend` (:365), used by `_cmd_score` (:150) and `_cmd_analyze` (:278);
  - `_cmd_validate` (:203), with `_validate_provider` (:310) and `_parse_validation_provider` (:356);
  - `llm_judge_evaluator(backend=...)` (`llm_judge.py:94`) and `analyze_for_dimensions` (:325).
- Every `tests/test_llm_judge.py` unit case patches `litellm.completion`.
- This also leaves these U6 scenarios untested: "structured judge/analysis/score", "mixed role backends" and "validation provider mix".

### R3 (partial)

- **Test.** Three behaviors are untested:
  - that Codex symlinks (does not copy) `auth.json` into the private `CODEX_HOME`;
  - that Codex refuses a missing or symlinked `auth.json` (`codex_backend.py:121-124`);
  - the Claude `loggedIn: false` path (`claude_backend.py:235`).
- Neither adapter invokes a login command, but no test pins that.

### R4 (partial)

- **Code.**
  - `create_backend` returns API-backend roles unwrapped (`factory.py:62-63`), so they never reach `events.jsonl` or `summary["llm_provenance"]` (`cli_optimize.py:142`). API judge provenance survives only in the per-candidate `side_info` (`llm_judge.py:154`).
  - The API proposer passes the model string to GEPA (`cli_optimize.py:243`, `reflection_lm` :331) and produces no `CompletionResult`. design:255 requires a callable backed by `LiteLLMBackend`, plus regression tests showing that GEPA's proposal behavior is unchanged (R5).
  - `call_id` is whitelisted in `_EVENT_KEYS` (`coordination.py:25`), but no caller passes it to `completion_event` (`provenance.py:29-30`).
  - `aggregate_provenance` (`provenance.py:43`) and `cache_fingerprint` (:63) are exported from `llm_backends/__init__.py:29` but have no production caller, so no run cache key includes the backend route.
- **Test.** No test covers the U6 scenario "every role contributes provenance".

### R6 (partial)

- **Test.** No offline test covers:
  - parsing of `--proposer-backend`, `--judge-backend`, `--analysis-backend`, `--subscription-concurrency`, `--no-api-fallback`, `--openai-api-fallback-model` or `--anthropic-api-fallback-model`;
  - CLI-over-TOML precedence (`_apply_spec_to_args`, `cli_optimize.py:496`);
  - command/HTTP evaluators rejecting a judge backend (`cli.py:521-527`, `_resolve_judge_evaluator_source` :628);
  - reserved selectors parsing before model strings (design:319; `cli_tools._parse_validation_provider` :356);
  - a custom `--api-base` reaching the fallback `LiteLLMBackend` without being printed (the backend plan logs only `custom_api_base: bool`, `cli_optimize.py:263`).
- **Code (diagnostic).** A spec containing both `proposer = "..."` and `[model.proposer]` fails inside `tomllib` with `Cannot overwrite a value (at line 3, column 13)`, which names neither key.
  - This misses the U2 scenario "scalar/table conflicts name keys" and design:529 ("conflict diagnostics").
  - For the same reason, "table overrides legacy scalar" cannot be expressed in a single file.
- **Not counted as a gap.** TOML has no concurrency key. design:305 and :321-338 define concurrency as a CLI option only.

### R7 (partial)

- **Test.** No host fixture checks that:
  - Codex-hosted command and skill text passes `--*-backend codex`;
  - Claude-hosted text passes `claude`;
  - an unknown host passes no backend flag (U7 scenario).
- `tests/test_prompt_plugin_contract.py` checks only doc terms; `tests/test_plugin_regression.py` checks only model and budget.
- Core non-inference holds on inspection, but no test pins it.

### R8 (partial)

- **Test.** Four isolation checks are missing:
  - `const` sentinel values in the user schema are not checked against argv (U5 scenario); only property names and enum values are.
  - The Codex `_MAX_PROMPT_BYTES`/`_MAX_OUTPUT_BYTES` caps (`codex_backend.py:36-37`) are untested.
  - Only `features.shell_tool=false` among `_ISOLATION_OVERRIDES` (:38) is asserted.
  - No test checks that prompts stay out of logs (U4 scenario).

### R9 (partial)

- **Test.** Three behaviors are untested:
  - The end-to-end child handoff has no test (U7 scenario "child respects provider slot/circuit"). The sequence is:
    1. `exported_environment` (`coordination.py:123`) sets `OPTIMIZE_ANYTHING_COORDINATION_DIR`/`_ID`.
    2. The generated evaluator child runs `create_backend`, then `RunCoordinator.from_environment` (`factory.py:66`, `coordination.py:110`).
    3. The child's slot and circuit match the parent's.
  - The capacity-override warning in `RunCoordinator.create` (:77) is not asserted.
  - There is no crashed-child test (U3 scenario "crashed child cannot poison a new run"). fcntl locks are released on process exit by design, but nothing proves it.

### R10 (partial)

- **Test.** These preflight rejections are untested:
  - `apiProvider != "firstParty"`, i.e. cloud auth (U5 scenario "API/cloud auth rejected");
  - `loggedIn: false`;
  - a missing executable, a version below 2.1.278, and missing required flags (U5 scenario "missing/old CLI remediation").
- Nonzero-exit and error-result mapping in `complete` are also untested (U5 scenario "output/exit/error mapping").
- **Note.** The preflight deliberately leaves `--safe-mode` out of the `--help` check (`claude_backend.py:224-225`; the code comment says the flag is "hidden from some --help versions"). A CLI without safe mode therefore fails only at the first completion, when it rejects the flag, rather than at preflight.

### R11 (partial)

- **Test.** Only the version-mismatch branch of `CodexSdkBackend._module` (`codex_backend.py:99-108`) is tested. Untested:
  - missing `Codex`/`CodexConfig`/`Sandbox`/`ApprovalMode`;
  - missing `Sandbox.read_only` or `ApprovalMode.deny_all`;
  - the `_sdk` missing-extra remediation (`:65`, U4 scenario).
- Only the failure path of structured output through Codex is tested; success has no test (U4 scenario "schema success").

### R12 (partial)

- **Test.** Four fallback checks are missing:
  - `Cancelled` and `ConfigurationError` are absent from the no-fallback parametrize (`tests/test_llm_fallback.py:58`), though R12 names both.
  - The tests exercise only `BackendUnavailable` and `AuthenticationError` as eligible errors; `RateLimitError` and `QuotaExceeded` never appear.
  - The warning-before-dispatch order is not proven. `test_fallback_is_same_vendor_sticky_per_role_and_warns_before_api` reads stderr only after the call returns.
  - Every fallback test injects `fallback_ready=lambda: True` (`tests/test_llm_fallback.py:46`, :63, :73, :84, :98, :126). The real `fallback_ready` (`fallback.py:33-38`) and the not-ready path are never tested, despite the name `test_no_fallback_to_other_vendor_or_without_readiness`.

## Preserved Phase-05 record

> Phase-05 (CI and Definition of Done) ran before this Phase-01 audit and wrote the sections below into this file. They are kept verbatim, one heading level lower.
> - Its "Deferred Items: None" is superseded by the Gaps section above.
> - Its test counts come from the Phase-05 run. The offline gates are re-run under "Offline Gate Results" (Phase-01 Tasks 3-5).
> - Its original front-matter link was `[[Subscription-Live-Evidence-2026-09-26]]`.

### CI

#### Final CI Run
- **Repository**: ASRagab/optimize-anything
- **Branch**: feat/codex-claude-subscription
- **Run ID**: 35814308325
- **URL**: [GitHub Actions CI Run](https://github.com/ASRagab/optimize-anything/actions/runs/35814308325)
- **Status**: ✅ PASS
- **Jobs**:
  - pytest (not integration) + smoke harness + score_check: **PASS**
  - Judge matrix job: **PASS**
- **Timestamp**: 2026-09-23T03:26:40Z

### Definition of Done

#### Code Review Findings
- ✅ No abandoned experimental code found
- ✅ No commented-out debug blocks found
- ✅ No `print` debugging statements in llm_backends
- ✅ No TODO/FIXME comments left in llm_backends
- ✅ All imports are used
- ✅ No environment variable bypasses of isolation/auth checks
- ✅ Exception handling correct: Timeout/Cancelled/InvalidResponse/ConfigurationError do NOT reach fallback path
  - Fallback only catches: BackendUnavailable, AuthenticationError, RateLimitError, QuotaExceeded

#### Deferred Items
None. All Definition of Done items verified as complete.

### Test Results Summary

All local pre-push contract checks passed:
- ✅ `uv sync` — environment resolution successful
- ✅ `uv run pytest -m "not integration"` — 443 tests passed, 18 deselected
- ✅ `uv run python scripts/check.py --skip-smoke` — 447 passed, 14 skipped
- ✅ `uv run python scripts/smoke_harness.py --budget 1` — PASS
- ✅ `uv run python scripts/score_check.py` — all gates passed
- ✅ `uv run pre-commit run --all-files` — TruffleHog PASS
- ✅ `git status` — clean (no uncommitted changes)
