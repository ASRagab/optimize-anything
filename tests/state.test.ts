import { describe, expect, it } from "bun:test";
import { addCandidate, cacheResult, createRunState, getCacheKey, getCachedResult } from "../src/core/state.js";

describe("RunState", () => {
  it("initializes empty", () => {
    const state = createRunState();
    expect(state.candidates.length).toBe(0);
    expect(state.metricCallCount).toBe(0);
  });

  it("adds candidates", () => {
    const state = createRunState();
    const result = addCandidate(state, {
      candidate: "hello",
      parentIndex: null,
      scores: new Map([["default", 0.8]]),
      aggregateScore: 0.8,
      sideInfo: [],
      metricCallIndex: 0,
    });
    expect(state.candidates.length).toBe(1);
    expect(result).toEqual({ index: 0, frontierChanged: true });
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
