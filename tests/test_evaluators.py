"""Tests for command_evaluator and http_evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from optimize_anything.evaluators import command_evaluator, http_evaluator, validate_evaluator_payload


class TestCommandEvaluator:
    def test_basic_evaluation(self, tmp_evaluator_script: Path):
        evaluate = command_evaluator([str(tmp_evaluator_script)])
        score, info = evaluate("hello")
        assert isinstance(score, float)
        assert score > 0
        assert "length" in info

    def test_returns_score_and_side_info(self, tmp_evaluator_script: Path):
        evaluate = command_evaluator([str(tmp_evaluator_script)])
        score, info = evaluate("test")
        assert score == pytest.approx(0.0392, abs=0.01)
        assert info["length"] == 4

    def test_invalid_json_output(self, tmp_bad_evaluator_script: Path):
        evaluate = command_evaluator([str(tmp_bad_evaluator_script)])
        score, info = evaluate("hello")
        assert score == 0.0
        assert "error" in info
        assert "not valid JSON" in info["error"]

    def test_command_failure(self, tmp_failing_evaluator_script: Path):
        evaluate = command_evaluator([str(tmp_failing_evaluator_script)])
        score, info = evaluate("hello")
        assert score == 0.0
        assert "error" in info
        assert "exited with code 1" in info["error"]

    def test_command_missing_executable(self, tmp_path: Path):
        missing = tmp_path / "missing-eval.sh"
        evaluate = command_evaluator([str(missing)])
        score, info = evaluate("hello")
        assert score == 0.0
        assert "error" in info
        assert "not found" in info["error"]

    def test_timeout(self, tmp_path: Path):
        script = tmp_path / "slow.sh"
        script.write_text("#!/usr/bin/env bash\nsleep 10\n")
        script.chmod(0o755)
        evaluate = command_evaluator([str(script)], timeout=0.1)
        score, info = evaluate("hello")
        assert score == 0.0
        assert "timed out" in info["error"]

    def test_candidate_passed_as_json(self, tmp_path: Path):
        script = tmp_path / "echo.sh"
        script.write_text('#!/usr/bin/env bash\ncat\n')
        script.chmod(0o755)
        evaluate = command_evaluator([str(script)])
        # The script echoes stdin back, which should be valid JSON
        score, info = evaluate("my candidate text")
        # Output is {"candidate": "my candidate text"} which has no "score"
        assert score == 0.0
        assert info.get("candidate") == "my candidate text"
        assert "missing required 'score'" in info["error"]

    def test_invalid_score_type(self, tmp_path: Path):
        script = tmp_path / "bad_score.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": "high"}\'\n')
        script.chmod(0o755)
        evaluate = command_evaluator([str(script)])
        score, info = evaluate("candidate")
        assert score == 0.0
        assert "must be numeric" in info["error"]

    def test_out_of_range_score_value(self, tmp_path: Path):
        script = tmp_path / "bad_range.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 1.2}\'\n')
        script.chmod(0o755)
        evaluate = command_evaluator([str(script)])
        score, info = evaluate("candidate")
        assert score == 0.0
        assert "between 0.0 and 1.0" in info["error"]

    def test_non_object_json_output(self, tmp_path: Path):
        script = tmp_path / "list_output.sh"
        script.write_text('#!/usr/bin/env bash\necho \'[1, 2, 3]\'\n')
        script.chmod(0o755)
        evaluate = command_evaluator([str(script)])
        score, info = evaluate("candidate")
        assert score == 0.0
        assert "must be a JSON object" in info["error"]


    def test_task_model_in_command_payload_and_env(self):
        with patch("optimize_anything.evaluators.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"score": 0.5}'
            mock_run.return_value = mock_proc

            evaluate = command_evaluator(["bash", "eval.sh"], task_model="openai/gpt-4o-mini")
            score, _ = evaluate("candidate text")

            assert score == 0.5
            call_kwargs = mock_run.call_args.kwargs
            payload = json.loads(call_kwargs["input"])
            assert payload["task_model"] == "openai/gpt-4o-mini"
            assert call_kwargs["env"]["OPTIMIZE_ANYTHING_TASK_MODEL"] == "openai/gpt-4o-mini"

    def test_example_in_command_payload(self):
        with patch("optimize_anything.evaluators.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"score": 0.5}'
            mock_run.return_value = mock_proc

            evaluate = command_evaluator(["bash", "eval.sh"])
            example = {"input": "foo", "label": "bar"}
            score, _ = evaluate("candidate text", example=example)

            assert score == 0.5
            payload = json.loads(mock_run.call_args.kwargs["input"])
            assert payload["example"] == example

    def test_command_uses_cwd(self, tmp_path: Path):
        script = tmp_path / "eval.sh"
        script.write_text(
            '#!/usr/bin/env bash\n'
            'input=$(cat)\n'
            'candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)[\'candidate\'])")\n'
            'if [ -f marker.txt ]; then\n'
            '  echo "{\\"score\\": 1.0, \\"candidate\\": \\"$candidate\\"}"\n'
            'else\n'
            '  echo "{\\"score\\": 0.0, \\"missing\\": \\"marker\\"}"\n'
            "fi\n"
        )
        script.chmod(0o755)
        (tmp_path / "marker.txt").write_text("ok")

        evaluate = command_evaluator(["./eval.sh"], cwd=str(tmp_path))
        score, info = evaluate("hello")

        assert score == 1.0
        assert info["candidate"] == "hello"


class TestHttpEvaluator:
    def test_basic_evaluation(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.85, "detail": "good"}
        mock_response.raise_for_status = MagicMock()

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response) as mock_post:
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test candidate")

            assert score == 0.85
            assert info == {"detail": "good"}
            mock_post.assert_called_once_with(
                "http://localhost:8000/eval",
                json={"_protocol_version": 2, "candidate": "test candidate"},
                timeout=30.0,
                headers={},
            )

    def test_custom_headers(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.5}
        mock_response.raise_for_status = MagicMock()

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response) as mock_post:
            evaluate = http_evaluator(
                "http://localhost:8000/eval",
                headers={"Authorization": "Bearer tok"},
            )
            evaluate("x")
            mock_post.assert_called_once_with(
                "http://localhost:8000/eval",
                json={"_protocol_version": 2, "candidate": "x"},
                timeout=30.0,
                headers={"Authorization": "Bearer tok"},
            )

    def test_task_model_in_http_payload(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.7}
        mock_response.raise_for_status = MagicMock()

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response) as mock_post:
            evaluate = http_evaluator("http://localhost:8000/eval", task_model="anthropic/claude-sonnet-4-6")
            score, _ = evaluate("test candidate")

            assert score == 0.7
            payload = mock_post.call_args.kwargs["json"]
            assert payload["task_model"] == "anthropic/claude-sonnet-4-6"

    def test_example_in_http_payload(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.9}
        mock_response.raise_for_status = MagicMock()

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response) as mock_post:
            evaluate = http_evaluator("http://localhost:8000/eval")
            example = {"context": "x", "expected": 1}
            score, _ = evaluate("test candidate", example=example)

            assert score == 0.9
            payload = mock_post.call_args.kwargs["json"]
            assert payload["example"] == example

    def test_timeout_error(self):
        import httpx as httpx_mod

        with patch(
            "optimize_anything.evaluators.httpx.post",
            side_effect=httpx_mod.TimeoutException("timed out"),
        ):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "timed out" in info["error"]

    def test_http_error(self):
        import httpx as httpx_mod

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch(
            "optimize_anything.evaluators.httpx.post",
            side_effect=httpx_mod.HTTPStatusError(
                "500", request=MagicMock(), response=mock_response
            ),
        ):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "500" in info["error"]

    def test_invalid_json_response(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "not json"

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "not valid JSON" in info["error"]

    def test_invalid_score_value(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"score": "great", "detail": "oops"}

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "must be numeric" in info["error"]

    def test_out_of_range_score_value(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"score": -0.25, "detail": "oops"}

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "between 0.0 and 1.0" in info["error"]

    def test_non_object_json_body(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [1, 2, 3]

        with patch("optimize_anything.evaluators.httpx.post", return_value=mock_response):
            evaluate = http_evaluator("http://localhost:8000/eval")
            score, info = evaluate("test")
            assert score == 0.0
            assert "must be a JSON object" in info["error"]


class TestValidateEvaluatorPayload:
    def test_valid_payload_returns_none(self):
        assert validate_evaluator_payload({"score": 0.5}) is None

    def test_valid_payload_with_extra_fields(self):
        assert validate_evaluator_payload({"score": 1.0, "feedback": "ok"}) is None

    def test_non_dict_returns_error(self):
        err = validate_evaluator_payload("not a dict")
        assert err == "evaluator output must be a JSON object"

    def test_non_dict_list_returns_error(self):
        err = validate_evaluator_payload([0.5])
        assert err == "evaluator output must be a JSON object"

    def test_missing_score_returns_error(self):
        err = validate_evaluator_payload({"feedback": "ok"})
        assert err == "evaluator output missing required 'score' field"

    def test_non_numeric_score_returns_error(self):
        err = validate_evaluator_payload({"score": "not-a-number"})
        assert err == "evaluator output 'score' must be numeric"

    def test_none_score_returns_error(self):
        err = validate_evaluator_payload({"score": None})
        assert err == "evaluator output 'score' must be numeric"

    def test_infinite_score_returns_error(self):
        import math
        err = validate_evaluator_payload({"score": math.inf})
        assert err == "evaluator output 'score' must be finite"

    def test_nan_score_returns_error(self):
        import math
        err = validate_evaluator_payload({"score": math.nan})
        assert err == "evaluator output 'score' must be finite"

    def test_score_below_zero_returns_error(self):
        err = validate_evaluator_payload({"score": -0.01})
        assert err == "evaluator output 'score' must be between 0.0 and 1.0"

    def test_score_above_one_returns_error(self):
        err = validate_evaluator_payload({"score": 1.01})
        assert err == "evaluator output 'score' must be between 0.0 and 1.0"

    def test_score_range_any_accepts_out_of_range_score(self):
        assert validate_evaluator_payload({"score": 1.5}, score_range="any") is None

    def test_score_range_any_rejects_nan_and_inf(self):
        import math
        assert validate_evaluator_payload({"score": math.nan}, score_range="any") == "evaluator output 'score' must be finite"
        assert validate_evaluator_payload({"score": math.inf}, score_range="any") == "evaluator output 'score' must be finite"


class TestScoreRangeParsing:
    def test_command_evaluator_unit_rejects_out_of_range(self, tmp_path: Path):
        script = tmp_path / "score_15.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 1.5}\'\n')
        script.chmod(0o755)

        evaluate = command_evaluator([str(script)], score_range="unit")
        score, info = evaluate("candidate")
        assert score == 0.0
        assert "between 0.0 and 1.0" in info["error"]

    def test_command_evaluator_any_accepts_out_of_range(self, tmp_path: Path):
        script = tmp_path / "score_15.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 1.5}\'\n')
        script.chmod(0o755)

        evaluate = command_evaluator([str(script)], score_range="any")
        score, info = evaluate("candidate")
        assert score == pytest.approx(1.5)
        assert "error" not in info

    def test_score_range_unit_is_default(self, tmp_path: Path):
        script = tmp_path / "score_15.sh"
        script.write_text('#!/usr/bin/env bash\necho \'{"score": 1.5}\'\n')
        script.chmod(0o755)

        evaluate = command_evaluator([str(script)])
        score, info = evaluate("candidate")
        assert score == 0.0
        assert "between 0.0 and 1.0" in info["error"]
