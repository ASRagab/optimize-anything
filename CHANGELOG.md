# Changelog

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
