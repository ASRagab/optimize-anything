# Changelog

## v0.5.0 - 2026-07-28

### Model defaults
- Updated the default proposer model to `openai/gpt-5.6-sol`
- Updated the default evaluator model to `openai/gpt-5.6-luna`
- Centralized project-owned model defaults across the CLI, evaluator generation, judge flows, and operational scripts
- Preserved proposer precedence as explicit CLI model, then `OPTIMIZE_ANYTHING_MODEL`, then the project default

### Prompt optimization workflow
- Added the `optimize-prompt` skill for inline prompts, files, embedded prompt regions, and independent batches
- Separated fast prompt-quality scoring from rigorous task-output evaluation with deterministic hard gates and held-out acceptance
- Kept repository sources unchanged during search and limited accepted edits to the recorded prompt destination

### Plugin distribution
- Added a self-locating locked-runtime launcher used by every packaged Claude command
- Added native Codex plugin and marketplace metadata over the same canonical skill tree
- Aligned Python, Claude, and Codex release metadata at 0.5.0

### Provider compatibility
- Let providers apply their own sampling defaults unless a judge temperature is explicitly supplied
- Removed hard-coded sampling parameters from generated judge and composite evaluators

### Documentation and verification
- Modernized runnable examples, command guidance, protocol docs, skills, and integration tooling for current model identifiers
- Added drift coverage for model defaults, CLI help and resolution, generated evaluators, and judge request payloads
- Added offline launcher, evaluator, workflow-fixture, documentation, manifest, and release-version contracts
- Synchronized package, plugin, and marketplace release versions

## v0.4.0 - 2026-07-27

### New features
- Added opt-in `--proposals-per-iteration N` and `[optimization].proposals_per_iteration` controls backed by GEPA's `SameParentSampling`
- Kept proposal fan-out independent from evaluator concurrency controls and preserved one proposal per iteration by default

### Dependency compatibility
- Upgraded GEPA to `0.1.4` within the compatible `0.1` release line
- Constrained LiteLLM to GEPA's supported `>=1.83.0,<1.92` range while retaining compromised-version exclusions
- Disabled unused best-validation-output retention to preserve bounded output memory

### Documentation and skills
- Documented fan-out cost, repeated-minibatch behavior, final-iteration budget overshoot, and forward-only state migration
- Aligned the packaged optimization guide and added contract coverage for the GEPA 0.1.4 guidance
- Synchronized package, plugin, and marketplace release versions

### Verification
- Full offline project gate, dependency compatibility checks, documentation contracts, and strict OpenSpec validation pass

## v0.3.5 - 2026-03-20

### Structural refactor
- Extracted `cli.py` monolith (1,639 lines) into 4 focused modules:
  - `preflight.py` — evaluator preflight validation checks
  - `persist.py` — run-directory persistence, diff output, artifact writing
  - `cli_optimize.py` — optimize subcommand implementation
  - `cli_tools.py` — score, validate, analyze, explain, budget, intake, generate-evaluator subcommands
- `cli.py` reduced to ~500 lines: argparse dispatcher + shared utilities

### New features
- Added `budget_utilization` section to optimize output contract with `requested`, `evaluator_calls`, `candidates_accepted`, and `efficiency` fields for transparent budget tracking

### Verification
- All 307 unit tests pass
- Doc contract and score check gates pass
- No circular import issues with extracted modules

## v0.3.2 - 2026-03-09

### Improvements
- Reduced CLI complexity with semantic helper extraction across core optimize/validate flows
- Eliminated remaining mypy errors across the source tree
- Improved internal typing and separation of responsibilities in `cli.py`, `spec_loader.py`, `llm_judge.py`, `result_contract.py`, `intake.py`, `evaluator_generator.py`, `evaluators.py`, and `stop.py`
- Preserved public CLI help surfaces while making internal command orchestration easier to maintain

### Verification
- `pytest` passes
- `mypy` reports no issues in 11 source files
- CLI smoke checks pass for top-level, `optimize`, and `validate` help

## v0.3.0 - 2026-03-03

### New features
- Dataset / valset workflows for multi-task optimization and generalization checks
- Parallel execution controls
- Run/result caching
- Early-stop behavior for budget efficiency
- Seedless optimization mode support
- Score-range handling improvements
- Task-model support
- `validate` command for multi-provider scoring checks
- `quick` and `compare` commands
- `evaluator-patterns` skill with ready-to-run evaluator templates

### Breaking changes
- Default generator behavior changed to judge-first flow
- Protocol v2 adds optional keys to evaluator/result payloads

### Migration notes
- Existing evaluators continue to work
- To preserve older generator-style behavior, use `--evaluator-type command`
