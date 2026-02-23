import { describe, expect, it } from "bun:test";
import { recommendBudget } from "../src/core/budget.js";

describe("recommendBudget", () => {
  it("returns deterministic recommendations for same input", () => {
    const input = { seedCandidate: "hello world", objective: "improve clarity" };
    const r1 = recommendBudget(input);
    const r2 = recommendBudget(input);

    expect(r1.recommended).toBe(r2.recommended);
    expect(r1.confidence).toBe(r2.confidence);
    expect(r1.rationale).toBe(r2.rationale);
  });

  it("returns base budget for simple inputs", () => {
    const result = recommendBudget({ seedCandidate: "short text" });
    expect(result.recommended).toBe(10);
    expect(result.factors.candidateComplexity).toBe("simple");
    expect(result.factors.objectiveComplexity).toBe("simple");
  });

  it("increases budget for complex candidates", () => {
    const simple = recommendBudget({ seedCandidate: "hi" });
    const complex = recommendBudget({
      seedCandidate: Array(150).fill("word").join(" "),
    });

    expect(complex.recommended).toBeGreaterThan(simple.recommended);
    expect(complex.factors.candidateComplexity).toBe("complex");
  });

  it("increases budget for complex objectives", () => {
    const noObj = recommendBudget({ seedCandidate: "test" });
    const complexObj = recommendBudget({
      seedCandidate: "test",
      objective: Array(150).fill("word").join(" "),
    });

    expect(complexObj.recommended).toBeGreaterThan(noObj.recommended);
    expect(complexObj.factors.objectiveComplexity).toBe("complex");
  });

  it("increases budget with dataset size", () => {
    const noDataset = recommendBudget({ seedCandidate: "test" });
    const withDataset = recommendBudget({ seedCandidate: "test", datasetSize: 100 });

    expect(withDataset.recommended).toBeGreaterThan(noDataset.recommended);
    expect(withDataset.factors.datasetSize).toBe(100);
  });

  it("returns low confidence without objective or dataset", () => {
    const result = recommendBudget({ seedCandidate: "test" });
    expect(result.confidence).toBe("low");
  });

  it("returns medium confidence with objective only", () => {
    const result = recommendBudget({ seedCandidate: "test", objective: "improve" });
    expect(result.confidence).toBe("medium");
  });

  it("returns high confidence with both objective and dataset", () => {
    const result = recommendBudget({
      seedCandidate: "test",
      objective: "improve clarity",
      datasetSize: 10,
    });
    expect(result.confidence).toBe("high");
  });

  it("handles tiny dataset size (1 example)", () => {
    const result = recommendBudget({ seedCandidate: "test", datasetSize: 1 });
    expect(result.recommended).toBeGreaterThanOrEqual(10);
    expect(result.rationale).toContain("Dataset size: 1");
  });

  it("handles large dataset size (10000 examples)", () => {
    const result = recommendBudget({ seedCandidate: "test", datasetSize: 10000 });
    expect(result.recommended).toBeGreaterThan(10);
    expect(Number.isFinite(result.recommended)).toBe(true);
  });

  it("includes rationale explaining all factors", () => {
    const result = recommendBudget({
      seedCandidate: "test candidate text",
      objective: "maximize readability",
      datasetSize: 5,
    });

    expect(result.rationale).toContain("Base budget");
    expect(result.rationale).toContain("Candidate complexity");
    expect(result.rationale).toContain("Objective complexity");
    expect(result.rationale).toContain("Dataset size");
    expect(result.rationale).toContain("Recommended");
  });
});
