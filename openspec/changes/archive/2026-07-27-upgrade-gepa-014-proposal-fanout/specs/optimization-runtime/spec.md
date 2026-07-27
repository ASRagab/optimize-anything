## MODIFIED Requirements

### Requirement: Optimizer dependencies are security constrained
The project SHALL require GEPA `0.1.4` or later within the compatible `0.1` release line and SHALL require a LiteLLM version in GEPA's supported range that excludes the compromised `1.82.7` and `1.82.8` releases.

#### Scenario: Dependency metadata selects supported versions
- **WHEN** project dependency metadata is inspected
- **THEN** GEPA allows `0.1.4`
- **AND** GEPA excludes `0.2.0`
- **AND** LiteLLM requires at least `1.83.0`
- **AND** LiteLLM excludes `1.82.7` and `1.82.8`
- **AND** LiteLLM excludes `1.92.0` and later versions

#### Scenario: Lockfile resolves the target release
- **WHEN** the project lockfile is inspected after the upgrade
- **THEN** the locked GEPA version is `0.1.4`
- **AND** the locked LiteLLM version is at least `1.83.0` and less than `1.92.0`
- **AND** the locked LiteLLM version is not `1.82.7` or `1.82.8`

## ADDED Requirements

### Requirement: Optimize avoids unused best-output retention
The `optimize-anything optimize` command SHALL disable GEPA best-validation-output retention while the wrapper does not expose or consume those outputs.

#### Scenario: Runtime configuration preserves bounded output memory
- **WHEN** an optimization runtime configuration is built
- **THEN** the GEPA engine configuration uses `track_best_outputs = false`

### Requirement: Optimize supports proposal fan-out
The `optimize-anything optimize` command SHALL support an optional positive `--proposals-per-iteration N` value that controls how many mutations GEPA attempts from the selected parent in each iteration.

#### Scenario: Default run keeps classic proposal behavior
- **WHEN** a user runs optimization without `--proposals-per-iteration` and without a proposal count in the spec file
- **THEN** GEPA uses its default single-mutation sampling strategy
- **AND** one proposal is attempted per iteration

#### Scenario: User opts into multiple proposals
- **WHEN** a user runs optimization with `--proposals-per-iteration 4`
- **THEN** the GEPA engine uses `SameParentSampling` with `n = 4`
- **AND** GEPA's default proposal selection strategy remains unchanged

#### Scenario: Explicit one preserves the default strategy
- **WHEN** a user runs optimization with `--proposals-per-iteration 1`
- **THEN** GEPA uses its default single-mutation sampling strategy

### Requirement: Proposal count is validated
The command and spec loader SHALL reject proposal counts that are not positive integers.

#### Scenario: CLI proposal count is invalid
- **WHEN** a user passes `--proposals-per-iteration 0`
- **THEN** the command exits with an error that identifies the positive-integer requirement

#### Scenario: Spec proposal count is invalid
- **WHEN** a TOML spec contains `proposals_per_iteration = 0`
- **THEN** spec loading fails with an error that identifies `optimization.proposals_per_iteration`

### Requirement: Spec files configure proposal fan-out
Optimization spec files SHALL configure proposal fan-out when the CLI does not provide a proposal count, and an explicit CLI value SHALL take precedence.

#### Scenario: Spec enables proposal fan-out
- **WHEN** a spec file contains `proposals_per_iteration = 3`
- **AND** the user does not pass `--proposals-per-iteration`
- **THEN** the GEPA engine uses `SameParentSampling` with `n = 3`

#### Scenario: CLI proposal count overrides the spec
- **WHEN** a spec file contains `proposals_per_iteration = 3`
- **AND** the user passes `--proposals-per-iteration 2`
- **THEN** the GEPA engine uses `SameParentSampling` with `n = 2`

### Requirement: Documentation distinguishes proposal fan-out from evaluator parallelism
User-facing optimization documentation, including the packaged optimization guide, SHALL distinguish proposal count from evaluator worker count and SHALL explain the cost and budget implications of proposal fan-out.

#### Scenario: User evaluates proposal fan-out
- **WHEN** a user reads optimize command documentation
- **THEN** the documentation explains that `--proposals-per-iteration` increases candidate mutations per iteration
- **AND** the documentation explains that `--workers` controls concurrent evaluator calls
- **AND** the documentation warns that proposal fan-out increases reflection and evaluation work
- **AND** the documentation warns that the final iteration can overshoot the metric-call budget

#### Scenario: Agent follows the packaged optimization guide
- **WHEN** an agent uses the packaged optimization guide for a GEPA 0.1.4 run
- **THEN** the guide explains the default single proposal and opt-in `SameParentSampling` fan-out behavior
- **AND** direct `EngineConfig` examples disable `track_best_outputs`
- **AND** the guide does not present the metric-call budget as a hard upper bound
- **AND** the guide warns that state written by GEPA 0.1.4 is not expected to load under GEPA 0.1.1
