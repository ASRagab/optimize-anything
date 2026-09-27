"""Offline account, isolation, schema, and cleanup tests for Codex SDK."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimize_anything.llm_backends import codex_backend
from optimize_anything.llm_backends.base import (
    AuthenticationError, BackendUnavailable, CompletionRequest, ConfigurationError,
    InvalidResponse, Timeout,
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


# --- Offline gap-closing tests: docs/verification/subscription-backends-audit.md ---
# Covers R3 (auth.json symlink/refusal/no-login), R8 (size caps, isolation overrides,
# prompt/log secrecy), and R11 (_module fail-closed branches, _sdk remediation,
# structured-output success).


class _RecordingSdk(FakeSdk):
    """FakeSdk variant that also appends every SDK/client/thread call name to `self.calls`,
    so a test can prove no call named or containing "login" was ever made."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def CodexConfig(self, **kwargs):
        self.calls.append("CodexConfig")
        return super().CodexConfig(**kwargs)

    def Codex(self, *, config):
        self.calls.append("Codex")
        return _RecordingClient(self, config)


class _RecordingClient(FakeClient):
    def account(self):
        self.sdk.calls.append("account")
        return super().account()

    def thread_start(self, **kwargs):
        self.sdk.calls.append("thread_start")
        super().thread_start(**kwargs)
        return _RecordingThread(self.sdk)


class _RecordingThread(FakeThread):
    def turn(self, prompt, **kwargs):
        self.sdk.calls.append("turn")
        return super().turn(prompt, **kwargs)


def _sdk_missing(name):
    """Build a stub SDK with a valid version but the named required isolation attribute
    absent, for exercising every CodexSdkBackend._module fail-closed branch."""
    sdk = SimpleNamespace(
        __version__=codex_backend._SDK_VERSION,
        Codex=lambda **kwargs: None,
        CodexConfig=lambda **kwargs: None,
        Sandbox=SimpleNamespace(read_only="read-only"),
        ApprovalMode=SimpleNamespace(deny_all="deny-all"),
    )
    if name in ("Codex", "CodexConfig", "Sandbox", "ApprovalMode"):
        delattr(sdk, name)
    elif name == "Sandbox.read_only":
        sdk.Sandbox = SimpleNamespace()
    elif name == "ApprovalMode.deny_all":
        sdk.ApprovalMode = SimpleNamespace()
    else:
        raise ValueError(f"unknown case: {name}")
    return sdk


class _MidFlightCheckClient(FakeClient):
    """FakeClient variant that inspects the private CODEX_HOME while the real complete()
    tempdirs are still alive (account() runs before both TemporaryDirectory contexts exit),
    proving the symlink lives inside the exact directory _client() forwarded to the SDK."""

    def account(self):
        private_home = self.config["env"]["CODEX_HOME"]
        linked = Path(private_home) / "auth.json"
        assert linked.is_symlink(), "auth.json inside the forwarded CODEX_HOME must be a symlink"
        assert linked.resolve() == self.sdk.real_auth_path.resolve()
        return super().account()


class _MidFlightCheckSdk(FakeSdk):
    def __init__(self, real_auth_path):
        super().__init__()
        self.real_auth_path = real_auth_path

    def Codex(self, *, config):
        return _MidFlightCheckClient(self, config)


def test_prepare_private_home_symlinks_auth_json_not_copies(tmp_path):
    """R3: auth.json must be linked, never copied — copying would leave a second credential
    file outside the user's control, defeating the "no credential copying" guarantee."""
    sdk = FakeSdk()
    backend = adapter(sdk, tmp_path)
    private_home = tmp_path / "private-home"
    private_home.mkdir()
    backend._prepare_private_home(str(private_home))
    linked = private_home / "auth.json"
    assert linked.is_symlink()
    assert linked.resolve() == backend._auth_path.resolve()


def test_prepare_private_home_link_target_matches_the_codex_home_forwarded_to_sdk(tmp_path):
    """R3: the symlink _prepare_private_home creates must sit inside the exact CODEX_HOME
    that _client() forwards to the SDK — testing _prepare_private_home in isolation proves
    the method works, but not that complete() wires the two calls to the same directory; a
    future change that passed mismatched paths would pass an isolated test but leak here."""
    auth = tmp_path / "auth.json"
    auth.touch()
    sdk = _MidFlightCheckSdk(auth)
    backend = CodexSdkBackend(sdk_module=sdk, auth_path=auth)
    result = backend.complete(CompletionRequest(prompt="private", role="proposer"))
    assert result.text == "done"


def test_missing_auth_json_is_rejected_before_thread_dispatch(tmp_path):
    """R3: a missing saved auth.json must fail closed with a typed, actionable error before
    any SDK thread or turn starts — dispatching first could waste isolation setup or mask
    that the user was never actually authenticated."""
    sdk = FakeSdk()
    backend = CodexSdkBackend(sdk_module=sdk, auth_path=tmp_path / "auth.json")
    with pytest.raises(BackendUnavailable) as exc_info:
        backend.complete(CompletionRequest(prompt="private", role="proposer"))
    assert str(exc_info.value) == "Saved Codex login was not found; run `codex login`"
    assert sdk.client_configs == []
    assert sdk.thread_args == []
    assert sdk.turn_args == []


def test_symlinked_saved_auth_json_is_rejected_before_thread_dispatch(tmp_path):
    """R3: a saved auth.json that is itself a symlink must be refused, not followed —
    accepting it would let something outside the user's saved-login location control what
    gets linked into the private CODEX_HOME."""
    sdk = FakeSdk()
    real_auth = tmp_path / "real-auth.json"
    real_auth.write_text("fake-chatgpt-auth-for-tests")
    saved_auth = tmp_path / "auth.json"
    saved_auth.symlink_to(real_auth)
    backend = CodexSdkBackend(sdk_module=sdk, auth_path=saved_auth)
    with pytest.raises(BackendUnavailable) as exc_info:
        backend.complete(CompletionRequest(prompt="private", role="proposer"))
    assert str(exc_info.value) == "Saved Codex login was not found; run `codex login`"
    assert sdk.client_configs == []
    assert sdk.thread_args == []
    assert sdk.turn_args == []


def test_no_login_call_on_symlink_success_or_auth_refusal_path(tmp_path, monkeypatch):
    """R3: neither the symlink-success path nor the missing-auth refusal path may invoke
    anything named or containing "login" — the adapter must only reuse a saved session,
    never initiate one. Both the fake SDK surface and the subprocess/os.system seams are
    recorded, so a future regression that shells out to `codex login` is caught even though
    codex_backend.py currently has no subprocess import at all."""
    process_calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process_calls.append((args, kwargs)))
    monkeypatch.setattr(os, "system", lambda cmd: process_calls.append(cmd))

    sdk = _RecordingSdk()
    adapter(sdk, tmp_path).complete(CompletionRequest(prompt="private", role="proposer"))
    assert "thread_start" in sdk.calls and "turn" in sdk.calls  # sanity: SDK was engaged

    missing_backend = CodexSdkBackend(sdk_module=sdk, auth_path=tmp_path / "missing-auth.json")
    with pytest.raises(BackendUnavailable):
        missing_backend.complete(CompletionRequest(prompt="private", role="proposer"))

    assert not any("login" in call.lower() for call in sdk.calls)
    assert process_calls == []


def test_over_cap_prompt_is_rejected_before_any_sdk_call(tmp_path, monkeypatch):
    """R8: an over-cap prompt must fail closed before any SDK dispatch — letting an
    oversized prompt reach the SDK would defeat the bounded-request guarantee the cap
    exists to enforce."""
    monkeypatch.setattr(codex_backend, "_MAX_PROMPT_BYTES", 10)
    sdk = FakeSdk()
    with pytest.raises(ConfigurationError) as exc_info:
        adapter(sdk, tmp_path).complete(
            CompletionRequest(prompt="this prompt is over ten bytes", role="proposer")
        )
    assert str(exc_info.value) == "Codex input exceeds the supported size"
    assert sdk.client_configs == []
    assert sdk.thread_args == []
    assert sdk.turn_args == []
    assert sdk.closed == 0


def test_over_cap_output_is_rejected_after_dispatch(tmp_path, monkeypatch):
    """R8: the output cap is enforced only after the SDK call returns, unlike the
    pre-dispatch prompt cap — this pins that exact post-dispatch behavior so a refactor
    can't silently move the check earlier or drop it."""
    monkeypatch.setattr(codex_backend, "_MAX_OUTPUT_BYTES", 5)
    sdk = FakeSdk()
    sdk.response = "x" * 20
    with pytest.raises(InvalidResponse) as exc_info:
        adapter(sdk, tmp_path).complete(CompletionRequest(prompt="private", role="proposer"))
    assert str(exc_info.value) == "Codex output exceeded the configured limit"
    assert len(sdk.turn_args) == 1  # the call was dispatched; only the output was rejected
    assert sdk.closed == 1


def test_every_isolation_override_reaches_the_sdk_config(tmp_path):
    """R8: every entry in _ISOLATION_OVERRIDES must reach the SDK config — before this test,
    only features.shell_tool=false was asserted, so a future entry that isn't forwarded
    would silently reopen whatever capability it was meant to close."""
    assert codex_backend._ISOLATION_OVERRIDES, "guard: an emptied constant would make the loop below pass vacuously"
    sdk = FakeSdk()
    adapter(sdk, tmp_path).complete(CompletionRequest(prompt="private", role="proposer"))
    forwarded = sdk.client_configs[0]["config_overrides"]
    for override in codex_backend._ISOLATION_OVERRIDES:
        assert override in forwarded, f"{override!r} was not forwarded to CodexConfig"


def test_prompt_sentinel_never_appears_in_logs_or_streams_on_success(tmp_path, caplog, capsys):
    """R8: prompts must never reach logs or stdout/stderr on the success path — logging
    prompt content would leak user artifacts even though the adapter never puts them in
    argv."""
    caplog.set_level("DEBUG")
    sdk = FakeSdk()
    sentinel = "CODEX-PROMPT-SENTINEL-DO-NOT-LOG"
    result = adapter(sdk, tmp_path).complete(CompletionRequest(prompt=sentinel, role="proposer"))
    assert result.text == "done"
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_prompt_sentinel_never_appears_in_logs_or_streams_on_error(
    tmp_path, caplog, capsys, monkeypatch
):
    """R8: the no-logging guarantee must hold on an error path too — a "helpful" debug log
    of the rejected prompt would leak it just as much as logging it on success."""
    caplog.set_level("DEBUG")
    monkeypatch.setattr(codex_backend, "_MAX_PROMPT_BYTES", 10)
    sdk = FakeSdk()
    sentinel = "CODEX-PROMPT-SENTINEL-DO-NOT-LOG"
    with pytest.raises(ConfigurationError):
        adapter(sdk, tmp_path).complete(CompletionRequest(prompt=sentinel, role="proposer"))
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


class _RaisingHandle(FakeHandle):
    """FakeHandle variant whose run() raises instead of completing, simulating an SDK-level
    failure whose message happens to contain the prompt."""

    def __init__(self, sdk, message):
        super().__init__(sdk)
        self._message = message

    def run(self):
        raise RuntimeError(self._message)


class _RaisingThread(FakeThread):
    def __init__(self, sdk, message):
        super().__init__(sdk)
        self._message = message

    def turn(self, prompt, **kwargs):
        self.sdk.turn_args.append((prompt, kwargs))
        self.sdk.handle = _RaisingHandle(self.sdk, self._message)
        return self.sdk.handle


class _RaisingClient(FakeClient):
    def __init__(self, sdk, config, message):
        super().__init__(sdk, config)
        self._message = message

    def thread_start(self, **kwargs):
        self.sdk.thread_args.append(kwargs)
        self.sdk.workspaces.append(kwargs["cwd"])
        assert list(Path(kwargs["cwd"]).iterdir()) == []
        return _RaisingThread(self.sdk, self._message)


class _RaisingSdk(FakeSdk):
    """FakeSdk variant whose turn dispatch raises, used to prove the generic
    `except Exception as exc: ... raise BackendUnavailable("Codex completion failed")`
    branch in complete() never lets the underlying exception message — which could carry
    the prompt — reach the caller, logs, or stdout/stderr."""

    def __init__(self, message):
        super().__init__()
        self._message = message

    def Codex(self, *, config):
        return _RaisingClient(self, config, self._message)


def test_prompt_sentinel_never_appears_in_logs_or_streams_on_sdk_exception(tmp_path, caplog, capsys):
    """R8: the generic exception-wrapping branch is the one place an SDK-level error message
    could carry the prompt through to the caller — the success and pre-dispatch
    ConfigurationError paths tested above never execute that branch, so this closes the gap
    between "no logging call exists" and "no message from that branch ever leaks"."""
    caplog.set_level("DEBUG")
    sentinel = "CODEX-PROMPT-SENTINEL-DO-NOT-LOG"
    sdk = _RaisingSdk(f"turn failed for prompt: {sentinel}")
    with pytest.raises(BackendUnavailable) as exc_info:
        adapter(sdk, tmp_path).complete(CompletionRequest(prompt=sentinel, role="proposer"))
    assert str(exc_info.value) == "Codex completion failed"
    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err


@pytest.mark.parametrize(
    "missing,expected_message",
    [
        ("Codex", "Codex SDK lacks required isolation controls"),
        ("CodexConfig", "Codex SDK lacks required isolation controls"),
        ("Sandbox", "Codex SDK lacks required isolation controls"),
        ("ApprovalMode", "Codex SDK lacks required isolation controls"),
        ("Sandbox.read_only", "Codex SDK lacks read-only or deny-all controls"),
        ("ApprovalMode.deny_all", "Codex SDK lacks read-only or deny-all controls"),
    ],
)
def test_module_fails_closed_when_an_isolation_control_is_missing(tmp_path, missing, expected_message):
    """R11: every fail-closed branch of CodexSdkBackend._module must raise BackendUnavailable
    with its remediation message, not just the version mismatch — a silently-missing Sandbox
    or ApprovalMode control would let a request run without the read-only/deny-all
    guarantees the isolation profile relies on."""
    sdk = _sdk_missing(missing)
    backend = adapter(sdk, tmp_path)
    with pytest.raises(BackendUnavailable) as exc_info:
        backend.preflight()
    assert str(exc_info.value) == expected_message


def test_sdk_import_failure_names_the_install_extra(monkeypatch):
    """R11: when the Codex SDK import fails, the error must name the exact pip extra so a
    user without openai-codex installed gets an actionable fix instead of a bare
    ImportError."""
    real_import_module = codex_backend.importlib.import_module

    def _raise_for_codex(name, *args, **kwargs):
        if name == "openai_codex":
            raise ImportError("No module named 'openai_codex'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(codex_backend.importlib, "import_module", _raise_for_codex)
    with pytest.raises(BackendUnavailable) as exc_info:
        codex_backend._sdk()
    assert str(exc_info.value) == "Install the Codex backend with `pip install 'optimize-anything[codex]'`"


def test_structured_output_success_carries_parsed_value(tmp_path):
    """R11: a schema-matching Codex response must surface the parsed structured value on
    the result — only the failure path was tested before, so a regression that stopped
    populating `structured` on success would have gone unnoticed."""
    sdk = FakeSdk()
    sdk.response = json.dumps({"score": 3})
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer", "maximum": 5}},
        "required": ["score"],
    }
    request = CompletionRequest(prompt="judge", role="judge", output_schema=schema)
    result = adapter(sdk, tmp_path).complete(request)
    assert result.structured == {"score": 3}
    assert result.text == json.dumps({"score": 3})
