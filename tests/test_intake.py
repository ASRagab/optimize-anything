"""Tests for evaluator intake normalization and validation."""

from __future__ import annotations

import pytest

from optimize_anything.intake import normalize_intake_spec


@pytest.mark.parametrize("data", [None, {}])
def test_defaults_from_none_or_empty_input(data):
    assert normalize_intake_spec(data) == {
        "artifact_class": "general_text",
        "quality_dimensions": [
            {"name": "correctness", "weight": 0.4},
            {"name": "clarity", "weight": 0.35},
            {"name": "conciseness", "weight": 0.25},
        ],
        "hard_constraints": [],
        "evaluation_pattern": "judge",
        "execution_mode": "command",
        "evaluator_cwd": None,
    }


def test_invalid_execution_mode_and_evaluation_pattern():
    with pytest.raises(ValueError, match="execution_mode must be one of"):
        normalize_intake_spec({"execution_mode": "grpc"})

    with pytest.raises(ValueError, match="evaluation_pattern must be one of"):
        normalize_intake_spec({"evaluation_pattern": "pairwise"})


@pytest.mark.parametrize(
    "pattern",
    ["verification", "judge", "simulation", "composite"],
)
def test_supported_evaluation_patterns(pattern):
    normalized = normalize_intake_spec({"evaluation_pattern": pattern})
    assert normalized["evaluation_pattern"] == pattern


def test_invalid_quality_dimensions_structure():
    with pytest.raises(ValueError, match="quality_dimensions must be a list of objects"):
        normalize_intake_spec({"quality_dimensions": "not-a-list"})

    with pytest.raises(ValueError, match="quality_dimensions\\[0\\] missing required field 'name'"):
        normalize_intake_spec({"quality_dimensions": [{"weight": 1.0}]})

    with pytest.raises(ValueError, match="quality_dimensions\\[0\\].name must be a non-empty string"):
        normalize_intake_spec({"quality_dimensions": [{"name": "  ", "weight": 1.0}]})


def test_invalid_quality_dimensions_non_numeric_weight():
    with pytest.raises(ValueError, match="quality_dimensions\\[0\\].weight must be numeric"):
        normalize_intake_spec({"quality_dimensions": [{"name": "clarity", "weight": "high"}]})


def test_quality_dimension_weights_are_normalized_deterministically():
    data = {
        "quality_dimensions": [
            {"name": " Dimension A ", "weight": 3},
            {"name": "Dimension B", "weight": 2},
            {"name": "Dimension C", "weight": 1},
        ]
    }

    first = normalize_intake_spec(data)["quality_dimensions"]
    second = normalize_intake_spec(data)["quality_dimensions"]

    assert first == second
    assert first == [
        {"name": "Dimension A", "weight": 0.5},
        {"name": "Dimension B", "weight": 0.3333},
        {"name": "Dimension C", "weight": 0.1667},
    ]
    assert sum(d["weight"] for d in first) == pytest.approx(1.0)


def test_hard_constraints_type_validation():
    with pytest.raises(ValueError, match="hard_constraints must be a list of strings"):
        normalize_intake_spec({"hard_constraints": "must not be a string"})

    with pytest.raises(ValueError, match="hard_constraints\\[1\\] must be a string"):
        normalize_intake_spec({"hard_constraints": ["ok", 123]})


def test_evaluator_cwd_type_validation():
    with pytest.raises(ValueError, match="evaluator_cwd must be a string or None"):
        normalize_intake_spec({"evaluator_cwd": 42})


def test_empty_quality_dimensions_raises():
    with pytest.raises(ValueError, match="must contain at least one dimension"):
        normalize_intake_spec({"quality_dimensions": []})


def test_non_mapping_intake_raises():
    with pytest.raises(ValueError, match="intake spec must be a mapping"):
        normalize_intake_spec(["not", "a", "mapping"])


def test_duplicate_dimension_name_raises():
    with pytest.raises(ValueError, match="Duplicate quality dimension name"):
        normalize_intake_spec(
            {
                "quality_dimensions": [
                    {"name": "clarity", "weight": 0.5},
                    {"name": "clarity", "weight": 0.5},
                ]
            }
        )


def _dim(**extra):
    return {"quality_dimensions": [{"name": "clarity", "weight": 1.0, **extra}]}


def test_levels_are_kept_stripped_and_attached_to_their_dimension():
    spec = normalize_intake_spec({
        "quality_dimensions": [
            {"name": "clarity", "weight": 1, "levels": [" vague ", "clear"]},
            {"name": "brevity", "weight": 1},
        ]
    })
    assert spec["quality_dimensions"] == [
        {"name": "clarity", "weight": 0.5, "levels": ["vague", "clear"]},
        {"name": "brevity", "weight": 0.5},
    ]


def test_no_levels_key_means_dimension_is_unchanged():
    assert normalize_intake_spec(_dim())["quality_dimensions"] == [{"name": "clarity", "weight": 1.0}]
    assert normalize_intake_spec(_dim(levels=None))["quality_dimensions"] == [{"name": "clarity", "weight": 1.0}]


@pytest.mark.parametrize(
    "levels, message",
    [
        ("poor, good", r"quality_dimensions\[0\]\.levels must be a list"),
        (["only one"], r"must contain 2 to 10 levels"),
        ([f"l{i}" for i in range(11)], r"must contain 2 to 10 levels"),
        (["ok", "  "], r"levels\[1\] must be a non-empty string"),
        (["ok", 3], r"levels\[1\] must be a non-empty string"),
    ],
)
def test_invalid_levels_raise_with_field_path(levels, message):
    with pytest.raises(ValueError, match=message):
        normalize_intake_spec(_dim(levels=levels))


def test_ten_levels_is_allowed():
    levels = [f"l{i}" for i in range(10)]
    assert normalize_intake_spec(_dim(levels=levels))["quality_dimensions"][0]["levels"] == levels
