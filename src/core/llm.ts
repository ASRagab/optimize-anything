import Anthropic from "@anthropic-ai/sdk";
import type { LanguageModel } from "../types.js";

type AnthropicModelOptions = {
  apiKey: string;
  model: string;
  maxTokens: number;
};

export class AnthropicModel implements LanguageModel {
  private client: Anthropic;
  private model: string;
  private maxTokens: number;

  constructor(options: AnthropicModelOptions) {
    this.client = new Anthropic({ apiKey: options.apiKey });
    this.model = options.model;
    this.maxTokens = options.maxTokens;
  }

  async generate(prompt: string, options?: { signal?: AbortSignal }): Promise<string> {
    const response = await this.client.messages.create(
      {
        model: this.model,
        max_tokens: this.maxTokens,
        messages: [{ role: "user", content: prompt }],
      },
      { signal: options?.signal },
    );

    const textBlock = response.content.find((item) => item.type === "text");
    if (!textBlock || textBlock.type !== "text") {
      return "";
    }

    return textBlock.text;
  }
}
