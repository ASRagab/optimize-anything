# Examples

## Evaluators

- `evaluators/echo_score.sh` -- Simple bash evaluator (scores by length)
- `evaluators/http_evaluator.py` -- HTTP evaluator server example

## Seeds

- `seeds/sample_seed.txt` -- Example prompt seed for optimization

## Quick Test

```bash
echo '{"candidate":"test"}' | bash evaluators/echo_score.sh
```
