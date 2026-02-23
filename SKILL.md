# optimize-anything

## What optimize-anything does

LLM-guided optimization for text artifacts (prompts, code snippets, configs, and skills) using an iterative propose -> evaluate -> reflect loop.

## Evaluator contract

- Input on stdin: JSON payload with `candidate` and optional `example`, `objective`, `background`.
- Output on stdout: JSON payload `{ "score": number, "sideInfo"?: object }`.
- `score` is a floating-point value where higher is better.
- `sideInfo` can include diagnostics (`stderr`, logs, or sub-scores) to guide next-step improvements.

## Safety warnings

- Evaluator commands run with full shell access under your local user permissions.
- Always set `maxMetricCalls` to cap evaluator/LLM cost.
- Review evaluator scripts before execution; treat them as trusted code only.

## Usage examples

Via MCP tool call:

`optimize({ seedCandidate: "...", evaluatorCommand: "eval.sh", maxMetricCalls: 10 })`

Via CLI:

`bun run src/cli/index.ts optimize --seed seed.txt --evaluator-command eval.sh --max-metric-calls 10`

## Optimization modes

- Single-task mode: optimize against one evaluator objective.
- Multi-task mode: optimize against a dataset/minibatch of examples.
- Generalization mode: optimize toward behavior that transfers across examples and validation checks.
