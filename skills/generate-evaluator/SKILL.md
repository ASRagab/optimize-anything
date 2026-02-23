---
name: generate-evaluator
description: Generate an evaluator script for a text artifact
---
Analyze the seed artifact and objective, then generate a bash or HTTP evaluator script
that scores candidates.

## Evaluator Contract
- Input: JSON on stdin -- `{"candidate": "<text>"}`
- Output: JSON on stdout -- `{"score": <float>, ...}`
- Score: higher is better (0.0 to 1.0 recommended)

## Steps
1. Identify the artifact type (prompt, code, config, etc.)
2. Define scoring criteria based on the objective
3. Generate the evaluator using optimize-anything's generate_evaluator tool
4. Test the evaluator with the seed artifact
5. Iterate on scoring logic until it matches your intent

## Example
```bash
# Generate a command evaluator
echo '{"candidate": "your seed text"}' | bash evaluator.sh
# Should output: {"score": 0.75, ...}
```
