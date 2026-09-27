"""Offline security and contract tests for Claude CLI completion."""

import json
import logging
import os
import sys
from pathlib import Path

import pytest

from optimize_anything.llm_backends.base import (
    AuthenticationError, BackendUnavailable, CompletionRequest, ConfigurationError, InvalidResponse, Timeout,
)
from optimize_anything.llm_backends.claude_backend import (
    ClaudeCliBackend, _ProcessOutput, _run_bounded, _subscription_env, _TRANSPORT_SCHEMA,
)


class FakeRunner:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"result": "done", "model": "sonnet"}
        self.auth = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}

    def __call__(self, argv, *, stdin, env, cwd, timeout, max_output):
        self.calls.append((list(argv), stdin, env, cwd, timeout, max_output))
        if "--version" in argv:
            return _ProcessOutput(0, b"2.1.278 (Claude Code)", b"")
        if "--help" in argv:
            from optimize_anything.llm_backends.claude_backend import _REQUIRED_FLAGS
            return _ProcessOutput(0, " ".join(_REQUIRED_FLAGS).encode(), b"")
        if "auth" in argv:
            return _ProcessOutput(0, json.dumps(self.auth).encode(), b"")
        assert Path(cwd).is_dir()
        assert Path(argv[argv.index("--mcp-config") + 1]).read_text() == '{"mcpServers":{}}'
        return _ProcessOutput(0, json.dumps(self.response).encode(), b"")


def backend(tmp_path, runner):
    executable = tmp_path / "claude"
    executable.write_text("")
    return ClaudeCliBackend(
        executable=str(executable), runner=runner,
        environ={
            "HOME": "/saved-login", "CLAUDE_CONFIG_DIR": "/saved-config",
            "ANTHROPIC_API_KEY": "sentinel-api-key", "CLAUDE_CODE_OAUTH_TOKEN": "sentinel-token",
            "CLAUDECODE": "parent-agent", "AWS_ACCESS_KEY_ID": "sentinel-aws",
            "CLAUDE_CODE_USE_BEDROCK": "1", "GOOGLE_APPLICATION_CREDENTIALS": "sentinel-google",
        },
    )


def test_preflight_requires_claude_subscription_under_scrubbed_env(tmp_path):
    runner = FakeRunner()
    adapter = backend(tmp_path, runner)
    assert adapter.preflight().auth_source == "claude_subscription"
    for _, _, env, _, _, _ in runner.calls:
        assert env["HOME"] == "/saved-login"
        assert env["CLAUDE_CONFIG_DIR"] == "/saved-config"
        assert all("sentinel" not in value for value in env.values())
        assert "CLAUDECODE" not in env
    runner.auth["authMethod"] = "apiKey"
    with pytest.raises(AuthenticationError):
        adapter.preflight()


def test_schema_and_user_content_stay_off_argv_and_are_locally_validated(tmp_path):
    runner = FakeRunner({"structured_output": {"payload": '{"secret-property":"secret-enum"}'}})
    adapter = backend(tmp_path, runner)
    schema = {
        "type": "object", "properties": {
            "secret-property": {"type": "string", "enum": ["secret-enum"]}
        }, "required": ["secret-property"],
    }
    result = adapter.complete(CompletionRequest(
        prompt="private-candidate", role="judge", output_schema=schema,
    ))
    assert result.structured["secret-property"] == "secret-enum"
    argv, stdin, env, cwd, _, _ = runner.calls[-1]
    joined = " ".join(argv)
    assert all(value not in joined for value in ("private-candidate", "secret-property", "secret-enum"))
    assert all(value in stdin.decode() for value in ("private-candidate", "secret-property", "secret-enum"))
    assert "--safe-mode" in argv and "--bare" not in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert not Path(cwd).exists()


def test_original_schema_rejects_transport_valid_value(tmp_path):
    runner = FakeRunner({"structured_output": {"payload": '{"score":2}'}})
    adapter = backend(tmp_path, runner)
    with pytest.raises(InvalidResponse):
        adapter.complete(CompletionRequest(
            prompt="judge", role="judge", output_schema={
                "type": "object", "properties": {"score": {"type": "integer", "maximum": 1}},
            },
        ))


def test_timeout_is_typed_and_private_workspace_is_removed(tmp_path):
    class TimedOut(FakeRunner):
        def __call__(self, argv, **kwargs):
            if "-p" in argv:
                self.calls.append((argv, kwargs["stdin"], kwargs["env"], kwargs["cwd"], kwargs["timeout"], kwargs["max_output"]))
                raise Timeout("timed out")
            return super().__call__(argv, **kwargs)

    runner = TimedOut()
    with pytest.raises(Timeout):
        backend(tmp_path, runner).complete(CompletionRequest(prompt="secret", role="proposer"))
    assert not Path(runner.calls[-1][3]).exists()


def test_scrubber_covers_paid_auth_and_keeps_saved_login_location():
    env = _subscription_env({
        "HOME": "/home/user", "CLAUDE_CONFIG_DIR": "/config",
        "ANTHROPIC_BASE_URL": "bad", "AZURE_CLIENT_SECRET": "bad",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE": "bad", "CLAUDE_CODE_API_KEY_HELPER": "bad",
    })
    assert env == {"HOME": "/home/user", "CLAUDE_CONFIG_DIR": "/config"}


def test_external_schema_ref_is_rejected_before_completion(tmp_path):
    runner = FakeRunner()
    with pytest.raises(ConfigurationError):
        backend(tmp_path, runner).complete(CompletionRequest(
            prompt="private", role="judge", output_schema={"$ref": "https://example.com/schema"},
        ))
    assert not any("-p" in call[0] for call in runner.calls)


def test_external_dynamic_schema_ref_is_rejected_before_completion(tmp_path):
    runner = FakeRunner()
    with pytest.raises(ConfigurationError):
        backend(tmp_path, runner).complete(CompletionRequest(
            prompt="private", role="judge",
            output_schema={"$dynamicRef": "http://127.0.0.1/internal"},
        ))
    assert not any("-p" in call[0] for call in runner.calls)


def test_real_process_runner_bounds_output_and_terminates_on_timeout(tmp_path):
    with pytest.raises(InvalidResponse):
        _run_bounded(
            [sys.executable, "-c", "print('x' * 10000)"], stdin=b"",
            env=os.environ, cwd=str(tmp_path), timeout=2, max_output=100,
        )
    with pytest.raises(Timeout):
        _run_bounded(
            [sys.executable, "-c", "import time; time.sleep(2)"], stdin=b"",
            env=os.environ, cwd=str(tmp_path), timeout=0.02, max_output=100,
        )


class OldVersionRunner(FakeRunner):
    """FakeRunner whose --version output is older than the adapter's minimum supported version."""

    def __call__(self, argv, **kwargs):
        if "--version" in argv:
            self.calls.append(
                (list(argv), kwargs["stdin"], kwargs["env"], kwargs["cwd"], kwargs["timeout"], kwargs["max_output"])
            )
            return _ProcessOutput(0, b"2.1.277 (Claude Code)", b"")
        return super().__call__(argv, **kwargs)


class MissingFlagRunner(FakeRunner):
    """FakeRunner whose --help output omits a required isolation flag other than --safe-mode."""

    def __call__(self, argv, **kwargs):
        if "--help" in argv:
            self.calls.append(
                (list(argv), kwargs["stdin"], kwargs["env"], kwargs["cwd"], kwargs["timeout"], kwargs["max_output"])
            )
            from optimize_anything.llm_backends.claude_backend import _REQUIRED_FLAGS
            flags = " ".join(flag for flag in _REQUIRED_FLAGS if flag != "--tools")
            return _ProcessOutput(0, flags.encode(), b"")
        return super().__call__(argv, **kwargs)


class CompletionOutputRunner(FakeRunner):
    """FakeRunner that returns a caller-supplied _ProcessOutput for the completion (-p) call."""

    def __init__(self, output):
        super().__init__()
        self._output = output

    def __call__(self, argv, **kwargs):
        if "-p" in argv:
            self.calls.append(
                (list(argv), kwargs["stdin"], kwargs["env"], kwargs["cwd"], kwargs["timeout"], kwargs["max_output"])
            )
            return self._output
        return super().__call__(argv, **kwargs)


class StdinEchoingRunner(FakeRunner):
    """FakeRunner whose completion call echoes the received stdin into stdout/stderr, so a test
    can prove the backend never relays raw child output containing the prompt."""

    def __init__(self, returncode):
        super().__init__()
        self._returncode = returncode

    def __call__(self, argv, **kwargs):
        if "-p" in argv:
            stdin = kwargs["stdin"]
            self.calls.append(
                (list(argv), stdin, kwargs["env"], kwargs["cwd"], kwargs["timeout"], kwargs["max_output"])
            )
            if self._returncode:
                return _ProcessOutput(self._returncode, stdin, b"err: " + stdin)
            return _ProcessOutput(0, json.dumps(self.response).encode(), b"stderr-noise: " + stdin)
        return super().__call__(argv, **kwargs)


def test_preflight_rejects_logged_out_status_before_any_completion_call(tmp_path):
    """R3/R10: a signed-out Claude CLI (loggedIn: false) must fail preflight with the sign-in
    remediation, and complete() must never launch a completion subprocess after that rejection."""
    runner = FakeRunner()
    runner.auth["loggedIn"] = False
    adapter = backend(tmp_path, runner)
    with pytest.raises(AuthenticationError) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert str(exc_info.value) == "Sign in to Claude Code with a Claude subscription"
    assert len(runner.calls) == 3
    assert not any("-p" in call[0] for call in runner.calls)


def test_adapter_never_invokes_auth_flow_commands(tmp_path):
    """R3: subscription adapters must never initiate their own login/setup-token flow; only
    version/help/auth-status/completion argv may reach the CLI, across both preflight and complete."""
    runner = FakeRunner()
    adapter = backend(tmp_path, runner)
    adapter.preflight()
    adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert runner.calls
    executable = str(tmp_path / "claude")
    for argv, *_ in runner.calls:
        assert argv[0] == executable
        for arg in argv[1:]:
            assert "login" not in arg
            assert "setup-token" not in arg


@pytest.mark.parametrize(
    "api_provider",
    ["bedrock", "console-api-key"],
    ids=["cloud-provider", "api-key-provider"],
)
def test_preflight_rejects_non_first_party_api_provider(tmp_path, api_provider):
    """R10: only a first-party claude.ai subscription is accepted; cloud-hosted auth or a direct
    API key must be rejected even when authMethod already reports claude.ai."""
    runner = FakeRunner()
    runner.auth["apiProvider"] = api_provider
    adapter = backend(tmp_path, runner)
    with pytest.raises(AuthenticationError) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert str(exc_info.value) == "Claude Code is not using a Claude subscription"
    assert len(runner.calls) == 3
    assert not any("-p" in call[0] for call in runner.calls)


def test_missing_executable_is_reported_with_remediation_and_no_calls(tmp_path):
    """R10: a Claude CLI that isn't installed must fail closed with install/sign-in remediation
    before any subprocess, including a completion call, is attempted."""
    runner = FakeRunner()
    missing_path = str(tmp_path / "no-such-claude")
    adapter = ClaudeCliBackend(executable=missing_path, runner=runner, environ={})
    with pytest.raises(BackendUnavailable) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert str(exc_info.value) == "Install Claude Code and sign in with `claude auth login`"
    assert runner.calls == []


def test_old_cli_version_is_rejected_before_help_or_auth_calls(tmp_path):
    """R10: a Claude CLI older than the minimum supported version must fail closed with
    actionable remediation, without proceeding to flag/auth checks or completion."""
    runner = OldVersionRunner()
    adapter = backend(tmp_path, runner)
    with pytest.raises(BackendUnavailable) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert str(exc_info.value) == "Claude Code 2.1.278 or newer is required"
    assert len(runner.calls) == 1
    assert "--version" in runner.calls[0][0]


def test_missing_required_help_flag_is_rejected_before_auth_or_completion(tmp_path):
    """R10: a Claude CLI whose --help omits a required isolation flag (other than the
    deliberately excluded --safe-mode) must fail closed before auth or completion."""
    runner = MissingFlagRunner()
    adapter = backend(tmp_path, runner)
    with pytest.raises(BackendUnavailable) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert str(exc_info.value) == "Claude Code lacks required isolation flags"
    assert len(runner.calls) == 2
    assert "--version" in runner.calls[0][0]
    assert "--help" in runner.calls[1][0]
    assert not any("auth" in call[0] for call in runner.calls)
    assert not any("-p" in call[0] for call in runner.calls)


@pytest.mark.parametrize(
    "output, expected_exception, expected_message",
    [
        (_ProcessOutput(1, b"", b"boom"), BackendUnavailable, "Claude completion failed"),
        (_ProcessOutput(0, b"not-json{", b""), InvalidResponse, "Claude returned malformed JSON"),
        (_ProcessOutput(0, b"[]", b""), InvalidResponse, "Claude returned an invalid completion"),
        (
            _ProcessOutput(0, json.dumps({"is_error": True}).encode(), b""),
            InvalidResponse,
            "Claude returned an invalid completion",
        ),
        (
            _ProcessOutput(
                0,
                json.dumps(
                    {"is_error": True, "subtype": "error_during_execution", "result": "partial"}
                ).encode(),
                b"",
            ),
            InvalidResponse,
            "Claude returned an invalid completion",
        ),
    ],
    ids=["nonzero-exit", "malformed-json", "non-dict-json", "is-error-no-result", "is-error-with-result"],
)
def test_complete_maps_exit_and_error_result_shapes_to_typed_errors(
    tmp_path, output, expected_exception, expected_message
):
    """R10: complete() must map each nonzero-exit/error-result shape it recognizes to the exact
    typed error the code implements, including when an is_error payload still carries a usable
    result, so callers can branch on category instead of parsing raw CLI output."""
    runner = CompletionOutputRunner(output)
    adapter = backend(tmp_path, runner)
    with pytest.raises(expected_exception) as exc_info:
        adapter.complete(CompletionRequest(prompt="hello", role="proposer"))
    assert exc_info.type is expected_exception
    assert str(exc_info.value) == expected_message


def test_user_schema_const_value_stays_off_argv(tmp_path):
    """R8: const sentinel values in the caller-supplied schema must travel only on stdin, never
    in argv of any call, since argv can leak into process listings or logs that stdin does not."""
    sentinel = "const-sentinel-quokka-42"
    schema = {
        "type": "object",
        "properties": {"marker": {"const": sentinel}},
        "required": ["marker"],
    }
    runner = FakeRunner({"structured_output": {"payload": json.dumps({"marker": sentinel})}})
    adapter = backend(tmp_path, runner)
    result = adapter.complete(CompletionRequest(prompt="benign", role="judge", output_schema=schema))
    assert result.structured["marker"] == sentinel
    for argv, *_ in runner.calls:
        assert all(sentinel not in arg for arg in argv)
    completion_argv, completion_stdin, *_ = next(call for call in runner.calls if "-p" in call[0])
    assert sentinel in completion_stdin.decode()
    assert completion_argv[completion_argv.index("--json-schema") + 1] == _TRANSPORT_SCHEMA


def test_prompt_sentinel_stays_out_of_logs_and_output_on_success(tmp_path, caplog, capsys):
    """R8: prompts are sensitive user/candidate content; even though the (simulated) child
    process's stderr chatter contains it, the backend must never print or log it on success."""
    sentinel = "prompt-sentinel-nightjar-9"
    caplog.set_level(logging.DEBUG)
    runner = StdinEchoingRunner(returncode=0)
    adapter = backend(tmp_path, runner)
    result = adapter.complete(CompletionRequest(prompt=sentinel, role="proposer"))
    assert result.text == "done"
    completion_call = next(call for call in runner.calls if "-p" in call[0])
    assert sentinel in completion_call[1].decode()
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_prompt_sentinel_stays_out_of_logs_and_error_on_nonzero_exit(tmp_path, caplog, capsys):
    """R8: even when completion fails and the (simulated) child echoes the prompt back on
    stdout/stderr, the raised error message and any logs/output must not repeat it."""
    sentinel = "prompt-sentinel-egret-9"
    caplog.set_level(logging.DEBUG)
    runner = StdinEchoingRunner(returncode=1)
    adapter = backend(tmp_path, runner)
    with pytest.raises(BackendUnavailable) as exc_info:
        adapter.complete(CompletionRequest(prompt=sentinel, role="proposer"))
    assert str(exc_info.value) == "Claude completion failed"
    completion_call = next(call for call in runner.calls if "-p" in call[0])
    assert sentinel in completion_call[1].decode()
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err
