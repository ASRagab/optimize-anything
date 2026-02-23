import { describe, expect, it } from "bun:test";
import { readFileSync, existsSync } from "node:fs";

describe("plugin packaging", () => {
  it(".mcp.json is valid JSON with required fields", () => {
    const content = readFileSync(".mcp.json", "utf8");
    const json = JSON.parse(content);
    expect(json.mcpServers).toBeDefined();
    expect(json.mcpServers["optimize-anything"]).toBeDefined();
    expect(json.mcpServers["optimize-anything"].command).toBe("bun");
  });

  it("SKILL.md exists and is non-empty", () => {
    expect(existsSync("SKILL.md")).toBe(true);
    const content = readFileSync("SKILL.md", "utf8");
    expect(content.length).toBeGreaterThan(0);
  });
});
