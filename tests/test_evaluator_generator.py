"""Tests for evaluator generator."""
from optimize_anything.evaluator_generator import generate_evaluator_script


class TestGenerateEvaluatorScript:
    def test_command_evaluator_is_bash(self):
        script = generate_evaluator_script(seed="hello", objective="improve clarity")
        assert script.startswith("#!/usr/bin/env bash")

    def test_command_evaluator_contains_objective(self):
        script = generate_evaluator_script(seed="hello", objective="improve clarity")
        assert "improve clarity" in script

    def test_command_evaluator_contains_seed_length(self):
        script = generate_evaluator_script(seed="hello world", objective="test")
        assert "11" in script  # len("hello world")

    def test_http_evaluator_is_python(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="http")
        assert "#!/usr/bin/env python3" in script

    def test_http_evaluator_has_server(self):
        script = generate_evaluator_script(seed="hello", objective="test", evaluator_type="http")
        assert "HTTPServer" in script
        assert "8000" in script

    def test_default_is_command(self):
        script = generate_evaluator_script(seed="x", objective="y")
        assert script.startswith("#!/usr/bin/env bash")
