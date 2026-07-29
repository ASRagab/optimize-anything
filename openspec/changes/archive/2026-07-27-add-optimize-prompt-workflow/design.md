## Context

`optimize-anything` already has the required optimization engine and contracts: `analyze` discovers rubric dimensions and emits intake JSON; `optimize` accepts built-in, command, or HTTP evaluators plus datasets and validation sets; `compare` and `validate` provide post-run evidence; run directories preserve the seed, best artifact, summary, and diff. The repository also ships a valid Claude Code plugin and shared `skills/`, but it has no Codex plugin manifest and its plugin commands assume a global `optimize-anything` executable even though the installation guide presents plugin and CLI installation as independent.

The built-in LLM judge scores the candidate prompt text. It does not execute that prompt on a target model and score the resulting task output. Prior evaluation evidence in the user's knowledge base reinforces that deterministic output or tool-contract evidence must outrank a surface text judge when the product behavior can be executed.

This change crosses skill instructions, evaluator assets, plugin packaging, installation documentation, and validation gates. It must remain additive and must preserve the current Python API, CLI subcommands, evaluator Protocol v2, and GEPA runtime behavior.

## Goals / Non-Goals

**Goals:**

- Provide one explicit `optimize-prompt` workflow for inline prompts, prompt files, embedded prompt regions, and independent prompt batches.
- Reuse existing analysis, intake, optimization, comparison, validation, persistence, and result contracts.
- Make fast prompt polish and rigorous task-output optimization distinct and honestly reported.
- Keep repository sources unchanged until a candidate passes the selected acceptance contract.
- Distribute one canonical skill implementation to Claude Code and Codex with a bundled runtime launcher.
- Leave deterministic offline checks behind for routing, evaluator behavior, safe application, launcher resolution, manifests, and version alignment.

**Non-Goals:**

- Add a new optimization algorithm, public Python API, or `optimize-anything prompt` CLI subcommand.
- Add an MCP server, daemon, prompt registry, hosted evaluation service, or credential broker.
- Provide a universal adapter for every possible prompt templating framework in the first release.
- Silently optimize coupled multi-component prompt systems as independent files.
- Prove downstream task improvement when only prompt-text evaluation was run.

## Decisions

### 1. Compose the existing CLI from one orchestration skill

The canonical workflow will live in `skills/optimize-prompt/`. It will route inputs, establish the evaluation contract, create temporary artifacts, invoke existing subcommands through the bundled launcher, compare evidence, and return or apply the accepted result.

This is preferred over a new CLI subcommand because the missing behavior is agent orchestration: understanding conversation text, finding embedded prompt regions, choosing when to ask for rubric details, and applying a targeted code edit. The existing CLI already owns deterministic runtime behavior. It is preferred over MCP because no remote data or long-running tool process is required.

### 2. Use one skill tree with native manifests for each host

The existing `.claude-plugin/` package remains the Claude Code distribution. A minimal `.codex-plugin/plugin.json` will point to `./skills/`, and `.agents/plugins/marketplace.json` will provide a repository marketplace entry. Host-specific command files may remain Claude-only, but workflow logic and evaluator resources must remain under the canonical skill directory.

This is preferred over a second repository or copied Codex skill because one source avoids drift in evaluator contracts, installation guidance, and releases.

### 3. Launch the bundled Python project instead of requiring a global CLI

A small self-locating launcher will resolve the installed plugin root and execute the existing project with `uv run --project <root> --locked optimize-anything`. The skill and every packaged command that invokes the CLI will route through this launcher. The standalone global CLI installer remains available for direct terminal users but is not a plugin prerequisite.

This is preferred over plugin installation hooks because both hosts can load skills and files without guaranteeing arbitrary package-install lifecycle scripts. It also avoids adding another executable implementation.

### 4. Keep fast and rigorous evaluation as separate contracts

Fast mode will compose `analyze`, intake normalization, and the existing built-in judge. It is the default when the user asks for a quick polish or supplies no representative examples. Its result will explicitly state that it measures prompt-text quality.

Rigorous mode will create a run-specific command evaluator from a bundled prompt-execution template. The evaluator will place the candidate in the declared prompt role, map the dataset example into the task input, call the target model, and judge the task output against expected behavior, criteria, and hard constraints. The common default adapter will support a system prompt plus `example.input`; examples may also provide expected output or criteria. Other prompt shapes require an explicit adapter created by the skill.

The evaluator continues using Protocol v2 (`candidate`, `example`, `task_model`) and returns the existing numeric score plus diagnostics. No runtime protocol extension is needed.

### 5. Treat prompt content and model output as untrusted evaluator data

Judge prompts will clearly delimit the candidate, example, and produced output and state that embedded instructions cannot change the evaluator rubric or JSON contract. Deterministic gates run before subjective judging when placeholders, schemas, syntax, token ceilings, or repository tests define hard constraints. Target or judge failures yield a non-accepting score and stage-specific diagnostics.

This does not make an LLM judge a security boundary; it limits accidental evaluator capture and makes hard checks authoritative.

### 6. Use temporary output and targeted application

Every workflow captures the baseline and runs optimization into a temporary directory or normal run directory. It compares baseline and candidate using identical evaluator configuration. Repository application occurs only after acceptance:

- Inline prompt: return the complete candidate in the conversation.
- Standalone file: replace file contents only when requested and accepted.
- Embedded prompt: use the host's normal editing tools to replace the recorded region while preserving delimiters, indentation, syntax, and unrelated code.
- Independent batch: run one acceptance decision per file.
- Coupled components: require an explicit structured-candidate path; never silently treat them as independent.

After a repository edit, run the cheapest relevant parse, schema, import, targeted test, lint, or type check. A failed check triggers repair or restoration of the original prompt region before completion.

### 7. Verification is layered and cost-aware

Offline tests will cover skill contracts, evaluator preflight/failure behavior, prompt injection resistance at the instruction-contract level, deterministic hard gates, launcher root resolution, manifest structure, and version alignment. A deterministic fake evaluator will cover end-to-end temporary output and safe application without provider calls.

Credentialed Claude and Codex host runs remain explicit release checks because they spend provider budget. The live regression will use bounded budgets and persist results, but the ordinary unified offline gate will not require secrets or network access.

## Risks / Trade-offs

- [Fast mode can improve wording while task behavior regresses] → Label its evidence boundary, require rigorous mode for performance claims, and never collapse the two result types.
- [A task-output evaluator can overfit or be gamed] → Support held-out validation, preserve diagnostics, prioritize deterministic contract checks, and reject train-only gains that fail validation.
- [Candidate prompts can influence an LLM judge] → Delimit untrusted content, keep rubric instructions authoritative, use hard gates, and allow cross-provider validation for important prompts.
- [Embedded prompt replacement can damage source syntax] → Record the exact region, optimize outside the source file, apply only after acceptance, and run the containing project's cheapest relevant check.
- [Plugin paths differ by host and installation source] → Use a launcher that resolves its own location and add local plus installed-plugin tests for both manifests.
- [First use may download Python dependencies] → Keep `uv` and Python prerequisites explicit, use the lockfile, and return actionable setup errors.
- [Rigorous mode costs more and can hit rate limits] → Require explicit target/judge models and budgets, reuse current worker controls, and keep fast mode available for low-cost iteration.

## Migration Plan

1. Add offline contract tests for the new skill, evaluator template, launcher, Codex metadata, and release-version alignment.
2. Add the canonical skill, bundled evaluator assets, and launcher without changing existing runtime APIs.
3. Route packaged Claude command instructions through the launcher and update installation documentation.
4. Add Codex plugin and marketplace metadata, then validate local discovery in a new Codex session.
5. Run the unified offline gate, Claude strict manifest validation, Codex package validation, and bounded live host regressions when credentials are explicitly available.
6. Release all active metadata at one aligned version.

Rollback is additive: remove the new skill, launcher, and Codex metadata; restore existing Claude command text and installation guidance; retain the unchanged Python CLI/runtime. Generated optimization run directories remain diagnostic artifacts and are not migration state.

## Open Questions

- No blocking design questions. The first implementation may choose the exact Codex marketplace display metadata and live-regression model names from current host documentation and available credentials without changing the capability contracts.
