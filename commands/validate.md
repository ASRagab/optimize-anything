---
name: validate
description: Cross-validate an artifact with multiple LLM judge providers
---
Use multiple LLM judges to verify that a quality improvement is not provider-specific.

## When to use
- After optimization and before accepting a final artifact
- When you want confidence that gains hold across providers
- When one model's scoring seems noisy or biased

## Usage
```bash
optimize-anything validate <file> \
  --providers openai/gpt-4o-mini anthropic/claude-sonnet-4-5 \
  --objective "Score for clarity and constraint adherence"
```

Optional:
- `--intake-json` or `--intake-file` for shared dimensions/constraints
- `--api-base` for custom provider endpoints

## Expected output
- Per-provider score and reasoning/diagnostics
- Aggregate stats: mean, stddev, min, max
- Quick read of agreement vs spread across providers
