import type { Candidate, EvaluationResult, SideInfo } from "../types.js";

type EvaluatorRawResult = EvaluationResult | number;

export function captureLog(): { log: (msg: string) => void; getLog: () => string } {
  const lines: string[] = [];
  return {
    log(msg: string) {
      lines.push(msg);
    },
    getLog() {
      return lines.join("\n");
    },
  };
}

export function normalizeEvalResult(raw: EvaluatorRawResult): EvaluationResult {
  if (typeof raw === "number") {
    return { score: raw, sideInfo: {} };
  }

  if (!Number.isFinite(raw.score)) {
    throw new Error("Evaluator result must include a finite numeric score");
  }

  return {
    score: raw.score,
    sideInfo: (raw.sideInfo ?? {}) as SideInfo,
  };
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableValue);
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    const out: Record<string, unknown> = {};
    for (const [key, val] of entries) {
      out[key] = stableValue(val);
    }
    return out;
  }
  return value;
}

export function hashEvalKey(candidate: Candidate, example?: unknown): string {
  return JSON.stringify(stableValue({ candidate, example }));
}
