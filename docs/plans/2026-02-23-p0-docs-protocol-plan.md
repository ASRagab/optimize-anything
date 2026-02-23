# optimize-anything P0 Implementation Plan: Docs, Packaging UX, and MCP Protocol Reliability

> Date: 2026-02-23
> Priority: P0 (must land before P1/P2)
> Goal: Make onboarding and MCP operation reliable, explicit, and production-safe.

## Why P0 Exists

External comparison showed our core algorithm and test discipline are stronger than peer implementations, but user onboarding and operational docs are underpowered. The biggest reliability risk is MCP protocol hygiene in stdio mode (stdout must contain JSON-RPC only).

P0 closes those gaps first so later UX and algorithm work has a stable foundation.

## Scope

### In Scope
- User-facing documentation overhaul for setup and first success
- MCP protocol reliability guarantees (stdout/stderr separation and tests)
- Evaluator cookbook and runnable examples
- Install and verification workflow for CLI + MCP

### Out of Scope
- New optimization algorithm behavior
- Parallel evaluator execution
- Dynamic budget and adaptive minibatching
- Explainability tool APIs

## Deliverables

1. `README.md` rewritten as a full quickstart and reference entry point
2. `docs/install.md` with platform-specific MCP setup and verification
3. `docs/evaluator-cookbook.md` with shell and HTTP evaluator recipes
4. `docs/mcp-protocol.md` defining protocol hygiene and logging rules
5. `examples/` directory with working evaluator examples
6. Protocol hygiene tests for MCP stdio behavior

## Constraints

- Runtime/build remains Bun + TypeScript
- No breaking changes to existing `optimize` MCP tool contract
- No logging to stdout in MCP server path except JSON-RPC messages
- Existing tests keep passing

## Workstreams

## WS1 - README and Docs Foundation

### Task P0.1 - Rewrite `README.md`

**Files**:
- `README.md`

**Changes**:
- Add sections: Overview, Prerequisites, Quickstart (CLI + MCP), Evaluator contract summary, Config options, Troubleshooting, Links
- Include copy-paste command examples that match current CLI flags and MCP tool args
- Include short architecture map with links to `src/core/*`

**Acceptance Criteria**:
- New user can run a successful CLI optimization and MCP tool call in under 10 minutes
- Every command in README is valid for the current codebase

### Task P0.2 - Add install guide

**Files**:
- `docs/install.md` (new)

**Changes**:
- Document prerequisites: Bun version, API key, evaluator requirements
- Document MCP config locations and snippets
- Add verification checklist and expected outputs
- Add uninstall/rollback note for MCP config edits

**Acceptance Criteria**:
- Guide includes macOS/Linux/Windows config-path notes
- Guide includes failure-recovery steps for common setup errors

### Task P0.3 - Add evaluator cookbook

**Files**:
- `docs/evaluator-cookbook.md` (new)

**Changes**:
- Define evaluator input/output contract with concrete JSON examples
- Provide shell evaluator template and HTTP evaluator template
- Document timeout behavior and error handling recommendations
- Include testing commands for evaluator validation

**Acceptance Criteria**:
- Cookbook contains at least 2 full runnable examples
- Cookbook examples match `createCommandEvaluator` and `createHttpEvaluator` behavior

## WS2 - MCP Protocol Reliability

### Task P0.4 - Codify protocol hygiene policy

**Files**:
- `docs/mcp-protocol.md` (new)

**Changes**:
- Define non-negotiables:
  - stdout: JSON-RPC only
  - stderr: diagnostics/logs
  - notifications: no response payload
  - parse errors: valid JSON-RPC error envelope
- Define logging pattern and examples for future contributors

**Acceptance Criteria**:
- Policy is explicit, short, and enforceable
- References `src/mcp/server.ts` implementation behavior

### Task P0.5 - Add protocol regression tests

**Files**:
- `tests/mcp.test.ts` (update)

**Changes**:
- Add test ensuring no non-JSON output on stdout during request handling
- Add test verifying notifications are silently consumed
- Add test verifying parse errors and unknown methods remain standards-compliant

**Acceptance Criteria**:
- Tests fail if accidental `console.log`/plain text is introduced to stdout
- Existing MCP tests still pass

## WS3 - Examples and Packaging UX

### Task P0.6 - Add runnable examples

**Files**:
- `examples/README.md` (new)
- `examples/evaluators/echo-score.sh` (new)
- `examples/evaluators/http-evaluator.ts` (new)
- `examples/seeds/sample-seed.txt` (new)

**Changes**:
- Provide end-to-end CLI example against shell evaluator
- Provide local HTTP evaluator example and invocation command
- Document expected output artifacts (`runDir`, `result.json`)

**Acceptance Criteria**:
- Examples execute with documented commands
- Examples do not require hidden env/config beyond ANTHROPIC key

## Validation Gates

### Gate P0-A (Docs Completeness)
```bash
# Manual checklist gate
# - README has quickstart + troubleshooting + links
# - docs/install.md exists
# - docs/evaluator-cookbook.md exists
# - docs/mcp-protocol.md exists
```

### Gate P0-B (Behavioral Verification)
```bash
bun test
bun run typecheck
bun build src/cli/index.ts --outdir dist
```

### Gate P0-C (Examples Smoke)
```bash
# run shell example evaluator end-to-end
bash examples/evaluators/echo-score.sh <<< '{"candidate":"test"}'
```

PASS: all 3 gates pass. FAIL: any broken command/example or test failure.

## Risks and Mitigations

- Risk: Docs drift from code.
  - Mitigation: Every command in docs must be executed once before merge.
- Risk: Protocol hygiene regresses later.
  - Mitigation: Regression tests and policy doc in repo.
- Risk: Example scripts become stale.
  - Mitigation: Keep examples minimal and tied to tested fixtures.

## Execution Order

1. P0.4 and P0.5 first (protocol baseline locked)
2. P0.1, P0.2, P0.3 in parallel
3. P0.6 last, then run all gates

## Exit Criteria

- New contributor can install and run one CLI + one MCP flow without reading source code.
- Protocol reliability constraints are codified and test-enforced.
- All tests/typecheck/build pass after documentation and test additions.
