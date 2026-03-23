"""Evaluator preflight validation checks."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _preflight_command_evaluator(
    command: list[str],
    *,
    cwd: str | None,
    score_range: str = "unit",
) -> str | None:
    cwd_path, path_error = _validate_command_preflight_paths(command=command, cwd=cwd)
    if path_error is not None:
        return path_error

    proc, run_error = _run_command_preflight(command=command, cwd=cwd, cwd_path=cwd_path)
    if run_error is not None:
        return run_error

    assert proc is not None
    return _validate_command_preflight_result(
        command=command,
        cwd=cwd,
        proc=proc,
        score_range=score_range,
    )


def _validate_command_preflight_paths(
    *,
    command: list[str],
    cwd: str | None,
) -> tuple[Path | None, str | None]:
    cwd_path: Path | None = None
    if cwd is not None:
        cwd_path = _resolve_path(cwd, base=Path.cwd())
        if not cwd_path.exists():
            return None, _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=f"evaluator cwd does not exist: {cwd}",
            )
        if not cwd_path.is_dir():
            return None, _format_preflight_error(
                command=command,
                cwd=cwd,
                detail=f"evaluator cwd is not a directory: {cwd}",
            )

    executable_error = _validate_command_executable(command[0], cwd_path)
    if executable_error is not None:
        return None, _format_preflight_error(command=command, cwd=cwd, detail=executable_error)

    script_arg = _maybe_script_path_arg(command)
    if script_arg is None:
        return cwd_path, None

    script_path = _resolve_path(script_arg, base=cwd_path or Path.cwd())
    if not script_path.exists():
        return None, _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=(
                f"script path not found: {script_arg}. "
                "Use a correct relative path or set --evaluator-cwd."
            ),
        )
    if script_path.is_dir():
        return None, _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=f"script path is a directory: {script_arg}",
        )
    return cwd_path, None


def _run_command_preflight(
    *,
    command: list[str],
    cwd: str | None,
    cwd_path: Path | None,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    payload = json.dumps({"_protocol_version": 2, "candidate": "__optimize_anything_preflight__"})
    run_cwd = str(cwd_path) if cwd_path is not None else None
    try:
        proc = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=10.0,
            cwd=run_cwd,
        )
    except FileNotFoundError:
        return None, _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=f"command executable not found: {command[0]}",
        )
    except subprocess.TimeoutExpired:
        return None, _format_preflight_error(
            command=command,
            cwd=cwd,
            detail="command timed out during preflight after 10.0s",
        )
    return proc, None


def _validate_command_preflight_result(
    *,
    command: list[str],
    cwd: str | None,
    proc: subprocess.CompletedProcess[str],
    score_range: str,
) -> str | None:
    if proc.returncode != 0:
        detail = f"command exited with code {proc.returncode}"
        stderr = proc.stderr.strip()
        if stderr:
            detail = f"{detail}; stderr: {stderr[:300]}"
        return _format_preflight_error(command=command, cwd=cwd, detail=detail)

    stdout = proc.stdout.strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        snippet = stdout[:300] if stdout else "<empty stdout>"
        return _format_preflight_error(
            command=command,
            cwd=cwd,
            detail=f"stdout is not valid JSON: {exc.msg}; stdout: {snippet}",
        )

    payload_error = _validate_evaluator_payload(result, score_range=score_range)
    if payload_error is not None:
        return _format_preflight_error(command=command, cwd=cwd, detail=payload_error)
    return None


def _preflight_http_evaluator(
    url: str,
    *,
    timeout: float = 10.0,
    score_range: str = "unit",
) -> str | None:
    import httpx

    payload = {"_protocol_version": 2, "candidate": "__optimize_anything_preflight__"}
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.TimeoutException:
        return (
            f"Error: HTTP evaluator preflight timed out after {timeout}s "
            f"(url: {url})"
        )
    except httpx.HTTPStatusError as e:
        return (
            f"Error: HTTP evaluator preflight returned HTTP {e.response.status_code} "
            f"(url: {url})"
        )
    except httpx.ConnectError:
        return (
            f"Error: HTTP evaluator preflight failed — connection refused "
            f"(url: {url}). Is the evaluator server running?"
        )
    except httpx.RequestError as e:
        return f"Error: HTTP evaluator preflight request failed (url: {url}): {e}"

    try:
        result = resp.json()
    except ValueError:
        snippet = resp.text[:300] if resp.text else "<empty body>"
        return (
            f"Error: HTTP evaluator preflight returned non-JSON response "
            f"(url: {url}): {snippet}"
        )

    payload_error = _validate_evaluator_payload(result, score_range=score_range)
    if payload_error is not None:
        return f"Error: HTTP evaluator preflight response invalid (url: {url}): {payload_error}"

    return None


def _validate_command_executable(command_part: str, cwd: Path | None) -> str | None:
    if "/" in command_part:
        executable = _resolve_path(command_part, base=cwd or Path.cwd())
        if not executable.exists():
            return f"command executable path not found: {command_part}"
        if executable.is_dir():
            return f"command executable is a directory: {command_part}"
        return None

    if shutil.which(command_part) is None:
        return f"command executable not found in PATH: {command_part}"
    return None


def _maybe_script_path_arg(command: list[str]) -> str | None:
    if len(command) < 2:
        return None
    executable = Path(command[0]).name.lower()
    if executable in {"bash", "sh", "zsh", "python", "python3", "node", "ruby", "perl"}:
        script_arg = command[1]
        if script_arg in {"-c", "-m"} or script_arg.startswith("-"):
            return None
        return script_arg
    return None


def _validate_evaluator_payload(result: object, score_range: str = "unit") -> str | None:
    from optimize_anything.evaluators import validate_evaluator_payload
    return validate_evaluator_payload(result, score_range=score_range)


def _resolve_path(path: str, *, base: Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = base / resolved
    return resolved


def _format_preflight_error(*, command: list[str], cwd: str | None, detail: str) -> str:
    command_text = " ".join(shlex.quote(part) for part in command)
    cwd_text = cwd or os.getcwd()
    return (
        f"Error: evaluator preflight failed for command '{command_text}' "
        f"(cwd: {cwd_text}): {detail}"
    )
