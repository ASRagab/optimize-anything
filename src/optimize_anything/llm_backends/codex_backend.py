"""Isolated single-turn completion through the optional Codex Python SDK."""

from __future__ import annotations

import importlib
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError  # type: ignore[import-untyped]

from .base import (
    AuthenticationError,
    BackendCapabilities,
    BackendStatus,
    BackendUnavailable,
    Cancelled,
    CompletionRequest,
    CompletionResult,
    ConfigurationError,
    InvalidResponse,
    RateLimitError,
    Timeout,
    Usage,
    thaw_json,
    validate_capabilities,
)
from .schema import reject_external_refs

_SDK_VERSION = "0.156.0"
_MAX_OUTPUT_BYTES = 1_048_576
_MAX_PROMPT_BYTES = 9_000_000
_ISOLATION_OVERRIDES = (
    "project_doc_max_bytes=0",
    "project_doc_fallback_filenames=[]",
    "web_search=\"disabled\"",
    "model_max_output_tokens=8192",
    "features.shell_tool=false",
    "features.unified_exec=false",
    "features.code_mode_host=false",
    "features.view_image=false",
    "features.multi_agent_v2=false",
    "features.multi_agent=false",
    "features.apps=false",
    "features.plugins=false",
    "features.plugin_sharing=false",
    "features.remote_plugin=false",
    "features.computer_use=false",
    "features.image_generation=false",
    "features.browser_use=false",
    "features.browser_use_external=false",
    "features.in_app_browser=false",
    "features.workspace_dependencies=false",
    "features.skill_mcp_dependency_install=false",
    "include_apply_patch_tool=false",
    "mcp_servers={}",
)


def _sdk() -> Any:
    try:
        return importlib.import_module("openai_codex")
    except ImportError:
        raise BackendUnavailable(
            "Install the Codex backend with `pip install 'optimize-anything[codex]'`"
        ) from None


def _account_type(status: Any) -> str | None:
    account = getattr(status, "account", None)
    if account is None:
        return None
    root = getattr(account, "root", account)
    return getattr(root, "type", None)


class CodexSdkBackend:
    """Creates a private, read-only ephemeral Codex thread for each request."""

    capabilities = BackendCapabilities(
        structured_output=True, model_override=True, sampling=False,
        cancellation=True, usage_reporting=True,
    )

    def __init__(
        self, *, model: str | None = None, sdk_module: Any = None,
        auth_path: Path | None = None,
    ) -> None:
        self.model = model
        self._sdk_module = sdk_module
        saved_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        self._auth_path = auth_path or saved_home / "auth.json"

    def _module(self) -> Any:
        sdk = self._sdk_module if self._sdk_module is not None else _sdk()
        if getattr(sdk, "__version__", None) != _SDK_VERSION:
            raise BackendUnavailable("Codex SDK 0.156.0 is required for the isolation profile")
        for name in ("Codex", "CodexConfig", "Sandbox", "ApprovalMode"):
            if not hasattr(sdk, name):
                raise BackendUnavailable("Codex SDK lacks required isolation controls")
        if not hasattr(sdk.Sandbox, "read_only") or not hasattr(sdk.ApprovalMode, "deny_all"):
            raise BackendUnavailable("Codex SDK lacks read-only or deny-all controls")
        return sdk

    def _client(self, sdk: Any, workspace: str, private_home: str) -> Any:
        config = sdk.CodexConfig(
            cwd=workspace, config_overrides=_ISOLATION_OVERRIDES,
            env={
                "CODEX_HOME": private_home,
                "OPENAI_API_KEY": "",
                "CODEX_API_KEY": "",
            },
        )
        return sdk.Codex(config=config)

    def _prepare_private_home(self, private_home: str) -> None:
        if not self._auth_path.is_file() or self._auth_path.is_symlink():
            raise BackendUnavailable("Saved Codex login was not found; run `codex login`")
        (Path(private_home) / "auth.json").symlink_to(self._auth_path)

    @staticmethod
    def _check_account(client: Any) -> None:
        try:
            status = client.account()
        except Exception:
            raise BackendUnavailable("Could not verify saved Codex authentication") from None
        if _account_type(status) != "chatgpt":
            raise AuthenticationError("Sign in to Codex through ChatGPT with `codex login`")

    def preflight(self) -> BackendStatus:
        sdk = self._module()
        try:
            with tempfile.TemporaryDirectory(prefix="optimize-codex-preflight-") as workspace, tempfile.TemporaryDirectory(prefix="optimize-codex-home-") as private_home:
                self._prepare_private_home(private_home)
                with self._client(sdk, workspace, private_home) as client:
                    self._check_account(client)
        except (AuthenticationError, BackendUnavailable):
            raise
        except Exception:
            raise BackendUnavailable("Codex isolation preflight failed") from None
        return BackendStatus(True, "codex", "subscription", "chatgpt")

    def complete(self, request: CompletionRequest) -> CompletionResult:
        validate_capabilities(request, self.capabilities)
        if request.sampling is not None:
            raise ConfigurationError("Codex subscription does not support sampling controls")
        sdk = self._module()
        model = request.model or self.model
        if model is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model):
            raise ConfigurationError("invalid Codex model name")
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
        if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
            raise ConfigurationError("Codex input exceeds the supported size")
        started = datetime.now(timezone.utc)
        begin = time.monotonic()
        actual_model = model
        try:
            with tempfile.TemporaryDirectory(prefix="optimize-codex-") as workspace, tempfile.TemporaryDirectory(prefix="optimize-codex-home-") as private_home:
                if list(Path(workspace).iterdir()):
                    raise BackendUnavailable("Codex workspace was not empty")
                self._prepare_private_home(private_home)
                with self._client(sdk, workspace, private_home) as client:
                    self._check_account(client)
                    thread = client.thread_start(
                        cwd=workspace, ephemeral=True,
                        sandbox=sdk.Sandbox.read_only,
                        approval_mode=sdk.ApprovalMode.deny_all,
                        base_instructions="Return only the requested answer. Do not use tools.",
                        developer_instructions="Do not access files, network tools, or external services.",
                        config={"project_doc_max_bytes": 0, "web_search": "disabled"},
                        model=model,
                    )
                    handle = thread.turn(
                        prompt, output_schema=schema,
                        sandbox=sdk.Sandbox.read_only,
                        approval_mode=sdk.ApprovalMode.deny_all,
                    )
                    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="codex-turn")
                    future = executor.submit(handle.run)
                    try:
                        result = future.result(timeout=request.timeout_seconds or 120)
                    except FutureTimeout:
                        try:
                            handle.interrupt()
                        except Exception:
                            pass
                        try:
                            future.result(timeout=5)
                        except Exception:
                            pass
                        raise Timeout("Codex completion timed out") from None
                    finally:
                        executor.shutdown(wait=False, cancel_futures=True)
                    try:
                        actual_model = getattr(thread.read().thread, "model", None) or model
                    except Exception:
                        pass
        except (AuthenticationError, BackendUnavailable, Timeout):
            raise
        except Exception as exc:
            if hasattr(sdk, "ServerBusyError") and isinstance(exc, sdk.ServerBusyError):
                raise RateLimitError("Codex is temporarily rate limited") from None
            raise BackendUnavailable("Codex completion failed") from None
        status = getattr(result, "status", None)
        status_value = getattr(status, "value", status)
        if status_value == "interrupted":
            raise Cancelled("Codex turn was cancelled")
        if getattr(result, "error", None) is not None or status_value != "completed":
            raise BackendUnavailable("Codex turn did not complete")
        text = getattr(result, "final_response", None)
        if not isinstance(text, str) or not text:
            raise InvalidResponse("Codex omitted completion text")
        if len(text.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            raise InvalidResponse("Codex output exceeded the configured limit")
        structured = None
        if schema is not None:
            import json

            try:
                structured = json.loads(text)
                Draft202012Validator(schema).validate(structured)
            except (ValueError, ValidationError, SchemaError):
                raise InvalidResponse("Codex output did not match the requested schema") from None
        raw_usage = getattr(getattr(result, "usage", None), "total", None)
        usage = Usage(
            input_tokens=getattr(raw_usage, "input_tokens", None),
            output_tokens=getattr(raw_usage, "output_tokens", None),
            total_tokens=getattr(raw_usage, "total_tokens", None),
        ) if raw_usage is not None else None
        return CompletionResult(
            text=text, structured=structured, requested_backend="codex",
            actual_backend="codex", requested_model=model, actual_model=actual_model,
            auth_class="subscription", auth_source="chatgpt", usage=usage,
            role=request.role, started_at=started.isoformat(),
            duration_seconds=time.monotonic() - begin,
            prompt_contract_version=request.prompt_contract_version,
            schema_contract_version=request.schema_contract_version,
        )
