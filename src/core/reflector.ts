import { buildReflectorPrompt } from "./proposer.js";
import type { Candidate, LanguageModel, SideInfo } from "../types.js";

export { buildReflectorPrompt };

export async function reflect(
  model: LanguageModel,
  candidate: Candidate,
  scores: Map<string, number>,
  sideInfo: SideInfo[],
): Promise<string> {
  try {
    const prompt = buildReflectorPrompt({ candidate, scores, sideInfo });
    return await model.generate(prompt);
  } catch {
    return "";
  }
}
