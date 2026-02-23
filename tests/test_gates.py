"""Tests for scripts/check.py gate runner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import check


class TestCheckGates:
    def test_passing_gate_returns_true(self, tmp_path: Path):
        ok = check._run_gate(
            "true command",
            ["python3", "-c", "import sys; sys.exit(0)"],
            cwd=tmp_path,
        )
        assert ok is True

    def test_failing_gate_returns_false(self, tmp_path: Path):
        ok = check._run_gate(
            "false command",
            ["python3", "-c", "import sys; sys.exit(1)"],
            cwd=tmp_path,
        )
        assert ok is False

    def test_skip_smoke_flag_parsed(self):
        parsed = check.argparse.ArgumentParser()
        parsed.add_argument("--skip-smoke", action="store_true", default=False)
        args = parsed.parse_args(["--skip-smoke"])
        assert args.skip_smoke is True

        args_default = parsed.parse_args([])
        assert args_default.skip_smoke is False
