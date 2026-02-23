# MCP Protocol Hygiene

> Non-negotiable rules for the optimize-anything MCP server.

## Transport: stdio

The server uses JSON-RPC 2.0 over stdin/stdout. Clients read stdout line-by-line, parsing each line as a JSON-RPC message.

## Rules

### 1. stdout: JSON-RPC only

Every byte written to `process.stdout` **must** be a complete JSON-RPC 2.0 message followed by a newline. No exceptions.

Violations include:
- `console.log()` calls in any code path reachable from the server
- Debug strings, stack traces, or progress text on stdout
- Partial or malformed JSON

**Enforcement:** Protocol regression tests assert every stdout line is valid JSON-RPC.

### 2. stderr: diagnostics and logs

All diagnostic output — debug logs, warnings, progress info — goes to `process.stderr`. Clients may display stderr but never parse it as protocol.

```typescript
// Correct
process.stderr.write("Processing optimization...\n");

// Wrong — breaks protocol
console.log("Processing optimization...");
```

### 3. Notifications: silently consumed

JSON-RPC notifications (messages without `id`) produce **no response**. The server reads them and moves on.

```json
// Client sends (no id):
{"jsonrpc":"2.0","method":"notifications/initialized"}
// Server: no output
```

### 4. Parse errors: valid JSON-RPC error envelope

If a line is not valid JSON, respond with a standard parse error:

```json
{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error"}}
```

### 5. Unknown methods: standard error

If the method is not recognized, respond with method-not-found:

```json
{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}
```

## Implementation Reference

See `src/mcp/server.ts`:

| Behavior | Location |
|---|---|
| JSON-RPC write helper | `writeJson()` — single point of stdout output |
| Notification handling | Line handler checks `request.id`; skips if absent or null |
| Parse error | `catch` block in line handler |
| Method routing | `handleRequest()` with explicit method matching |

## Adding New Capabilities

When adding features (progress notifications, new tools):

1. Never import or call `console.log` in files reachable from `server.ts`
2. Use `writeJson()` for all protocol output
3. Add a protocol regression test for the new behavior
4. Verify with `bun test --grep "mcp"` before merging

## Progress Visibility

The `optimize` tool includes progress snapshots in the result `content` array. Progress is serialized as additional `text` content items appended after the final result.

Progress shape (`ProgressUpdate`):
```json
{
  "phase": "evaluating",
  "iterationIndex": 3,
  "metricCallsUsed": 7,
  "metricCallsBudget": 20,
  "frontierSize": 2,
  "bestScore": 0.82,
  "timestamp": 1708646400000
}
```

Progress is throttled to emit at most once per iteration to avoid output bloat. It does **not** alter the final result payload shape — the first content item remains the optimization result.

## Available Tools

| Tool | Description |
|---|---|
| `optimize` | Run LLM-guided optimization with BYO evaluator |
| `explain_optimization` | Explain why the best candidate won |
| `recommend_budget` | Get advisory budget recommendation |

## Error Codes

| Code | Meaning |
|---|---|
| -32700 | Parse error (invalid JSON) |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32001 | Application error (missing API key, etc.) |
| -32000 | Internal server error |
