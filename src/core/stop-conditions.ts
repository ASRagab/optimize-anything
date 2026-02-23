import type { RunState, StopCondition } from "../types.js";

export class MaxMetricCallsStopper implements StopCondition {
  readonly name = "max_metric_calls";

  constructor(private readonly max: number) {}

  shouldStop(state: RunState): boolean {
    return state.metricCallCount >= this.max;
  }
}

export class TimeoutStopper implements StopCondition {
  readonly name = "timeout";

  constructor(private readonly timeoutMs: number) {}

  shouldStop(state: RunState): boolean {
    return Date.now() - state.startTime >= this.timeoutMs;
  }
}

export class NoImprovementStopper implements StopCondition {
  readonly name = "no_improvement";
  private readonly patience: number;

  constructor(patience: number) {
    this.patience = patience;
  }
  shouldStop(state: RunState): boolean {
    return state.iterationCount - state.lastFrontierChangeIteration >= this.patience;
  }
}

export class ScoreThresholdStopper implements StopCondition {
  readonly name = "score_threshold";

  constructor(private readonly threshold: number) {}

  shouldStop(state: RunState): boolean {
    return state.candidates.some((candidate) => candidate.aggregateScore >= this.threshold);
  }
}

export class CompositeStopper implements StopCondition {
  readonly name = "composite";

  constructor(private readonly conditions: StopCondition[]) {}

  shouldStop(state: RunState): boolean {
    return this.conditions.some((condition) => condition.shouldStop(state));
  }
}
