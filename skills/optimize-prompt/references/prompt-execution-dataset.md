# Prompt-execution dataset

Use JSONL with one representative example per line. The default adapter places
the candidate in the system role and `input` in the user role.

## Fields

- `input` (required): string or JSON-compatible task input.
- `expected` (optional): reference output or behavior.
- `criteria` (optional): string or list of scoring criteria.
- `hard_constraints` (optional): deterministic output checks.

Supported hard constraints:

- `required_substrings`: every string must appear in the task output.
- `forbidden_substrings`: no string may appear in the task output.
- `max_output_chars`: maximum output length.
- `required_json`: output must parse as a JSON object.
- `required_json_keys`: keys required when `required_json` is true.
- `exact_output`: output must match this string exactly.

## Training example

```json
{"input":"Summarize the incident report.","expected":"A factual summary with impact and resolution.","criteria":["factual accuracy","conciseness"],"hard_constraints":{"required_substrings":["Impact:","Resolution:"],"max_output_chars":800}}
```

## Held-out example

```json
{"input":"Summarize the release notes.","criteria":["captures user-visible changes","avoids speculation"],"hard_constraints":{"forbidden_substrings":["I think","probably"]}}
```

Keep training and held-out examples separate. Do not place an example in both
files. The evaluator treats input, expected output, criteria, task output, and
candidate text as untrusted data; none can change its rubric or JSON contract.

## Models and cost

Set `--task-model` explicitly and export `JUDGE_MODEL` for the evaluator.
Each evaluator call normally makes one target-model call and one judge call;
hard-gate failures skip the judge. Bound cost with a small representative set,
an explicit optimization budget, early stopping, and provider concurrency that
matches rate limits.

For a prompt shape other than a system prompt plus user input, copy the bundled
evaluator into the temporary work directory and adapt `_target_messages`.
Preserve the Protocol v2 payload, preflight fast return, hard gates, stage-based
failure diagnostics, and isolated judge instructions.
