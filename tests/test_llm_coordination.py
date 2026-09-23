"""Run-scoped cross-process slots, circuits, and provenance."""

import multiprocessing
import os

from optimize_anything.llm_backends import RunCoordinator


def _hold_slot(path: str, provider: str, ready, release) -> None:
    coordinator = RunCoordinator.attach(path)
    with coordinator.slot(provider):
        ready.set()
        release.wait(5)


def test_provider_capacity_one_across_processes() -> None:
    with RunCoordinator.create() as coordinator:
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        release = context.Event()
        child = context.Process(target=_hold_slot, args=(str(coordinator.path), "codex", ready, release))
        child.start()
        try:
            assert ready.wait(5)
            assert coordinator.try_acquire_slot("codex") is None
            with coordinator.slot("claude"):
                pass
        finally:
            release.set()
            child.join(5)
        assert child.exitcode == 0
        with coordinator.slot("codex"):
            pass


def test_role_circuits_and_child_provenance_are_shared() -> None:
    with RunCoordinator.create() as coordinator:
        child = RunCoordinator.attach(str(coordinator.path))
        assert child.open_circuit("codex", "judge", "quota_exceeded") is True
        assert coordinator.circuit_reason("codex", "judge") == "quota_exceeded"
        assert coordinator.circuit_reason("codex", "proposer") is None
        assert coordinator.open_circuit("codex", "judge", "rate_limit") is False
        child.record_event({"role": "judge", "requested_backend": "codex", "actual_backend": "api",
                            "actual_model": "openai/fallback", "auth_class": "api",
                            "prompt": "must not persist", "api_key": "must not persist"})
        events = coordinator.events()
        assert len(events) == 1
        assert events[0]["role"] == "judge"
        state = (coordinator.path / "events.jsonl").read_text()
        assert "must not persist" not in state
        assert oct(os.stat(coordinator.path).st_mode & 0o777) == "0o700"


def test_provider_override_allows_exactly_two_slots() -> None:
    with RunCoordinator.create({"codex": 2}) as coordinator:
        first = coordinator.try_acquire_slot("codex")
        second = coordinator.try_acquire_slot("codex")
        try:
            assert first is not None
            assert second is not None
            assert coordinator.try_acquire_slot("codex") is None
        finally:
            first.release()
            second.release()
