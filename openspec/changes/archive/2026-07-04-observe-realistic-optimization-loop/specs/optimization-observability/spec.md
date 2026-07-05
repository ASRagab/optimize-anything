## ADDED Requirements

### Requirement: Realistic optimization benchmark
The system SHALL provide a repeatable benchmark for optimizing a useful text artifact that maintainers would plausibly accept into the project.

#### Scenario: Benchmark uses a project-relevant artifact
- **WHEN** a maintainer runs the benchmark setup
- **THEN** the seed artifact is project-relevant documentation or guidance, not a toy length or marketing example
- **AND** the benchmark states the optimization objective and acceptance constraints

#### Scenario: Benchmark can run without changing the source artifact
- **WHEN** a maintainer runs the benchmark
- **THEN** the optimization uses a copied seed or explicit output path
- **AND** the tracked source artifact is not overwritten unless the maintainer separately accepts the result

### Requirement: Training scorer emits actionable diagnostics
The system SHALL include a deterministic training scorer for the benchmark that returns a numeric score plus diagnostic fields useful to the optimizer.

#### Scenario: Scorer returns optimizer-compatible JSON
- **WHEN** the scorer receives an evaluator payload containing `candidate`
- **THEN** it returns a JSON object with a finite numeric `score`
- **AND** the score is valid for the configured score range

#### Scenario: Scorer reports improvement dimensions
- **WHEN** the scorer evaluates a candidate
- **THEN** the JSON response includes dimension scores or feedback fields that identify why the candidate scored as it did
- **AND** those diagnostics are specific enough to guide a subsequent reflection step

### Requirement: Observation report summarizes loop behavior
The system SHALL produce an observation report for a benchmark run that summarizes whether the optimization loop explored candidates and improved the artifact.

#### Scenario: Report includes core loop telemetry
- **WHEN** a benchmark run completes
- **THEN** the report includes the initial score, best score, score delta, candidate count, total metric calls, top diagnostics, diff summary, and run directory

#### Scenario: Report references persisted artifacts
- **WHEN** a benchmark run writes a run directory
- **THEN** the report identifies where to find the seed, best artifact, summary JSON, and relevant optimizer runtime artifacts

### Requirement: Ineffective optimization signals
The system SHALL flag runs that do not provide credible evidence of optimization effectiveness.

#### Scenario: Seed-only run is flagged
- **WHEN** the optimization evaluates only the seed candidate
- **THEN** the report marks the run as ineffective
- **AND** it recommends checking model configuration, budget, evaluator behavior, or API credentials

#### Scenario: Flat or trivial improvement is flagged
- **WHEN** the best score does not exceed the initial score by the configured meaningful improvement threshold
- **THEN** the report marks the improvement as insufficient
- **AND** it surfaces scorer diagnostics or next-step guidance for improving the evaluator or objective

### Requirement: Held-out validation evidence
The system SHALL support held-out validation of the optimized artifact so benchmark acceptance is not based only on the training scorer.

#### Scenario: Held-out validation runs after optimization
- **WHEN** a benchmark run produces a best artifact
- **THEN** maintainers can score that artifact with a held-out rubric, scorer, or multi-provider judge
- **AND** the validation output records whether the optimized artifact passes the acceptance threshold

#### Scenario: Validation detects scorer gaming
- **WHEN** the training scorer improves but held-out validation fails or regresses
- **THEN** the report marks the result as not accepted
- **AND** it preserves enough evidence to inspect the discrepancy

### Requirement: Documented acceptance workflow
The system SHALL document how to run the realistic benchmark, inspect the observation report, validate the result, and accept or reject an optimized artifact.

#### Scenario: Maintainer follows benchmark documentation
- **WHEN** a maintainer reads the documentation for optimization effectiveness verification
- **THEN** it provides concrete commands, expected outputs, acceptance criteria, and troubleshooting guidance
- **AND** it distinguishes benchmark evidence from source changes that should be reviewed separately
