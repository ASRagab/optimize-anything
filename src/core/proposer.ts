import type { Candidate, SideInfo } from "../types.js";

type BuildProposerPromptOptions = {
  currentCandidate: Candidate;
  scores: Map<string, number>;
  sideInfo: SideInfo[];
  objective?: string;
  background?: string;
  constraints?: string[];
  componentToMutate?: string;
  historySummary?: string;
};

type BuildReflectorPromptOptions = {
  candidate: Candidate;
  sideInfo: SideInfo[];
  scores: Map<string, number>;
};

function candidateToText(candidate: Candidate, componentToMutate?: string): string {
  if (typeof candidate === "string") {
    return candidate;
  }

  if (componentToMutate && candidate[componentToMutate]) {
    return `${componentToMutate}: ${candidate[componentToMutate]}`;
  }

  return JSON.stringify(candidate, null, 2);
}

function mapToLines(map: Map<string, number>): string {
  return [...map.entries()].map(([k, v]) => `${k}: ${v}`).join("\n");
}

function sideInfoToLines(sideInfo: SideInfo[]): string {
  return sideInfo
    .map((entry) => JSON.stringify(entry))
    .filter((line) => line.length > 0)
    .join("\n");
}

export function buildProposerPrompt(options: BuildProposerPromptOptions): string {
  const candidateText = candidateToText(options.currentCandidate, options.componentToMutate);
  const scoreText = mapToLines(options.scores);
  const asiText = sideInfoToLines(options.sideInfo);
  const constraints = (options.constraints ?? []).join("\n") || "none";

  return [
    "You are improving a candidate artifact.",
    `Objective: ${options.objective ?? "improve score"}`,
    `Background: ${options.background ?? "none"}`,
    options.componentToMutate ? `Component to mutate: ${options.componentToMutate}` : "",
    "Current candidate:",
    candidateText,
    "Scores:",
    scoreText,
    "Actionable side info:",
    asiText,
    "Constraints:",
    constraints,
    options.historySummary ? `History: ${options.historySummary}` : "",
    "Return only the improved candidate.",
  ]
    .filter((line) => line.length > 0)
    .join("\n\n");
}

export function buildReflectorPrompt(options: BuildReflectorPromptOptions): string {
  return [
    "Analyze evaluator feedback and summarize improvement actions.",
    "Candidate:",
    candidateToText(options.candidate),
    "Scores:",
    mapToLines(options.scores),
    "Diagnostics:",
    sideInfoToLines(options.sideInfo),
  ].join("\n\n");
}

export function parseProposedCandidate(llmResponse: string): string {
  const match = llmResponse.match(/```(?:\w+)?\n([\s\S]*?)```/);
  if (match && match[1]) {
    return match[1].trim();
  }
  return llmResponse;
}
