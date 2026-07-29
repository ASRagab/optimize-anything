"""Validate deterministic fixtures for prompt workflow delivery semantics."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures" / "optimize_prompt_workflow.json"


def test_workflow_fixtures_cover_all_delivery_paths():
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    assert {case["id"] for case in cases} == {
        "inline-return",
        "standalone-apply",
        "embedded-apply",
        "rejected-noop",
        "independent-batch",
        "coupled-refusal",
    }


def test_embedded_fixture_preserves_valid_python_syntax():
    case = next(
        case
        for case in json.loads(FIXTURES.read_text(encoding="utf-8"))
        if case["id"] == "embedded-apply"
    )
    assert case["baseline_source"].replace(case["baseline"], case["candidate"]) == case[
        "expected_source"
    ]
    compile(case["expected_source"], "fixture.py", "exec")


def test_rejected_and_multi_file_fixtures_are_explicit():
    cases = {
        case["id"]: case
        for case in json.loads(FIXTURES.read_text(encoding="utf-8"))
    }
    assert cases["rejected-noop"]["expected"] == cases["rejected-noop"]["baseline"]
    assert len(cases["independent-batch"]["destinations"]) == 2
    assert cases["coupled-refusal"]["expected_action"] == "refuse-independent-optimization"
