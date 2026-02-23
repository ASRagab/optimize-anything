import { describe, expect, it } from "bun:test";
import {
  optimizeAnything,
  createCommandEvaluator,
  createHttpEvaluator,
  AnthropicModel,
  MaxMetricCallsStopper,
  TimeoutStopper,
  NoImprovementStopper,
  ScoreThresholdStopper,
  CompositeStopper,
  EventEmitter,
  serializeEvents,
  deserializeEvents,
  saveState,
  loadState,
  captureLog,
  normalizeEvalResult,
  hashEvalKey,
} from "../src/index.js";

describe("barrel exports", () => {
  it("exports all public API symbols", () => {
    expect(optimizeAnything).toBeFunction();
    expect(createCommandEvaluator).toBeFunction();
    expect(createHttpEvaluator).toBeFunction();
    expect(AnthropicModel).toBeFunction();
    expect(MaxMetricCallsStopper).toBeFunction();
    expect(TimeoutStopper).toBeFunction();
    expect(NoImprovementStopper).toBeFunction();
    expect(ScoreThresholdStopper).toBeFunction();
    expect(CompositeStopper).toBeFunction();
    expect(EventEmitter).toBeFunction();
    expect(serializeEvents).toBeFunction();
    expect(deserializeEvents).toBeFunction();
    expect(saveState).toBeFunction();
    expect(loadState).toBeFunction();
    expect(captureLog).toBeFunction();
    expect(normalizeEvalResult).toBeFunction();
    expect(hashEvalKey).toBeFunction();
  });
});
