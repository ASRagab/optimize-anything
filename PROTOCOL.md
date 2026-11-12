# Evaluator Protocol

Source of truth for the evaluator contract.
Applies to: `command_evaluator`, `http_evaluator`, `llm_judge_evaluator`, preflight validation, and dataset/valset loading.

---

## 1) Evaluator contract

### 1.1 Input payload

The optimizer sends one JSON object per evaluator call:

```json
{
  "_protocol_version": 2,
  "candidate": "<text>",
  "task_model": "openai/gpt-5.6-luna",
  "example": {
    "...": "dataset example object"
  }
}
```

The object is delivered:
- on `stdin` for command evaluators
- as the JSON POST body for HTTP evaluators

### 1.2 Fields

#### Required keys
- `candidate` (string): artifact text to score

#### Optional keys
- `_protocol_version` (integer): protocol marker. The runtime always sends `2`.
- `task_model` (string): metadata identifying the model being optimized for task execution
- `example` (object): one dataset record (see section 4)

### 1.3 When fields appear

- **No dataset**: the payload contains `_protocol_version`, `candidate`, and `task_model` when `--task-model` is set. It has no `example`.
- **Dataset mode (`--dataset`)**: one evaluator call per candidate/example pair. The payload includes `example`.
- **Generalization mode (`--dataset` + `--valset`)**:
  - Training and evolution calls use `dataset` examples (with the `example` key).
  - Validation aggregation uses `valset` examples (with the `example` key).

### 1.4 Reading the payload

- An evaluator that reads only `candidate` is valid.
- Evaluators MUST ignore keys they do not use.
- Evaluators are not required to read or return the protocol marker.

### 1.5 Output

An evaluator returns one JSON object:

```json
{"score": 0.73, "reasoning": "...", "any_other_side_info": "..."}
```

- `score` is required.
- All other keys are side information, kept for reflection and debugging.

---

## 2) Score range

`--score-range` selects one of two validation modes:
- `unit` (default): score must be in `[0.0, 1.0]`
- `any`: score must be a finite float (unbounded)

| Component | `--score-range unit` | `--score-range any` |
|---|---|---|
| `command_evaluator` | Enforce numeric + finite + range `[0,1]` in parse path; preflight enforces the same | Enforce numeric + finite only in parse path; preflight enforces the same |
| `http_evaluator` | Enforce numeric + finite + range `[0,1]` in parse path; preflight enforces the same | Enforce numeric + finite only in parse path; preflight enforces the same |
| `llm_judge_evaluator` | Always returns and clamps to `[0,1]` | Always returns and clamps to `[0,1]` |
| `validate_evaluator_payload` | Enforce numeric + finite + `[0,1]` | Enforce numeric + finite only |

### 2.1 Notes

- The LLM judge ignores `--score-range`.
- In `any` mode, NaN and ±Inf remain invalid.
- For command and HTTP adapters, parse-time and preflight-time rules MUST match.

---

## 3) Task-model propagation

`--task-model` is metadata. It does not change how candidates are executed.

### 3.1 Payload

When provided, `task_model` is included in the payload:

```json
{
  "_protocol_version": 2,
  "candidate": "...",
  "task_model": "provider/model",
  "example": {"...": "..."}
}
```

Without a dataset, `example` is omitted.

### 3.2 Environment (command evaluators)

Command evaluators also receive:

- `OPTIMIZE_ANYTHING_TASK_MODEL=<value of --task-model>`

The variable is added to the existing environment.

### 3.3 Built-in evaluators

- The judge model (`--judge-model`) is the evaluator model.
- The Jev evaluator (`--jev-model`) is a built-in evaluator like the LLM judge. It does not use this payload. It reads `TYPESAFE_API_KEY` and uses no environment keys from this document.
- `task_model` identifies the model under optimization and is passed through as metadata.

---

## 4) Dataset / valset format

### 4.1 File format

- Encoding: UTF-8
- Type: JSONL (one JSON object per non-blank line)
- Blank lines: allowed and skipped

Each non-blank line MUST parse as a JSON object:

```json
{"input": "...", "expected": "...", "metadata": {"difficulty": "easy"}}
```

The protocol requires no fixed field names. Evaluator logic defines what each field means.

### 4.2 Validation rules

For both `dataset` and `valset`:

1. The file must be readable as UTF-8.
2. At most **10,000** non-blank records.
3. Each non-blank line must be valid JSON.
4. The parsed value must be an object (`{}`), not an array, string, or number.
5. Blank lines are skipped and do not count toward the 10,000 limit.

### 4.3 Malformed lines

- A malformed JSON line or non-object record fails validation with explicit line numbers.
- The error message includes:
  - the file path
  - the offending line number(s)
  - a brief parse or type reason
- The CLI exits non-zero. Optimization does not start with an invalid dataset or valset.

### 4.4 Runtime usage

- In dataset-backed modes, each evaluation call binds one record into the payload under `example`.
- `dataset` drives optimization and evolution calls.
- `valset` (if provided) drives validation and generalization aggregates.

---

## 5) Stability rules

1. **Candidate-only evaluators keep working.** An evaluator that consumes only `candidate` is always valid.
2. **The output schema is stable.** `score` is required. Additional keys are side information.
3. **The default score range is `[0,1]`.**
4. **The LLM judge always uses `[0,1]`.** `--score-range` does not affect it.
5. **Single-artifact mode sends no `example`.** Without `--dataset` or `--valset`, the payload carries no dataset record.
6. **New payload keys are optional.** Existing evaluators can ignore them.
