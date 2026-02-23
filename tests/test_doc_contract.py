"""Documentation drift guard for core contract terms."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = (Path("README.md"), Path("docs/mcp-protocol.md"))


def _read_text(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _combined_docs_text() -> str:
    return "\n".join(_read_text(path) for path in DOC_PATHS)


def _assert_contains_terms(*, text: str, terms: list[str], label: str) -> None:
    missing = [term for term in terms if term not in text]
    assert not missing, f"{label} is missing required terms: {', '.join(missing)}"


def _assert_source_defines_keys(*, source: str, keys: list[str], label: str) -> None:
    missing = [
        key for key in keys if re.search(rf'["\']{re.escape(key)}["\']\s*:', source) is None
    ]
    assert not missing, f"{label} is missing required keys: {', '.join(missing)}"


def test_intake_schema_fields_are_documented():
    docs_text = _combined_docs_text()
    required_fields = [
        "artifact_class",
        "quality_dimensions",
        "hard_constraints",
        "evaluation_pattern",
        "execution_mode",
        "evaluator_cwd",
    ]

    _assert_contains_terms(
        text=docs_text,
        terms=required_fields,
        label="docs",
    )


def test_optimize_output_keys_are_documented_and_in_runtime_contract():
    required_keys = [
        "best_artifact",
        "total_metric_calls",
        "score_summary",
        "top_diagnostics",
        "plateau_guidance",
    ]

    docs_text = _combined_docs_text()
    _assert_contains_terms(
        text=docs_text,
        terms=required_keys,
        label="docs",
    )

    result_contract_source = _read_text(Path("src/optimize_anything/result_contract.py"))
    _assert_source_defines_keys(
        source=result_contract_source,
        keys=required_keys,
        label="src/optimize_anything/result_contract.py",
    )


def test_cli_intake_flags_are_documented_and_in_runtime():
    required_flags = ["--intake-json", "--intake-file", "--evaluator-cwd"]

    docs_text = _combined_docs_text()
    _assert_contains_terms(
        text=docs_text,
        terms=required_flags,
        label="docs",
    )

    cli_source = _read_text(Path("src/optimize_anything/cli.py"))
    _assert_contains_terms(
        text=cli_source,
        terms=required_flags,
        label="src/optimize_anything/cli.py",
    )
