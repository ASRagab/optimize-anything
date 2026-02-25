---
name: explain
description: Show the optimization plan for given inputs
---

# explain

Display the optimization plan that would be executed for the given seed artifact, evaluator, and configuration — without actually running it.

## Usage

```
optimize-anything explain SEED_FILE --evaluator-command bash eval.sh --objective "your goal"
```

## Example

```
optimize-anything explain prompt.txt \
  --evaluator-command bash evaluators/clarity.sh \
  --budget 50
```

See [README](../README.md) for full flag documentation.
