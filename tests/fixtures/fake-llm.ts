import type { LanguageModel } from "../../src/types.js";

export function createFakeLlm(responses: string[]): LanguageModel {
  let i = 0;
  return {
    async generate() {
      return responses[i++] ?? responses[responses.length - 1] ?? "";
    },
  };
}
