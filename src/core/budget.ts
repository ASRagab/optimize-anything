import type { BudgetRecommendation } from "../types.js";

type BudgetInput = {
  seedCandidate: string;
  objective?: string;
  datasetSize?: number;
};

function classifyComplexity(text: string): "simple" | "moderate" | "complex" {
  const words = text.split(/\s+/).filter(Boolean).length;
  if (words <= 20) return "simple";
  if (words <= 100) return "moderate";
  return "complex";
}

const BASE_BUDGET = 10;
const COMPLEXITY_MULTIPLIERS: Record<string, number> = {
  simple: 1,
  moderate: 1.5,
  complex: 2,
};

export function recommendBudget(input: BudgetInput): BudgetRecommendation {
  const candidateComplexity = classifyComplexity(input.seedCandidate);
  const objectiveComplexity = input.objective
    ? classifyComplexity(input.objective)
    : "simple";
  const datasetSize = input.datasetSize ?? 0;

  // Compute recommended budget
  let budget = BASE_BUDGET;
  budget *= COMPLEXITY_MULTIPLIERS[candidateComplexity];
  budget *= COMPLEXITY_MULTIPLIERS[objectiveComplexity];

  // Dataset factor: more examples = more budget for generalization
  if (datasetSize > 0) {
    budget *= 1 + Math.log2(Math.max(1, datasetSize)) * 0.25;
  }

  const recommended = Math.round(budget);

  // Confidence based on how much signal we have
  let confidence: "low" | "medium" | "high";
  if (!input.objective && datasetSize === 0) {
    confidence = "low";
  } else if (input.objective && datasetSize > 0) {
    confidence = "high";
  } else {
    confidence = "medium";
  }

  // Build rationale
  const parts: string[] = [];
  parts.push(`Base budget: ${BASE_BUDGET}`);
  parts.push(`Candidate complexity: ${candidateComplexity} (${COMPLEXITY_MULTIPLIERS[candidateComplexity]}x)`);
  parts.push(`Objective complexity: ${objectiveComplexity} (${COMPLEXITY_MULTIPLIERS[objectiveComplexity]}x)`);
  if (datasetSize > 0) {
    parts.push(`Dataset size: ${datasetSize} (${(1 + Math.log2(Math.max(1, datasetSize)) * 0.25).toFixed(2)}x)`);
  }
  parts.push(`Recommended: ${recommended} metric calls`);

  return {
    recommended,
    confidence,
    rationale: parts.join(". ") + ".",
    factors: {
      datasetSize,
      candidateComplexity,
      objectiveComplexity,
    },
  };
}
