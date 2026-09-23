---
name: analyze
description: Discover quality dimensions for an artifact and objective
---
When running in Codex, pass `--analysis-backend codex`; in Claude Code, pass
`--analysis-backend claude`. A subscription backend may omit `--judge-model`.
Unknown hosts use the existing API model. Announce possible same-vendor billed
API fallback, or pass `--no-api-fallback` when it is not acceptable.

# analyze

Use an LLM to discover relevant quality dimensions for a given artifact and optimization objective. Returns dimensions with suggested weights as intake JSON.

## Usage

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" analyze SEED_FILE --judge-model openai/gpt-5.6-luna --objective "Quality"
```

## Example

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" analyze my-prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Score for clarity and persuasiveness"
```

In Codex or Claude Code, replace `--judge-model ...` with
`--analysis-backend codex` or `--analysis-backend claude`, respectively.

## Next Step: optimize with discovered dimensions
After dimension discovery, proceed directly to optimization using the returned `intake_json`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" optimize my-prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Score for clarity and persuasiveness" \
  --intake-json '<paste intake_json from analyze>' \
  --budget 50 --diff --run-dir runs/ --early-stop
```

See [README](../README.md) for full flag documentation.
