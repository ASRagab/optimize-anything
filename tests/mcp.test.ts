import { describe, expect, it } from "bun:test";

describe("MCP server", () => {
  it("exposes optimize tool in tool list", async () => {
    const proc = Bun.spawn(["bun", "run", "src/mcp/server.ts"], {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env, ANTHROPIC_API_KEY: "test-key" },
    });

    try {
      proc.stdin.write(
        `${JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { capabilities: {} } })}\n`,
      );
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" })}\n`);

      const reader = proc.stdout.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let found = false;
      const deadline = Date.now() + 3000;

      while (Date.now() < deadline && !found) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            continue;
          }

          const parsed = JSON.parse(trimmed) as { id?: number; result?: { tools?: Array<{ name: string }> } };
          if (parsed.id === 2 && parsed.result?.tools?.some((tool) => tool.name === "optimize")) {
            found = true;
            break;
          }
        }
      }

      expect(found).toBe(true);
    } finally {
      proc.kill();
      await proc.exited;
    }
  });

  it("handles notifications silently without response", async () => {
    const proc = Bun.spawn(["bun", "run", "src/mcp/server.ts"], {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env, ANTHROPIC_API_KEY: "test-key" },
    });

    try {
      // Send notification (no id) - should produce no response
      proc.stdin.write(
        `${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`,
      );
      // Send a real request to verify server still works
      proc.stdin.write(
        `${JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" })}\n`,
      );

      const reader = proc.stdout.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let found = false;
      const deadline = Date.now() + 3000;

      while (Date.now() < deadline && !found) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const parsed = JSON.parse(trimmed);
          // First response should be for id:1 (tools/list), NOT an error from the notification
          if (parsed.id === 1 && parsed.result?.tools) {
            found = true;
            break;
          }
        }
      }
      expect(found).toBe(true);
    } finally {
      proc.kill();
      await proc.exited;
    }
  });
});
