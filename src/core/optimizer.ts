import { buildProposerPrompt, parseProposedCandidate } from "./proposer.js";
import { MaxMetricCallsStopper } from "./stop-conditions.js";
import { createRunState, addCandidate } from "./state.js";
import { saveState, loadState } from "./persistence.js";
import { selectCurrentBest, selectFromFrontier } from "./candidate-selector.js";
import { evaluateCandidate, retryGenerate } from "./evaluate.js";
import { EventEmitter } from "./events.js";
import { reflect } from "./reflector.js";
import type {
  Candidate,
  EventCallback,
  Evaluator,
  LanguageModel,
  OptimizeConfig,
  OptimizeResult,
  OptimizationEvent,
  StopCondition,
} from "../types.js";

type OptimizeOptions<E = unknown> = {
  seedCandidate: Candidate | null;
  evaluator: Evaluator<E>;
  model: LanguageModel;
  retryBaseDelay?: number;
  dataset?: E[];
  valset?: E[];
  objective?: string;
  background?: string;
  config?: OptimizeConfig;
  stopConditions?: StopCondition[];
  onEvent?: EventCallback;
};


function applyMutation(candidate: Candidate, rawMutation: string, component?: string): Candidate {
  if (typeof candidate === "string") {
    return rawMutation;
  }

  const keys = Object.keys(candidate);
  if (keys.length === 0) {
    return rawMutation;
  }

  const target = component && candidate[component] !== undefined ? component : keys[0];
  return {
    ...candidate,
    [target]: rawMutation,
  };
}

export async function optimizeAnything<E = unknown>(opts: OptimizeOptions<E>): Promise<OptimizeResult> {
  if (!opts.seedCandidate) {
    throw new Error("seedCandidate is required in v0");
  }

  const state = createRunState();
  const maxMetricCalls = opts.config?.engine?.maxMetricCalls ?? 20;
  const maxIterations = Math.max(1, maxMetricCalls * 2);
  const seed = opts.config?.engine?.seed ?? 42;
  const stopConditions = opts.stopConditions ?? [new MaxMetricCallsStopper(maxMetricCalls)];
  const dataset = opts.dataset ?? [];
  const reflectionEnabled = opts.config?.reflection?.enabled === true;
  const reflectionModel = opts.config?.reflection?.reflectionModel ?? opts.model;

  const evalOpts = { evaluator: opts.evaluator, objective: opts.objective, background: opts.background, dataset, state, maxMetricCalls, seed };
  const emitter = new EventEmitter();
  if (opts.onEvent) emitter.on(opts.onEvent);
  const emitEvent = (event: OptimizationEvent) => { state.events.push(event); emitter.emit(event); };

  let initialRecord;
  const resumeFrom = opts.config?.tracking?.resumeFrom;
  if (resumeFrom) {
    const loaded = await loadState(resumeFrom);
    Object.assign(state, loaded);
    initialRecord = state.candidates[0];
  } else {
    emitEvent({ type: "optimization_start", timestamp: Date.now() });
    emitEvent({ type: "evaluation_start", timestamp: Date.now() });
    initialRecord = await evaluateCandidate(opts.seedCandidate, 0, evalOpts);
    const { frontierChanged: seedFrontierChanged } = addCandidate(state, initialRecord);
    emitEvent({
      type: "evaluation_end",
      timestamp: Date.now(),
      candidateIndex: 0,
    });
    if (seedFrontierChanged) {
      emitEvent({ type: "frontier_updated", timestamp: Date.now() });
    }
  }

  let componentCursor = 0;
  let lastReflection = "";
  while (!stopConditions.some((condition) => condition.shouldStop(state))) {
    if (state.iterationCount >= maxIterations) {
      break;
    }

    emitEvent({
      type: "iteration_start",
      timestamp: Date.now(),
      iterationIndex: state.iterationCount,
    });

    const baseIndex = selectFromFrontier(state.candidates, state.frontier, seed + state.iterationCount);
    if (baseIndex < 0) {
      break;
    }
    const base = state.candidates[baseIndex];

    let componentToMutate: string | undefined;
    if (typeof base.candidate !== "string") {
      const components = Object.keys(base.candidate);
      if (components.length > 0) {
        componentToMutate = components[componentCursor % components.length];
        componentCursor += 1;
      }
    }

    const prompt = buildProposerPrompt({
      currentCandidate: base.candidate,
      scores: base.scores,
      sideInfo: base.sideInfo,
      objective: opts.objective,
      background: opts.background,
      constraints: [],
      componentToMutate,
      historySummary: lastReflection || undefined,
    });

    const llmResponse = await retryGenerate(opts.model, prompt, { baseDelay: opts.retryBaseDelay ?? 1000 });
    if (llmResponse === null) {
      emitEvent({
        type: "error",
        timestamp: Date.now(),
        iterationIndex: state.iterationCount,
        data: { reason: "llm_failure", message: "All LLM retries exhausted" },
      });
      state.iterationCount += 1;
      continue;
    }

    const proposedText = parseProposedCandidate(llmResponse);
    const proposedCandidate = applyMutation(base.candidate, proposedText, componentToMutate);

    emitEvent({
      type: "candidate_proposed",
      timestamp: Date.now(),
      iterationIndex: state.iterationCount,
      data: { parentIndex: baseIndex },
    });

    emitEvent({ type: "evaluation_start", timestamp: Date.now(), iterationIndex: state.iterationCount });
    const nextRecord = await evaluateCandidate(proposedCandidate, state.iterationCount + 1, evalOpts);
    nextRecord.parentIndex = baseIndex;
    const { index: nextIndex, frontierChanged } = addCandidate(state, nextRecord);

    emitEvent({
      type: "evaluation_end",
      timestamp: Date.now(),
      candidateIndex: nextIndex,
      iterationIndex: state.iterationCount,
    });

    if (frontierChanged) {
      emitEvent({ type: "frontier_updated", timestamp: Date.now(), iterationIndex: state.iterationCount });
    }
    emitEvent({
      type: frontierChanged ? "candidate_accepted" : "candidate_rejected",
      timestamp: Date.now(),
      candidateIndex: nextIndex,
      iterationIndex: state.iterationCount,
    });

    if (reflectionEnabled) {
      lastReflection = await reflect(reflectionModel, proposedCandidate, nextRecord.scores, nextRecord.sideInfo);
    }

    if (opts.config?.tracking?.runDir) {
      try {
        await saveState(state, opts.config.tracking.runDir);
      } catch (error) {
        emitEvent({
          type: "error",
          timestamp: Date.now(),
          iterationIndex: state.iterationCount,
          data: {
            reason: "persistence_failure",
            message: error instanceof Error ? error.message : String(error),
          },
        });
      }
    }

    emitEvent({
      type: "iteration_end",
      timestamp: Date.now(),
      iterationIndex: state.iterationCount,
    });
    state.iterationCount += 1;

    if (state.metricCallCount >= maxMetricCalls) {
      break;
    }
  }

  const triggeredStopper = stopConditions.find((c) => c.shouldStop(state));
  if (triggeredStopper) {
    emitEvent({
      type: "stop_condition_met",
      timestamp: Date.now(),
      data: { condition: triggeredStopper.name },
    });
  }

  emitEvent({
    type: "optimization_end",
    timestamp: Date.now(),
  });

  const bestIndex = selectCurrentBest(state.candidates);
  const best = bestIndex >= 0 ? state.candidates[bestIndex] : initialRecord;

  return {
    bestCandidate: best.candidate,
    bestScore: best.aggregateScore,
    candidates: state.candidates,
    frontier: [...state.frontier],
    totalMetricCalls: state.metricCallCount,
    events: state.events,
    runDir: opts.config?.tracking?.runDir,
  };
}
