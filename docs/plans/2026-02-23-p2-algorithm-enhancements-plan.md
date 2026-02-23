# optimize-anything P2 Implementation Plan: Algorithm Enhancements and Performance Modes

> Date: 2026-02-23
> Priority: P2 (starts only after P0 and P1 completion)
> Goal: Improve optimization quality/throughput with controlled, test-gated algorithm enhancements.

## Why P2 Exists

P0 and P1 focus on reliability and UX. P2 improves optimization performance and decision quality without sacrificing determinism, debuggability, or test reliability.

## Scope

### In Scope
- Adaptive minibatch strategy
- Richer reflection schema and bounded history usage
- Optional parallel evaluator mode with safe fallback

### Out of Scope
- Full population-based genetic operators
- Distributed execution
- Non-deterministic stochastic search modes by default

## Deliverables

1. Adaptive minibatch selector with explicit strategy config
2. Structured reflection object used by proposer context
3. Parallel evaluation mode guarded by config and deterministic ordering

## Constraints

- Maintain deterministic behavior when seed is fixed
- Keep `src/core/*.ts` files <= 300 lines
- Preserve existing API by default; new behavior behind options
- No type-safety bypasses

## Workstreams

## WS1 - Adaptive Minibatch Strategy

### Task P2.1 - Extend engine config

**Files**:
- `src/types.ts`

**Changes**:
- Add minibatch strategy options under engine/reflection config:
  - `minibatchStrategy?: "fixed" | "adaptive" | "hard_first"`
  - `minibatchSize?: number`
  - `minibatchMax?: number`

**Acceptance Criteria**:
- Backward-compatible defaults preserve current behavior

### Task P2.2 - Implement adaptive selector

**Files**:
- `src/core/candidate-selector.ts`
- `src/core/evaluate.ts`

**Changes**:
- Add adaptive selection function considering:
  - iteration stage
  - metric budget remaining
  - frontier stagnation signal (`lastFrontierChangeIteration`)
- Implement hard-first heuristic based on historical low-scoring examples when available

**Acceptance Criteria**:
- Deterministic output for same seed/config
- Graceful fallback to fixed strategy

### Task P2.3 - Minibatch tests

**Files**:
- `tests/candidate-selector.test.ts`
- `tests/optimizer.test.ts`

**Changes**:
- Add tests for adaptive growth behavior
- Add tests for determinism under fixed seed
- Add tests for hard-first strategy selection

**Acceptance Criteria**:
- Strategy behaviors covered and stable

## WS2 - Reflection Schema Upgrade

### Task P2.4 - Introduce structured reflection format

**Files**:
- `src/types.ts`
- `src/core/reflector.ts`
- `src/core/proposer.ts`
- `src/core/optimizer.ts`

**Changes**:
- Define reflection shape, e.g.:
  - `wins: string[]`
  - `failures: string[]`
  - `next_actions: string[]`
  - `confidence: number`
- Parse/normalize model reflection output with safe fallback
- Bound reflection payload size before injecting into proposer prompt

**Acceptance Criteria**:
- Reflection is structured and bounded
- Reflection failure does not crash loop

### Task P2.5 - Reflection tests

**Files**:
- `tests/optimizer.test.ts`
- `tests/proposer.test.ts`

**Changes**:
- Verify structured fields flow into proposer context
- Verify truncation/size bounds
- Verify fallback on malformed reflection output

**Acceptance Criteria**:
- Stable behavior across malformed/empty reflection outputs

## WS3 - Optional Parallel Evaluator Mode

### Task P2.6 - Parallel evaluate path

**Files**:
- `src/core/evaluate.ts`
- `src/types.ts`

**Changes**:
- Implement optional parallel execution over minibatch when enabled
- Preserve deterministic score map ordering and aggregation
- Enforce per-eval timeout/cancellation propagation

**Acceptance Criteria**:
- Parallel mode disabled by default
- Sequential and parallel modes produce equivalent scores (modulo timing)

### Task P2.7 - Parallel mode tests + benchmark smoke

**Files**:
- `tests/evaluate.test.ts` (new or update)
- `tests/optimizer.test.ts`

**Changes**:
- Validate equivalence of sequential vs parallel outputs on deterministic evaluator
- Validate timeout/cancellation handling in parallel mode
- Add lightweight timing smoke comparison (non-flaky)

**Acceptance Criteria**:
- No flaky timing assertions
- Deterministic correctness preserved

## Validation Gates

### Gate P2-A (Correctness)
```bash
bun test --grep "adaptive"
bun test --grep "reflection"
bun test --grep "parallel"
```

### Gate P2-B (Full Regression)
```bash
bun test
bun run typecheck
bun build src/cli/index.ts --outdir dist
```

### Gate P2-C (File Size and Determinism)
```bash
wc -l src/core/*.ts
bun test --grep "deterministic"
```

PASS: all gates pass with no core file > 300 lines.

## Risks and Mitigations

- Risk: Adaptive heuristics reduce reproducibility.
  - Mitigation: Seed-bound deterministic heuristics and tests.
- Risk: Parallel mode introduces race/order nondeterminism.
  - Mitigation: stable collection order and explicit aggregation ordering.
- Risk: Reflection schema parsing brittleness.
  - Mitigation: schema normalization with robust fallback.

## Execution Order

1. WS1 complete and gated
2. WS2 complete and gated
3. WS3 complete and gated
4. Full regression and release readiness pass

## Exit Criteria

- Adaptive strategy improves coverage without destabilizing determinism.
- Reflection is structured and usable for iterative improvements.
- Optional parallel mode provides throughput gains with preserved correctness.
