import { describe, expect, it } from "bun:test";
import { parseArgs } from "../src/cli/index.js";

describe("CLI arg parsing", () => {
  it("parses seed + evaluator-command + max-metric-calls", () => {
    const args = parseArgs([
      "optimize",
      "--seed",
      "examples/seed.txt",
      "--evaluator-command",
      "examples/eval.sh",
      "--max-metric-calls",
      "5",
    ]);
    expect(args.command).toBe("optimize");
    expect(args.seed).toBe("examples/seed.txt");
    expect(args.evaluatorCommand).toBe("examples/eval.sh");
    expect(args.maxMetricCalls).toBe(5);
  });

  it("parses objective and background", () => {
    const args = parseArgs([
      "optimize",
      "--objective",
      "Improve the code",
      "--background",
      "TypeScript project",
      "--evaluator-command",
      "eval.sh",
    ]);
    expect(args.objective).toBe("Improve the code");
  });

  it("detects NaN for non-numeric max-metric-calls", () => {
    const args = parseArgs(["optimize", "--max-metric-calls", "abc", "--evaluator-command", "eval.sh"]);
    expect(Number.isNaN(args.maxMetricCalls)).toBe(true);
  });
});
