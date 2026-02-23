import { describe, expect, it } from "bun:test";
import type { Candidate, EvaluationResult, Evaluator } from "../src/types.js";

function isEvaluationResult(value: EvaluationResult | number): value is EvaluationResult {
  return typeof value === "object" && value !== null && "score" in value;
}

describe("type helpers", () => {
  it("narrows EvaluationResult | number", () => {
    const resultA: EvaluationResult | number = 0.5;
    const resultB: EvaluationResult | number = { score: 0.9, sideInfo: { note: "ok" } };

    expect(isEvaluationResult(resultA)).toBe(false);
    expect(isEvaluationResult(resultB)).toBe(true);

    if (isEvaluationResult(resultB)) {
      expect(resultB.score).toBe(0.9);
      expect(resultB.sideInfo?.note).toBe("ok");
    }
  });

  it("accepts both candidate union shapes", () => {
    const textCandidate: Candidate = "hello";
    const componentCandidate: Candidate = { prompt: "hello", code: "print(1)" };

    expect(typeof textCandidate).toBe("string");
    expect(typeof componentCandidate).toBe("object");
  });

  it("matches evaluator signature", async () => {
    const evaluator: Evaluator = async ({ candidate }) => {
      if (typeof candidate === "string") {
        return { score: candidate.length > 0 ? 1 : 0 };
      }

      return 0.5;
    };

    const fromString = await evaluator({ candidate: "x", log: () => {} });
    const fromObject = await evaluator({ candidate: { prompt: "x" }, log: () => {} });

    expect(isEvaluationResult(fromString)).toBe(true);
    expect(fromObject).toBe(0.5);
  });
});
