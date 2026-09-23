"""Installed runtime for versioned generated LLM evaluator scripts."""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any, TextIO

from optimize_anything.llm_backends.base import Role
from optimize_anything.llm_backends.schema import score_output_schema, strip_code_fences

RUNTIME_CONTRACT_VERSION = 1
def _resolve_backend(config: Mapping[str, Any], *, role: Role) -> Any:
    """Keep the installed backend factory boundary in one replaceable place."""
    from optimize_anything.llm_backends.base import BackendSpec
    from optimize_anything.llm_backends.factory import create_backend

    spec = BackendSpec(
        backend=config.get("backend", "api"),
        model=config.get("model"),
        api_base=config.get("api_base"),
        api_fallback=config.get("api_fallback", False),
        api_fallback_model=config.get("api_fallback_model"),
        max_concurrency=config.get("max_concurrency", 1),
    )
    return create_backend(spec, role=role)


def run_generated_evaluator(
    config: Mapping[str, Any],
    *,
    backend_resolver: Callable[..., Any] | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Read JSON lines and emit one canonical numeric-score line per input line."""
    source = input_stream if input_stream is not None else sys.stdin
    destination = output_stream if output_stream is not None else sys.stdout
    resolver = backend_resolver or _resolve_backend
    backend = None

    for line in source:
        if not line.strip():
            continue
        required_version = config.get("min_runtime_contract_version")
        if (not isinstance(required_version, int) or isinstance(required_version, bool)
                or required_version < 1 or required_version > RUNTIME_CONTRACT_VERSION):
            _emit(destination, {
                "score": 0.0, "error": "incompatible_runtime",
                "reasoning": "Generated evaluator runtime contract is incompatible; upgrade optimize-anything.",
            })
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _emit(destination, {"score": 0.0, "error": "invalid_input", "reasoning": "Input must be valid JSON."})
            continue
        if not isinstance(payload, dict):
            _emit(destination, {"score": 0.0, "error": "invalid_input", "reasoning": "Input must be a JSON object."})
            continue

        candidate = str(payload.get("candidate", ""))
        if candidate == "__optimize_anything_preflight__":
            _emit(destination, {"score": 1.0, "reasoning": "Evaluator runtime is ready."})
            continue
        is_composite = config.get("evaluator_type") == "composite"
        if is_composite:
            failures = _local_constraint_failures(candidate)
            if failures:
                _emit(destination, {
                    "score": 0.0, "reasoning": "Hard constraints failed",
                    "hard_constraint_failures": failures,
                    "hard_constraints_satisfied": False,
                })
                continue

        try:
            if backend is None:
                backend = resolver(config, role="judge")
            from optimize_anything.llm_backends.base import CompletionRequest

            request = CompletionRequest(
                prompt=_build_prompt(candidate, payload.get("example") if config.get("dataset") else None, config),
                role="judge",
                model=config.get("model"),
                output_schema=score_output_schema(
                    [str(name) for name, _ in config.get("quality_dimensions", ())],
                    include_hard_constraints=bool(config.get("hard_constraints")),
                ),
                timeout_seconds=60.0,
                prompt_contract_version="generated-evaluator-v1",
                schema_contract_version="generated-evaluator-v1",
            )
            completion = backend.complete(request)
            parsed = completion.structured
            if parsed is None:
                parsed = json.loads(strip_code_fences(completion.text))
            result = _score_result(parsed, config, is_composite=is_composite)
            from optimize_anything.llm_backends.provenance import completion_event

            try:
                result["llm_provenance"] = completion_event(completion)
            except (AttributeError, TypeError):
                # Injectable test/third-party backends may implement only text/structured.
                pass
        except (ImportError, ModuleNotFoundError):
            result = {
                "score": 0.0, "error": "runtime_backend_unavailable",
                "reasoning": "Install a compatible optimize-anything runtime and backend extra.",
            }
        except Exception as exc:
            result = {
                "score": 0.0, "error": "evaluator_failed",
                "reasoning": f"Evaluator failed: {type(exc).__name__}.",
            }
        _emit(destination, result)
    return 0


def _build_prompt(candidate: str, example: Any, config: Mapping[str, Any]) -> str:
    dimensions = "\n".join(
        f"- {name} (weight={weight})" for name, weight in config.get("quality_dimensions", ())
    )
    constraints = "\n".join(f"- {item}" for item in config.get("hard_constraints", ())) or "(none)"
    example_text = json.dumps(example, ensure_ascii=False, indent=2) if example is not None else "(none)"
    return (
        "You are a careful, objective evaluator. Return only a JSON object.\n"
        f"## Objective\n{config['objective']}\n\n"
        f"## Template Family\n{config['template_family']}\n\n"
        f"## Rubric Summary\n{config['rubric_summary']}\n\n"
        f"## Quality Dimensions\n{dimensions}\n\n"
        f"## Hard Constraints\n{constraints}\n\n"
        f"## Example Context (optional)\n{example_text}\n\n"
        f"## Artifact to Evaluate\n```\n{candidate}\n```\n\n"
        "Return JSON with score, reasoning, one numeric key per quality dimension, and "
        "hard_constraints_satisfied when constraints are present. score must be in [0,1]."
    )


def _local_constraint_failures(candidate: str) -> list[str]:
    failures = []
    if not candidate.strip():
        failures.append("candidate must not be empty")
    if len(candidate) > 12000:
        failures.append("candidate exceeds max_len=12000")
    if re.search(r"TODO|TBD|\[FILL\]", candidate):
        failures.append("candidate contains placeholder tokens")
    return failures


def _score_result(parsed: Any, config: Mapping[str, Any], *, is_composite: bool) -> dict[str, Any]:
    if not isinstance(parsed, Mapping):
        return {"score": 0.0, "error": "invalid_response", "reasoning": "Judge returned non-object JSON."}
    raw_score = _unit_float(parsed.get("score"))
    result: dict[str, Any] = {
        "score": raw_score,
        "reasoning": str(parsed.get("reasoning", "No reasoning provided.")),
        "dimension_scores": {},
    }
    for name, _ in config.get("quality_dimensions", ()):
        value = _unit_float(parsed.get(name))
        result["dimension_scores"][name] = value
        if name not in {"score", "reasoning", "dimension_scores", "error", "hard_constraints_satisfied", "hard_constraint_failures"}:
            result[name] = value
    if config.get("hard_constraints") and parsed.get("hard_constraints_satisfied") is False:
        result["score"] = 0.0
        result["hard_constraints_satisfied"] = False
    elif is_composite:
        result["hard_constraints_satisfied"] = True
    return result


def _unit_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0


def _emit(stream: TextIO, result: Mapping[str, Any]) -> None:
    stream.write(json.dumps(result, ensure_ascii=False) + "\n")
