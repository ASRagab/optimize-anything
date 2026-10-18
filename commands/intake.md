---
name: intake
description: Normalize and validate an intake specification
---

# intake

Normalize and validate an intake specification, filling in defaults for quality dimensions and evaluation patterns.

## Usage

```
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" intake --intake-json '{"artifact_class": "prompt"}'
```

## Example

```
"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything" intake --intake-file intake.json
```

A quality dimension may carry optional `levels`: 2 to 10 strings ordered from lowest to highest. Only `--jev-model` uses them, as the rubric for that dimension.

```
{"quality_dimensions": [{"name": "clarity", "weight": 1.0, "levels": ["Vague", "Mostly clear", "Clear and specific"]}]}
```

See [README](../README.md) for full flag documentation.
