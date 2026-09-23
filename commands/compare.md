---
name: compare
description: Side-by-side comparison of two artifacts using composed score calls
---
When comparison uses LLM scoring, select the current host explicitly:
`--judge-backend codex` in Codex or `--judge-backend claude` in Claude Code.
Unknown hosts keep API defaults. Announce possible same-vendor billed API
fallback, or add `--no-api-fallback` to prohibit it.
Compare two artifacts with the same scoring setup by composing existing `score` calls.

## Usage
`/optimize-anything:compare <original> <optimized> --objective "..." [--judge-model ...]`

## Procedure
1. Score the original artifact:
   - `"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" score <original> --judge-model <model> --objective "..." [--intake-json ...]`
2. Score the optimized artifact with the exact same evaluator setup.
3. Present side-by-side:
   - Overall score for each artifact
   - Per-dimension diagnostics (shared keys)
   - Overall delta (optimized - original)
4. Show a text diff between original and optimized.
5. Highlight:
   - **Improvements**: dimensions with positive delta
   - **Regressions**: dimensions with negative delta
