---
name: score
description: Score a single artifact with an evaluator
---

# score

Score a single artifact file using a command evaluator, HTTP evaluator, or LLM judge — without running optimization.

## Usage

```
optimize-anything score SEED_FILE --evaluator-command bash eval.sh
optimize-anything score SEED_FILE --judge-model openai/gpt-4o-mini --objective "Score clarity"
```

## Example

```
optimize-anything score my-prompt.txt \
  --evaluator-command bash evaluators/clarity.sh

optimize-anything score my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score for persuasiveness"
```

See [README](../README.md) for full flag documentation.
