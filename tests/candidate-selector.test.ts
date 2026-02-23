import { describe, expect, it } from "bun:test";
import { selectCurrentBest, selectFromFrontier, selectMinibatch } from "../src/core/candidate-selector.js";
import type { CandidateRecord } from "../src/types.js";

describe("candidate selection", () => {
  const makeCandidates = (): CandidateRecord[] => [
    {
      candidate: "a",
      parentIndex: null,
      scores: new Map([
        ["x", 0.9],
        ["y", 0.3],
      ]),
      aggregateScore: 0.6,
      sideInfo: [],
      metricCallIndex: 0,
    },
    {
      candidate: "b",
      parentIndex: null,
      scores: new Map([
        ["x", 0.3],
        ["y", 0.9],
      ]),
      aggregateScore: 0.6,
      sideInfo: [],
      metricCallIndex: 1,
    },
    {
      candidate: "c",
      parentIndex: null,
      scores: new Map([
        ["x", 0.7],
        ["y", 0.7],
      ]),
      aggregateScore: 0.7,
      sideInfo: [],
      metricCallIndex: 2,
    },
  ];

  it("selectCurrentBest picks highest aggregate", () => {
    const candidates = makeCandidates();
    const idx = selectCurrentBest(candidates);
    expect(idx).toBe(2);
  });

  it("selectFromFrontier picks from frontier set", () => {
    const candidates = makeCandidates();
    const frontier = new Set([0, 1, 2]);
    const idx = selectFromFrontier(candidates, frontier, 42);
    expect(frontier.has(idx)).toBe(true);
  });

  it("selectMinibatch returns correct subset size", () => {
    const dataset = [1, 2, 3, 4, 5];
    const result = selectMinibatch(dataset, 3, 42);
    expect(result.length).toBe(3);
    for (const item of result) {
      expect(dataset).toContain(item);
    }
  });

  it("selectMinibatch is deterministic with same seed", () => {
    const dataset = [1, 2, 3, 4, 5];
    const a = selectMinibatch(dataset, 3, 42);
    const b = selectMinibatch(dataset, 3, 42);
    expect(a).toEqual(b);
  });
});
