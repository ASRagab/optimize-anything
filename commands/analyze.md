---
name: analyze
description: Discover quality dimensions for an artifact and objective
---

# analyze

Use an LLM to discover relevant quality dimensions for a given artifact and optimization objective. Returns dimensions with suggested weights as intake JSON.

## Usage

```bash
optimize-anything analyze SEED_FILE --judge-model openai/gpt-4o-mini --objective "Quality"
```

## Example

```bash
optimize-anything analyze my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score for clarity and persuasiveness"
```

## Next Step: optimize with discovered dimensions
After dimension discovery, proceed directly to optimization using the returned `intake_json`:

```bash
optimize-anything optimize my-prompt.txt \
  --judge-model openai/gpt-4o-mini \
  --objective "Score for clarity and persuasiveness" \
  --intake-json '<paste intake_json from analyze>' \
  --budget 50 --diff --run-dir runs/ --early-stop
```

See [README](../README.md) for full flag documentation.
