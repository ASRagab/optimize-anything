---
name: score
description: Score a single artifact with an evaluator
---
For an LLM judge, use `--judge-backend codex` in Codex or
`--judge-backend claude` in Claude Code; the subscription model may be omitted.
Do not add a judge backend for command or HTTP evaluators. Announce possible
same-vendor billed API fallback, or add `--no-api-fallback` to prohibit it.

# score

Score a single artifact file using a command evaluator, HTTP evaluator, or LLM judge — without running optimization.

## Usage

```
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" score SEED_FILE --evaluator-command bash eval.sh
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" score SEED_FILE --judge-model openai/gpt-5.6-luna --objective "Score clarity"
```

## Example

```
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" score my-prompt.txt \
  --evaluator-command bash evaluators/clarity.sh

"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" score my-prompt.txt \
  --judge-model openai/gpt-5.6-luna \
  --objective "Score for persuasiveness"
```

See [README](../README.md) for full flag documentation.
