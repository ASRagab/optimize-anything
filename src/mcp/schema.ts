export const optimizeToolSchema = {
  name: "optimize",
  description: "Run LLM-guided optimization on a text artifact with a BYO evaluator",
  inputSchema: {
    type: "object",
    properties: {
      seedCandidate: { type: "string", description: "Initial text artifact to optimize" },
      evaluatorCommand: {
        type: "string",
        description: "Command to run as evaluator (stdin candidate -> JSON stdout)",
      },
      evaluatorUrl: { type: "string", description: "HTTP URL for evaluator" },
      objective: { type: "string", description: "Natural language objective" },
      background: { type: "string", description: "Domain knowledge and constraints" },
      maxMetricCalls: { type: "number", description: "Maximum evaluator invocations", default: 20 },
    },
    required: [],
    oneOf: [
      { required: ["seedCandidate", "evaluatorCommand"] },
      { required: ["seedCandidate", "evaluatorUrl"] },
      { required: ["objective", "evaluatorCommand"] },
      { required: ["objective", "evaluatorUrl"] },
    ],
  },
} as const;

export const explainToolSchema = {
  name: "explain_optimization",
  description: "Explain why the best candidate won in a completed optimization run",
  inputSchema: {
    type: "object",
    properties: {
      runResult: {
        type: "object",
        description: "The result object from a completed optimize call (with candidates, events, frontier)",
      },
    },
    required: ["runResult"],
  },
} as const;

export const recommendBudgetToolSchema = {
  name: "recommend_budget",
  description: "Get an advisory budget recommendation for an optimization run",
  inputSchema: {
    type: "object",
    properties: {
      seedCandidate: { type: "string", description: "The initial text artifact" },
      objective: { type: "string", description: "Natural language objective" },
      datasetSize: { type: "number", description: "Number of examples in the dataset", default: 0 },
    },
    required: ["seedCandidate"],
  },
} as const;
