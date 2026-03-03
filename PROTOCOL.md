# Evaluator Protocol v2

Status: **Source of truth** for Phase 1 implementation
Applies to: `command_evaluator`, `http_evaluator`, `llm_judge_evaluator`, preflight validation, dataset/valset loading

---

## 1) Evaluator Payload v2

### 1.1 Current protocol (v1)

Current evaluator input payload is:

```json
{"candidate": "<text>"}
```

This is sent:
- on `stdin` for command evaluators
- as JSON POST body for HTTP evaluators

### 1.2 Extended protocol (v2)

Protocol v2 extends the input payload with optional metadata and example context:

```json
{
  "_protocol_version": 2,
  "candidate": "<text>",
  "task_model": "openai/gpt-4o-mini",
  "example": {
    "...": "dataset example object"
  }
}
```

#### Required keys
- `candidate` (string): artifact/candidate text to score

#### Optional keys
- `_protocol_version` (integer): when present for v2 payloads, value MUST be `2`
- `task_model` (string): metadata identifying the model being optimized for task execution
- `example` (object): one dataset example record (see dataset schema below)

### 1.3 Emission rules

- **No dataset mode**: payload contains `candidate` (+ optional `task_model`) and `_protocol_version: 2`.
- **Dataset mode (`--dataset`)**: one evaluator call per candidate/example pair; payload includes `example`.
- **Generalization mode (`--dataset` + `--valset`)**:
  - Training/evolution calls use `dataset` examples (with `example` key)
  - Validation aggregation uses `valset` examples (with `example` key)

### 1.4 Backward compatibility behavior

- Evaluators that only read `candidate` remain valid under v2.
- Unknown keys MUST be ignored by evaluators unless explicitly used.
- v1 evaluators are not required to return or acknowledge protocol version.

### 1.5 Evaluator output contract (unchanged)

Evaluator output remains:

```json
{"score": 0.73, "reasoning": "...", "any_other_side_info": "..."}
```

- `score` is required
- all non-`score` keys are side information
- side information is preserved for reflection/debugging

---

## 2) Score Range Behavior Matrix

`--score-range` introduces two validation modes:
- `unit` (default): score must be in `[0.0, 1.0]`
- `any`: score must be a finite float (unbounded)

| Component | `--score-range unit` | `--score-range any` |
|---|---|---|
| `command_evaluator` | Enforce numeric + finite + range `[0,1]` in parse path; preflight enforces same | Enforce numeric + finite only in parse path; preflight enforces same |
| `http_evaluator` | Enforce numeric + finite + range `[0,1]` in parse path; preflight enforces same | Enforce numeric + finite only in parse path; preflight enforces same |
| `llm_judge_evaluator` | Always returns/clamps to `[0,1]` | Always returns/clamps to `[0,1]` (unchanged) |
| `validate_evaluator_payload` | Enforce numeric + finite + `[0,1]` | Enforce numeric + finite only |

### 2.1 Notes

- LLM judge behavior is intentionally invariant to `--score-range`.
- In `any` mode, NaN and ±Inf remain invalid.
- For command/HTTP adapters, parse-time and preflight-time rules MUST match.

---

## 3) Task-Model Propagation

`--task-model` is metadata in Phase 1 (not hard-coupled execution logic).

### 3.1 Payload propagation

When provided, include in evaluator payload:

```json
{
  "_protocol_version": 2,
  "candidate": "...",
  "task_model": "provider/model",
  "example": {"...": "..."}
}
```

(If not in dataset mode, omit `example`.)

### 3.2 Environment propagation (command evaluator)

For command evaluators, also set:

- `OPTIMIZE_ANYTHING_TASK_MODEL=<value of --task-model>`

This env var is additive; existing env handling remains intact.

### 3.3 LLM judge relation

- Judge model (`--judge-model`) remains the evaluator model.
- `task_model` identifies the target model under optimization and is passed through as metadata for future evaluator logic.

---

## 4) Dataset / Valset Format

### 4.1 File format

- Encoding: UTF-8
- Type: JSONL (one JSON object per non-blank line)
- Blank lines: allowed and skipped

Each non-blank line MUST parse as a JSON object:

```json
{"input": "...", "expected": "...", "metadata": {"difficulty": "easy"}}
```

No fixed field names are required by protocol; evaluator logic defines semantic interpretation.

### 4.2 Validation rules

For both `dataset` and `valset`:

1. File must be readable as UTF-8.
2. Maximum non-blank valid records: **10,000**.
3. Each non-blank line must be valid JSON.
4. Parsed JSON value must be an object (`{}`), not array/string/number/etc.
5. Blank lines are skipped and not counted toward the 10,000 limit.

### 4.3 Malformed line handling

- On malformed JSON or non-object record, fail validation with explicit line numbers.
- Error messages MUST include:
  - file path
  - offending line number(s)
  - brief parse/type reason
- CLI exits non-zero; optimization does not start with invalid dataset/valset.

### 4.4 Runtime usage

- For each evaluation call in dataset-backed modes, one record is bound into payload under `example`.
- `dataset` drives optimization/evolution calls.
- `valset` (if provided) drives validation/generalization aggregates.

---

## 5) Backward Compatibility Guarantees

The following are guaranteed not to break in v2:

1. **Existing v1 evaluators remain usable**
   - Evaluators that only consume `candidate` continue to work.

2. **Evaluator output schema remains stable**
   - Required output key is still `score`.
   - Additional output keys remain side-info.

3. **Default score behavior remains strict unit interval**
   - Default mode is still equivalent to legacy `[0,1]` checks.

4. **LLM judge continues `[0,1]` semantics**
   - No behavior change from score-range flag.

5. **Single-artifact mode remains unchanged in UX**
   - Running without `--dataset`/`--valset` preserves current flow; only additive payload metadata may appear.

6. **Protocol extension is additive, not breaking**
   - New keys (`_protocol_version`, `example`, `task_model`) are optional and ignorable by existing evaluators.

---

## Implementation Checklist Reference (Phase 1)

- Add `_protocol_version: 2` to outbound evaluator payloads
- Add optional `task_model` payload field + command env var
- Add optional `example` payload field in dataset-backed modes
- Implement score-range switch in both parse and preflight validators
- Implement JSONL loader with UTF-8, object-per-line, max-10k, malformed line reporting
- Ensure docs/tests reflect v2 contract and compatibility guarantees
