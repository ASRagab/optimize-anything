---
name: optimize
description: Optimize a text artifact with a BYO evaluator using gepa
---
Run optimization on the given artifact using a question-driven workflow.

## Required Flow

1. Collect context:
   - artifact type (prompt, skill, docs, code, config)
   - objective and constraints
   - evaluator source (`command` or `http`)
   - execution path for evaluator (for plugin use, ask for absolute project path and pass as `evaluator_cwd`)
2. If no evaluator exists, invoke the `generate-evaluator` skill.
3. Validate evaluator manually before optimization:
   - command: `echo '{"candidate":"test"}' | bash eval.sh`
   - http: `curl -X POST <url> -H "Content-Type: application/json" -d '{"candidate":"test"}'`
4. Run optimization with explicit objective and reasonable budget.
5. Return:
   - improved artifact
   - evaluator diagnostics that mattered most
   - quick next-step suggestions if score plateaued

## Reusable Quality Profiles

When users are unsure how to score quality, suggest one of these profile starters:

- **Instructional artifacts** (docs, runbooks, guides): clarity, completeness, actionability, safety.
- **Instruction artifacts** (prompts, skills, agent SOPs): intent alignment, constraint adherence, robustness, specificity.
- **Executable artifacts** (code, scripts, configs): correctness, reliability, performance, maintainability.
- **Analytical artifacts** (queries, analysis plans, reports): factual correctness, methodological rigor, efficiency, interpretability.
