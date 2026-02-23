import { createInterface } from "node:readline";
import { createCommandEvaluator, createHttpEvaluator } from "../core/evaluator.js";
import { AnthropicModel } from "../core/llm.js";
import { optimizeAnything } from "../core/optimizer.js";
import { optimizeToolSchema } from "./schema.js";

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
    writeJson({ jsonrpc: "2.0", id: request.id, result: { tools: [optimizeToolSchema] } });
    return;
  }

  if (request.method === "tools/call") {
    const name = String(request.params?.name ?? "");
    const args = (request.params?.arguments ?? {}) as Record<string, unknown>;
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

    writeJson({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        content: [
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
        ],
      },
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
