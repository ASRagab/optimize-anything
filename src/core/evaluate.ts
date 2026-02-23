import { normalizeEvalResult, hashEvalKey, captureLog } from "./asi.js";
import { cacheResult, getCacheKey, getCachedResult } from "./state.js";
import { selectMinibatch } from "./candidate-selector.js";
import type {
  Candidate,
  CandidateRecord,
  EvaluationContext,
  Evaluator,
  LanguageModel,
  RunState,
  SideInfo,
} from "../types.js";

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export async function retryGenerate(
  model: LanguageModel,
  prompt: string,
  options: { maxRetries?: number; baseDelay?: number } = {},
): Promise<string | null> {
  const maxRetries = options.maxRetries ?? 3;
  const baseDelay = options.baseDelay ?? 1000;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await model.generate(prompt);
    } catch {
      if (attempt === maxRetries) return null;
      await new Promise((r) => setTimeout(r, baseDelay * 2 ** attempt));
    }
  }

  return null;
}

export type EvaluateCandidateOptions<E = unknown> = {
  evaluator: Evaluator<E>;
  objective?: string;
  background?: string;
  dataset: E[];
  state: RunState;
  maxMetricCalls: number;
  seed: number;
};

export async function evaluateCandidate<E = unknown>(
  candidate: Candidate,
  iterationIndex: number,
  opts: EvaluateCandidateOptions<E>,
): Promise<CandidateRecord> {
  const { state, dataset, maxMetricCalls, seed } = opts;
  const examples =
    dataset.length > 0 ? selectMinibatch(dataset, 2, seed + iterationIndex) : [undefined as E | undefined];
  const scoreMap = new Map<string, number>();
  const allSideInfo: SideInfo[] = [];
  const logger = captureLog();

  for (let i = 0; i < examples.length; i++) {
    const example = examples[i];
    const metricKey = example !== undefined ? hashEvalKey("", example) : "score";
    const key = getCacheKey(candidate, example);
    const cached = getCachedResult(state, key);
    if (cached) {
      const normalizedCached = normalizeEvalResult(cached);
      scoreMap.set(metricKey, normalizedCached.score);
      allSideInfo.push(normalizedCached.sideInfo ?? {});
      continue;
    }

    if (state.metricCallCount >= maxMetricCalls) break;

    const raw = await opts.evaluator({
      candidate,
      example,
      objective: opts.objective,
      background: opts.background,
      log: logger.log,
    } as EvaluationContext<E>);

    const normalized = normalizeEvalResult(raw);
    cacheResult(state, key, normalized);
    state.metricCallCount += 1;
    scoreMap.set(metricKey, normalized.score);
    allSideInfo.push(normalized.sideInfo ?? {});
  }

  if (logger.getLog()) {
    allSideInfo.unshift({ log: logger.getLog() });
  }

  return {
    candidate,
    parentIndex: null,
    scores: scoreMap,
    aggregateScore: average([...scoreMap.values()]),
    sideInfo: allSideInfo,
    metricCallIndex: state.metricCallCount,
  };
}
