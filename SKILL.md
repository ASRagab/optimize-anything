---
name: optimize-anything
description: Optimize any text artifact -- prompts, code, configs -- using evolutionary search with gepa
---
optimize-anything uses gepa to evolve text artifacts through LLM-guided mutations
scored by your custom evaluator.

## Quick Start
1. Prepare a seed artifact (the text you want to optimize)
2. Create an evaluator (use the generate-evaluator skill)
3. Run optimization with /optimize or the optimize tool

## Available Skills
- **generate-evaluator** -- Create an evaluator script for your artifact
- **optimization-guide** -- Step-by-step optimization workflow

## Available Tools (MCP)
- **optimize** -- Run optimization on an artifact
- **explain** -- Preview what optimization would do
- **recommend_budget** -- Get budget recommendations
- **generate_evaluator** -- Generate an evaluator script
