# optimize-anything P1 Implementation Plan: Product UX, Progress Visibility, and Explainability

> Date: 2026-02-23
> Priority: P1 (starts only after P0 exits clean)
> Goal: Improve runtime UX and trust without changing core optimization contracts.

## Why P1 Exists

After P0, users can install and run reliably. P1 improves the day-to-day experience: visibility into long-running optimizations, understandable outcomes, and safer budget recommendations.

## Scope

### In Scope
- Progress/status surfacing for MCP users
- Explainability output for optimization outcomes
- Dynamic budget helper (advisory, not mandatory)

### Out of Scope
- Core selection/evaluation algorithm changes
- Parallel execution engine internals
- Adaptive minibatch logic

## Deliverables

1. MCP-visible progress lifecycle for long runs
2. New explanation capability (why best candidate won)
3. Budget recommendation helper
4. UX docs for each feature + tests

## Constraints

- Must preserve existing `optimize` response shape
- New capabilities should be additive (new tool, optional params, or separate endpoint)
- No stdout protocol violations

## Design Decisions

1. Prefer additive APIs over mutating existing required inputs
2. Reuse existing event stream (`state.events`) as source of truth
3. Keep explanation deterministic from recorded run data where possible

## Workstreams

## WS1 - Progress Visibility

### Task P1.1 - Define progress model

**Files**:
- `src/types.ts`
- `src/mcp/schema.ts`
- `docs/mcp-protocol.md` (update)

**Changes**:
- Add a progress payload shape (phase, metric calls used, iteration index, frontier size)
- Decide delivery mode:
  - Option A: MCP progress notifications
  - Option B: periodic status callbacks serialized in result content

**Acceptance Criteria**:
- Progress schema is explicit and versioned
- Backwards compatibility with existing clients is maintained

### Task P1.2 - Implement progress emission in MCP layer

**Files**:
- `src/mcp/server.ts`

**Changes**:
- Map optimizer events to user-facing progress updates
- Ensure progress channel does not corrupt stdio protocol
- Add lightweight throttling to avoid event spam

**Acceptance Criteria**:
- Long runs show visible progress transitions
- Short runs produce minimal overhead

### Task P1.3 - Progress tests

**Files**:
- `tests/mcp.test.ts`

**Changes**:
- Add tests for progress update format and sequencing
- Add tests that progress does not alter final result payload contract

**Acceptance Criteria**:
- Tests assert both protocol correctness and user-visible status behavior

## WS2 - Explainability Surface

### Task P1.4 - Add explanation API/tool

**Files**:
- `src/mcp/schema.ts`
- `src/mcp/server.ts`
- `src/core/explain.ts` (new)
- `src/index.ts` (export)

**Changes**:
- Add `explain_optimization` capability that takes either run dir or result artifact
- Build summary from candidate deltas, score changes, sideInfo, and event timeline
- Return concise sections: wins, regressions, dominant factors, next actions

**Acceptance Criteria**:
- Explanation references concrete iteration/candidate evidence
- Handles missing partial data gracefully

### Task P1.5 - Explainability tests

**Files**:
- `tests/explain.test.ts` (new)
- `tests/mcp.test.ts` (update)

**Changes**:
- Verify deterministic explanation for deterministic run fixture
- Verify explanation degrades gracefully when sideInfo is sparse

**Acceptance Criteria**:
- Stable outputs for fixed fixture
- No crashes on partial input

## WS3 - Dynamic Budget Helper

### Task P1.6 - Add advisory budget utility

**Files**:
- `src/core/budget.ts` (new)
- `src/cli/index.ts`
- `src/mcp/schema.ts`
- `src/mcp/server.ts`

**Changes**:
- Implement `recommendBudget(input)` helper using simple, explainable heuristics:
  - dataset size
  - candidate complexity proxy
  - objective complexity hints
- Add CLI flag `--recommend-budget` mode or MCP helper tool

**Acceptance Criteria**:
- For same inputs, recommendation is deterministic
- Output includes rationale and confidence level

### Task P1.7 - Budget helper tests

**Files**:
- `tests/budget.test.ts` (new)
- `tests/cli.test.ts` (update)

**Changes**:
- Validate deterministic recommendations
- Validate boundary behavior (tiny/huge datasets)

**Acceptance Criteria**:
- No flaky tests
- Heuristic behavior documented and tested

## Validation Gates

### Gate P1-A
```bash
bun test --grep "progress"
bun test --grep "explain"
bun test --grep "budget"
```

### Gate P1-B
```bash
bun test
bun run typecheck
bun build src/cli/index.ts --outdir dist
```

### Gate P1-C (Contract Safety)
```bash
# Existing optimize MCP contract remains valid
bun test --grep "mcp"
```

PASS: all gates pass and no contract regressions.

## Risks and Mitigations

- Risk: Progress transport complexity leaks into protocol errors.
  - Mitigation: Keep emission adapter in MCP layer only; add protocol tests.
- Risk: Explain output becomes verbose and low-signal.
  - Mitigation: Fixed schema and length bounds.
- Risk: Budget helper over-promises accuracy.
  - Mitigation: Clearly label as advisory and include rationale.

## Execution Order

1. P1.1 -> P1.2 -> P1.3
2. P1.4 -> P1.5
3. P1.6 -> P1.7
4. Run all gates

## Exit Criteria

- User can see run progress in MCP client for longer jobs.
- User can ask "why did this win" and get evidence-based output.
- User can obtain a deterministic budget recommendation before launching a run.
