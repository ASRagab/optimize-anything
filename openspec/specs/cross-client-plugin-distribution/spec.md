## Purpose

Define shared packaging, runtime, installation, release, and verification contracts for distributing the prompt workflow to Claude Code and Codex.

## Requirements

### Requirement: One shared skill source serves Claude Code and Codex
The repository SHALL maintain one canonical `skills/` source tree for the prompt workflow and SHALL package that tree for both the existing Claude Code plugin and a Codex skills-only plugin without duplicating skill instructions or evaluator assets.

#### Scenario: Claude Code discovers the skill
- **WHEN** the repository is installed through its Claude Code marketplace
- **THEN** Claude Code discovers the canonical `optimize-prompt` skill and its bundled resources
- **AND** existing plugin commands remain available

#### Scenario: Codex discovers the skill
- **WHEN** the repository is installed as a Codex plugin
- **THEN** the Codex manifest points to the canonical `skills/` tree
- **AND** Codex discovers `optimize-prompt` as an invokable skill

### Requirement: Host manifests use native plugin contracts
The repository SHALL retain valid Claude Code plugin and marketplace manifests and SHALL add a valid `.codex-plugin/plugin.json` manifest plus a Codex repository marketplace entry suitable for local and Git-backed installation.

#### Scenario: Claude manifest is validated
- **WHEN** the Claude plugin validator runs in strict mode against the repository
- **THEN** the plugin and marketplace manifests pass without errors or warnings treated as errors

#### Scenario: Codex manifest is validated
- **WHEN** the Codex plugin package is inspected or installed
- **THEN** its manifest declares a stable kebab-case name, aligned version, description, and `./skills/` path
- **AND** its marketplace source resolves to the repository plugin root

### Requirement: Plugin invocation includes the optimization runtime
An installed plugin SHALL be able to run the bundled `optimize-anything` project without requiring a separately installed global `optimize-anything` executable. The launcher SHALL resolve the plugin root from its own installed location and use the repository's locked Python project.

#### Scenario: Global CLI is absent
- **WHEN** a plugin user invokes the prompt workflow on a host with `uv` and supported Python but no global `optimize-anything` command
- **THEN** the workflow invokes the bundled project through the canonical launcher
- **AND** the optimization CLI starts successfully

#### Scenario: Runtime prerequisite is missing
- **WHEN** `uv`, a supported Python interpreter, or required model credentials are unavailable
- **THEN** the launcher or workflow fails with an actionable prerequisite message
- **AND** does not modify the source prompt

#### Scenario: Existing plugin command invokes the CLI
- **WHEN** a packaged Claude command needs an `optimize-anything` subcommand
- **THEN** its instructions route execution through the canonical bundled launcher
- **AND** do not assume a global executable is installed

### Requirement: Installation guidance distinguishes host and runtime concerns
User-facing documentation SHALL provide verified Claude Code and Codex installation, invocation, update, and removal instructions while explaining the shared runtime prerequisites and the optional standalone global CLI installation.

#### Scenario: Claude user follows installation guidance
- **WHEN** a Claude Code user follows the documented marketplace flow
- **THEN** the plugin skill and commands are discoverable
- **AND** the prompt workflow can launch the bundled runtime

#### Scenario: Codex user follows installation guidance
- **WHEN** a Codex user follows the documented local or Git-backed marketplace flow
- **THEN** the plugin and `optimize-prompt` skill are discoverable in a new session
- **AND** the prompt workflow can launch the bundled runtime

#### Scenario: User wants only the standalone CLI
- **WHEN** a user chooses the existing CLI installer instead of either plugin
- **THEN** the documentation preserves that installation path
- **AND** does not imply that plugin metadata or skills are installed with the CLI

### Requirement: Release versions remain aligned
Release metadata SHALL keep the Python package, Claude plugin manifest, active Claude marketplace version fields, and Codex plugin manifest on the same release version. The Codex repository marketplace entry identifies the plugin source and has no version field.

#### Scenario: Release contract test runs
- **WHEN** release metadata tests inspect all package and plugin manifests
- **THEN** every active version field in the Python package and plugin manifests has the same value
- **AND** the Codex marketplace source resolves to the repository plugin root
- **AND** a version mismatch fails the test with the differing sources identified

### Requirement: Distribution has offline and optional live verification
The repository SHALL provide offline contract checks for both plugin packages and SHALL retain optional live host scenarios for confirming skill discovery, runtime launch, inline prompt return, and repository prompt application.

#### Scenario: Offline gate runs without provider credentials
- **WHEN** the unified offline gate runs
- **THEN** it validates skill frontmatter, bundled resource paths, launcher behavior with a deterministic evaluator, manifest structure, and release-version alignment
- **AND** it does not require paid model calls

#### Scenario: Live plugin regression is requested
- **WHEN** a maintainer explicitly runs the credentialed plugin regression gate
- **THEN** the gate exercises the supported host workflow within its configured spend limit
- **AND** records whether the optimized result was returned or applied as expected
