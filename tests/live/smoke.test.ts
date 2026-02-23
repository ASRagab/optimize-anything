import { describe, expect, it } from "bun:test";
import { optimizeAnything } from "../../src/core/optimizer.js";
import { AnthropicModel } from "../../src/core/llm.js";

const SKIP = !process.env.ANTHROPIC_API_KEY;

describe.skipIf(SKIP)("live smoke test", () => {
  it(
    "improves a trivial candidate with real LLM",
    async () => {
      const model = new AnthropicModel({
        apiKey: process.env.ANTHROPIC_API_KEY!,
        model: "claude-sonnet-4-20250514",
        maxTokens: 1024,
      });

      const result = await optimizeAnything({
        seedCandidate: "say goobye",
        evaluator: async (ctx) => {
          const c = typeof ctx.candidate === "string" ? ctx.candidate : "";
          const hasHello = c.toLowerCase().includes("hello") ? 0.5 : 0;
          const hasWorld = c.toLowerCase().includes("world") ? 0.5 : 0;
          return { score: hasHello + hasWorld, sideInfo: { candidate: c } };
        },
        model,
        objective: 'Produce a string that contains both "hello" and "world"',
        config: { engine: { maxMetricCalls: 3 } },
      });

      expect(result.bestScore).toBeGreaterThan(0);
      expect(result.totalMetricCalls).toBeLessThanOrEqual(3);
    },
    60_000,
  );
});
