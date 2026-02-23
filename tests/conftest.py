"""Shared test fixtures for optimize-anything."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_evaluator_script(tmp_path: Path) -> Path:
    """Create a temporary evaluator script that returns a fixed score."""
    script = tmp_path / "eval.sh"
    script.write_text(
        textwrap.dedent("""\
            #!/usr/bin/env bash
            # Read JSON from stdin, echo a score based on candidate length
            input=$(cat)
            candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
            length=${#candidate}
            echo "{\\"score\\": 0.${length}, \\"length\\": $length}"
        """)
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def tmp_bad_evaluator_script(tmp_path: Path) -> Path:
    """Create an evaluator script that outputs invalid JSON."""
    script = tmp_path / "bad_eval.sh"
    script.write_text(
        textwrap.dedent("""\
            #!/usr/bin/env bash
            echo "not json"
        """)
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def tmp_failing_evaluator_script(tmp_path: Path) -> Path:
    """Create an evaluator script that exits with error."""
    script = tmp_path / "fail_eval.sh"
    script.write_text(
        textwrap.dedent("""\
            #!/usr/bin/env bash
            echo "something went wrong" >&2
            exit 1
        """)
    )
    script.chmod(0o755)
    return script
