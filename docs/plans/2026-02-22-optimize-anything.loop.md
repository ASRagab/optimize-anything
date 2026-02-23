# Optimize Anything — Ultrawork Implementation Loop

This loop executes `docs/plans/2026-02-22-optimize-anything.md` in strict gate order.

## Loop Rules

1. Execute exactly one task at a time.
2. Do not start the next task until the current gate passes.
3. After each task:
   - run the gate commands,
   - record pass/fail evidence,
   - run simplification review (file size + unnecessary complexity check).
4. If a gate fails: fix root cause, re-run gate, and only then continue.

## Execution Checklist

- [x] Task 0 -> Gate 0
- [x] Task 1 -> Gate 1
- [x] Task 2 -> Gate 2
- [x] Task 3 -> Gate 3
- [x] Task 4 -> Gate 4
- [x] Task 5 -> Gate 5 (CRITICAL)
- [x] Task 6 -> Gate 6
- [x] Task 7 -> Gate 7
- [x] Task 8 -> Gate 8
- [x] Task 9 -> Gate 9 (FINAL)

## Gate Evidence Log Template

For each task, append:

```text
Task: <n>
Date: <YYYY-MM-DD>
Commands:
- <cmd1>
- <cmd2>
Result:
- PASS | FAIL
Notes:
- <key observations>
```

## Immediate Start Point

Start with Task 0 from `docs/plans/2026-02-22-optimize-anything.md`.

## Gate Evidence Log

```text
Task: 0
Date: 2026-02-22
Commands:
- bun install
- bun test
- bun run typecheck
Result:
- PASS
Notes:
- Implemented scaffold and core type definitions per Task 0.
- Gate 0 passed after fixing Bun config compatibility and adding bun-types for TypeScript test typing.
- Simplification review: all new files are concise; largest file `src/types.ts` is 110 lines.
```

```text
Task: 1
Date: 2026-02-22
Commands:
- bun test tests/evaluator.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Implemented ASI normalization, log capture, command evaluator, and HTTP evaluator.
- Evaluator tests cover number/object normalization, log capture, command execution, error handling, and HTTP post/parse flow.
- Simplification review: largest Task 1 file is `src/core/evaluator.ts` at 108 lines.
```

```text
Task: 2
Date: 2026-02-22
Commands:
- bun test tests/stop-conditions.test.ts tests/events.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Added composable stop conditions (budget, timeout, no-improvement, score-threshold, composite).
- Added event emitter plus JSONL serialize/deserialize utilities.
- Simplification review: largest Task 2 file is `src/core/stop-conditions.ts` at 66 lines.
```

```text
Task: 3
Date: 2026-02-22
Commands:
- bun test tests/pareto.test.ts tests/state.test.ts tests/persistence.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Implemented Pareto dominance/frontier ops, run state management, deterministic cache keys, and state persistence.
- Persistence now saves `state.json` and `events.jsonl` and supports load/resume reconstruction.
- Simplification review: largest Task 3 file is `tests/pareto.test.ts` at 88 lines.
```

```text
Task: 4
Date: 2026-02-22
Commands:
- bun test tests/proposer.test.ts tests/candidate-selector.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Added Anthropic language model wrapper, proposer/reflector prompt builders, candidate parser, and selection helpers.
- Added fake LLM fixture for deterministic tests and covered candidate/ASI/objective/multi-component prompt behavior.
- Simplification review: largest Task 4 file is `src/core/proposer.ts` at 87 lines.
```

```text
Task: 5
Date: 2026-02-22
Commands:
- bun test tests/optimizer.test.ts
- bun test
- bun run typecheck
- wc -l src/core/*.ts
Result:
- PASS
Notes:
- Implemented `optimizeAnything()` integrating state, frontier, evaluator cache, proposer, selection, events, and optional persistence.
- Added deterministic golden trajectory test for single-task event ordering.
- Simplification review: all `src/core/*.ts` files are <= 300 lines; largest is `src/core/optimizer.ts` at 233 lines.
```

```text
Task: 6
Date: 2026-02-22
Commands:
- bun test tests/cli.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Implemented CLI arg parsing plus optimize command runner in `src/cli/index.ts`.
- Added CLI arg parsing tests for evaluator command, max metric calls, objective, and background.
- Simplification review: largest Task 6 file is `src/cli/index.ts` at 122 lines.
```

```text
Task: 7
Date: 2026-02-22
Commands:
- bun test tests/mcp.test.ts
- bun run typecheck
Result:
- PASS
Notes:
- Implemented MCP optimize tool schema and stdio JSON-RPC server with `initialize`, `tools/list`, and `tools/call` handling.
- Added MCP integration test that spawns the server and verifies `tools/list` includes `optimize`.
- Simplification review: largest Task 7 file is `src/mcp/server.ts` at 127 lines.
```

```text
Task: 8
Date: 2026-02-22
Commands:
- node -e "JSON.parse(require('node:fs').readFileSync('.mcp.json','utf8')); console.log('valid-json')"
- bun run --bun tsc --noEmit
Result:
- PASS
Notes:
- Added `.mcp.json` stdio server wiring for Claude Code plugin auto-start.
- Added `SKILL.md` with evaluator contract, safety warnings, usage examples, and optimization mode descriptions.
- Simplification review: packaging files are minimal and focused on required operator guidance.
```

```text
Task: 9
Date: 2026-02-22
Commands:
- bun test
- bun run typecheck
- bun test tests/live/
- bun test tests/mcp.test.ts
- wc -l src/**/*.ts
Result:
- PASS
Notes:
- Full suite passed after completing tasks 0-8; MCP test and live smoke suite command both executed successfully.
- File-size audit passed: no source file exceeds 300 lines; largest is `src/core/optimizer.ts` at 233 lines.
- Conceptual review complete: each `src/core/*.ts` module maps to the GEPA concept table in the implementation plan.
```
