import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createCommandEvaluator, createHttpEvaluator } from "../core/evaluator.js";
import { AnthropicModel } from "../core/llm.js";
import { optimizeAnything } from "../core/optimizer.js";

export type CliArgs = {
  command: string;
  seed?: string;
  output?: string;
  runDir?: string;
  evaluatorCommand?: string;
  evaluatorUrl?: string;
  objective?: string;
  background?: string;
  maxMetricCalls?: number;
};

export function parseArgs(argv: string[]): CliArgs {
  const command = argv[0] ?? "";
  const args: CliArgs = { command };

  for (let i = 1; i < argv.length; i++) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--seed") {
      args.seed = value;
      i++;
    } else if (key === "--output") {
      args.output = value;
      i++;
    } else if (key === "--run-dir") {
      args.runDir = value;
      i++;
    } else if (key === "--evaluator-command") {
      args.evaluatorCommand = value;
      i++;
    } else if (key === "--evaluator-url") {
      args.evaluatorUrl = value;
      i++;
    } else if (key === "--objective") {
      args.objective = value;
      i++;
    } else if (key === "--background") {
      args.background = value;
      i++;
    } else if (key === "--max-metric-calls") {
      args.maxMetricCalls = Number(value);
      i++;
    }
  }

  return args;
}

async function runCli(rawArgv: string[]): Promise<void> {
  const args = parseArgs(rawArgv);
  if (args.command !== "optimize") {
    throw new Error("Only 'optimize' command is supported");
  }

  if (args.maxMetricCalls !== undefined && Number.isNaN(args.maxMetricCalls)) {
    throw new Error("--max-metric-calls must be a number");
  }

  if (!args.seed && !args.objective) {
    throw new Error("Provide --seed or --objective");
  }

  let seedCandidate: string | null = null;
  if (args.seed) {
    try {
      seedCandidate = await readFile(args.seed, "utf8");
    } catch (error) {
      throw new Error(`Seed file not found: ${args.seed}`);
    }
  } else {
    seedCandidate = args.objective ?? null;
  }
  if (!seedCandidate) {
    throw new Error("No seed candidate available");
  }

  const evaluator = args.evaluatorCommand
    ? createCommandEvaluator(args.evaluatorCommand)
    : args.evaluatorUrl
      ? createHttpEvaluator(args.evaluatorUrl)
      : null;

  if (!evaluator) {
    throw new Error("Provide --evaluator-command or --evaluator-url");
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY is required");
  }

  const model = new AnthropicModel({
    apiKey,
    model: "claude-sonnet-4-20250514",
    maxTokens: 1024,
  });

  const runDir = args.runDir ?? `./runs/${Date.now()}`;
  await mkdir(runDir, { recursive: true });

  const result = await optimizeAnything({
    seedCandidate,
    evaluator,
    model,
    objective: args.objective,
    background: args.background,
    config: {
      engine: { maxMetricCalls: args.maxMetricCalls ?? 20 },
      tracking: { runDir },
    },
  });

  const outputText = typeof result.bestCandidate === "string" ? result.bestCandidate : JSON.stringify(result.bestCandidate, null, 2);
  if (args.output) {
    await writeFile(args.output, outputText, "utf8");
  } else {
    process.stdout.write(outputText + "\n");
  }

  await writeFile(join(runDir, "result.json"), JSON.stringify(result, null, 2), "utf8");
}

if (import.meta.main) {
  runCli(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
}
