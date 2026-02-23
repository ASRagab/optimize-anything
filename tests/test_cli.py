"""Tests for CLI."""

from __future__ import annotations

import json
from pathlib import Path

from optimize_anything.cli import main


class TestCLI:
    def test_optimize_help(self, capsys):
        """Verify optimize subcommand help works."""
        try:
            main(["optimize", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "seed_file" in captured.out

    def test_explain(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        result = main(["explain", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        assert "11 chars" in captured.out

    def test_explain_with_objective(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hello world")
        result = main(["explain", str(seed_file), "--objective", "Make formal"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Make formal" in captured.out

    def test_budget_short(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("Hi")
        result = main(["budget", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recommended_budget"] == 50

    def test_budget_medium(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("x" * 300)
        result = main(["budget", str(seed_file)])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recommended_budget"] == 100

    def test_optimize_missing_evaluator(self, tmp_path: Path, capsys):
        seed_file = tmp_path / "seed.txt"
        seed_file.write_text("test")
        result = main(["optimize", str(seed_file)])
        assert result == 1

    def test_missing_seed_file(self, capsys):
        result = main(["explain", "/nonexistent/file.txt"])
        assert result == 1
        captured = capsys.readouterr()
        assert "file not found" in captured.err
