import { describe, expect, it } from "bun:test";
import {
  CompositeStopper,
  MaxMetricCallsStopper,
  NoImprovementStopper,
  ScoreThresholdStopper,
  TimeoutStopper,
} from "../src/core/stop-conditions.js";

describe("stop conditions", () => {
  const makeState = (overrides: Partial<Record<string, unknown>> = {}) => ({
    candidates: [],
    frontier: new Set<number>(),
    metricCallCount: 0,
    iterationCount: 0,
    lastFrontierChangeIteration: 0,
    startTime: Date.now(),
    events: [],
    evaluationCache: new Map(),
    ...overrides,
  });

  it("MaxMetricCalls stops at budget", () => {
    const stop = new MaxMetricCallsStopper(10);
    expect(stop.shouldStop(makeState({ metricCallCount: 9 }) as never)).toBe(false);
    expect(stop.shouldStop(makeState({ metricCallCount: 10 }) as never)).toBe(true);
  });

  it("Timeout stops after elapsed time", () => {
    const stop = new TimeoutStopper(1000);
    const old = makeState({ startTime: Date.now() - 2000 });
    expect(stop.shouldStop(old as never)).toBe(true);
  });

  it("NoImprovement stops after N stale iterations", () => {
    const stop = new NoImprovementStopper(3);
    expect(stop.shouldStop(makeState({ iterationCount: 1, lastFrontierChangeIteration: 0 }) as never)).toBe(false);
    expect(stop.shouldStop(makeState({ iterationCount: 3, lastFrontierChangeIteration: 0 }) as never)).toBe(true);
  });

  it("ScoreThreshold stops when target reached", () => {
    const stop = new ScoreThresholdStopper(0.95);
    const candidate = {
      candidate: "x",
      parentIndex: null,
      scores: new Map<string, number>(),
      aggregateScore: 0.96,
      sideInfo: [],
      metricCallIndex: 0,
    };
    const state = makeState({ candidates: [candidate] });
    expect(stop.shouldStop(state as never)).toBe(true);
  });

  it("Composite combines multiple conditions with OR", () => {
    const stop = new CompositeStopper([new MaxMetricCallsStopper(100), new ScoreThresholdStopper(1.0)]);
    expect(stop.shouldStop(makeState({ metricCallCount: 100 }) as never)).toBe(true);
    expect(stop.shouldStop(makeState({ metricCallCount: 1 }) as never)).toBe(false);
  });
});
