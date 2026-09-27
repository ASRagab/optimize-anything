"""Run-scoped cross-process slots, circuits, and provenance."""

import multiprocessing
import os
import select
import subprocess
import sys
import textwrap
import time
import warnings

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


def test_child_process_shares_parent_slot_and_circuit_via_exported_environment() -> None:
    """R9: a generated-evaluator child process must resolve the SAME run coordinator as
    its parent through the exported OPTIMIZE_ANYTHING_COORDINATION_DIR/_ID environment
    (coordination.py:123, factory.py:66) — otherwise a child could dispatch a second
    concurrent subscription call, or ignore a circuit the parent already tripped, and
    defeat per-run serialization across the whole optimization run."""
    with RunCoordinator.create() as coordinator:
        with coordinator.exported_environment():
            child_env = dict(os.environ)
        assert coordinator.open_circuit("claude", "judge", "quota_exceeded") is True

        script = textwrap.dedent("""
            from optimize_anything.llm_backends import BackendSpec, Timeout, create_backend

            backend = create_backend(BackendSpec(backend="claude"), role="judge")
            coordinator = backend.coordinator
            assert coordinator is not None, "child must resolve the parent's coordinator"
            try:
                with coordinator.slot("claude", timeout_seconds=1.0):
                    print("SLOT_ACQUIRED")
            except Timeout:
                print("SLOT_BUSY")
            print(f"CIRCUIT={coordinator.circuit_reason('claude', 'judge')}")
        """)

        with coordinator.slot("claude"):
            busy = subprocess.run(
                [sys.executable, "-c", script], env=child_env,
                capture_output=True, text=True, timeout=5,
            )
        assert busy.returncode == 0, busy.stderr
        assert "SLOT_BUSY" in busy.stdout
        assert "CIRCUIT=quota_exceeded" in busy.stdout

        free = subprocess.run(
            [sys.executable, "-c", script], env=child_env,
            capture_output=True, text=True, timeout=5,
        )
        assert free.returncode == 0, free.stderr
        assert "SLOT_ACQUIRED" in free.stdout


def test_capacity_override_warns_on_stderr_not_via_warnings_module(capsys) -> None:
    """R9: overriding a provider's subscription concurrency relaxes the default
    one-call-in-flight guarantee, so RunCoordinator.create must warn with a plain
    stderr print — not through Python's warnings module, whose default once-per-location
    filter would silently swallow a repeated override in the same process, and whose
    output a caller running with -W ignore or PYTHONWARNINGS=ignore would suppress
    entirely."""
    with RunCoordinator.create():
        pass
    assert capsys.readouterr().err == ""

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with RunCoordinator.create({"codex": 2}):
            pass
    assert caught == []
    captured = capsys.readouterr()
    assert "Warning: codex subscription concurrency set to 2." in captured.err
    assert "claude" not in captured.err


def _read_line_with_timeout(stream, timeout: float) -> str:
    """Block for at most `timeout` seconds for one line from a child process pipe."""
    ready, _, _ = select.select([stream], [], [], timeout)
    if not ready:
        raise TimeoutError(f"no output from child within {timeout}s")
    return stream.readline()


def test_crashed_child_releases_slot_and_new_run_does_not_see_old_circuits() -> None:
    """R9: a provider slot must not stay locked forever just because the process holding
    it was killed, and a brand-new run must not inherit a previous run's open circuits —
    otherwise one crashed evaluator child could permanently wedge every later run's use of
    a provider, or a stale circuit could force a fresh run straight to the paid fallback."""
    with RunCoordinator.create() as coordinator:
        with coordinator.exported_environment():
            child_env = dict(os.environ)

        script = textwrap.dedent("""
            import time
            from optimize_anything.llm_backends import BackendSpec, create_backend

            backend = create_backend(BackendSpec(backend="claude"), role="judge")
            coordinator = backend.coordinator
            lease = coordinator.try_acquire_slot("claude")
            assert lease is not None
            coordinator.open_circuit("claude", "judge", "quota_exceeded")
            print("SLOT_HELD", flush=True)
            time.sleep(30)
        """)

        with subprocess.Popen(
            [sys.executable, "-c", script], env=child_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ) as proc:
            try:
                line = _read_line_with_timeout(proc.stdout, 5.0)
                assert line.strip() == "SLOT_HELD"
                assert coordinator.try_acquire_slot("claude") is None

                proc.kill()
                proc.wait(timeout=5)

                deadline = time.monotonic() + 5
                lease = None
                while lease is None and time.monotonic() < deadline:
                    lease = coordinator.try_acquire_slot("claude")
                    if lease is None:
                        time.sleep(0.05)
                assert lease is not None, "parent could not reacquire the slot after the child was killed"
                lease.release()
            finally:
                proc.kill()
                proc.wait(timeout=5)

        assert coordinator.circuit_reason("claude", "judge") == "quota_exceeded"

        with RunCoordinator.create() as fresh:
            assert fresh.path != coordinator.path
            assert fresh.circuit_reason("claude", "judge") is None
