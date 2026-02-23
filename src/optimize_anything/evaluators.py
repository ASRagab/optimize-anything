"""Evaluator factories for external processes and HTTP services.

These bridge external scoring systems to gepa's evaluator protocol:
    evaluator(candidate: str) -> float | tuple[float, dict]
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

import httpx


def command_evaluator(
    command: list[str],
    *,
    timeout: float = 30.0,
) -> Callable[[str], tuple[float, dict[str, Any]]]:
    """Create an evaluator that runs a shell command.

    The command receives JSON on stdin: {"candidate": "<text>"}
    and must output JSON on stdout with at least a "score" field.
    Additional fields become side information for gepa's reflection.

    Args:
        command: Command and arguments to execute.
        timeout: Max seconds to wait for the command.

    Returns:
        An evaluator function compatible with gepa.
    """

    def evaluate(candidate: str) -> tuple[float, dict[str, Any]]:
        payload = json.dumps({"candidate": candidate})
        try:
            proc = subprocess.run(
                command,
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return 0.0, {"error": f"Command timed out after {timeout}s"}

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

        score = float(result.get("score", 0.0))
        side_info = {k: v for k, v in result.items() if k != "score"}
        return score, side_info

    return evaluate


def http_evaluator(
    url: str,
    *,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> Callable[[str], tuple[float, dict[str, Any]]]:
    """Create an evaluator that calls an HTTP endpoint.

    Sends a POST request with JSON body: {"candidate": "<text>"}
    Expects a JSON response with at least a "score" field.

    Args:
        url: HTTP endpoint URL.
        timeout: Max seconds to wait for the response.
        headers: Optional HTTP headers.

    Returns:
        An evaluator function compatible with gepa.
    """

    def evaluate(candidate: str) -> tuple[float, dict[str, Any]]:
        payload = {"candidate": candidate}
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

        score = float(result.get("score", 0.0))
        side_info = {k: v for k, v in result.items() if k != "score"}
        return score, side_info

    return evaluate
