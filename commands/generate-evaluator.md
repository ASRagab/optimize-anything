---
name: generate-evaluator
description: Generate a scoring evaluator script for an artifact type
---

# generate-evaluator

Generate a bash or HTTP evaluator script tailored to a specific artifact type and optimization objective.

## Usage

```
optimize-anything generate-evaluator SEED_FILE --objective "your goal"
```

## Example

```
optimize-anything generate-evaluator my-prompt.txt \
  --objective "Score persuasiveness and clarity" \
  --evaluator-type command
```

See [README](../README.md) for full flag documentation.
