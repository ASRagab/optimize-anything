import { hashEvalKey } from "./asi.js";
import { insertIntoFrontier } from "./pareto.js";
import type { Candidate, CandidateRecord, EvaluationResult, RunState } from "../types.js";

export function createRunState(): RunState {
  return {
    candidates: [],
    frontier: new Set<number>(),
    metricCallCount: 0,
    iterationCount: 0,
    lastFrontierChangeIteration: 0,
    startTime: Date.now(),
    events: [],
    evaluationCache: new Map<string, EvaluationResult>(),
  };
}

export function addCandidate(state: RunState, record: CandidateRecord): { index: number; frontierChanged: boolean } {
  state.candidates.push(record);
  const index = state.candidates.length - 1;
  const frontierChanged = insertIntoFrontier(index, state.candidates, state.frontier);
  if (frontierChanged) {
    state.lastFrontierChangeIteration = state.iterationCount;
  }
  return { index, frontierChanged };
}

export function getCacheKey(candidate: Candidate, example?: unknown): string {
  return hashEvalKey(candidate, example);
}

export function getCachedResult(state: RunState, key: string): EvaluationResult | undefined {
  return state.evaluationCache.get(key);
}

export function cacheResult(state: RunState, key: string, result: EvaluationResult): void {
  state.evaluationCache.set(key, result);
}
