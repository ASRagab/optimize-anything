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

- [ ] Task 0 -> Gate 0
- [ ] Task 1 -> Gate 1
- [ ] Task 2 -> Gate 2
- [ ] Task 3 -> Gate 3
- [ ] Task 4 -> Gate 4
- [ ] Task 5 -> Gate 5 (CRITICAL)
- [ ] Task 6 -> Gate 6
- [ ] Task 7 -> Gate 7
- [ ] Task 8 -> Gate 8
- [ ] Task 9 -> Gate 9 (FINAL)

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
