import { describe, expect, it } from "bun:test";
import { readFileSync } from "node:fs";
import { optimizeAnything } from "../src/core/optimizer.js";
import { createFakeLlm } from "./fixtures/fake-llm.js";
import type { EvaluationContext } from "../src/types.js";

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
    const evaluator = async () => {
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
    const evaluator = async () => {
      callCount++;
      return 0.8;
    };
    const fakeLlm = createFakeLlm(["same-candidate"]);

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 10 } },
    });

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
    expect(events).toContain("evaluation_start");
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

  it("uses 'score' key when no dataset provided", async () => {
    const fakeLlm = createFakeLlm(["improved"]);
    const evaluator = async () => 0.7;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
    });

    for (const candidate of result.candidates) {
      expect([...candidate.scores.keys()]).toEqual(["score"]);
    }
  });

  it("uses stable example-based metric keys with dataset", async () => {
    const fakeLlm = createFakeLlm(["v1", "v2"]);
    const evaluator = async () => 0.5;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      dataset: [{ id: "a" }, { id: "b" }],
      config: { engine: { maxMetricCalls: 6, seed: 42 } },
    });

    // All candidates should have the same metric key names (stable hashes, not positional)
    const keyNames = result.candidates.map((c) => [...c.scores.keys()].sort());
    for (const keys of keyNames) {
      expect(keys.every((k) => k !== "metric_0" && k !== "metric_1")).toBe(true);
    }
  });

  it("captures evaluator log calls into sideInfo", async () => {
    const fakeLlm = createFakeLlm(["v1"]);
    const evaluator = async (ctx: EvaluationContext) => {
      ctx.log("diagnostic message");
      return 0.8;
    };

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
    });

    const hasDiagnostic = result.candidates.some((c) =>
      c.sideInfo.some((si) => si.log?.includes("diagnostic message")),
    );
    expect(hasDiagnostic).toBe(true);
  });

  it("continues optimization after LLM failure", async () => {
    let callIndex = 0;
    const failThenSucceed = {
      async generate() {
        callIndex++;
        if (callIndex <= 4) {
          throw new Error("API timeout");
        }
        return "improved-v1";
      },
    };
    const evaluator = async () => 0.8;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: failThenSucceed,
      retryBaseDelay: 0,
      config: { engine: { maxMetricCalls: 3 } },
    });

    expect(result.events.some((e) => e.type === "error")).toBe(true);
    expect(result.bestCandidate).toBeDefined();
  });

  it("emits error event when all LLM retries exhausted", async () => {
    const alwaysFail = {
      async generate() {
        throw new Error("permanent failure");
      },
    };
    const evaluator = async () => 0.5;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: alwaysFail,
      retryBaseDelay: 0,
      config: { engine: { maxMetricCalls: 2 } },
    });

    const errors = result.events.filter((e) => e.type === "error");
    expect(errors.length).toBeGreaterThan(0);
    expect(errors[0].data?.reason).toBe("llm_failure");
  });

  it("continues after persistence failure", async () => {
    const fakeLlm = createFakeLlm(["v1"]);
    const evaluator = async () => 0.7;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: {
        engine: { maxMetricCalls: 2 },
        tracking: { runDir: "/dev/null/impossible/path" },
      },
    });

    expect(result.bestCandidate).toBeDefined();
    expect(result.events.some((e) => e.type === "error" && e.data?.reason === "persistence_failure")).toBe(true);
  });

  it("matches golden event trajectory", async () => {
    const fakeLlm = createFakeLlm(["improved-v1"]);
    const evaluator = async (ctx: EvaluationContext) => {
      const s = typeof ctx.candidate === "string" ? ctx.candidate : "";
      return s.includes("improved") ? 1 : 0.1;
    };
    const result = await optimizeAnything({
      seedCandidate: "seed",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
    });

    const actual = result.events.map((e) => JSON.stringify({ type: e.type })).join("\n");
    const expected = readFileSync("tests/golden/single-task.jsonl", "utf8").trim();
    expect(actual).toBe(expected);

    // M2: Also verify evaluation_end events have candidateIndex
    const evalEnds = result.events.filter((e) => e.type === "evaluation_end");
    for (const e of evalEnds) {
      expect(typeof e.candidateIndex).toBe("number");
    }
  });

  it("emits frontier_updated when Pareto front changes", async () => {
    const fakeLlm = createFakeLlm(["better"]);
    const evaluator = async (ctx: EvaluationContext) => {
      return typeof ctx.candidate === "string" && ctx.candidate.includes("better") ? 0.9 : 0.1;
    };

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
    });

    expect(result.events.some((e) => e.type === "frontier_updated")).toBe(true);
  });

  it("emits stop_condition_met when stopping", async () => {
    const fakeLlm = createFakeLlm(["v1"]);
    const evaluator = async () => 0.5;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 } },
    });

    const stopEvent = result.events.find((e) => e.type === "stop_condition_met");
    expect(stopEvent).toBeDefined();
    expect(stopEvent!.data?.condition).toBe("max_metric_calls");
  });

  it("iteration_start and iteration_end have matching indices", async () => {
    const fakeLlm = createFakeLlm(["v1", "v2"]);
    const evaluator = async () => 0.5;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 3 } },
    });

    const starts = result.events.filter((e) => e.type === "iteration_start");
    const ends = result.events.filter((e) => e.type === "iteration_end");
    expect(starts.length).toBe(ends.length);
    for (let i = 0; i < starts.length; i++) {
      expect(starts[i].iterationIndex).toBe(ends[i].iterationIndex);
    }
  });

  it("calls reflector when reflection enabled", async () => {
    const calls: string[] = [];
    const trackingLlm = {
      async generate(prompt: string) {
        calls.push(prompt.slice(0, 20));
        return "reflected-output";
      },
    };
    const evaluator = async () => 0.5;

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: trackingLlm,
      config: { engine: { maxMetricCalls: 2 }, reflection: { enabled: true } },
    });

    // Should have at least 2 model calls: proposer + reflector
    expect(calls.length).toBeGreaterThanOrEqual(2);
  });

  it("reflection text feeds into next proposer prompt", async () => {
    const prompts: string[] = [];
    let callCount = 0;
    const trackingLlm = {
      async generate(prompt: string) {
        callCount++;
        prompts.push(prompt);
        if (prompt.includes("Analyze evaluator")) return "focus on edge cases";
        return `v${callCount}`;
      },
    };
    const evaluator = async () => 0.5;

    await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: trackingLlm,
      config: { engine: { maxMetricCalls: 3 }, reflection: { enabled: true } },
    });

    const proposerPrompts = prompts.filter((p) => p.includes("improving a candidate"));
    const hasReflectionInPrompt = proposerPrompts.some((p) => p.includes("focus on edge cases"));
    expect(hasReflectionInPrompt).toBe(true);
  });

  it("reflection failure does not crash optimizer", async () => {
    let callCount = 0;
    const failingReflector = {
      async generate(prompt: string) {
        callCount++;
        if (prompt.includes("Analyze evaluator")) throw new Error("reflection failed");
        return "v1";
      },
    };
    const evaluator = async () => 0.5;

    const result = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: failingReflector,
      config: { engine: { maxMetricCalls: 2 }, reflection: { enabled: true } },
    });

    expect(result.bestCandidate).toBeDefined();
  });
  it("resumes from persisted state", async () => {
    const os = await import("node:os");
    const fs = await import("node:fs");
    const path = await import("node:path");
    const runDir = fs.mkdtempSync(path.join(os.tmpdir(), "oa-resume-"));

    const fakeLlm = createFakeLlm(["v1", "v2", "v3", "v4"]);
    const evaluator = async () => 0.5;

    // First run: 2 metric calls, saves state
    const result1 = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: fakeLlm,
      config: { engine: { maxMetricCalls: 2 }, tracking: { runDir } },
    });

    expect(result1.totalMetricCalls).toBeLessThanOrEqual(2);

    // Second run: resume from saved state, allow 4 more calls
    const result2 = await optimizeAnything({
      seedCandidate: "start",
      evaluator,
      model: createFakeLlm(["v5", "v6"]),
      config: { engine: { maxMetricCalls: 4 }, tracking: { resumeFrom: runDir } },
    });

    // Should have carried over metric calls from first run
    expect(result2.totalMetricCalls).toBeGreaterThan(result1.totalMetricCalls);

    // Clean up
    fs.rmSync(runDir, { recursive: true, force: true });
  });

});
