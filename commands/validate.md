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
  --providers openai/gpt-5.6-luna anthropic/claude-sonnet-5 gemini/gemini-3.6-flash \
  --objective "Score for clarity and constraint adherence"
```

Gemini uses LiteLLM's `gemini/` provider prefix.

Optional:
- `--intake-json` or `--intake-file` for shared dimensions/constraints
- `--api-base` for custom provider endpoints

## Expected output
- Per-provider score and reasoning/diagnostics
- Aggregate stats: mean, stddev, min, max
- Quick read of agreement vs spread across providers
