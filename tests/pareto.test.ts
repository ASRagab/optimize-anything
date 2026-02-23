import { describe, expect, it } from "bun:test";
import { dominates, insertIntoFrontier } from "../src/core/pareto.js";
import type { CandidateRecord } from "../src/types.js";

describe("Pareto dominance", () => {
  it("a dominates b when better on all dimensions", () => {
    const a = new Map([
      ["x", 0.9],
      ["y", 0.8],
    ]);
    const b = new Map([
      ["x", 0.7],
      ["y", 0.6],
    ]);
    expect(dominates(a, b)).toBe(true);
    expect(dominates(b, a)).toBe(false);
  });

  it("neither dominates when each excels on different dimensions", () => {
    const a = new Map([
      ["x", 0.9],
      ["y", 0.3],
    ]);
    const b = new Map([
      ["x", 0.3],
      ["y", 0.9],
    ]);
    expect(dominates(a, b)).toBe(false);
    expect(dominates(b, a)).toBe(false);
  });
});

describe("frontier insertion", () => {
  it("adds non-dominated candidate to frontier", () => {
    const candidates: CandidateRecord[] = [
      {
        candidate: "a",
        parentIndex: null,
        scores: new Map([["x", 0.5]]),
        aggregateScore: 0.5,
        sideInfo: [],
        metricCallIndex: 0,
      },
      {
        candidate: "b",
        parentIndex: null,
        scores: new Map([["x", 0.9]]),
        aggregateScore: 0.9,
        sideInfo: [],
        metricCallIndex: 1,
      },
    ];
    const frontier = new Set([0]);
    insertIntoFrontier(1, candidates, frontier);
    expect(frontier.has(1)).toBe(true);
    expect(frontier.has(0)).toBe(false);
  });

  it("preserves both when neither dominates", () => {
    const candidates: CandidateRecord[] = [
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
    ];
    const frontier = new Set([0]);
    insertIntoFrontier(1, candidates, frontier);
    expect(frontier.size).toBe(2);
  });
});
