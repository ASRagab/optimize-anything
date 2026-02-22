# Optimize Anything — Claude Code–first Design (v0)

## Goal
Ship a Claude Code–first optimizer that improves text artifacts via propose → evaluate → reflect loops, with **bring‑your‑own evaluator** only in v0. Deliver as a Claude Code plugin that auto-starts a local MCP stdio server and provides a skill that teaches evaluator requirements and safe usage.

## Non‑Goals (v0)
- Built‑in evaluators (LLM judge, lint, tests)
- Async MCP status/stop tools
- Multi‑task or generalization modes
- Persistent run storage

## Architecture
- **optimizer‑core** library implementing propose → evaluate → reflect.
- **CLI** wrapper for local runs.
- **MCP stdio server** exposing `optimize` tool (sync in v0).
- **Claude Code plugin** that bundles:
  - `.mcp.json` to auto-start the stdio server via `${CLAUDE_PLUGIN_ROOT}`
  - `skills/optimize-anything/SKILL.md` documenting evaluator contract, safety, and usage

## Components
### 1) optimizer‑core
- **Proposer**: LLM mutation of current best; inputs: best candidate, history summary, ASI, constraints.
- **Evaluator runner** (BYO only):
  - **command**: runs shell command; pipes candidate to stdin; expects JSON `{score, diagnostics?}`.
  - **http**: POST `{candidate}`; expects JSON `{score, diagnostics?}`.
- **Reflector**: LLM summarizing score deltas + diagnostics into ASI.
- **Budget + state**: iteration/time/token caps; best tracking; history with diff.
- **Constraints**: optional banned regex + max size/diff limit.

### 2) CLI
- Thin wrapper around core.
- Accepts `seed_candidate` or `objective` plus evaluator config.
- Writes best candidate + run report to disk.

### 3) MCP stdio server
- Single tool `optimize` in v0 (sync).
- No SSE transport (deprecated for Claude Code); stdio only for local v0.

### 4) Claude Code plugin
- `.claude-plugin/plugin.json` minimal metadata.
- `.mcp.json` to auto‑start stdio server.
- `skills/optimize-anything/SKILL.md` describing evaluator contract and safety.
- Optional `commands/optimize.md` to scaffold evaluator template (v1).

## Data Flow
1. **Request intake**: CLI/MCP receives seed/objective + evaluator + optional constraints/budgets.
2. **Initialize**: generate baseline (if objective) → evaluate baseline.
3. **Loop**:
   - propose candidate
   - constraint checks (regex + size/diff limit)
   - evaluate candidate → score + diagnostics
   - reflect → ASI
   - update best + history
   - budget check
4. **Return**: `OptimizeResult` with best candidate + trace.

## Error Handling & Safety
- **Evaluator errors**: non‑zero exit / invalid JSON / HTTP error → record diagnostics; score=0 or candidate rejected.
- **Timeouts**: evaluator timeout → ASI diagnostic; continue.
- **Constraints**: failing constraint discards candidate without evaluation.
- **Security**: evaluator commands run with user permissions; document sandboxing guidance in SKILL.md.
- **Determinism**: advise fixed seeds; v1 may support repeat/average.

## Testing
- **Unit**: evaluator runner (command/http), constraint checks, budget tracking.
- **Integration**: CLI end‑to‑end with deterministic evaluator.
- **MCP**: tool schema + stdio round‑trip.

## Packaging (Claude Code)
- Plugin structure:
  - `.claude-plugin/plugin.json`
  - `.mcp.json`
  - `skills/optimize-anything/SKILL.md`
  - `servers/optimize-anything` (stdio entrypoint)
- Use `${CLAUDE_PLUGIN_ROOT}` for all paths.

## Open Questions (v1+)
- Async optimization status/stop
- Built‑in evaluators
- Multi‑task/generalization modes
- Persistence + run visualization
