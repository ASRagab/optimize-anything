import { captureLog, normalizeEvalResult } from "./asi.js";
import type { EvaluationResult, Evaluator } from "../types.js";

type CommandEvaluatorOptions = {
  timeoutMs?: number;
};

type HttpEvaluatorOptions = {
  timeoutMs?: number;
  headers?: Record<string, string>;
};

function withTimeout(signal: AbortSignal | undefined, timeoutMs: number | undefined): AbortSignal | undefined {
  if (signal && timeoutMs && timeoutMs > 0) {
    return AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]);
  }
  if (signal) {
    return signal;
  }
  if (timeoutMs && timeoutMs > 0) {
    return AbortSignal.timeout(timeoutMs);
  }
  return undefined;
}

export function createCommandEvaluator(command: string, opts: CommandEvaluatorOptions = {}): Evaluator {
  return async (ctx) => {
    const signal = withTimeout(ctx.signal, opts.timeoutMs);
    const payload = JSON.stringify({
      candidate: ctx.candidate,
      example: ctx.example,
      objective: ctx.objective,
      background: ctx.background,
    });

    const proc = Bun.spawn({
      cmd: ["bash", "-c", command],
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      signal,
    });

    proc.stdin.write(payload);
    proc.stdin.end();

    const [stdoutText, stderrText, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);

    if (exitCode !== 0) {
      throw new Error(`Evaluator command failed with exit code ${exitCode}: ${stderrText.trim()}`);
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(stdoutText);
    } catch (error) {
      throw new Error(`Evaluator command returned invalid JSON: ${(error as Error).message}`);
    }

    const normalized = normalizeEvalResult(parsed as EvaluationResult | number);
    const sideInfo = {
      ...(normalized.sideInfo ?? {}),
      ...(stderrText.trim() ? { stderr: stderrText.trim() } : {}),
    };

    return {
      score: normalized.score,
      sideInfo,
    };
  };
}

export function createHttpEvaluator(url: string, opts: HttpEvaluatorOptions = {}): Evaluator {
  return async (ctx) => {
    const signal = withTimeout(ctx.signal, opts.timeoutMs);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(opts.headers ?? {}),
      },
      body: JSON.stringify({
        candidate: ctx.candidate,
        example: ctx.example,
        objective: ctx.objective,
        background: ctx.background,
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP evaluator failed with status ${response.status}`);
    }

    const raw = (await response.json()) as EvaluationResult | number;
    const normalized = normalizeEvalResult(raw);
    return {
      score: normalized.score,
      sideInfo: normalized.sideInfo ?? {},
    };
  };
}

export { captureLog, normalizeEvalResult };
