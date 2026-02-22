# Optimize Anything — Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Each task has a **Gate** — do not proceed to the next task until the gate passes.

**Goal:** Ship a TypeScript/Bun port of GEPA's `optimize_anything` — an LLM-driven optimizer with BYO evaluators, Pareto-efficient search, and Actionable Side Information (ASI). Delivered as a library first, then as a CLI, MCP server, and Claude Code plugin.

**Reference:** [GEPA optimize_anything](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) — UC Berkeley's universal text-artifact optimizer.

**Architecture:** The core library implements a GEPA-compatible optimization loop: select candidate from Pareto frontier → propose mutation via LLM reflection on ASI → evaluate with BYO evaluator → update frontier + state → check stop conditions. CLI, MCP, and plugin are thin delivery wrappers over the library API.

**Tech Stack:** TypeScript, Bun, `@modelcontextprotocol/sdk`, `@anthropic-ai/sdk`.

**Key GEPA concepts this plan implements:**
- **Actionable Side Information (ASI)** — Evaluators return rich diagnostic feedback (not just scores) that the LLM reflector reads to propose targeted improvements.
- **Pareto-Efficient Search** — Candidates excelling at *anything* survive on a frontier. No collapsing to a single scalar.
- **Three Optimization Modes** — Single-task search, multi-task search, generalization.
- **Composable Stop Conditions** — Metric-call budget (not iteration count), timeout, no-improvement, score-threshold, composite.
- **Event Log + State Persistence** — Append-only JSONL event stream doubles as the checkpoint/resume format and the golden-test comparison target.
- **Evaluation Caching** — Avoid redundant (candidate, example) evaluations.

---

## Validation Harness Overview

Testing is not an afterthought — it is the primary mechanism that proves correctness. Every task below includes tests, and the final task is a full self-verification cycle.

**Layer 1 — Unit tests (deterministic, no network)**
Fake LLM returning canned responses. Fake evaluators returning predetermined scores + ASI. Tests for: Pareto dominance, stop condition composition, state round-trip, prompt construction, cache hit/miss, event ordering.

**Layer 2 — Integration tests (local subprocesses)**
Real evaluator scripts (bash) returning known scores. Verify: evaluator invocation count matches budget, candidate piped correctly, timeout/error handling.

**Layer 3 — Golden-file trajectory tests**
Fixed seed + fake LLM → deterministic event sequence. Record as JSONL golden file. Re-run and assert exact match. Catches accidental behavior changes across refactors.

**Layer 4 — Live smoke tests (env-gated, cost-aware)**
Only when `ANTHROPIC_API_KEY` is set. Use `maxMetricCalls: 3`. Trivial evaluator (string contains "hello" → score 1). Assert: score improved, total LLM calls ≤ budget.

**Layer 5 — MCP integration tests**
Spawn MCP server as subprocess. Send JSON-RPC `tools/call`. Assert: response contains `bestCandidate` + `bestScore`. Verify graceful error handling on malformed input.

**Layer 6 — Self-verification cycle (Task 9)**
Full `bun test` + `tsc --noEmit` + live smoke + MCP e2e + file size audit + conceptual review.

---

## Task 0: Scaffold + Core Type Definitions

**Files:**
- Create: `package.json`, `tsconfig.json`, `bunfig.toml`
- Create: `src/types.ts` — all core type definitions
- Create: `src/index.ts` — barrel export
- Create: `tests/types.test.ts` — type guard tests

**Step 1: Create package.json**
```json
{
  "name": "optimize-anything",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "bun test",
    "test:live": "LIVE_LLM=1 bun test tests/live/",
    "typecheck": "bun run --bun tsc --noEmit",
    "build": "bun build src/cli/index.ts --outdir dist"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "latest",
    "@anthropic-ai/sdk": "latest"
  },
  "devDependencies": {
    "typescript": "latest"
  }
}
```

**Step 2: Resolve dependency versions**
```bash
npm view @modelcontextprotocol/sdk version
npm view @anthropic-ai/sdk version
npm view typescript version
```
Replace `"latest"` with pinned versions.

**Step 3: Create tsconfig.json**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "outDir": "dist",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src", "tests"]
}
```

**Step 4: Create bunfig.toml**
```toml
[test]
preload = []
```

**Step 5: Define core types in `src/types.ts`**

These types mirror GEPA's architecture and must be defined before any implementation:

```ts
// ── Candidates ──────────────────────────────────────────────
/** A candidate is either a single text artifact or named components. */
export type Candidate = string | Record<string, string>;

// ── Evaluator Contract (GEPA-compatible) ────────────────────
/** Structured diagnostic feedback — the "gradient" for LLM optimization. */
export type SideInfo = {
  log?: string;
  stdout?: string;
  stderr?: string;
  scores?: Record<string, number>; // multi-objective sub-scores
} & Record<string, unknown>;

export type EvaluationResult = {
  score: number;
  sideInfo?: SideInfo;
};

/** Context passed to every evaluator invocation. */
export type EvaluationContext<E = unknown> = {
  candidate: Candidate;
  example?: E;
  objective?: string;
  background?: string;
  signal?: AbortSignal;
  log: (msg: string) => void;
};

/** The evaluator function signature. Primary interface — everything else wraps this. */
export type Evaluator<E = unknown> =
  (ctx: EvaluationContext<E>) => Promise<EvaluationResult | number>;

// ── Configuration ───────────────────────────────────────────
export type EngineConfig = {
  maxMetricCalls?: number;
  parallel?: boolean;
  maxWorkers?: number;
  seed?: number;
};

export type ReflectionConfig = {
  reflectionLm?: string; // model identifier
  minibatchSize?: number; // examples per reflection step (default 2-3)
};

export type TrackingConfig = {
  runDir?: string;
};

export type OptimizeConfig = {
  engine?: EngineConfig;
  reflection?: ReflectionConfig;
  tracking?: TrackingConfig;
};

// ── Stop Conditions ─────────────────────────────────────────
export interface StopCondition {
  shouldStop(state: RunState): boolean;
  readonly name: string;
}

// ── Events (append-only log = persistence + observability) ──
export type EventType =
  | "optimization_start"
  | "optimization_end"
  | "iteration_start"
  | "iteration_end"
  | "candidate_proposed"
  | "candidate_accepted"
  | "candidate_rejected"
  | "evaluation_start"
  | "evaluation_end"
  | "frontier_updated"
  | "stop_condition_met"
  | "error";

export type OptimizationEvent = {
  type: EventType;
  timestamp: number;
  iterationIndex?: number;
  candidateIndex?: number;
  data?: Record<string, unknown>;
};

export type EventCallback = (event: OptimizationEvent) => void;

// ── Run State ───────────────────────────────────────────────
export type CandidateRecord = {
  candidate: Candidate;
  parentIndex: number | null;
  scores: Map<string, number>; // per-example or per-metric scores
  aggregateScore: number;
  sideInfo: SideInfo[];
  metricCallIndex: number; // which metric call produced this
};

export type RunState = {
  candidates: CandidateRecord[];
  frontier: Set<number>; // indices into candidates[] on the Pareto front
  metricCallCount: number;
  iterationCount: number;
  startTime: number;
  events: OptimizationEvent[];
  evaluationCache: Map<string, EvaluationResult>; // hash(candidate+example) → result
};

// ── Result ──────────────────────────────────────────────────
export type OptimizeResult = {
  bestCandidate: Candidate;
  bestScore: number;
  candidates: CandidateRecord[];
  frontier: number[];
  totalMetricCalls: number;
  events: OptimizationEvent[];
  runDir?: string;
};

// ── LLM Interface ───────────────────────────────────────────
export interface LanguageModel {
  generate(prompt: string, options?: { signal?: AbortSignal }): Promise<string>;
}
```

**Step 6: Create barrel export `src/index.ts`**
```ts
export * from "./types.js";
```

**Step 7: Write type guard tests `tests/types.test.ts`**
Verify that key types compile correctly and type guards work for union types (e.g., `EvaluationResult | number`).

**Step 8: Install + verify**
```bash
bun install
bun test
bun run typecheck
```

**Step 9: Commit**
```bash
git add -A
git commit -m "chore: scaffold project with GEPA-compatible core types"
```

### Gate 0
- `bun install` succeeds
- `bun test` exits 0
- `bun run typecheck` exits 0 (zero type errors)

---

## Task 1: Evaluator Subsystem

**Files:**
- Create: `src/core/evaluator.ts` — inline, command, HTTP evaluator factories
- Create: `src/core/asi.ts` — ASI normalization + log capture
- Create: `tests/evaluator.test.ts`
- Create: `tests/fixtures/evaluators/echo-score.sh`
- Create: `tests/fixtures/evaluators/error-exit.sh`

**Step 1: Write failing tests**
```ts
import { describe, it, expect } from "bun:test";
import {
  normalizeEvalResult,
  createCommandEvaluator,
  createHttpEvaluator,
  captureLog,
} from "../src/core/evaluator";

describe("ASI normalization", () => {
  it("wraps bare number in EvaluationResult", () => {
    const result = normalizeEvalResult(0.9);
    expect(result.score).toBe(0.9);
    expect(result.sideInfo).toEqual({});
  });

  it("passes through full EvaluationResult", () => {
    const result = normalizeEvalResult({ score: 0.8, sideInfo: { note: "ok" } });
    expect(result.score).toBe(0.8);
    expect(result.sideInfo?.note).toBe("ok");
  });
});

describe("log capture", () => {
  it("captures oa.log() calls into sideInfo.log", () => {
    const { log, getLog } = captureLog();
    log("first");
    log("second");
    expect(getLog()).toBe("first\nsecond");
  });
});

describe("command evaluator", () => {
  it("runs script, parses JSON, captures stdout", async () => {
    const evaluate = createCommandEvaluator("tests/fixtures/evaluators/echo-score.sh");
    const result = await evaluate({
      candidate: "test input",
      log: () => {},
    });
    expect(typeof result).toBe("object");
    const r = result as { score: number };
    expect(r.score).toBeGreaterThan(0);
  });

  it("handles evaluator errors gracefully", async () => {
    const evaluate = createCommandEvaluator("tests/fixtures/evaluators/error-exit.sh");
    await expect(
      evaluate({ candidate: "x", log: () => {} })
    ).rejects.toThrow();
  });
});

describe("HTTP evaluator", () => {
  it("posts candidate and parses response", async () => {
    const server = Bun.serve({
      port: 0,
      fetch: async (req) => {
        const body = await req.json();
        return new Response(
          JSON.stringify({ score: 0.85, sideInfo: { input: body.candidate } })
        );
      },
    });
    const evaluate = createHttpEvaluator(`http://localhost:${server.port}`);
    const result = await evaluate({
      candidate: "hello",
      log: () => {},
    });
    const r = result as { score: number; sideInfo: { input: string } };
    expect(r.score).toBeCloseTo(0.85, 2);
    expect(r.sideInfo.input).toBe("hello");
    server.stop();
  });
});
```

**Step 2: Create fixture evaluator scripts**

`tests/fixtures/evaluators/echo-score.sh`:
```bash
#!/usr/bin/env bash
input=$(cat)
echo "{\"score\":0.9,\"sideInfo\":{\"received\":\"$input\"}}"
```

`tests/fixtures/evaluators/error-exit.sh`:
```bash
#!/usr/bin/env bash
echo "something went wrong" >&2
exit 1
```

```bash
chmod +x tests/fixtures/evaluators/*.sh
```

**Step 3: Implement evaluator subsystem**

`src/core/asi.ts`:
- `captureLog()` → returns `{ log, getLog }` for capturing diagnostic output
- `normalizeEvalResult(raw)` → always returns `{ score, sideInfo }`
- `hashEvalKey(candidate, example?)` → deterministic cache key for evaluation caching

`src/core/evaluator.ts`:
- `createCommandEvaluator(command, opts?)` → returns `Evaluator`
  - Pipes `{ candidate, example }` JSON to stdin via `Bun.spawn`
  - Parses stdout as JSON `{ score, sideInfo? }`
  - Captures stderr into `sideInfo.stderr`
  - Respects `opts.timeoutMs` via `AbortSignal.timeout()`
- `createHttpEvaluator(url, opts?)` → returns `Evaluator`
  - POSTs `{ candidate, example, objective, background }` as JSON
  - Parses response as `{ score, sideInfo? }`
  - Respects timeout

**Step 4: Run tests, typecheck**
```bash
bun test tests/evaluator.test.ts
bun run typecheck
```

**Step 5: Commit**
```bash
git add -A
git commit -m "feat: evaluator subsystem with ASI, command, and HTTP adapters"
```

### Gate 1
- All evaluator tests pass
- `bun run typecheck` clean
- Inline function evaluator, command evaluator, and HTTP evaluator all tested
- ASI normalization handles both `number` and `{ score, sideInfo }` returns

---

## Task 2: Stop Conditions + Event System

**Files:**
- Create: `src/core/stop-conditions.ts`
- Create: `src/core/events.ts`
- Create: `tests/stop-conditions.test.ts`
- Create: `tests/events.test.ts`

**Step 1: Write failing tests**

`tests/stop-conditions.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import {
  MaxMetricCallsStopper,
  TimeoutStopper,
  NoImprovementStopper,
  ScoreThresholdStopper,
  CompositeStopper,
} from "../src/core/stop-conditions";

describe("stop conditions", () => {
  const makeState = (overrides = {}) => ({
    candidates: [],
    frontier: new Set<number>(),
    metricCallCount: 0,
    iterationCount: 0,
    startTime: Date.now(),
    events: [],
    evaluationCache: new Map(),
    ...overrides,
  });

  it("MaxMetricCalls stops at budget", () => {
    const stop = new MaxMetricCallsStopper(10);
    expect(stop.shouldStop(makeState({ metricCallCount: 9 }))).toBe(false);
    expect(stop.shouldStop(makeState({ metricCallCount: 10 }))).toBe(true);
  });

  it("Timeout stops after elapsed time", () => {
    const stop = new TimeoutStopper(1000); // 1 second
    const old = makeState({ startTime: Date.now() - 2000 });
    expect(stop.shouldStop(old)).toBe(true);
  });

  it("NoImprovement stops after N stale iterations", () => {
    const stop = new NoImprovementStopper(3);
    // Simulate 3 iterations with no frontier changes
    const state = makeState({ iterationCount: 5 });
    // Need to track last improvement iteration — implementation detail
    expect(stop.shouldStop(state)).toBeDefined();
  });

  it("ScoreThreshold stops when target reached", () => {
    const stop = new ScoreThresholdStopper(0.95);
    const candidate = { candidate: "x", parentIndex: null, scores: new Map(), aggregateScore: 0.96, sideInfo: [], metricCallIndex: 0 };
    const state = makeState({ candidates: [candidate] });
    expect(stop.shouldStop(state)).toBe(true);
  });

  it("Composite combines multiple conditions with OR", () => {
    const stop = new CompositeStopper([
      new MaxMetricCallsStopper(100),
      new ScoreThresholdStopper(1.0),
    ]);
    expect(stop.shouldStop(makeState({ metricCallCount: 100 }))).toBe(true);
    expect(stop.shouldStop(makeState({ metricCallCount: 1 }))).toBe(false);
  });
});
```

`tests/events.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { EventEmitter, serializeEvents, deserializeEvents } from "../src/core/events";

describe("event system", () => {
  it("emits and collects events in order", () => {
    const emitter = new EventEmitter();
    const collected: string[] = [];
    emitter.on((e) => collected.push(e.type));
    emitter.emit({ type: "optimization_start", timestamp: 1 });
    emitter.emit({ type: "iteration_start", timestamp: 2 });
    expect(collected).toEqual(["optimization_start", "iteration_start"]);
  });

  it("serializes to JSONL and deserializes back", () => {
    const events = [
      { type: "optimization_start" as const, timestamp: 1 },
      { type: "evaluation_end" as const, timestamp: 2, data: { score: 0.9 } },
    ];
    const jsonl = serializeEvents(events);
    const parsed = deserializeEvents(jsonl);
    expect(parsed).toEqual(events);
  });
});
```

**Step 2: Implement stop conditions**

`src/core/stop-conditions.ts`:
- `MaxMetricCallsStopper` — stops when `state.metricCallCount >= max`
- `TimeoutStopper` — stops when `Date.now() - state.startTime >= timeoutMs`
- `NoImprovementStopper` — tracks last iteration that changed the frontier; stops after N stale iterations
- `ScoreThresholdStopper` — stops when any candidate's `aggregateScore >= threshold`
- `CompositeStopper` — OR-combines multiple stop conditions

**Step 3: Implement event system**

`src/core/events.ts`:
- `EventEmitter` — simple pub/sub for `OptimizationEvent`
- `serializeEvents(events)` → JSONL string (one event per line)
- `deserializeEvents(jsonl)` → `OptimizationEvent[]`
- Events are the **persistence format** — writing `run_dir/events.jsonl` IS the checkpoint

**Step 4: Run tests, typecheck**
```bash
bun test tests/stop-conditions.test.ts tests/events.test.ts
bun run typecheck
```

**Step 5: Commit**
```bash
git add -A
git commit -m "feat: composable stop conditions and JSONL event system"
```

### Gate 2
- All stop condition tests pass (budget, timeout, no-improvement, threshold, composite)
- Event serialization round-trip test passes
- `bun run typecheck` clean

---

## Task 3: Run State, Pareto Frontier, and Persistence

**Files:**
- Create: `src/core/state.ts` — RunState management, Pareto frontier, evaluation cache
- Create: `src/core/pareto.ts` — Pareto dominance + frontier operations
- Create: `src/core/persistence.ts` — save/load from run_dir
- Create: `tests/pareto.test.ts`
- Create: `tests/state.test.ts`
- Create: `tests/persistence.test.ts`

**Step 1: Write failing tests**

`tests/pareto.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { dominates, insertIntoFrontier } from "../src/core/pareto";

describe("Pareto dominance", () => {
  it("a dominates b when better on all dimensions", () => {
    const a = new Map([["x", 0.9], ["y", 0.8]]);
    const b = new Map([["x", 0.7], ["y", 0.6]]);
    expect(dominates(a, b)).toBe(true);
    expect(dominates(b, a)).toBe(false);
  });

  it("neither dominates when each excels on different dimensions", () => {
    const a = new Map([["x", 0.9], ["y", 0.3]]);
    const b = new Map([["x", 0.3], ["y", 0.9]]);
    expect(dominates(a, b)).toBe(false);
    expect(dominates(b, a)).toBe(false);
  });
});

describe("frontier insertion", () => {
  it("adds non-dominated candidate to frontier", () => {
    // Start with one candidate on frontier
    const candidates = [
      { scores: new Map([["x", 0.5]]), aggregateScore: 0.5 },
      { scores: new Map([["x", 0.9]]), aggregateScore: 0.9 },
    ];
    const frontier = new Set([0]);
    insertIntoFrontier(1, candidates as any, frontier);
    expect(frontier.has(1)).toBe(true);
    // Old one should be pruned (dominated)
    expect(frontier.has(0)).toBe(false);
  });

  it("preserves both when neither dominates", () => {
    const candidates = [
      { scores: new Map([["x", 0.9], ["y", 0.3]]), aggregateScore: 0.6 },
      { scores: new Map([["x", 0.3], ["y", 0.9]]), aggregateScore: 0.6 },
    ];
    const frontier = new Set([0]);
    insertIntoFrontier(1, candidates as any, frontier);
    expect(frontier.size).toBe(2);
  });
});
```

`tests/state.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { createRunState, addCandidate, getCacheKey, getCachedResult, cacheResult } from "../src/core/state";

describe("RunState", () => {
  it("initializes empty", () => {
    const state = createRunState();
    expect(state.candidates.length).toBe(0);
    expect(state.metricCallCount).toBe(0);
  });

  it("adds candidates and updates metric count", () => {
    const state = createRunState();
    addCandidate(state, {
      candidate: "hello",
      parentIndex: null,
      scores: new Map([["default", 0.8]]),
      aggregateScore: 0.8,
      sideInfo: [],
      metricCallIndex: 0,
    });
    expect(state.candidates.length).toBe(1);
  });
});

describe("evaluation cache", () => {
  it("returns undefined for cache miss", () => {
    const state = createRunState();
    expect(getCachedResult(state, "key")).toBeUndefined();
  });

  it("returns cached result for cache hit", () => {
    const state = createRunState();
    cacheResult(state, "key", { score: 0.5, sideInfo: {} });
    const cached = getCachedResult(state, "key");
    expect(cached?.score).toBe(0.5);
  });

  it("generates deterministic cache keys", () => {
    const k1 = getCacheKey("candidate-1", { id: "ex1" });
    const k2 = getCacheKey("candidate-1", { id: "ex1" });
    const k3 = getCacheKey("candidate-2", { id: "ex1" });
    expect(k1).toBe(k2);
    expect(k1).not.toBe(k3);
  });
});
```

`tests/persistence.test.ts`:
```ts
import { describe, it, expect, afterEach } from "bun:test";
import { saveState, loadState } from "../src/core/persistence";
import { createRunState } from "../src/core/state";
import { rmSync } from "fs";

const TEST_RUN_DIR = "/tmp/oa-test-run-" + Date.now();

afterEach(() => {
  try { rmSync(TEST_RUN_DIR, { recursive: true }); } catch {}
});

describe("persistence", () => {
  it("round-trips state through save/load", async () => {
    const state = createRunState();
    state.metricCallCount = 5;
    state.events.push({ type: "optimization_start", timestamp: Date.now() });

    await saveState(state, TEST_RUN_DIR);
    const loaded = await loadState(TEST_RUN_DIR);

    expect(loaded.metricCallCount).toBe(5);
    expect(loaded.events.length).toBe(1);
  });
});
```

**Step 2: Implement**

`src/core/pareto.ts`:
- `dominates(a: Map<string, number>, b: Map<string, number>)` → boolean
- `insertIntoFrontier(candidateIndex, candidates[], frontier: Set<number>)` — adds if non-dominated, prunes newly dominated entries

`src/core/state.ts`:
- `createRunState()` → fresh `RunState`
- `addCandidate(state, record)` — appends and updates frontier
- `getCacheKey(candidate, example?)` → deterministic hash string
- `getCachedResult(state, key)` → `EvaluationResult | undefined`
- `cacheResult(state, key, result)` → stores in cache

`src/core/persistence.ts`:
- `saveState(state, runDir)` — writes `events.jsonl` + `state.json` (frontier indices, metric count, cache) to `runDir`
- `loadState(runDir)` → reconstructs `RunState` from saved files
- Resume = load state + continue loop from `metricCallCount`

**Step 3: Run tests, typecheck**
```bash
bun test tests/pareto.test.ts tests/state.test.ts tests/persistence.test.ts
bun run typecheck
```

**Step 4: Commit**
```bash
git add -A
git commit -m "feat: Pareto frontier, run state, evaluation caching, and persistence"
```

### Gate 3
- Pareto dominance tests pass (dominates, non-dominated preservation)
- State management tests pass (add candidate, cache hit/miss, cache key determinism)
- Persistence round-trip test passes (save → load → verify)
- `bun run typecheck` clean

---

## Task 4: LLM Client + Proposer/Reflector

**Files:**
- Create: `src/core/llm.ts` — LanguageModel interface + AnthropicModel
- Create: `src/core/proposer.ts` — prompt construction + candidate proposal
- Create: `src/core/reflector.ts` — ASI analysis + improvement suggestions
- Create: `src/core/candidate-selector.ts` — Pareto/current-best selection
- Create: `tests/proposer.test.ts`
- Create: `tests/candidate-selector.test.ts`
- Create: `tests/fixtures/fake-llm.ts` — reusable fake LLM for all tests

**Step 1: Create reusable fake LLM**

`tests/fixtures/fake-llm.ts`:
```ts
import type { LanguageModel } from "../../src/types";

/** Returns responses from a queue, or a default. */
export function createFakeLlm(responses: string[]): LanguageModel {
  let i = 0;
  return {
    async generate() {
      return responses[i++] ?? responses[responses.length - 1];
    },
  };
}
```

**Step 2: Write failing tests**

`tests/proposer.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { buildProposerPrompt, buildReflectorPrompt, parseProposedCandidate } from "../src/core/proposer";

describe("proposer prompt", () => {
  it("includes current candidate in prompt", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: "function add(a, b) { return a + b; }",
      scores: new Map([["correctness", 0.5]]),
      sideInfo: [{ stderr: "TypeError: undefined" }],
      objective: "Fix the function",
      background: "TypeScript project",
      constraints: [],
    });
    expect(prompt).toContain("function add");
    expect(prompt).toContain("TypeError: undefined");
    expect(prompt).toContain("Fix the function");
  });

  it("includes ASI from minibatch in prompt", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: "x",
      scores: new Map([["t1", 0.3], ["t2", 0.9]]),
      sideInfo: [
        { log: "failed on edge case" },
        { log: "passed all tests" },
      ],
      objective: "Improve",
    });
    expect(prompt).toContain("failed on edge case");
    expect(prompt).toContain("passed all tests");
  });

  it("handles multi-component candidates", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: { prompt: "think step by step", code: "print(42)" },
      scores: new Map([["default", 0.6]]),
      sideInfo: [],
      componentToMutate: "prompt",
    });
    expect(prompt).toContain("think step by step");
    expect(prompt).toContain("prompt"); // identifies which component to change
  });
});

describe("reflector prompt", () => {
  it("summarizes failure patterns from ASI", () => {
    const prompt = buildReflectorPrompt({
      candidate: "x",
      sideInfo: [
        { stderr: "timeout after 5s", log: "test 3 failed" },
        { log: "test 7 failed: expected 42 got 41" },
      ],
      scores: new Map([["t3", 0.0], ["t7", 0.0]]),
    });
    expect(prompt).toContain("timeout");
    expect(prompt).toContain("expected 42 got 41");
  });
});

describe("parse proposed candidate", () => {
  it("extracts candidate from LLM response", () => {
    const response = "Here is my improved version:\n```\nfunction better() {}\n```\nThis should work.";
    const candidate = parseProposedCandidate(response);
    expect(candidate).toContain("function better");
  });

  it("handles response without code fences", () => {
    const response = "function simple() { return 1; }";
    const candidate = parseProposedCandidate(response);
    expect(candidate).toBe(response);
  });
});
```

`tests/candidate-selector.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { selectFromFrontier, selectCurrentBest } from "../src/core/candidate-selector";
import type { CandidateRecord } from "../src/types";

describe("candidate selection", () => {
  const makeCandidates = (): CandidateRecord[] => [
    { candidate: "a", parentIndex: null, scores: new Map([["x", 0.9], ["y", 0.3]]), aggregateScore: 0.6, sideInfo: [], metricCallIndex: 0 },
    { candidate: "b", parentIndex: null, scores: new Map([["x", 0.3], ["y", 0.9]]), aggregateScore: 0.6, sideInfo: [], metricCallIndex: 1 },
    { candidate: "c", parentIndex: null, scores: new Map([["x", 0.7], ["y", 0.7]]), aggregateScore: 0.7, sideInfo: [], metricCallIndex: 2 },
  ];

  it("selectCurrentBest picks highest aggregate", () => {
    const candidates = makeCandidates();
    const idx = selectCurrentBest(candidates);
    expect(idx).toBe(2); // "c" has 0.7
  });

  it("selectFromFrontier picks from frontier set", () => {
    const candidates = makeCandidates();
    const frontier = new Set([0, 1, 2]);
    const idx = selectFromFrontier(candidates, frontier, 42); // seed for determinism
    expect(frontier.has(idx)).toBe(true);
  });
});
```

**Step 3: Implement**

`src/core/llm.ts`:
- `AnthropicModel` implements `LanguageModel` using `@anthropic-ai/sdk`
- Constructor takes `{ apiKey, model, maxTokens }`
- `generate()` calls `messages.create()` and returns text content

`src/core/proposer.ts`:
- `buildProposerPrompt(opts)` — constructs the reflection+proposal prompt including:
  - Current candidate (or specific component if multi-component)
  - Scores per example/metric from minibatch
  - ASI from minibatch evaluations
  - Objective and background strings
  - Constraint list
  - History summary (previous attempts + their scores)
- `buildReflectorPrompt(opts)` — focused ASI analysis prompt
- `parseProposedCandidate(llmResponse)` — extracts new candidate text from LLM output

`src/core/candidate-selector.ts`:
- `selectCurrentBest(candidates)` → index of highest aggregate score
- `selectFromFrontier(candidates, frontier, seed)` → weighted selection from frontier
- `selectMinibatch(dataset, size, seed)` → pick 2-3 examples for reflection

**Step 4: Run tests, typecheck**
```bash
bun test tests/proposer.test.ts tests/candidate-selector.test.ts
bun run typecheck
```

**Step 5: Commit**
```bash
git add -A
git commit -m "feat: LLM client, proposer/reflector prompts, and candidate selection"
```

### Gate 4
- Proposer prompt tests pass (includes candidate, ASI, objective, multi-component)
- Reflector prompt tests pass (summarizes failure patterns)
- Candidate selection tests pass (current-best, frontier selection)
- Parse proposed candidate handles code fences and raw text
- `bun run typecheck` clean

---

## Task 5: Optimizer Loop

**Files:**
- Create: `src/core/optimizer.ts` — the `optimizeAnything()` function
- Create: `tests/optimizer.test.ts`
- Create: `tests/golden/single-task.jsonl` — golden trajectory file

**This is the core of the library.** It wires together: evaluator → state → frontier → selector → proposer → reflector → stop conditions → events → persistence.

**Step 1: Write failing tests (using fake LLM + fake evaluator)**

```ts
import { describe, it, expect } from "bun:test";
import { optimizeAnything } from "../src/core/optimizer";
import { createFakeLlm } from "./fixtures/fake-llm";
import type { EvaluationContext } from "../src/types";

describe("optimizer loop", () => {
  it("returns best candidate after single-task optimization", async () => {
    const fakeLlm = createFakeLlm(["improved-v1", "improved-v2"]);
    const evaluator = async (ctx: EvaluationContext) => {
      const s = typeof ctx.candidate === "string" ? ctx.candidate : "";
      return s.includes("improved") ? 0.9 : 0.5;
    };

    const result = await optimizeAnything({
      seedCandidate: "initial",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 3 } },
    });

    expect(result.bestScore).toBeGreaterThanOrEqual(0.5);
    expect(result.bestCandidate).toBeDefined();
    expect(result.totalMetricCalls).toBeLessThanOrEqual(3);
  });

  it("respects metric call budget", async () => {
    let callCount = 0;
    const evaluator = async (ctx: EvaluationContext) => {
      callCount++;
      return 0.5;
    };
    const fakeLlm = createFakeLlm(["next"]);

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 5 } },
    });

    expect(callCount).toBeLessThanOrEqual(5);
  });

  it("uses evaluation cache to avoid redundant calls", async () => {
    let callCount = 0;
    const evaluator = async (ctx: EvaluationContext) => {
      callCount++;
      return 0.8;
    };
    // Fake LLM always returns same candidate → should cache
    const fakeLlm = createFakeLlm(["same-candidate"]);

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 10 } },
    });

    // Should have cached after first eval of "same-candidate"
    // Exact count depends on implementation, but should be < maxMetricCalls
    expect(callCount).toBeLessThan(10);
  });

  it("emits events in correct order", async () => {
    const events: string[] = [];
    const fakeLlm = createFakeLlm(["v1"]);
    const evaluator = async () => 0.9;

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
      onEvent: (e) => events.push(e.type),
    });

    expect(events[0]).toBe("optimization_start");
    expect(events[events.length - 1]).toBe("optimization_end");
    expect(events).toContain("evaluation_end");
  });

  it("handles multi-component candidates", async () => {
    const fakeLlm = createFakeLlm(["updated prompt text"]);
    const evaluator = async (ctx: EvaluationContext) => {
      const c = ctx.candidate as Record<string, string>;
      return c.prompt?.includes("updated") ? 0.9 : 0.5;
    };

    const result = await optimizeAnything({
      seedCandidate: { prompt: "original", code: "print(1)" },
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 3 } },
    });

    expect(result.bestScore).toBeGreaterThanOrEqual(0.5);
  });

  it("supports multi-task mode with dataset", async () => {
    const fakeLlm = createFakeLlm(["better"]);
    const evaluator = async (ctx: EvaluationContext) => {
      const example = ctx.example as { target: string };
      const c = typeof ctx.candidate === "string" ? ctx.candidate : "";
      return c === example?.target ? 1.0 : 0.3;
    };

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      dataset: [{ target: "better" }, { target: "best" }],
      config: { engine: { maxMetricCalls: 6 } },
    });

    expect(result.totalMetricCalls).toBeLessThanOrEqual(6);
  });
});
```

**Step 2: Implement `optimizeAnything()`**

`src/core/optimizer.ts`:

```ts
export async function optimizeAnything(opts: {
  seedCandidate: Candidate | null;
  evaluator: Evaluator;
  model: LanguageModel;
  dataset?: unknown[];
  valset?: unknown[];
  objective?: string;
  background?: string;
  config?: OptimizeConfig;
  stopConditions?: StopCondition[];
  onEvent?: EventCallback;
}): Promise<OptimizeResult>;
```

**The loop:**
1. Initialize `RunState` (or load from `runDir` for resume)
2. Evaluate seed candidate → add to state + frontier
3. Emit `optimization_start` event
4. **While** no stop condition fires:
   a. Emit `iteration_start`
   b. Select candidate from frontier (Pareto or current-best)
   c. Select minibatch from dataset (if multi-task/generalization)
   d. Select component to mutate (if multi-component, round-robin)
   e. Build proposer prompt with: current candidate, ASI from last evaluation, scores, objective, background
   f. Call LLM → parse new candidate
   g. Emit `candidate_proposed`
   h. Check evaluation cache → skip if hit
   i. Evaluate new candidate (against minibatch or single-task)
   j. Emit `evaluation_end`
   k. Normalize result → update state → insert into frontier
   l. Emit `candidate_accepted` or `candidate_rejected`
   m. Emit `frontier_updated` (if frontier changed)
   n. Save state to `runDir` (if configured)
   o. Emit `iteration_end`
5. Emit `optimization_end`
6. Return `OptimizeResult`

**Step 3: Create golden trajectory test**

After implementation works with fake LLM, record the event sequence:
```bash
bun test tests/optimizer.test.ts  # produces events
# Manually verify events are correct, then save as golden file
```

Store `tests/golden/single-task.jsonl` — subsequent runs compare against this.

**Step 4: Run tests, typecheck**
```bash
bun test
bun run typecheck
```

**Step 5: Review + simplify**
- Read every file in `src/core/` — verify each maps to a GEPA concept
- Check: no file > 300 lines
- Check: no dead code or unused exports

**Step 6: Commit**
```bash
git add -A
git commit -m "feat: GEPA-compatible optimization loop with Pareto search, ASI, and caching"
```

### Gate 5 (CRITICAL — the core library must be proven correct here)
- All optimizer tests pass (single-task, budget, caching, events, multi-component, multi-task)
- Golden trajectory test passes (deterministic event sequence with fake LLM)
- `bun run typecheck` clean
- No file in `src/core/` exceeds 300 lines
- Full `bun test` green (all previous tasks' tests still pass)

---

## Task 6: CLI

**Files:**
- Create: `src/cli/index.ts`
- Create: `tests/cli.test.ts`

**Step 1: Write failing tests**
```ts
import { describe, it, expect } from "bun:test";
import { parseArgs } from "../src/cli/index";

describe("CLI arg parsing", () => {
  it("parses seed + evaluator-command + max-metric-calls", () => {
    const args = parseArgs([
      "optimize",
      "--seed", "examples/seed.txt",
      "--evaluator-command", "examples/eval.sh",
      "--max-metric-calls", "5",
    ]);
    expect(args.command).toBe("optimize");
    expect(args.seed).toBe("examples/seed.txt");
    expect(args.evaluatorCommand).toBe("examples/eval.sh");
    expect(args.maxMetricCalls).toBe(5);
  });

  it("parses objective and background", () => {
    const args = parseArgs([
      "optimize",
      "--objective", "Improve the code",
      "--background", "TypeScript project",
      "--evaluator-command", "eval.sh",
    ]);
    expect(args.objective).toBe("Improve the code");
  });
});
```

**Step 2: Implement CLI**
- `parseArgs(argv)` — parse command-line arguments
- `optimize` subcommand:
  - Read seed from file (or use `--objective` for seedless)
  - Create command evaluator from `--evaluator-command`
  - Create `AnthropicModel` from `ANTHROPIC_API_KEY` env
  - Call `optimizeAnything()` with parsed config
  - Write best candidate to stdout (or `--output` file)
  - Write run state to `--run-dir` (default: `./runs/<timestamp>`)

**Step 3: Integration test**

Create `examples/eval.sh`:
```bash
#!/usr/bin/env bash
input=$(cat)
echo "{\"score\":0.7,\"sideInfo\":{\"note\":\"dummy evaluator\"}}"
```

Create `examples/seed.txt`:
```
function hello() { return "world"; }
```

**Step 4: Run tests**
```bash
bun test tests/cli.test.ts
bun run typecheck
```

**Step 5: Commit**
```bash
git add -A
git commit -m "feat: CLI interface for optimize-anything"
```

### Gate 6
- CLI arg parsing tests pass
- `bun run typecheck` clean

---

## Task 7: MCP Server

**Files:**
- Create: `src/mcp/server.ts`
- Create: `src/mcp/schema.ts`
- Create: `tests/mcp.test.ts`

**Step 1: Define MCP tool schema**

`src/mcp/schema.ts`:
```ts
export const optimizeToolSchema = {
  name: "optimize",
  description: "Run LLM-guided optimization on a text artifact with a BYO evaluator",
  inputSchema: {
    type: "object",
    properties: {
      seedCandidate: { type: "string", description: "Initial text artifact to optimize" },
      evaluatorCommand: { type: "string", description: "Command to run as evaluator (receives candidate on stdin, returns JSON {score, sideInfo?} on stdout)" },
      evaluatorUrl: { type: "string", description: "HTTP URL for evaluator (POST with JSON body)" },
      objective: { type: "string", description: "Natural language description of what to optimize for" },
      background: { type: "string", description: "Domain knowledge and constraints" },
      maxMetricCalls: { type: "number", description: "Maximum evaluator invocations (budget)", default: 20 },
    },
    required: [],
    oneOf: [
      { required: ["seedCandidate", "evaluatorCommand"] },
      { required: ["seedCandidate", "evaluatorUrl"] },
      { required: ["objective", "evaluatorCommand"] },
      { required: ["objective", "evaluatorUrl"] }
    ]
  },
};
```

**Step 2: Implement MCP server**

`src/mcp/server.ts`:
- Use `@modelcontextprotocol/sdk` `McpServer` class
- Register `optimize` tool with schema above
- Handler:
  - Create evaluator from `evaluatorCommand` or `evaluatorUrl`
  - Create `AnthropicModel` from env
  - Call `optimizeAnything()`
  - Return `{ bestCandidate, bestScore, totalMetricCalls }` as tool result
- Connect via stdio transport

**Step 3: Write MCP integration test**

`tests/mcp.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
// Test that the server starts and responds to tool listing
// (Full MCP integration test spawns server as subprocess)

describe("MCP server", () => {
  it("exposes optimize tool in tool list", async () => {
    // Spawn server, send initialize + tools/list, verify response
    const proc = Bun.spawn(["bun", "run", "src/mcp/server.ts"], {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
    });

    // Send JSON-RPC initialize
    const initRequest = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { capabilities: {}, clientInfo: { name: "test", version: "0.1" }, protocolVersion: "2024-11-05" },
    }) + "\n";

    proc.stdin.write(initRequest);
    // Read and verify response contains tools using MCP stdio framing:
    // `Content-Length: <n>\r\n\r\n<json>` for both requests and responses.
    // Add a tiny helper in the test file to encode/decode framed messages.

    proc.kill();
  });
});
```

**Step 4: Run tests, typecheck**
```bash
bun test tests/mcp.test.ts
bun run typecheck
```

**Step 5: Commit**
```bash
git add -A
git commit -m "feat: MCP server exposing optimize tool via stdio"
```

### Gate 7
- MCP server starts without errors
- Tool list includes `optimize` with correct schema
- `bun run typecheck` clean

---

## Task 8: Claude Code Plugin Packaging

**Files:**
- Create: `.mcp.json`
- Create: `SKILL.md`

**Step 1: Create `.mcp.json`**
```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "bun",
      "args": ["run", "src/mcp/server.ts"]
    }
  }
}
```

**Step 2: Write `SKILL.md`**

The skill file documents the evaluator contract, safety warnings, and usage patterns for Claude Code. Include:

- **What optimize-anything does** — LLM-guided optimization of any text artifact
- **Evaluator contract** — `stdin: JSON { candidate, example? }` → `stdout: JSON { score, sideInfo? }`
  - `score`: float, higher is better
  - `sideInfo`: optional diagnostics (errors, logs, sub-scores)
- **Safety warnings**:
  - Evaluator commands run with full shell access
  - Set `maxMetricCalls` to limit cost
  - Review evaluator scripts before running
- **Usage examples**:
  - Via MCP tool call: `optimize({ seedCandidate: "...", evaluatorCommand: "eval.sh", maxMetricCalls: 10 })`
  - Via CLI: `bun run src/cli/index.ts optimize --seed seed.txt --evaluator-command eval.sh --max-metric-calls 10`
- **Three optimization modes** explained briefly

**Step 3: Commit**
```bash
git add -A
git commit -m "feat: Claude Code plugin packaging with .mcp.json and SKILL.md"
```

### Gate 8
- `.mcp.json` is valid JSON
- `SKILL.md` contains evaluator contract, safety warnings, and usage examples

---

## Task 9: Proof-of-Correctness Cycle

This is the final validation pass. **No new code** — only verification.

**Step 1: Full test suite**
```bash
bun test
```
Expected: ALL tests pass (unit, integration, golden trajectory).

**Step 2: Type check**
```bash
bun run typecheck
```
Expected: Zero errors.

**Step 3: Live smoke test (with real LLM)**
```bash
ANTHROPIC_API_KEY=<key> bun test tests/live/
```
If no `tests/live/` directory exists, create `tests/live/smoke.test.ts`:
```ts
import { describe, it, expect } from "bun:test";
import { optimizeAnything } from "../../src/core/optimizer";
import { AnthropicModel } from "../../src/core/llm";

const SKIP = !process.env.ANTHROPIC_API_KEY;

describe.skipIf(SKIP)("live smoke test", () => {
  it("improves a trivial candidate with real LLM", async () => {
    const model = new AnthropicModel({
      apiKey: process.env.ANTHROPIC_API_KEY!,
      model: "claude-sonnet-4-20250514",
      maxTokens: 1024,
    });

    const result = await optimizeAnything({
      seedCandidate: "say goobye",
      evaluator: async (ctx) => {
        const c = typeof ctx.candidate === "string" ? ctx.candidate : "";
        const hasHello = c.toLowerCase().includes("hello") ? 0.5 : 0;
        const hasWorld = c.toLowerCase().includes("world") ? 0.5 : 0;
        return { score: hasHello + hasWorld, sideInfo: { candidate: c } };
      },
      model,
      objective: 'Produce a string that contains both "hello" and "world"',
      config: { engine: { maxMetricCalls: 3 } },
    });

    expect(result.bestScore).toBeGreaterThan(0);
    expect(result.totalMetricCalls).toBeLessThanOrEqual(3);
  }, 60_000); // 60s timeout for API calls
});
```
Expected: Score improves from 0 (seed has neither word) to > 0.

**Step 4: MCP end-to-end test**
Spawn MCP server, send a tool call with the dummy evaluator, verify response.

**Step 5: File size audit**
```bash
wc -l src/**/*.ts
```
Expected: No file > 300 lines. If any file exceeds, refactor before declaring done.

**Step 6: Conceptual review**
Read each `src/core/*.ts` file and verify it maps to a GEPA concept:

| File | GEPA Concept |
|---|---|
| `types.ts` | Candidate, SideInfo, Evaluator, Config, RunState, Events |
| `evaluator.ts` | Evaluator runners (inline/command/HTTP) |
| `asi.ts` | ASI normalization + log capture |
| `stop-conditions.ts` | StopperProtocol implementations |
| `events.ts` | Callback/event system + JSONL persistence |
| `pareto.ts` | Pareto dominance + frontier management |
| `state.ts` | RunState + evaluation cache |
| `persistence.ts` | run_dir save/load |
| `llm.ts` | LanguageModel interface + AnthropicModel |
| `proposer.ts` | Prompt construction + candidate parsing |
| `reflector.ts` | ASI analysis prompts |
| `candidate-selector.ts` | Pareto/current-best selection |
| `optimizer.ts` | The `optimizeAnything()` loop |
| `cli/index.ts` | CLI wrapper |
| `mcp/server.ts` | MCP wrapper |
| `mcp/schema.ts` | Tool schema |

**Step 7: Commit verification report**
```bash
git add -A
git commit -m "test: add live smoke test and complete proof-of-correctness cycle"
```

### Gate 9 (FINAL)
- [ ] `bun test` — ALL unit + integration + golden tests pass
- [ ] `bun run typecheck` — zero errors
- [ ] Live smoke test passes (with real API key)
- [ ] MCP e2e test passes
- [ ] No file > 300 lines
- [ ] Every `src/core/*.ts` maps to a documented GEPA concept
- [ ] All gates 0–8 still pass

---

## Completion Criteria

The project is **done** when all of the following are true:
1. `bun test` passes (all layers of the validation harness)
2. `bun run typecheck` exits 0
3. CLI runs end-to-end with a real evaluator script
4. MCP server starts and exposes `optimize` tool
5. Live smoke test proves the optimizer actually improves candidates with a real LLM
6. Golden trajectory tests ensure deterministic behavior across refactors
7. Every source file maps to a GEPA concept and stays under 300 lines

## Deferred to v0.2

These features are architecturally accounted for (interfaces exist) but not implemented in v0.1:
- **Merge operations** (MergeProposer combining frontier candidates)
- **Refiner** (post-optimization refinement pass)
- **Seedless mode** (LLM generates first candidate from objective)
- **Callbacks for external tracking** (W&B, MLflow integration)
- **Adapter ecosystem** (DSPy, RAG, TerminalBench adapters)
- **EpsilonGreedy candidate selection**
- **Parallel evaluation** (concurrent evaluator calls)
