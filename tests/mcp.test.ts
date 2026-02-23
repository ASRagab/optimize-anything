import { describe, expect, it } from "bun:test";

/** Collect stdout lines from the MCP server, ending stdin first to flush output. */
async function collectStdoutLines(
  proc: ReturnType<typeof Bun.spawn>,
  { waitMs = 300 }: { waitMs?: number } = {},
): Promise<string[]> {
  // Give the server time to process, then close stdin to signal EOF
  await Bun.sleep(waitMs);
  const stdin = proc.stdin as import("bun").FileSink;
  stdin.end();

  const output = await new Response(proc.stdout as ReadableStream).text();
  return output
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function spawnMcp() {
  return Bun.spawn(["bun", "run", "src/mcp/server.ts"], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env, ANTHROPIC_API_KEY: "test-key" },
  });
}

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

describe("MCP protocol hygiene", () => {
  it("every stdout line is valid JSON-RPC during normal operation", async () => {
    const proc = spawnMcp();
    try {
      // Send a sequence of mixed requests
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { capabilities: {} } })}\n`);
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" })}\n`);
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 3, method: "unknown/method" })}\n`);

      const lines = await collectStdoutLines(proc, { waitMs: 500 });

      // 3 requests with id -> exactly 3 responses (notification produces none)
      expect(lines.length).toBe(3);
      for (const line of lines) {
        const parsed = JSON.parse(line);
        expect(parsed.jsonrpc).toBe("2.0");
        // Every response must have an id
        expect(parsed.id !== undefined).toBe(true);
        // Every response must have exactly one of result or error
        expect("result" in parsed || "error" in parsed).toBe(true);
        expect("result" in parsed && "error" in parsed).toBe(false);
      }
    } finally {
      proc.kill();
      await proc.exited;
    }
  });

  it("returns standards-compliant parse error for invalid JSON", async () => {
    const proc = spawnMcp();
    try {
      proc.stdin.write("this is not json\n");

      const lines = await collectStdoutLines(proc);

      expect(lines.length).toBe(1);
      const parsed = JSON.parse(lines[0]);
      expect(parsed.jsonrpc).toBe("2.0");
      expect(parsed.id).toBeNull();
      expect(parsed.error.code).toBe(-32700);
      expect(parsed.error.message).toContain("Parse error");
    } finally {
      proc.kill();
      await proc.exited;
    }
  });

  it("returns method-not-found for unknown methods", async () => {
    const proc = spawnMcp();
    try {
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 42, method: "bogus/method" })}\n`);

      const lines = await collectStdoutLines(proc);

      expect(lines.length).toBe(1);
      const parsed = JSON.parse(lines[0]);
      expect(parsed.jsonrpc).toBe("2.0");
      expect(parsed.id).toBe(42);
      expect(parsed.error.code).toBe(-32601);
      expect(parsed.error.message).toContain("Method not found");
    } finally {
      proc.kill();
      await proc.exited;
    }
  });

  it("returns invalid-params for unknown tool name", async () => {
    const proc = spawnMcp();
    try {
      proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "nonexistent", arguments: {} } })}\n`);

      const lines = await collectStdoutLines(proc);

      expect(lines.length).toBe(1);
      const parsed = JSON.parse(lines[0]);
      expect(parsed.jsonrpc).toBe("2.0");
      expect(parsed.id).toBe(5);
      expect(parsed.error.code).toBe(-32602);
    } finally {
      proc.kill();
      await proc.exited;
    }
  });
});
