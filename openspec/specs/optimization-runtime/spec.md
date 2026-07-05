## Requirements

### Requirement: Optimizer dependencies are security constrained
The project SHALL require GEPA `0.1.1` or later within the compatible `0.1` release line and SHALL require a LiteLLM version newer than the compromised `1.82.7` and `1.82.8` releases.

#### Scenario: Dependency metadata excludes compromised LiteLLM versions
- **WHEN** project dependency metadata is inspected
- **THEN** GEPA allows `0.1.1`
- **AND** LiteLLM requires at least `1.83.0`
- **AND** LiteLLM excludes `1.82.7` and `1.82.8`

#### Scenario: Lockfile resolves to safe versions
- **WHEN** the project lockfile is inspected after the upgrade
- **THEN** the locked GEPA version is `0.1.1`
- **AND** the locked LiteLLM version is not `1.82.7` or `1.82.8`
- **AND** the locked LiteLLM version is at least `1.83.0`

### Requirement: Optimize runs in parallel by default
The `optimize-anything optimize` command SHALL configure GEPA evaluation to run in parallel when the user does not provide an explicit concurrency override.

#### Scenario: Default optimize run is parallel
- **WHEN** a user runs `optimize-anything optimize` without `--parallel`, `--no-parallel`, or `--workers`
- **THEN** the GEPA engine configuration uses `parallel = true`
- **AND** GEPA may use its default worker count

### Requirement: Optimize accepts explicit parallel mode
The `optimize-anything optimize` command SHALL continue accepting `--parallel` as an explicit request for parallel evaluation.

#### Scenario: Existing parallel flag still works
- **WHEN** a user runs `optimize-anything optimize --parallel`
- **THEN** the GEPA engine configuration uses `parallel = true`

### Requirement: Optimize supports serial opt-out
The `optimize-anything optimize` command SHALL provide `--no-parallel` to disable parallel evaluator calls.

#### Scenario: User disables parallel execution
- **WHEN** a user runs `optimize-anything optimize --no-parallel`
- **THEN** the GEPA engine configuration uses `parallel = false`
- **AND** no explicit worker count is passed to GEPA

### Requirement: Worker count implies parallel execution
The `optimize-anything optimize` command SHALL treat `--workers N` as a request for parallel evaluation with a bounded worker count.

#### Scenario: User sets worker count
- **WHEN** a user runs `optimize-anything optimize --workers 4`
- **THEN** the GEPA engine configuration uses `parallel = true`
- **AND** the GEPA engine configuration uses `max_workers = 4`

### Requirement: Conflicting concurrency options are rejected
The `optimize-anything optimize` command SHALL reject configurations that disable parallelism while also specifying a worker count.

#### Scenario: CLI flags conflict
- **WHEN** a user runs `optimize-anything optimize --no-parallel --workers 4`
- **THEN** the command exits with an error
- **AND** the error explains that `--workers` requires parallel execution

#### Scenario: Spec file values conflict
- **WHEN** a spec file contains `parallel = false` and `workers = 4`
- **THEN** the command exits with an error
- **AND** the error explains that workers require parallel execution

### Requirement: Spec files can configure concurrency
Optimization spec files SHALL be able to enable or disable parallel execution when no CLI concurrency flag overrides the spec value.

#### Scenario: Spec file disables parallel execution
- **WHEN** a spec file contains `parallel = false`
- **AND** the user does not pass `--parallel`, `--no-parallel`, or `--workers`
- **THEN** the GEPA engine configuration uses `parallel = false`

#### Scenario: CLI concurrency flag overrides spec file
- **WHEN** a spec file contains `parallel = false`
- **AND** the user runs `optimize-anything optimize --parallel --spec-file <file>`
- **THEN** the GEPA engine configuration uses `parallel = true`

### Requirement: Documentation describes concurrency expectations
User-facing documentation SHALL explain that optimization runs evaluator calls in parallel by default and SHALL document when to use `--no-parallel`.

#### Scenario: User needs serial evaluator execution
- **WHEN** a user reads optimize command documentation
- **THEN** the documentation describes `--no-parallel`
- **AND** the documentation warns that evaluators with shared files, process-global state, or strict provider rate limits may need serial execution
