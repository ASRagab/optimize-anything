# Installation Guide

## Prerequisites

| Requirement | Minimum | Check |
|---|---|---|
| Bun | >= 1.0 | `bun --version` |
| ANTHROPIC_API_KEY | Set in env | `echo $ANTHROPIC_API_KEY` |

## Install from Source

```bash
git clone <repo-url>
cd optimize-anything
bun install
```

### Verify Installation

```bash
# Run tests
bun test

# Type check
bun run typecheck

# Build CLI
bun build src/cli/index.ts --outdir dist
```

All three commands should complete without errors.

## MCP Client Configuration

### Claude Desktop (macOS)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "bun",
      "args": ["run", "/absolute/path/to/optimize-anything/src/mcp/server.ts"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Claude Desktop (Linux)

Edit `~/.config/Claude/claude_desktop_config.json` with the same structure as above.

### Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json` with the same structure, using Windows paths:

```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "bun",
      "args": ["run", "C:\\Users\\you\\optimize-anything\\src\\mcp\\server.ts"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Other MCP Clients

Any MCP client that supports stdio transport can use optimize-anything. The server reads JSON-RPC 2.0 from stdin and writes responses to stdout.

```json
{
  "command": "bun",
  "args": ["run", "/path/to/optimize-anything/src/mcp/server.ts"]
}
```

## Verification Checklist

After configuring your MCP client:

1. **Restart the MCP client** to pick up config changes
2. **Check tool listing** — the `optimize` tool should appear
3. **Test with a simple call:**
   ```json
   {
     "seedCandidate": "hello world",
     "evaluatorCommand": "echo '{\"score\": 1}'",
     "maxMetricCalls": 1
   }
   ```
4. **Expected result:** a JSON response with `bestCandidate`, `bestScore`, and `totalMetricCalls`

## Common Setup Errors

| Error | Cause | Fix |
|---|---|---|
| `spawn bun ENOENT` | Bun not in PATH for MCP client | Use absolute path: `/Users/you/.bun/bin/bun` |
| `ANTHROPIC_API_KEY missing` | Env var not passed through | Add `env` block to MCP config |
| `Cannot find module` | Wrong path in `args` | Use absolute path to `src/mcp/server.ts` |
| Server starts but no tools | Config syntax error | Validate JSON with `jq . < config.json` |
| Tool call hangs | Evaluator script not executable | Run `chmod +x evaluator.sh` |

## Uninstall / Rollback

1. Remove the `optimize-anything` entry from your MCP client config file
2. Restart the MCP client
3. Optionally delete the cloned repository: `rm -rf optimize-anything`

No global packages or system-level changes are made during installation.
