import { describe, expect, it } from "bun:test";
import { buildProposerPrompt, buildReflectorPrompt, parseProposedCandidate } from "../src/core/proposer.js";

describe("proposer prompt", () => {
  it("includes current candidate in prompt", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: "function add(a, b) { return a + b; }",
      scores: new Map([["correctness", 0.5]]),
      sideInfo: [{ stderr: "TypeError: undefined" }],
      objective: "Fix the function",
      background: "TypeScript project",
      constraints: [],
    });
    expect(prompt).toContain("function add");
    expect(prompt).toContain("TypeError: undefined");
    expect(prompt).toContain("Fix the function");
  });

  it("includes ASI from minibatch in prompt", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: "x",
      scores: new Map([
        ["t1", 0.3],
        ["t2", 0.9],
      ]),
      sideInfo: [{ log: "failed on edge case" }, { log: "passed all tests" }],
      objective: "Improve",
    });
    expect(prompt).toContain("failed on edge case");
    expect(prompt).toContain("passed all tests");
  });

  it("handles multi-component candidates", () => {
    const prompt = buildProposerPrompt({
      currentCandidate: { prompt: "think step by step", code: "print(42)" },
      scores: new Map([["default", 0.6]]),
      sideInfo: [],
      componentToMutate: "prompt",
    });
    expect(prompt).toContain("think step by step");
    expect(prompt).toContain("prompt");
  });
});

describe("reflector prompt", () => {
  it("summarizes failure patterns from ASI", () => {
    const prompt = buildReflectorPrompt({
      candidate: "x",
      sideInfo: [
        { stderr: "timeout after 5s", log: "test 3 failed" },
        { log: "test 7 failed: expected 42 got 41" },
      ],
      scores: new Map([
        ["t3", 0.0],
        ["t7", 0.0],
      ]),
    });
    expect(prompt).toContain("timeout");
    expect(prompt).toContain("expected 42 got 41");
  });
});

describe("parse proposed candidate", () => {
  it("extracts candidate from LLM response", () => {
    const response = "Here is my improved version:\n```\nfunction better() {}\n```\nThis should work.";
    const candidate = parseProposedCandidate(response);
    expect(candidate).toContain("function better");
  });

  it("handles response without code fences", () => {
    const response = "function simple() { return 1; }";
    const candidate = parseProposedCandidate(response);
    expect(candidate).toBe(response);
  });
});
