---
name: optimize-anything
description: Optimize any text artifact -- prompts, code, configs, skills -- using evolutionary search with gepa
---
optimize-anything uses [gepa](https://gepa-ai.github.io/gepa/) to evolve text artifacts
through LLM-guided mutations scored by your custom evaluator. gepa proposes changes,
evaluates them, reflects on what worked, and iterates — like a researcher improving
a draft through structured feedback cycles.

## What Can Be Optimized

Any text artifact with a measurable quality signal:
- **Prompts and instructions** — system prompts, agent SOPs, few-shot examples
- **Code** — algorithms, configs, SQL queries, GPU kernels
- **Skills and tools** — SKILL.md files, tool descriptions, agent architectures
- **Content** — templates, documentation, structured output formats

## Quick Start

1. **Prepare a seed** — the text you want to optimize
2. **Create an evaluator** — use the **generate-evaluator** skill to build one matched to your objective
3. **Run optimization** — use `/optimize`, the `optimize` MCP tool, or the CLI

## Available Skills

- **generate-evaluator** — Choose the right evaluator pattern (verification, LLM-as-judge, simulation, composite) and generate a script
- **optimization-guide** — Full workflow walkthrough covering optimization modes, configuration, budget, and result interpretation

## Available Tools (MCP)

| Tool | Use |
|---|---|
| `optimize` | Run optimization with a seed + evaluator |
| `explain` | Preview what optimization would do |
| `recommend_budget` | Get budget recommendation for your artifact |
| `generate_evaluator` | Generate a starter evaluator script |

## Key Concept: Evaluator Quality = Optimization Quality

gepa's reflection LM reads your evaluator's output to decide what to change next. Return rich feedback — sub-scores, error messages, improvement hints — not just a number. An evaluator returning `{"score": 0.4, "clarity": 0.8, "completeness": 0.2, "missing": "no error handling instructions"}` drives far better optimization than one returning `{"score": 0.4}`.
