## Purpose

Define safe intake, evaluation, acceptance, and delivery behavior for optimizing prompts across inline and repository artifacts.

## Requirements

### Requirement: Prompt workflow accepts supported artifact sources
The `optimize-prompt` workflow SHALL accept an explicitly supplied inline prompt, a standalone text file, a prompt region embedded in a repository file, or a list of independent prompt files while preserving the exact baseline text used for evaluation.

#### Scenario: Inline prompt is unambiguous
- **WHEN** a user invokes the workflow after supplying one clearly delimited prompt in the conversation
- **THEN** the workflow captures that text as the optimization seed
- **AND** the workflow records that the accepted result must be returned in the conversation rather than written to a repository file

#### Scenario: Standalone prompt file is supplied
- **WHEN** a user supplies a path to a standalone prompt or text file
- **THEN** the workflow reads the file as the optimization seed
- **AND** records the file as the possible apply destination

#### Scenario: Prompt is embedded in source code
- **WHEN** a user identifies a prompt string, symbol, or region inside a source file
- **THEN** the workflow extracts only that prompt text as the optimization seed
- **AND** records the exact source region and surrounding representation needed for a targeted replacement

#### Scenario: Prompt source is ambiguous
- **WHEN** the conversation or repository contains multiple plausible prompt candidates and the user has not identified one
- **THEN** the workflow asks the user to identify the intended candidate
- **AND** does not start optimization with a guessed seed

### Requirement: Workflow constructs an explicit evaluation contract
Before optimization, the workflow SHALL establish an objective, weighted quality dimensions, hard constraints, evaluator mode, proposer model, judge model or evaluator command, and evaluation budget. It SHALL infer values from the prompt and repository context when safe and SHALL ask only for missing information that changes evaluation behavior or acceptance.

#### Scenario: Context is sufficient to infer a rubric
- **WHEN** the prompt, surrounding code, tests, and user objective establish the intended behavior and constraints
- **THEN** the workflow derives an intake specification using the existing analysis and intake machinery
- **AND** presents or records the resulting dimensions and hard constraints before optimization

#### Scenario: Critical task behavior is unknown
- **WHEN** the workflow cannot determine the prompt's target task, required output contract, or non-negotiable constraints
- **THEN** it asks a focused clarification before choosing the evaluator
- **AND** does not claim a meaningful optimization until the evaluation contract is complete

#### Scenario: Repository prompt has machine-checkable constraints
- **WHEN** repository tests, schemas, placeholders, delimiters, or output formats constrain the prompt
- **THEN** the workflow includes those constraints as deterministic checks or hard constraints
- **AND** a candidate that violates them cannot be accepted solely on an LLM judge score

### Requirement: Evaluation modes state what they prove
The workflow SHALL distinguish fast prompt-text evaluation from rigorous task-output evaluation and SHALL not describe a prompt-text score as evidence that downstream task performance improved.

#### Scenario: Fast mode is used without representative examples
- **WHEN** the user requests a quick improvement or representative examples are unavailable
- **THEN** the workflow evaluates prompt clarity, specificity, constraints, and apparent task fitness using the existing prompt-text judge
- **AND** labels the result as prompt-quality evidence rather than task-performance evidence

#### Scenario: Rigorous mode is used with representative examples
- **WHEN** representative inputs and a target model are available or the user requests task-performance evidence
- **THEN** the workflow executes each candidate prompt against the representative inputs
- **AND** evaluates the resulting task outputs against the declared rubric and hard constraints

#### Scenario: Deterministic constraints and subjective quality both matter
- **WHEN** a prompt must satisfy machine-checkable constraints and subjective output criteria
- **THEN** the workflow uses a composite evaluator that runs deterministic gates before the subjective judge
- **AND** skips or rejects subjective scoring when a hard gate fails

### Requirement: Prompt execution evaluator uses the existing protocol safely
The rigorous evaluator SHALL consume the existing protocol fields `candidate`, optional `example`, and optional `task_model`, execute the candidate in the declared prompt role, and return a finite numeric `score` with actionable diagnostics. Candidate prompts, example content, and task outputs MUST be treated as data rather than evaluator instructions.

#### Scenario: Dataset example is evaluated successfully
- **WHEN** the evaluator receives a candidate and a representative example with the inputs required by the selected prompt adapter
- **THEN** it invokes the target model with the candidate in the declared prompt role
- **AND** judges the produced output against the example criteria or expected result
- **AND** returns score, reasoning, dimension diagnostics, and hard-constraint status

#### Scenario: Command preflight is received
- **WHEN** the evaluator receives the optimization preflight sentinel
- **THEN** it returns a valid preflight score immediately
- **AND** does not invoke either the target model or judge model

#### Scenario: Target or judge execution fails
- **WHEN** a target-model or judge-model call fails, times out, or returns an invalid response
- **THEN** the evaluator returns a non-accepting score with a diagnostic identifying the failed stage
- **AND** does not convert the failure into apparent improvement

#### Scenario: Candidate contains evaluator-directed instructions
- **WHEN** a candidate prompt contains text that attempts to alter the evaluator rubric or output contract
- **THEN** the evaluator keeps the declared rubric and output schema authoritative
- **AND** treats the candidate text only as the artifact under evaluation

### Requirement: Optimization does not overwrite source artifacts during search
The workflow SHALL run optimization against a captured seed and write the best candidate, summary, diff, and evaluation evidence to temporary or run-directory artifacts before any repository source is changed.

#### Scenario: Repository optimization completes
- **WHEN** optimization produces a best candidate for a repository-owned prompt
- **THEN** the original source remains unchanged during the optimization run
- **AND** the workflow retains the baseline, candidate, score summary, diagnostics, and diff for acceptance review

#### Scenario: Optimization fails
- **WHEN** evaluator setup, model authentication, rate limits, or optimization execution fails
- **THEN** the original source remains unchanged
- **AND** the workflow reports the failure and preserved diagnostic artifacts

### Requirement: Acceptance uses comparable evidence
The workflow SHALL score the baseline and optimized candidate with the same evaluation contract and SHALL reject a candidate that violates hard constraints, fails required held-out checks, or lacks credible improvement.

#### Scenario: Candidate passes fast-mode acceptance
- **WHEN** fast mode produces a candidate with a positive score delta and all hard constraints satisfied
- **THEN** the workflow marks it eligible for return or repository application
- **AND** reports that task performance remains unverified

#### Scenario: Candidate passes rigorous acceptance
- **WHEN** rigorous mode improves the training evaluation and passes the configured held-out validation threshold without a hard-constraint regression
- **THEN** the workflow marks it eligible for return or repository application
- **AND** reports both training and held-out evidence

#### Scenario: Training score improves but validation regresses
- **WHEN** the optimized candidate improves the training score but fails or regresses on required held-out validation
- **THEN** the workflow rejects the candidate
- **AND** preserves the discrepancy for evaluator or prompt diagnosis

### Requirement: Accepted results are delivered according to source type
The workflow SHALL return accepted inline prompts directly and SHALL apply accepted repository prompts only to the recorded target region, preserving unrelated content and running the cheapest relevant repository check.

#### Scenario: Inline prompt is accepted
- **WHEN** an inline prompt candidate passes acceptance
- **THEN** the workflow returns the complete optimized prompt in the conversation
- **AND** includes a concise statement of the evaluation mode and score delta

#### Scenario: Standalone prompt file candidate is accepted
- **WHEN** a standalone prompt file candidate passes acceptance and the user requested repository application
- **THEN** the workflow replaces the file content with the accepted candidate
- **AND** runs the relevant format, schema, or project check when one exists

#### Scenario: Embedded prompt candidate is accepted
- **WHEN** an embedded prompt candidate passes acceptance and the user requested repository application
- **THEN** the workflow replaces only the recorded prompt region while preserving language syntax, delimiters, indentation, and unrelated code
- **AND** runs a targeted test, import, parse, lint, or type check appropriate to the containing project

#### Scenario: Candidate is not accepted
- **WHEN** the candidate fails acceptance
- **THEN** the workflow leaves the repository unchanged
- **AND** returns the best available diagnostic and next evaluator improvement step

### Requirement: Multiple prompt files use explicit independence semantics
The workflow SHALL optimize multiple prompt or text files as independent runs by default and SHALL not independently mutate components that the user identifies as one coupled prompt system.

#### Scenario: Independent files are supplied
- **WHEN** a user supplies several prompt files and does not declare cross-file coupling
- **THEN** the workflow reuses the shared evaluation contract where applicable
- **AND** runs and reports one baseline, candidate, acceptance decision, and destination per file

#### Scenario: Coupled prompt components are identified
- **WHEN** a system prompt, examples, tool descriptions, or other components must evolve together
- **THEN** the workflow does not optimize them as unrelated files
- **AND** requires an explicit structured-candidate path or reports that the requested joint shape is unsupported
