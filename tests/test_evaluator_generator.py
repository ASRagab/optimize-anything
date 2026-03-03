"""Tests for evaluator generator."""
import json
import subprocess
from pathlib import Path

from optimize_anything.evaluator_generator import generate_evaluator_script


class TestGenerateEvaluatorScript:
    def test_command_evaluator_is_bash(self):
        script = generate_evaluator_script(seed="hello", objective="improve clarity", evaluator_type="command")
        assert script.startswith("#!/usr/bin/env bash")

    def test_command_evaluator_contains_objective(self):
        script = generate_evaluator_script(seed="hello", objective="improve clarity", evaluator_type="command")
        assert "improve clarity" in script

    def test_command_evaluator_contains_seed_length(self):
        script = generate_evaluator_script(seed="hello world", objective="test", evaluator_type="command")
        assert "11" in script  # len("hello world")

    def test_http_evaluator_is_python(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="http")
        assert "#!/usr/bin/env python3" in script

    def test_http_evaluator_has_server(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="http")
        assert "HTTPServer" in script
        assert "8000" in script

    def test_default_is_judge(self):
        script = generate_evaluator_script(seed="x", objective="y")
        assert script.startswith("#!/usr/bin/env python3")
        assert "litellm" in script

    def test_judge_evaluator_contains_litellm_and_objective(self):
        objective = "assess clarity and usefulness"
        script = generate_evaluator_script(seed="hello", objective=objective, evaluator_type="judge")
        assert "from litellm import completion" in script
        assert objective in script

    def test_judge_evaluator_handles_missing_api_key_gracefully(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="judge")
        assert "Missing API key" in script
        assert "missing_api_key" in script

    def test_objective_with_quotes_is_safe_in_command_script(self, tmp_path: Path):
        objective = 'Improve "install docs"\nfor O\'Reilly users'
        script = generate_evaluator_script(seed="hello", objective=objective, evaluator_type="command")

        script_path = tmp_path / "eval.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)

        proc = subprocess.run(
            [str(script_path)],
            input=json.dumps({"candidate": "hello world"}),
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(proc.stdout)
        assert result["objective"] == objective

    def test_objective_with_quotes_is_safe_in_http_script(self):
        objective = 'Keep "BigQuery" SQL safe for O\'Reilly'
        script = generate_evaluator_script(
            seed="select * from table",
            objective=objective,
            evaluator_type="http",
        )
        assert f"OBJECTIVE = {objective!r}" in script

    def test_command_script_handles_large_candidate(self, tmp_path: Path):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="command")
        script_path = tmp_path / "eval.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)

        large_candidate = "x" * 200_000
        proc = subprocess.run(
            [str(script_path)],
            input=json.dumps({"candidate": large_candidate}),
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(proc.stdout)
        assert result["length"] == 200_000

    def test_command_script_includes_diagnostics_keys(self):
        script = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={
                "artifact_class": "instructional_content",
                "rubric_summary": "Prioritize clarity and examples",
            },
        )
        assert "template_family" in script
        assert "rubric_summary" in script
        assert "objective" in script

    def test_intake_selects_template_family_categories(self):
        instructional = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={"artifact_class": "instructional_content"},
        )
        instruction_artifact = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={"artifact_class": "instruction_artifact"},
        )
        executable = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={"artifact_class": "executable_analytical"},
        )
        fallback = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={"artifact_class": "unknown_type"},
        )

        assert "TEMPLATE_FAMILY = 'instructional_content'" in instructional
        assert "TEMPLATE_FAMILY = 'instruction_artifact'" in instruction_artifact
        assert "TEMPLATE_FAMILY = 'executable_analytical'" in executable
        assert "TEMPLATE_FAMILY = 'general_text'" in fallback

    def test_intake_quality_dimensions_are_embedded(self):
        script = generate_evaluator_script(
            seed="hello",
            objective="test",
            evaluator_type="command",
            intake={
                "quality_dimensions": [
                    {"name": "accuracy", "weight": 0.7},
                    {"name": "clarity", "weight": 0.3},
                ]
            },
        )
        assert "QUALITY_DIMENSIONS = [('accuracy', 0.7), ('clarity', 0.3)]" in script

    def test_composite_evaluator_has_constraints_and_judge(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="composite")
        assert "_constraint_non_empty" in script
        assert "hard_constraint_failures" in script
        assert "_run_judge" in script
        assert "litellm" in script

    def test_dataset_flag_adds_example_extraction_for_all_types(self):
        for ev_type in ["judge", "command", "http", "composite"]:
            script = generate_evaluator_script(
                seed="hello",
                objective="test",
                evaluator_type=ev_type,
                dataset=True,
            )
            assert "example" in script
            assert "data.get(\"example\")" in script
