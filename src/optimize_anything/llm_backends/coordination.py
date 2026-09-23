"""Private run-scoped coordination shared by optimization child processes."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from .base import ConfigurationError, Timeout

COORDINATION_DIR_ENV = "OPTIMIZE_ANYTHING_COORDINATION_DIR"
COORDINATION_ID_ENV = "OPTIMIZE_ANYTHING_COORDINATION_ID"
_PROVIDERS = ("codex", "claude")
_ROLES = ("proposer", "judge", "analysis", "score", "validation")
_EVENT_KEYS = frozenset({
    "run_id", "call_id", "role", "requested_backend", "actual_backend",
    "requested_model", "actual_model", "auth_class", "auth_source", "started_at",
    "duration_seconds", "input_tokens", "output_tokens", "total_tokens", "retry_count",
    "fallback_source", "fallback_reason", "prompt_contract_version", "schema_contract_version",
})
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:+@-]{1,128}$")
_MAX_EVENT_BYTES = 4096
_MAX_LOG_BYTES = 1_048_576


class _SlotLease:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def release(self) -> None:
        if self._fd >= 0:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> _SlotLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class RunCoordinator:
    """OS-lock-backed provider slots, sticky role circuits, and safe events."""

    def __init__(self, path: Path, *, owner: bool = False) -> None:
        self.path = path
        self._owner = owner
        self._verify_private_path(path)
        try:
            metadata = json.loads((path / "run.json").read_text())
        except (OSError, ValueError) as exc:
            raise ConfigurationError("invalid coordination directory") from exc
        self.run_id: str = metadata["run_id"]
        self.capacities: dict[str, int] = metadata["capacities"]

    @staticmethod
    def _verify_private_path(path: Path) -> None:
        try:
            info = path.lstat()
        except OSError as exc:
            raise ConfigurationError("coordination directory is unavailable") from exc
        if not path.is_dir() or path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ConfigurationError("coordination directory is not private")

    @classmethod
    def create(
        cls, capacities: Mapping[str, int] | None = None, *,
        max_concurrency: Mapping[str, int] | None = None,
    ) -> RunCoordinator:
        selected = capacities or max_concurrency or {}
        if any(key not in _PROVIDERS or not isinstance(value, int) or value < 1
               for key, value in selected.items()):
            raise ConfigurationError("invalid provider capacity")
        capacity = {provider: selected.get(provider, 1) for provider in _PROVIDERS}
        for provider, count in capacity.items():
            if count != 1:
                print(f"Warning: {provider} subscription concurrency set to {count}.", file=sys.stderr)
        path = Path(tempfile.mkdtemp(prefix="optimize-anything-run-"))
        os.chmod(path, 0o700)
        run_id = uuid.uuid4().hex
        (path / "run.json").write_text(json.dumps({"run_id": run_id, "capacities": capacity}))
        (path / "circuits.json").write_text("{}")
        (path / "events.jsonl").touch(mode=0o600)
        (path / "state.lock").touch(mode=0o600)
        (path / "events.lock").touch(mode=0o600)
        for provider, count in capacity.items():
            for index in range(count):
                (path / f"slot-{provider}-{index}.lock").touch(mode=0o600)
        return cls(path, owner=True)

    @classmethod
    def attach(cls, path: str | os.PathLike[str], *, expected_run_id: str | None = None) -> RunCoordinator:
        coordinator = cls(Path(path))
        if expected_run_id is not None and coordinator.run_id != expected_run_id:
            raise ConfigurationError("coordination run identifier mismatch")
        return coordinator

    @classmethod
    def from_environment(cls) -> RunCoordinator | None:
        path = os.environ.get(COORDINATION_DIR_ENV)
        run_id = os.environ.get(COORDINATION_ID_ENV)
        if not path and not run_id:
            return None
        if not path or not run_id:
            raise ConfigurationError("incomplete coordination environment")
        return cls.attach(path, expected_run_id=run_id)

    def child_environment(self) -> dict[str, str]:
        return {COORDINATION_DIR_ENV: str(self.path), COORDINATION_ID_ENV: self.run_id}

    @contextmanager
    def exported_environment(self) -> Iterator[None]:
        """Temporarily expose this run to evaluator child processes."""
        previous: dict[str, str | None] = {}
        for key, value in self.child_environment().items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        try:
            yield
        finally:
            for key, previous_value in previous.items():
                if previous_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous_value

    def __enter__(self) -> RunCoordinator:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owner:
            shutil.rmtree(self.path)
            self._owner = False

    def _provider(self, provider: str) -> None:
        if provider not in _PROVIDERS:
            raise ConfigurationError("unsupported subscription provider")

    def try_acquire_slot(self, provider: str) -> _SlotLease | None:
        self._provider(provider)
        for index in range(self.capacities[provider]):
            fd = os.open(self.path / f"slot-{provider}-{index}.lock", os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            return _SlotLease(fd)
        return None

    @contextmanager
    def slot(self, provider: str, *, timeout_seconds: float | None = None) -> Iterator[None]:
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        lease = self.try_acquire_slot(provider)
        while lease is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise Timeout("provider slot wait timed out")
            time.sleep(0.02)
            lease = self.try_acquire_slot(provider)
        try:
            yield
        finally:
            lease.release()

    @contextmanager
    def _lock(self, name: str) -> Iterator[None]:
        fd = os.open(self.path / name, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def circuit_reason(self, provider: str, role: str) -> str | None:
        self._provider(provider)
        if role not in _ROLES:
            raise ConfigurationError("unsupported completion role")
        with self._lock("state.lock"):
            state = json.loads((self.path / "circuits.json").read_text())
            return state.get(f"{provider}:{role}")

    def open_circuit(self, provider: str, role: str, reason: str) -> bool:
        self._provider(provider)
        if role not in _ROLES or not _SAFE_VALUE.fullmatch(reason):
            raise ConfigurationError("invalid circuit state")
        with self._lock("state.lock"):
            state_path = self.path / "circuits.json"
            state = json.loads(state_path.read_text())
            key = f"{provider}:{role}"
            if key in state:
                return False
            state[key] = reason
            fd, temporary = tempfile.mkstemp(prefix="circuits-", dir=self.path)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(state, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, state_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return True

    def record_event(self, event: Mapping[str, Any]) -> bool:
        """Append whitelisted, bounded non-content metadata; drop unsafe values."""
        safe: dict[str, Any] = {"run_id": self.run_id}
        for key in _EVENT_KEYS - {"run_id"}:
            value = event.get(key)
            if isinstance(value, str) and _SAFE_VALUE.fullmatch(value):
                safe[key] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                safe[key] = value
        line = json.dumps(safe, sort_keys=True, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        if len(data) > _MAX_EVENT_BYTES:
            return False
        with self._lock("events.lock"):
            path = self.path / "events.jsonl"
            if path.stat().st_size + len(data) > _MAX_LOG_BYTES:
                return False
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
        return True

    def events(self) -> list[dict[str, Any]]:
        with self._lock("events.lock"):
            return [json.loads(line) for line in (self.path / "events.jsonl").read_text().splitlines()]
