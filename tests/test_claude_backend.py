"""Offline security and contract tests for Claude CLI completion."""

import json
import os
import sys
from pathlib import Path

import pytest

from optimize_anything.llm_backends.base import (
    AuthenticationError, CompletionRequest, ConfigurationError, InvalidResponse, Timeout,
)
from optimize_anything.llm_backends.claude_backend import (
    ClaudeCliBackend, _ProcessOutput, _run_bounded, _subscription_env,
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
