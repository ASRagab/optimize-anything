---
name: analyze
description: Discover quality dimensions for an artifact and objective
---

# analyze

Use an LLM to discover relevant quality dimensions for a given artifact and optimization objective. Returns dimensions with suggested weights as intake JSON.

## Usage

```
optimize-anything analyze SEED_FILE --judge-model openai/gpt-4o-mini --objective "Quality"
```

## Example

```
optimize-anything analyze my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score for clarity and persuasiveness"
```

See [README](../README.md) for full flag documentation.
