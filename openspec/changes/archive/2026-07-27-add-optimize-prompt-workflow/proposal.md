## Why

The repository already exposes the evaluator, optimization, comparison, and validation primitives needed to improve prompts, but users must manually assemble them and the current plugin distribution does not provide a complete Codex-and-Claude workflow. A dedicated prompt workflow can turn inline prompts and repository-owned prompt text into validated improvements without adding another optimization engine.

## What Changes

- Add an `optimize-prompt` skill that accepts prompt text from the conversation, standalone text files, prompt regions embedded in source files, or multiple independent prompt files.
- Guide users from objective and rubric construction through fast prompt-text evaluation or rigorous task-output evaluation using representative examples.
- Optimize into temporary artifacts, compare the baseline and candidate with the same evaluation contract, and either return the accepted prompt or apply only the targeted repository prompt region.
- Add a reusable prompt-execution evaluator pattern that runs candidate prompts against a target model before judging task outputs; retain the existing built-in judge as the clearly labeled fast-polish path.
- Distribute the shared skills and bundled runtime through both the existing Claude Code plugin and a Codex skills-only plugin, with one self-contained launcher and aligned installation guidance.
- Support independent multi-file optimization by default; require explicit structured-candidate handling for prompt components that must evolve together.

## Capabilities

### New Capabilities
- `prompt-optimization-workflow`: End-to-end prompt capture, rubric construction, evaluator selection, optimization, acceptance validation, result return, and safe repository application.
- `cross-client-plugin-distribution`: Shared Claude Code and Codex plugin packaging, runtime launch, installation, version alignment, and host-specific discovery validation.

### Modified Capabilities

None. The change composes the existing optimization runtime and observability contracts without changing their requirements.

## Impact

- Adds a packaged skill and prompt-execution evaluator support under `skills/`.
- Adds Codex plugin metadata while retaining `.claude-plugin/` and the existing Claude commands.
- Updates installation and user-facing workflow documentation so plugin users can invoke the bundled runtime without a separate global CLI install.
- Extends static contract tests, offline evaluator tests, and optional live plugin regression coverage for inline return and repository apply flows.
- Does not change the public Python optimization API, GEPA runtime behavior, evaluator protocol, or existing CLI subcommands.
