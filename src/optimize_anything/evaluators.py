"""Evaluator factories for external processes and HTTP services.

These bridge external scoring systems to gepa's evaluator protocol:
    evaluator(candidate: str, example: object | None = None) -> float | tuple[float, dict]
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from typing import Any, Callable

import httpx


def command_evaluator(
    command: list[str],
    *,
    timeout: float = 30.0,
    cwd: str | None = None,
    score_range: str = "unit",
    task_model: str | None = None,
) -> Callable[[str, Any | None], tuple[float, dict[str, Any]]]:
    """Create an evaluator that runs a shell command."""

    def evaluate(candidate: str, example: Any | None = None) -> tuple[float, dict[str, Any]]:
        payload_data: dict[str, Any] = {
            "_protocol_version": 2,
            "candidate": candidate,
        }
        if example is not None:
            payload_data["example"] = example
        if task_model is not None:
            payload_data["task_model"] = task_model
        payload = json.dumps(payload_data)
        env = None
        if task_model is not None:
            env = os.environ.copy()
            env["OPTIMIZE_ANYTHING_TASK_MODEL"] = task_model
        try:
            proc = subprocess.run(
                command,
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
        except FileNotFoundError:
            return 0.0, {"error": f"Command executable not found: {command[0]}"}
        except subprocess.TimeoutExpired:
            return 0.0, {"error": f"Command timed out after {timeout}s"}
        except OSError as e:
            return 0.0, {"error": f"Command failed to start: {e}"}

        if proc.returncode != 0:
            return 0.0, {
                "error": f"Command exited with code {proc.returncode}",
                "stderr": proc.stderr.strip(),
            }

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return 0.0, {
                "error": "Command output is not valid JSON",
                "stdout": proc.stdout.strip(),
            }

        return _parse_evaluator_result(result, score_range=score_range)

    return evaluate


def http_evaluator(
    url: str,
    *,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    score_range: str = "unit",
    task_model: str | None = None,
) -> Callable[[str, Any | None], tuple[float, dict[str, Any]]]:
    """Create an evaluator that calls an HTTP endpoint."""

    def evaluate(candidate: str, example: Any | None = None) -> tuple[float, dict[str, Any]]:
        payload: dict[str, Any] = {
            "_protocol_version": 2,
            "candidate": candidate,
        }
        if example is not None:
            payload["example"] = example
        if task_model is not None:
            payload["task_model"] = task_model
        try:
            resp = httpx.post(
                url,
                json=payload,
                timeout=timeout,
                headers=headers or {},
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            return 0.0, {"error": f"HTTP request timed out after {timeout}s"}
        except httpx.HTTPStatusError as e:
            return 0.0, {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except httpx.RequestError as e:
            return 0.0, {"error": f"HTTP request failed: {e}"}

        try:
            result = resp.json()
        except (json.JSONDecodeError, ValueError):
            return 0.0, {
                "error": "Response is not valid JSON",
                "body": resp.text[:500],
            }

        return _parse_evaluator_result(result, score_range=score_range)

    return evaluate


def validate_evaluator_payload(result: Any, score_range: str = "unit") -> str | None:
    """Return None if valid, or a human-readable error string."""
    if not isinstance(result, dict):
        return "evaluator output must be a JSON object"
    if "score" not in result:
        return "evaluator output missing required 'score' field"
    raw_score = result["score"]
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return "evaluator output 'score' must be numeric"
    if not math.isfinite(score):
        return "evaluator output 'score' must be finite"
    if score_range == "unit" and (score < 0.0 or score > 1.0):
        return "evaluator output 'score' must be between 0.0 and 1.0"
    return None


def _parse_evaluator_result(result: Any, score_range: str = "unit") -> tuple[float, dict[str, Any]]:
    """Validate evaluator JSON payload and extract score + side information."""
    if not isinstance(result, dict):
        return 0.0, {
            "error": "Evaluator output must be a JSON object",
            "received_type": type(result).__name__,
        }

    side_info = {k: v for k, v in result.items() if k != "score"}
    if "score" not in result:
        side_info["error"] = "Evaluator output missing required 'score' field"
        return 0.0, side_info

    raw_score = result["score"]
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return _evaluator_score_error(side_info, raw_score, "Evaluator 'score' must be numeric")

    if not math.isfinite(score):
        return _evaluator_score_error(side_info, raw_score, "Evaluator 'score' must be finite")

    if score_range == "unit" and (score < 0.0 or score > 1.0):
        return _evaluator_score_error(
            side_info,
            raw_score,
            "Evaluator 'score' must be between 0.0 and 1.0",
        )
    return score, side_info


def _evaluator_score_error(
    side_info: dict[str, Any],
    raw_score: Any,
    message: str,
) -> tuple[float, dict[str, Any]]:
    side_info["error"] = message
    side_info["score"] = raw_score
    return 0.0, side_info
