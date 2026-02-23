import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { deserializeEvents, serializeEvents } from "./events.js";
import { createRunState } from "./state.js";
import type { CandidateRecord, EvaluationResult, RunState, SideInfo } from "../types.js";

type PersistedCandidateRecord = Omit<CandidateRecord, "scores"> & {
  scores: [string, number][];
};

type PersistedState = {
  candidates: PersistedCandidateRecord[];
  frontier: number[];
  metricCallCount: number;
  iterationCount: number;
  lastFrontierChangeIteration: number;
  startTime: number;
  evaluationCache: [string, EvaluationResult][];
};

function serializeCandidate(record: CandidateRecord): PersistedCandidateRecord {
  return {
    ...record,
    scores: [...record.scores.entries()],
    sideInfo: record.sideInfo as SideInfo[],
  };
}

function deserializeCandidate(record: PersistedCandidateRecord): CandidateRecord {
  return {
    ...record,
    scores: new Map(record.scores),
  };
}

export async function saveState(state: RunState, runDir: string): Promise<void> {
  await mkdir(runDir, { recursive: true });

  const stateFile = join(runDir, "state.json");
  const eventsFile = join(runDir, "events.jsonl");

  const persisted: PersistedState = {
    candidates: state.candidates.map(serializeCandidate),
    frontier: [...state.frontier],
    metricCallCount: state.metricCallCount,
    iterationCount: state.iterationCount,
    lastFrontierChangeIteration: state.lastFrontierChangeIteration,
    startTime: state.startTime,
    evaluationCache: [...state.evaluationCache.entries()],
  };

  await writeFile(stateFile, JSON.stringify(persisted, null, 2), "utf8");
  await writeFile(eventsFile, serializeEvents(state.events), "utf8");
}

export async function loadState(runDir: string): Promise<RunState> {
  const stateFile = join(runDir, "state.json");
  const eventsFile = join(runDir, "events.jsonl");

  const [rawState, rawEvents] = await Promise.all([
    readFile(stateFile, "utf8"),
    readFile(eventsFile, "utf8"),
  ]);

  const parsed = JSON.parse(rawState) as PersistedState;
  const state = createRunState();
  state.candidates = parsed.candidates.map(deserializeCandidate);
  state.frontier = new Set(parsed.frontier);
  state.metricCallCount = parsed.metricCallCount;
  state.iterationCount = parsed.iterationCount;
  state.lastFrontierChangeIteration = parsed.lastFrontierChangeIteration;
  state.startTime = parsed.startTime;
  state.events = deserializeEvents(rawEvents);
  state.evaluationCache = new Map(parsed.evaluationCache);
  return state;
}
