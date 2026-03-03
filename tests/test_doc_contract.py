"""Documentation drift guard for core contract terms."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = (
    Path("README.md"),
    Path("CLAUDE.md"),
)


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
        "evaluator_failure_signal",
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


def test_removed_server_artifacts_not_referenced_in_active_docs():
    docs_text = _combined_docs_text()
    forbidden_terms = ["optimize_anything.server", "tests/test_server.py"]
    for term in forbidden_terms:
        assert term not in docs_text, f"active docs still reference removed artifact: {term}"


def test_validate_subcommand_is_documented_and_in_runtime():
    docs_text = _combined_docs_text()
    _assert_contains_terms(text=docs_text, terms=["validate"], label="docs")

    cli_source = _read_text(Path("src/optimize_anything/cli.py"))
    _assert_contains_terms(text=cli_source, terms=["validate_parser", "_cmd_validate"], label="src/optimize_anything/cli.py")


# --- Plugin manifest tests ---


def _plugin_json() -> dict:
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPluginManifest:
    def test_manifest_has_required_fields(self):
        data = _plugin_json()
        for field in ("name", "version", "description"):
            assert field in data, f"plugin.json missing '{field}'"

    def test_commands_directory_has_expected_files(self):
        """Auto-discovery finds commands from the commands/ directory."""
        commands_dir = REPO_ROOT / "commands"
        assert commands_dir.is_dir(), "commands/ directory missing"
        command_files = {p.stem for p in commands_dir.glob("*.md")}
        expected = {"optimize", "intake", "explain", "budget", "score", "analyze", "quick", "validate", "compare"}
        assert expected.issubset(command_files), (
            f"Missing command files: {expected - command_files}"
        )

    def test_skills_directory_has_expected_entries(self):
        """Auto-discovery finds skills from skills/*/SKILL.md."""
        skills_dir = REPO_ROOT / "skills"
        assert skills_dir.is_dir(), "skills/ directory missing"
        skill_dirs = {
            p.parent.name for p in skills_dir.glob("*/SKILL.md")
        }
        expected = {"generate-evaluator", "optimization-guide"}
        assert expected.issubset(skill_dirs), (
            f"Missing skill directories: {expected - skill_dirs}"
        )
