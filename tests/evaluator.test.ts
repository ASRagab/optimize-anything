import { describe, expect, it } from "bun:test";
import {
  captureLog,
  createCommandEvaluator,
  createHttpEvaluator,
  normalizeEvalResult,
} from "../src/core/evaluator.js";

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
    if (typeof result === "number") {
      throw new Error("expected object result from command evaluator");
    }
    expect(result.score).toBeGreaterThan(0);
  });

  it("handles evaluator errors gracefully", async () => {
    const evaluate = createCommandEvaluator("tests/fixtures/evaluators/error-exit.sh");
    await expect(evaluate({ candidate: "x", log: () => {} })).rejects.toThrow();
  });

  it("respects timeout", async () => {
    const evaluate = createCommandEvaluator("sleep 10", { timeoutMs: 100 });
    await expect(evaluate({ candidate: "x", log: () => {} })).rejects.toThrow();
  });
});

describe("HTTP evaluator", () => {
  it("posts candidate and parses response", async () => {
    const server = Bun.serve({
      port: 0,
      fetch: async (req) => {
        const body = await req.json();
        return new Response(JSON.stringify({ score: 0.85, sideInfo: { input: body.candidate } }));
      },
    });

    try {
      const evaluate = createHttpEvaluator(`http://localhost:${server.port}`);
      const result = await evaluate({
        candidate: "hello",
        log: () => {},
      });
      if (typeof result === "number") {
        throw new Error("expected object result from http evaluator");
      }
      expect(result.score).toBeCloseTo(0.85, 2);
      expect(result.sideInfo?.input).toBe("hello");
    } finally {
      server.stop();
    }
  });
});
