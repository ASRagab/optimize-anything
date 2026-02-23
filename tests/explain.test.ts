import { describe, expect, it } from "bun:test";
import { explainOptimization } from "../src/core/explain.js";
import type { CandidateRecord, OptimizationEvent } from "../src/types.js";

function makeCandidate(score: number, parentIndex: number | null = null, sideInfo: Record<string, unknown>[] = []): CandidateRecord {
  return {
    candidate: `candidate-${score}`,
    parentIndex,
    scores: new Map([["default", score]]),
    aggregateScore: score,
    sideInfo: sideInfo as CandidateRecord["sideInfo"],
    metricCallIndex: 0,
  };
}

function makeEvent(type: OptimizationEvent["type"], iterationIndex?: number, data?: Record<string, unknown>): OptimizationEvent {
  return { type, timestamp: Date.now(), iterationIndex, data };
}

describe("explainOptimization", () => {
  it("returns empty explanation for no candidates", () => {
    const result = explainOptimization({
      candidates: [],
      frontier: [],
      events: [],
      bestScore: 0,
    });

    expect(result.summary).toContain("No optimization data");
    expect(result.nextActions.length).toBeGreaterThan(0);
  });

  it("reports improvement from seed to best", () => {
    const candidates = [makeCandidate(0.3), makeCandidate(0.7, 0), makeCandidate(0.9, 1)];
    const events = [
      makeEvent("optimization_start"),
      makeEvent("candidate_accepted", 0),
      makeEvent("frontier_updated", 0),
      makeEvent("iteration_end", 0),
      makeEvent("candidate_accepted", 1),
      makeEvent("frontier_updated", 1),
      makeEvent("iteration_end", 1),
      makeEvent("optimization_end"),
    ];

    const result = explainOptimization({
      candidates,
      frontier: [2],
      events,
      bestScore: 0.9,
    });

    expect(result.wins.some((w) => w.includes("0.3000") && w.includes("0.9000"))).toBe(true);
    expect(result.summary).toContain("improved");
  });

  it("reports no improvement when best equals seed", () => {
    const candidates = [makeCandidate(0.5), makeCandidate(0.3, 0)];
    const events = [
      makeEvent("candidate_rejected", 0),
      makeEvent("iteration_end", 0),
    ];

    const result = explainOptimization({
      candidates,
      frontier: [0],
      events,
      bestScore: 0.5,
    });

    expect(result.regressions.some((r) => r.includes("No improvement"))).toBe(true);
  });

  it("reports acceptance and rejection rates", () => {
    const candidates = [makeCandidate(0.5), makeCandidate(0.6, 0), makeCandidate(0.4, 0), makeCandidate(0.3, 0)];
    const events = [
      makeEvent("candidate_accepted", 0),
      makeEvent("iteration_end", 0),
      makeEvent("candidate_rejected", 1),
      makeEvent("iteration_end", 1),
      makeEvent("candidate_rejected", 2),
      makeEvent("iteration_end", 2),
    ];

    const result = explainOptimization({
      candidates,
      frontier: [1],
      events,
      bestScore: 0.6,
    });

    expect(result.wins.some((w) => w.includes("1/3"))).toBe(true);
    expect(result.regressions.some((r) => r.includes("2/3"))).toBe(true);
  });

  it("identifies dominant sideInfo factors", () => {
    const si = [{ scores: { readability: 0.8, accuracy: 0.7 } }];
    const candidates = [makeCandidate(0.5, null, si), makeCandidate(0.6, 0, si), makeCandidate(0.7, 1, si)];

    const result = explainOptimization({
      candidates,
      frontier: [2],
      events: [],
      bestScore: 0.7,
    });

    expect(result.dominantFactors.some((f) => f.includes("readability"))).toBe(true);
    expect(result.dominantFactors.some((f) => f.includes("accuracy"))).toBe(true);
  });

  it("handles sparse sideInfo gracefully", () => {
    const candidates = [makeCandidate(0.5), makeCandidate(0.6, 0)];

    const result = explainOptimization({
      candidates,
      frontier: [1],
      events: [],
      bestScore: 0.6,
    });

    // Should not crash and should produce valid output
    expect(result.summary).toBeTruthy();
    expect(result.dominantFactors.length).toBe(0);
  });

  it("is deterministic for same input", () => {
    const candidates = [makeCandidate(0.3), makeCandidate(0.7, 0)];
    const events = [
      makeEvent("candidate_accepted", 0),
      makeEvent("frontier_updated", 0),
      makeEvent("iteration_end", 0),
    ];
    const input = { candidates, frontier: [1], events, bestScore: 0.7 };

    const result1 = explainOptimization(input);
    const result2 = explainOptimization(input);

    expect(result1.wins).toEqual(result2.wins);
    expect(result1.regressions).toEqual(result2.regressions);
    expect(result1.summary).toEqual(result2.summary);
  });
});
