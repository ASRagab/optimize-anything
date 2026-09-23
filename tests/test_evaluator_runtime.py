"""Contract tests for the installed generated-evaluator runtime."""

import io
import json
from types import SimpleNamespace

from optimize_anything import evaluator_runtime


def _config(**overrides):
    config = {
        "min_runtime_contract_version": 1,
        "evaluator_type": "judge",
        "objective": "Assess accuracy",
        "template_family": "general_text",
        "rubric_summary": "Accurate answers",
        "quality_dimensions": [("accuracy", 0.7), ("clarity", 0.3)],
        "hard_constraints": ["Do not invent citations"],
        "dataset": True,
        "backend": "codex",
        "model": "gpt-5.6-luna",
        "api_base": None,
        "api_fallback": False,
        "api_fallback_model": None,
        "max_concurrency": 1,
    }
    config.update(overrides)
    return config


def test_runtime_scores_json_lines_and_forwards_role_config_and_examples():
    requests = []
    resolved = []

    class Backend:
        def complete(self, request):
            requests.append(request)
            return SimpleNamespace(structured={"score": 0.8, "reasoning": "Good", "accuracy": 0.9, "clarity": 0.6})

    def resolver(config, *, role):
        resolved.append((config, role))
        return Backend()

    output = io.StringIO()
    source = io.StringIO('\n'.join([
        json.dumps({"candidate": "First", "example": {"expected": "A"}}),
        json.dumps({"candidate": "Second", "example": {"expected": "B"}}),
    ]) + '\n')
    evaluator_runtime.run_generated_evaluator(
        _config(), backend_resolver=resolver, input_stream=source, output_stream=output
    )

    results = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(results) == 2
    assert all(result["score"] == 0.8 for result in results)
    assert results[0]["accuracy"] == 0.9
    assert resolved[0][1] == "judge"
    assert resolved[0][0]["backend"] == "codex"
    assert '"expected": "A"' in requests[0].prompt
    assert "Do not invent citations" in requests[0].prompt
    assert "First" in requests[0].prompt
    assert "Second" in requests[1].prompt


def test_composite_constraints_short_circuit_without_backend_call():
    output = io.StringIO()

    def resolver(config, *, role):
        raise AssertionError("constraint failure must not dispatch")

    evaluator_runtime.run_generated_evaluator(
        _config(evaluator_type="composite"),
        backend_resolver=resolver,
        input_stream=io.StringIO(json.dumps({"candidate": "TODO"}) + "\n"),
        output_stream=output,
    )
    result = json.loads(output.getvalue())
    assert result["score"] == 0.0
    assert result["hard_constraints_satisfied"] is False
    assert result["hard_constraint_failures"]


def test_preflight_probe_does_not_call_backend():
    output = io.StringIO()

    def resolver(config, *, role):
        raise AssertionError("preflight must remain local")

    evaluator_runtime.run_generated_evaluator(
        _config(),
        backend_resolver=resolver,
        input_stream=io.StringIO(json.dumps({"candidate": "__optimize_anything_preflight__"}) + "\n"),
        output_stream=output,
    )

    assert json.loads(output.getvalue()) == {
        "score": 1.0,
        "reasoning": "Evaluator runtime is ready.",
    }


def test_runtime_reports_incompatible_contract_and_invalid_json_as_score_lines():
    output = io.StringIO()
    evaluator_runtime.run_generated_evaluator(
        _config(min_runtime_contract_version=999),
        input_stream=io.StringIO('{}\n'),
        output_stream=output,
    )
    incompatible = json.loads(output.getvalue())
    assert incompatible["score"] == 0.0
    assert incompatible["error"] == "incompatible_runtime"
    assert "upgrade" in incompatible["reasoning"].lower()

    output = io.StringIO()
    evaluator_runtime.run_generated_evaluator(
        _config(), input_stream=io.StringIO('not json\n'), output_stream=output,
        backend_resolver=lambda config, *, role: None,
    )
    invalid = json.loads(output.getvalue())
    assert invalid["score"] == 0.0
    assert invalid["error"] == "invalid_input"


def test_dimension_name_cannot_replace_canonical_score():
    class Backend:
        def complete(self, request):
            return SimpleNamespace(structured={"score": 0.8, "reasoning": "Good"})

    output = io.StringIO()
    evaluator_runtime.run_generated_evaluator(
        _config(quality_dimensions=[("score", 1.0)], backend="codex"),
        backend_resolver=lambda config, *, role: Backend(),
        input_stream=io.StringIO('{"candidate": "answer"}\n'),
        output_stream=output,
    )
    result = json.loads(output.getvalue())
    assert result["score"] == 0.8
    assert result["dimension_scores"]["score"] == 0.8
