"""Offline account, isolation, schema, and cleanup tests for Codex SDK."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimize_anything.llm_backends.base import (
    AuthenticationError, BackendUnavailable, CompletionRequest, InvalidResponse, Timeout,
)
from optimize_anything.llm_backends.codex_backend import CodexSdkBackend


class FakeHandle:
    def __init__(self, sdk):
        self.sdk = sdk
        self.interrupted = False

    def run(self):
        if self.sdk.timeout:
            import time
            time.sleep(0.1)
        return SimpleNamespace(
            status="completed", error=None, final_response=self.sdk.response,
            usage=SimpleNamespace(total=SimpleNamespace(
                input_tokens=2, output_tokens=3, total_tokens=5,
            )),
        )

    def interrupt(self):
        self.interrupted = True


class FakeThread:
    def __init__(self, sdk):
        self.sdk = sdk

    def turn(self, prompt, **kwargs):
        self.sdk.turn_args.append((prompt, kwargs))
        self.sdk.handle = FakeHandle(self.sdk)
        return self.sdk.handle


class FakeClient:
    def __init__(self, sdk, config):
        self.sdk = sdk
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.sdk.closed += 1

    def account(self):
        return SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type=self.sdk.auth_type)))

    def thread_start(self, **kwargs):
        self.sdk.thread_args.append(kwargs)
        self.sdk.workspaces.append(kwargs["cwd"])
        assert list(Path(kwargs["cwd"]).iterdir()) == []
        return FakeThread(self.sdk)


class FakeSdk:
    __version__ = "0.156.0"
    Sandbox = SimpleNamespace(read_only="read-only")
    ApprovalMode = SimpleNamespace(deny_all="deny-all")

    def __init__(self):
        self.auth_type = "chatgpt"
        self.response = "done"
        self.timeout = False
        self.thread_args = []
        self.turn_args = []
        self.workspaces = []
        self.client_configs = []
        self.closed = 0
        self.handle = None

    def CodexConfig(self, **kwargs):
        self.client_configs.append(kwargs)
        return kwargs

    def Codex(self, *, config):
        return FakeClient(self, config)


def adapter(sdk, tmp_path):
    auth = tmp_path / "auth.json"
    auth.touch()
    return CodexSdkBackend(sdk_module=sdk, auth_path=auth)


def test_chatgpt_account_and_ephemeral_private_turn(tmp_path):
    sdk = FakeSdk()
    result = adapter(sdk, tmp_path).complete(CompletionRequest(prompt="private-prompt", role="proposer"))
    assert result.text == "done" and result.auth_source == "chatgpt"
    thread = sdk.thread_args[0]
    assert thread["ephemeral"] is True
    assert thread["sandbox"] == "read-only"
    assert thread["approval_mode"] == "deny-all"
    assert sdk.turn_args[0][0] == "private-prompt"
    assert "private-prompt" not in repr(sdk.client_configs)
    assert "features.shell_tool=false" in sdk.client_configs[0]["config_overrides"]
    private_home = sdk.client_configs[0]["env"]["CODEX_HOME"]
    assert not Path(private_home).exists()
    assert all(not Path(workspace).exists() for workspace in sdk.workspaces)
    assert sdk.closed == 1


def test_api_key_auth_is_rejected_before_thread_dispatch(tmp_path):
    sdk = FakeSdk()
    sdk.auth_type = "apiKey"
    with pytest.raises(AuthenticationError):
        adapter(sdk, tmp_path).complete(CompletionRequest(prompt="private", role="judge"))
    assert sdk.thread_args == []


def test_version_mismatch_fails_closed(tmp_path):
    sdk = FakeSdk()
    sdk.__version__ = "0.157.0"
    with pytest.raises(BackendUnavailable):
        adapter(sdk, tmp_path).preflight()
    assert sdk.client_configs == []


def test_structured_output_is_validated_locally(tmp_path):
    sdk = FakeSdk()
    sdk.response = json.dumps({"score": 2})
    request = CompletionRequest(prompt="judge", role="judge", output_schema={
        "type": "object", "properties": {"score": {"type": "integer", "maximum": 1}},
    })
    with pytest.raises(InvalidResponse):
        adapter(sdk, tmp_path).complete(request)
    assert sdk.turn_args[0][1]["output_schema"] == {
        "type": "object", "properties": {"score": {"type": "integer", "maximum": 1}},
    }


def test_timeout_interrupts_and_cleans_up(tmp_path):
    sdk = FakeSdk()
    sdk.timeout = True
    with pytest.raises(Timeout):
        adapter(sdk, tmp_path).complete(CompletionRequest(
            prompt="private", role="proposer", timeout_seconds=0.01,
        ))
    assert sdk.handle.interrupted is True
    assert sdk.closed == 1
    assert all(not Path(workspace).exists() for workspace in sdk.workspaces)
