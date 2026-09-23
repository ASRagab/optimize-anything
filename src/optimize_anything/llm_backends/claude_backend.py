"""Local, isolated Claude Code subscription completion adapter."""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Mapping, Sequence, cast

from jsonschema import Draft202012Validator, SchemaError, ValidationError  # type: ignore[import-untyped]

from .base import (
    AuthenticationError,
    BackendCapabilities,
    BackendStatus,
    BackendUnavailable,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    InvalidResponse,
    Timeout,
    Usage,
    thaw_json,
    validate_capabilities,
)
from .schema import reject_external_refs

_MIN_VERSION = (2, 1, 278)
_MAX_OUTPUT_BYTES = 1_048_576
_MAX_PROMPT_BYTES = 9_000_000
_TRANSPORT_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {"payload": {"type": "string"}},
        "required": ["payload"],
        "additionalProperties": False,
    },
    separators=(",", ":"),
)
_REQUIRED_FLAGS = (
    "--safe-mode",
    "--tools",
    "--disable-slash-commands",
    "--strict-mcp-config",
    "--mcp-config",
    "--no-session-persistence",
    "--output-format",
    "--json-schema",
    "--permission-prompts",
)
_BLOCKED_ENV_NAMES = {
    "CLAUDECODE",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_API_KEY_HELPER",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_ANTHROPIC_API",
    "API_KEY_HELPER",
}
_BLOCKED_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
    "AWS_",
    "GOOGLE_",
    "CLOUDSDK_",
    "GCP_",
    "VERTEX_",
    "BEDROCK_",
    "AZURE_",
    "FOUNDRY_",
)


@dataclass(frozen=True)
class _ProcessOutput:
    returncode: int
    stdout: bytes
    stderr: bytes


def _subscription_env(source: Mapping[str, str]) -> dict[str, str]:
    """Retain saved-login discovery while removing paid-auth overrides."""
    return {
        key: value
        for key, value in source.items()
        if key.upper() not in _BLOCKED_ENV_NAMES
        and not key.upper().startswith(_BLOCKED_ENV_PREFIXES)
    }


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, ProcessLookupError):
        if process.poll() is None:
            process.terminate()
    try:
        if process.poll() is None:
            process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError):
        if process.poll() is None:
            process.kill()
    if process.poll() is None:
        process.wait(timeout=2)


def _run_bounded(
    argv: Sequence[str], *, stdin: bytes, env: Mapping[str, str], cwd: str,
    timeout: float, max_output: int,
) -> _ProcessOutput:
    """Drain pipes incrementally and stop the child before buffers exceed the cap."""
    process = subprocess.Popen(
        argv, cwd=cwd, env=dict(env), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    assert process.stdin and process.stdout and process.stderr
    selector = selectors.DefaultSelector()
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    deadline = time.monotonic() + timeout
    written = 0
    try:
        for stream in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        if stdin:
            selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Timeout("Claude completion timed out")
            for key, _ in selector.select(min(remaining, 0.25)):
                stream = cast(BinaryIO, key.fileobj)
                if stream is process.stdin:
                    try:
                        written += os.write(stream.fileno(), stdin[written:written + 65536])
                    except BrokenPipeError:
                        written = len(stdin)
                    if written >= len(stdin):
                        selector.unregister(stream)
                        stream.close()
                else:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    buffers[stream].extend(chunk)
                    if sum(map(len, buffers.values())) > max_output:
                        raise InvalidResponse("Claude output exceeded the configured limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Timeout("Claude completion timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise Timeout("Claude completion timed out") from None
        return _ProcessOutput(returncode, bytes(buffers[process.stdout]), bytes(buffers[process.stderr]))
    finally:
        selector.close()
        _terminate(process)


class ClaudeCliBackend:
    """Runs one no-tools Claude print request using the user's saved login."""

    capabilities = BackendCapabilities(
        structured_output=True, model_override=True, sampling=False,
        cancellation=True, usage_reporting=True,
    )

    def __init__(
        self, *, executable: str = "claude", model: str | None = None,
        runner: Callable[..., _ProcessOutput] = _run_bounded,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = executable
        self.model = model
        self._runner = runner
        self._environ = environ

    def _env(self) -> dict[str, str]:
        return _subscription_env(os.environ if self._environ is None else self._environ)

    def _run(self, argv: Sequence[str], *, stdin: bytes = b"", cwd: str, timeout: float,
             max_output: int = 65536) -> _ProcessOutput:
        try:
            return self._runner(
                argv, stdin=stdin, env=self._env(), cwd=cwd,
                timeout=timeout, max_output=max_output,
            )
        except (Timeout, InvalidResponse):
            raise
        except (OSError, subprocess.SubprocessError):
            raise BackendUnavailable("Claude Code could not be started") from None

    def preflight(self) -> BackendStatus:
        executable = shutil.which(self.executable) if os.sep not in self.executable else self.executable
        if not executable or not Path(executable).is_file():
            raise BackendUnavailable("Install Claude Code and sign in with `claude auth login`")
        with tempfile.TemporaryDirectory(prefix="optimize-claude-preflight-") as workspace:
            version = self._run([executable, "--version"], cwd=workspace, timeout=10)
            match = re.search(rb"(\d+)\.(\d+)\.(\d+)", version.stdout)
            if version.returncode or not match or tuple(map(int, match.groups())) < _MIN_VERSION:
                raise BackendUnavailable("Claude Code 2.1.278 or newer is required")
            help_output = self._run([executable, "--help"], cwd=workspace, timeout=10)
            help_text = help_output.stdout.decode("utf-8", "replace")
            # --safe-mode is documented but hidden from some --help versions.
            required = tuple(flag for flag in _REQUIRED_FLAGS if flag != "--safe-mode")
            if help_output.returncode or any(flag not in help_text for flag in required):
                raise BackendUnavailable("Claude Code lacks required isolation flags")
            auth = self._run([executable, "auth", "status"], cwd=workspace, timeout=10)
        if auth.returncode:
            raise AuthenticationError("Sign in to Claude Code with a Claude subscription")
        try:
            status = json.loads(auth.stdout)
        except (ValueError, UnicodeDecodeError):
            raise BackendUnavailable("Claude auth status was not valid JSON") from None
        if not isinstance(status, dict) or not status.get("loggedIn"):
            raise AuthenticationError("Sign in to Claude Code with a Claude subscription")
        if status.get("authMethod") != "claude.ai" or status.get("apiProvider") != "firstParty":
            raise AuthenticationError("Claude Code is not using a Claude subscription")
        return BackendStatus(True, "claude", "subscription", "claude_subscription")

    def complete(self, request: CompletionRequest) -> CompletionResult:
        validate_capabilities(request, self.capabilities)
        if request.sampling is not None:
            raise ConfigurationError("Claude subscription does not support sampling controls")
        model = request.model or self.model
        if model is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model):
            raise ConfigurationError("invalid Claude model name")
        schema = thaw_json(request.output_schema) if request.output_schema is not None else None
        if schema is not None:
            reject_external_refs(schema)
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError:
                raise ConfigurationError("invalid output schema") from None
        prompt = request.prompt
        if request.system_prompt:
            prompt = f"System instruction:\n{request.system_prompt}\n\nTask:\n{prompt}"
        if schema is not None:
            prompt += "\n\nReturn a JSON value matching this schema inside the payload string:\n"
            prompt += json.dumps(schema, ensure_ascii=False)
        prompt_bytes = prompt.encode("utf-8")
        if len(prompt_bytes) > _MAX_PROMPT_BYTES:
            raise ConfigurationError("Claude input exceeds the supported size")
        self.preflight()
        started = datetime.now(timezone.utc)
        begin = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="optimize-claude-") as workspace:
            mcp_path = Path(workspace, "mcp.json")
            fd = os.open(mcp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write('{"mcpServers":{}}')
            argv = [
                self.executable, "-p", "--safe-mode", "--tools", "",
                "--disable-slash-commands",
                "--strict-mcp-config", "--mcp-config", str(mcp_path),
                "--no-session-persistence", "--permission-mode", "dontAsk",
                "--permission-prompts", "none", "--no-chrome",
                "--output-format", "json",
            ]
            if model:
                argv.extend(["--model", model])
            if schema is not None:
                argv.extend(["--json-schema", _TRANSPORT_SCHEMA])
            output = self._run(
                argv, stdin=prompt_bytes, cwd=workspace,
                timeout=request.timeout_seconds or 120, max_output=_MAX_OUTPUT_BYTES,
            )
        if output.returncode:
            raise BackendUnavailable("Claude completion failed")
        try:
            response = json.loads(output.stdout)
        except (UnicodeDecodeError, ValueError):
            raise InvalidResponse("Claude returned malformed JSON") from None
        if not isinstance(response, dict) or response.get("is_error"):
            raise InvalidResponse("Claude returned an invalid completion")
        structured = None
        if schema is not None:
            envelope = response.get("structured_output")
            if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), str):
                raise InvalidResponse("Claude omitted structured output")
            try:
                structured = json.loads(envelope["payload"])
                Draft202012Validator(schema).validate(structured)
            except (ValueError, ValidationError, SchemaError):
                raise InvalidResponse("Claude output did not match the requested schema") from None
            text = json.dumps(structured, ensure_ascii=False)
        else:
            raw_text = response.get("result")
            if not isinstance(raw_text, str) or not raw_text:
                raise InvalidResponse("Claude omitted completion text")
            text = raw_text
        usage_data = response.get("usage") or {}
        usage = Usage(
            input_tokens=usage_data.get("input_tokens"),
            output_tokens=usage_data.get("output_tokens"),
        ) if isinstance(usage_data, dict) else None
        return CompletionResult(
            text=text, structured=structured, requested_backend="claude",
            actual_backend="claude", requested_model=model,
            actual_model=response.get("model") or model,
            auth_class="subscription", auth_source="claude_subscription",
            usage=usage, role=request.role, started_at=started.isoformat(),
            duration_seconds=time.monotonic() - begin,
            prompt_contract_version=request.prompt_contract_version,
            schema_contract_version=request.schema_contract_version,
        )
