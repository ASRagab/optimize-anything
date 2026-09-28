# Examples

## Evaluators

- `examples/evaluators/echo_score.sh` -- Simple bash evaluator (scores by length)
- `examples/evaluators/http_evaluator.py` -- HTTP evaluator server example

## Seeds

- `examples/seeds/sample_seed.txt` -- Example prompt seed for optimization

## Quick Test

From the repository root:

```bash
echo '{"candidate":"test"}' | bash examples/evaluators/echo_score.sh
```
