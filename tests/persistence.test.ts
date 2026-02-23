import { afterEach, describe, expect, it } from "bun:test";
import { rmSync } from "node:fs";
import { loadState, saveState } from "../src/core/persistence.js";
import { createRunState } from "../src/core/state.js";

const TEST_RUN_DIR = `/tmp/oa-test-run-${Date.now()}`;

afterEach(() => {
  rmSync(TEST_RUN_DIR, { recursive: true, force: true });
});

describe("persistence", () => {
  it("round-trips state through save/load", async () => {
    const state = createRunState();
    state.metricCallCount = 5;
    state.lastFrontierChangeIteration = 2;
    state.events.push({ type: "optimization_start", timestamp: Date.now() });
    await saveState(state, TEST_RUN_DIR);
    const loaded = await loadState(TEST_RUN_DIR);
    expect(loaded.metricCallCount).toBe(5);
    expect(loaded.lastFrontierChangeIteration).toBe(2);
    expect(loaded.events.length).toBe(1);
  });
});
