---
name: optimization-guide
description: Guide for using optimize-anything to improve text artifacts
---
Walk through the optimization workflow:

## Workflow
1. **Choose seed** -- start with your current best version of the artifact
2. **Create evaluator** -- use generate-evaluator skill or write your own
3. **Set budget** -- use recommend_budget tool or start with 100 evaluations
4. **Run optimization** -- use the optimize tool or CLI
5. **Interpret results** -- review the best candidate and improvement trajectory

## Tips
- Start with a small budget (50) to validate your evaluator
- Include diagnostic info in evaluator output for better reflection
- The objective string helps gepa's reflection LM understand your goal
- Use background to provide domain knowledge and constraints
