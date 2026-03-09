# Changelog

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
