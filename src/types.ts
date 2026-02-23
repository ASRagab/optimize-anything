export type Candidate = string | Record<string, string>;

export type SideInfo = {
  log?: string;
  stdout?: string;
  stderr?: string;
  scores?: Record<string, number>;
} & Record<string, unknown>;

export type EvaluationResult = {
  score: number;
  sideInfo?: SideInfo;
};

export type EvaluationContext<E = unknown> = {
  candidate: Candidate;
  example?: E;
  objective?: string;
  background?: string;
  signal?: AbortSignal;
  log: (msg: string) => void;
};

export type Evaluator<E = unknown> = (
  ctx: EvaluationContext<E>,
) => Promise<EvaluationResult | number>;

export type EngineConfig = {
  maxMetricCalls?: number;
  parallel?: boolean;
  maxWorkers?: number;
  seed?: number;
};

export type ReflectionConfig = {
  enabled?: boolean;
  reflectionLm?: string;
  reflectionModel?: LanguageModel;
  minibatchSize?: number;
};

export type TrackingConfig = {
  runDir?: string;
  resumeFrom?: string;
};

export type OptimizeConfig = {
  engine?: EngineConfig;
  reflection?: ReflectionConfig;
  tracking?: TrackingConfig;
};

export interface StopCondition {
  shouldStop(state: RunState): boolean;
  readonly name: string;
}

export type EventType =
  | "optimization_start"
  | "optimization_end"
  | "iteration_start"
  | "iteration_end"
  | "candidate_proposed"
  | "candidate_accepted"
  | "candidate_rejected"
  | "evaluation_start"
  | "evaluation_end"
  | "frontier_updated"
  | "stop_condition_met"
  | "error";

export type OptimizationEvent = {
  type: EventType;
  timestamp: number;
  iterationIndex?: number;
  candidateIndex?: number;
  data?: Record<string, unknown>;
};

export type EventCallback = (event: OptimizationEvent) => void;

export type CandidateRecord = {
  candidate: Candidate;
  parentIndex: number | null;
  scores: Map<string, number>;
  aggregateScore: number;
  sideInfo: SideInfo[];
  metricCallIndex: number;
};

export type RunState = {
  candidates: CandidateRecord[];
  frontier: Set<number>;
  metricCallCount: number;
  iterationCount: number;
  lastFrontierChangeIteration: number;
  startTime: number;
  events: OptimizationEvent[];
  evaluationCache: Map<string, EvaluationResult>;
};

export type OptimizeResult = {
  bestCandidate: Candidate;
  bestScore: number;
  candidates: CandidateRecord[];
  frontier: number[];
  totalMetricCalls: number;
  events: OptimizationEvent[];
  runDir?: string;
};

export interface LanguageModel {
  generate(prompt: string, options?: { signal?: AbortSignal }): Promise<string>;
}
