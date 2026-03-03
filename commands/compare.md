---
name: compare
description: Side-by-side comparison of two artifacts using composed score calls
---
Compare two artifacts with the same scoring setup by composing existing `score` calls.

## Usage
`/optimize-anything:compare <original> <optimized> --objective "..." [--judge-model ...]`

## Procedure
1. Score the original artifact:
   - `optimize-anything score <original> --judge-model <model> --objective "..." [--intake-json ...]`
2. Score the optimized artifact with the exact same evaluator setup.
3. Present side-by-side:
   - Overall score for each artifact
   - Per-dimension diagnostics (shared keys)
   - Overall delta (optimized - original)
4. Show a text diff between original and optimized.
5. Highlight:
   - **Improvements**: dimensions with positive delta
   - **Regressions**: dimensions with negative delta
