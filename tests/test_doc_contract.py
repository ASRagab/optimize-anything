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
        "budget_utilization",
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


def test_optimization_guide_matches_gepa_014_contract():
    skill_text = _read_text(Path("skills/optimization-guide/SKILL.md"))
    _assert_contains_terms(
        text=skill_text,
        terms=[
            "--proposals-per-iteration",
            "proposals_per_iteration",
            "SameParentSampling",
            "track_best_outputs=False",
            "--workers",
            "final iteration",
            "GEPA 0.1.1",
        ],
        label="skills/optimization-guide/SKILL.md",
    )
    assert "Verify `total_metric_calls` < `budget`" not in skill_text


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


def test_all_command_markdown_files_have_name_and_description_frontmatter():
    commands_dir = REPO_ROOT / "commands"
    command_files = sorted(commands_dir.glob("*.md"))
    assert command_files, "No command markdown files found in commands/"

    for path in command_files:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        assert match is not None, f"{path.relative_to(REPO_ROOT)} missing YAML frontmatter"
        frontmatter = match.group(1)
        assert re.search(r"^name:\s*.+$", frontmatter, flags=re.MULTILINE), (
            f"{path.relative_to(REPO_ROOT)} frontmatter missing 'name'"
        )
        assert re.search(r"^description:\s*.+$", frontmatter, flags=re.MULTILINE), (
            f"{path.relative_to(REPO_ROOT)} frontmatter missing 'description'"
        )


def test_bash_evaluator_template_fast_returns_for_preflight():
    skill_text = _read_text(Path("skills/evaluator-patterns/SKILL.md"))
    pattern_2 = skill_text.split("## Pattern 2:", maxsplit=1)[1].split(
        "## Pattern 3:", maxsplit=1
    )[0]
    guard = (
        'if [ "$candidate" = "__optimize_anything_preflight__" ]; then\n'
        "  printf '{\"score\":0.5}\\n'\n"
        "  exit 0\n"
        "fi"
    )

    assert guard in pattern_2
    assert pattern_2.index(guard) < pattern_2.index('workdir="$(mktemp -d)"')


def test_concepts_mentions_multi_task_and_generalization():
    concepts_text = _read_text(Path("CONCEPTS.md"))
    _assert_contains_terms(
        text=concepts_text,
        terms=["Multi-task", "Generalization"],
        label="CONCEPTS.md",
    )


# --- Plugin manifest tests ---


def _plugin_json() -> dict:
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPluginManifest:
    def test_manifest_has_required_fields(self):
        data = _plugin_json()
        for field in ("name", "version", "description"):
            assert field in data, f"plugin.json missing '{field}'"

    def test_release_versions_match(self):
        pyproject_text = _read_text(Path("pyproject.toml"))
        pyproject_match = re.search(
            r'^version\s*=\s*"([^"]+)"$', pyproject_text, flags=re.MULTILINE
        )
        assert pyproject_match is not None, "pyproject.toml missing project version"

        marketplace = json.loads(
            _read_text(Path(".claude-plugin/marketplace.json"))
        )
        versions = {
            "pyproject.toml": pyproject_match.group(1),
            ".claude-plugin/plugin.json": _plugin_json()["version"],
            ".claude-plugin/marketplace.json metadata": marketplace["metadata"]["version"],
            ".claude-plugin/marketplace.json plugin": marketplace["plugins"][0]["version"],
        }

        assert len(set(versions.values())) == 1, f"release versions differ: {versions}"

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
        expected = {"generate-evaluator", "optimization-guide", "evaluator-patterns"}
        assert expected.issubset(skill_dirs), (
            f"Missing skill directories: {expected - skill_dirs}"
        )


# --- Jev evaluator surface -------------------------------------------------

JEV_DOCS = (
    Path("README.md"),
    Path("CLAUDE.md"),
    Path("PROTOCOL.md"),
    Path("commands/score.md"),
    Path("commands/optimize.md"),
    Path("skills/optimization-guide/SKILL.md"),
)
LEVELS_DOCS = (
    Path("README.md"),
    Path("CLAUDE.md"),
    Path("CONCEPTS.md"),
    Path("commands/intake.md"),
    Path("skills/optimization-guide/SKILL.md"),
)


def _help_text(command: str, capsys) -> str:
    import pytest

    from optimize_anything.cli import main

    with pytest.raises(SystemExit):
        main([command, "--help"])
    return capsys.readouterr().out


def test_jev_flag_is_documented_where_users_learn_evaluators():
    for path in JEV_DOCS:
        _assert_contains_terms(
            text=_read_text(path), terms=["--jev-model", "TYPESAFE_API_KEY"], label=str(path)
        )


def test_jev_key_variable_name_matches_runtime_and_help(capsys):
    from optimize_anything.jev_judge import API_KEY_ENV

    # Docs name the variable the code actually reads, not a stale spelling.
    assert API_KEY_ENV == "TYPESAFE_API_KEY"
    for command in ("optimize", "score"):
        help_text = _help_text(command, capsys)
        _assert_contains_terms(
            text=help_text, terms=["--jev-model", API_KEY_ENV], label=f"{command} --help"
        )


def test_jev_flag_documented_on_every_parser_that_accepts_it():
    cli_source = _read_text(Path("src/optimize_anything/cli.py"))
    assert cli_source.count('"--jev-model"') == 2  # optimize and score only
    for command in ("analyze", "validate", "compare"):
        doc = _read_text(Path(f"commands/{command}.md"))
        assert "--jev-model" not in doc, f"commands/{command}.md documents a flag its CLI lacks"


def test_rubric_levels_documented_with_the_limits_intake_enforces():
    from optimize_anything.intake import MAX_LEVELS, MIN_LEVELS

    limit_phrase = f"{MIN_LEVELS} to {MAX_LEVELS}"
    for path in LEVELS_DOCS:
        text = _read_text(path)
        assert "levels" in text, f"{path} does not mention rubric levels"
        assert limit_phrase in text, f"{path} does not state the '{limit_phrase}' level limit"


def test_readme_intake_example_normalizes():
    from optimize_anything.intake import normalize_intake_spec

    readme = _read_text(Path("README.md"))
    match = re.search(r"--intake-json '(\{.*?\})'", readme)
    assert match is not None, "README intake example not found"
    normalize_intake_spec(json.loads(match.group(1)))


def test_levels_evidence_note_exists_and_is_cited_by_the_docs():
    note = "docs/verification/jev-judge-ab-2026-10-17.md"
    assert (REPO_ROOT / note).is_file(), f"{note} is cited by the docs but missing"
    for path in (Path("README.md"), Path("commands/intake.md"), Path("skills/optimization-guide/SKILL.md")):
        assert note in _read_text(path), f"{path} makes the levels claim without citing {note}"
