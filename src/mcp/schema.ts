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
