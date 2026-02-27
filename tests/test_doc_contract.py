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


# --- Plugin manifest tests ---


def _plugin_json() -> dict:
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPluginManifest:
    def test_manifest_has_required_fields(self):
        data = _plugin_json()
        for field in ("name", "version", "description"):
            assert field in data, f"plugin.json missing '{field}'"

    def test_manifest_has_commands_array(self):
        data = _plugin_json()
        assert "commands" in data
        assert isinstance(data["commands"], list)
        assert len(data["commands"]) > 0

    def test_manifest_has_skills_array(self):
        data = _plugin_json()
        assert "skills" in data
        assert isinstance(data["skills"], list)
        assert len(data["skills"]) > 0

    def test_each_command_has_name_and_description(self):
        for cmd in _plugin_json()["commands"]:
            assert "name" in cmd, f"Command missing 'name': {cmd}"
            assert "description" in cmd, f"Command missing 'description': {cmd}"

    def test_each_skill_has_name_path_and_description(self):
        data = _plugin_json()
        for skill in data["skills"]:
            assert "name" in skill, f"Skill missing 'name': {skill}"
            assert "path" in skill, f"Skill missing 'path': {skill}"
            assert "description" in skill, f"Skill missing 'description': {skill}"
            skill_path = REPO_ROOT / skill["path"]
            assert skill_path.exists(), f"Skill file not found: {skill_path}"

    def test_known_commands_present(self):
        command_names = {cmd["name"] for cmd in _plugin_json()["commands"]}
        expected = {"optimize", "generate-evaluator", "intake", "explain", "budget", "score", "analyze"}
        assert expected.issubset(command_names), (
            f"Missing commands in manifest: {expected - command_names}"
        )
