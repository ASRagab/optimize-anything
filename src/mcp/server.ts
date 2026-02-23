import { createInterface } from "node:readline";
import { createCommandEvaluator, createHttpEvaluator } from "../core/evaluator.js";
import { AnthropicModel } from "../core/llm.js";
import { optimizeAnything } from "../core/optimizer.js";
import { explainOptimization } from "../core/explain.js";
import { recommendBudget } from "../core/budget.js";
import { selectCurrentBest } from "../core/candidate-selector.js";
import { optimizeToolSchema, explainToolSchema, recommendBudgetToolSchema } from "./schema.js";
import type { ProgressUpdate, OptimizationEvent, CandidateRecord } from "../types.js";

function buildProgressFromEvents(
  events: OptimizationEvent[],
  candidates: CandidateRecord[],
  frontier: number[],
  metricCallsBudget: number,
): ProgressUpdate[] {
  const updates: ProgressUpdate[] = [];
  let metricCalls = 0;
  let currentFrontierSize = 0;
  let bestScore = 0;

  for (const event of events) {
    if (event.type === "evaluation_end") metricCalls++;
    if (event.type === "frontier_updated") {
      currentFrontierSize++;
      const bestIdx = selectCurrentBest(candidates.slice(0, metricCalls));
      if (bestIdx >= 0) bestScore = candidates[bestIdx].aggregateScore;
    }
    if (event.type === "iteration_end" && event.iterationIndex !== undefined) {
      updates.push({
        phase: "evaluating",
        iterationIndex: event.iterationIndex,
        metricCallsUsed: metricCalls,
        metricCallsBudget,
        frontierSize: currentFrontierSize || frontier.length,
        bestScore,
        timestamp: event.timestamp,
      });
    }
  }

  if (updates.length > 0) {
    updates[updates.length - 1].phase = "complete";
  }

  return updates;
}

type JsonRpcRequest = {
  jsonrpc: "2.0";
  id?: number | string;
  method: string;
  params?: Record<string, unknown>;
};

function writeJson(message: unknown): void {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

async function handleRequest(request: JsonRpcRequest): Promise<void> {
  if (request.method === "initialize") {
    writeJson({ jsonrpc: "2.0", id: request.id, result: { protocolVersion: "2024-11-05", capabilities: {} } });
    return;
  }

  if (request.method === "tools/list") {
    writeJson({ jsonrpc: "2.0", id: request.id, result: { tools: [optimizeToolSchema, explainToolSchema, recommendBudgetToolSchema] } });
    return;
  }

  if (request.method === "tools/call") {
    const name = String(request.params?.name ?? "");
    const args = (request.params?.arguments ?? {}) as Record<string, unknown>;

    if (name === "recommend_budget") {
      const seedCandidate = typeof args.seedCandidate === "string" ? args.seedCandidate : "";
      const objective = typeof args.objective === "string" ? args.objective : undefined;
      const datasetSize = typeof args.datasetSize === "number" ? args.datasetSize : 0;
      const rec = recommendBudget({ seedCandidate, objective, datasetSize });
      writeJson({ jsonrpc: "2.0", id: request.id, result: { content: [{ type: "text", text: JSON.stringify(rec, null, 2) }] } });
      return;
    }

    if (name === "explain_optimization") {
      const runResult = args.runResult as { candidates?: CandidateRecord[]; frontier?: number[]; events?: OptimizationEvent[]; bestScore?: number } | undefined;
      if (!runResult?.candidates) {
        writeJson({ jsonrpc: "2.0", id: request.id, error: { code: -32602, message: "runResult with candidates is required" } });
        return;
      }
      const explanation = explainOptimization({
        candidates: runResult.candidates,
        frontier: runResult.frontier ?? [],
        events: runResult.events ?? [],
        bestScore: runResult.bestScore ?? 0,
      });
      writeJson({ jsonrpc: "2.0", id: request.id, result: { content: [{ type: "text", text: JSON.stringify(explanation, null, 2) }] } });
      return;
    }

    if (name !== "optimize") {
      writeJson({ jsonrpc: "2.0", id: request.id, error: { code: -32602, message: "Unknown tool" } });
      return;
    }

    const evaluatorCommand = typeof args.evaluatorCommand === "string" ? args.evaluatorCommand : undefined;
    const evaluatorUrl = typeof args.evaluatorUrl === "string" ? args.evaluatorUrl : undefined;
    const seedCandidate = typeof args.seedCandidate === "string" ? args.seedCandidate : null;
    const objective = typeof args.objective === "string" ? args.objective : undefined;
    const background = typeof args.background === "string" ? args.background : undefined;
    const maxMetricCalls = typeof args.maxMetricCalls === "number" ? args.maxMetricCalls : 20;

    const evaluator = evaluatorCommand
      ? createCommandEvaluator(evaluatorCommand)
      : evaluatorUrl
        ? createHttpEvaluator(evaluatorUrl)
        : null;
    if (!evaluator) {
      writeJson({ jsonrpc: "2.0", id: request.id, error: { code: -32602, message: "Missing evaluator configuration" } });
      return;
    }

    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      writeJson({ jsonrpc: "2.0", id: request.id, error: { code: -32001, message: "ANTHROPIC_API_KEY missing" } });
      return;
    }

    const model = new AnthropicModel({
      apiKey,
      model: "claude-sonnet-4-20250514",
      maxTokens: 1024,
    });

    const result = await optimizeAnything({
      seedCandidate: seedCandidate ?? objective ?? null,
      evaluator,
      model,
      objective,
      background,
      config: { engine: { maxMetricCalls } },
    });

    // Build progress timeline retrospectively from events
    const progressUpdates = buildProgressFromEvents(result.events, result.candidates, result.frontier, maxMetricCalls);

    // Build content array: result first, then progress log
    const content: Array<{ type: string; text: string }> = [
      {
        type: "text",
        text: JSON.stringify(
          {
            bestCandidate: result.bestCandidate,
            bestScore: result.bestScore,
            totalMetricCalls: result.totalMetricCalls,
          },
          null,
          2,
        ),
      },
    ];

    if (progressUpdates.length > 0) {
      content.push({
        type: "text",
        text: JSON.stringify({ progress: progressUpdates }),
      });
    }

    writeJson({
      jsonrpc: "2.0",
      id: request.id,
      result: { content },
    });
    return;
  }

  writeJson({ jsonrpc: "2.0", id: request.id, error: { code: -32601, message: "Method not found" } });
}

if (import.meta.main) {
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on("line", async (line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }

    let request: JsonRpcRequest;
    try {
      request = JSON.parse(trimmed) as JsonRpcRequest;
    } catch {
      writeJson({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } });
      return;
    }

    // Handle notifications (messages without id) silently
    if (request.id === undefined || request.id === null) {
      return;
    }

    try {
      await handleRequest(request);
    } catch (error) {
      writeJson({
        jsonrpc: "2.0",
        id: request.id,
        error: { code: -32000, message: error instanceof Error ? error.message : String(error) },
      });
    }
  });
}
