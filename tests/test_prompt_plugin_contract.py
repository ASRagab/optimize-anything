"""Contracts for the shared prompt workflow and dual-client plugin."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RESOURCES = (
    Path("skills/optimize-prompt/SKILL.md"),
    Path("skills/optimize-prompt/agents/openai.yaml"),
    Path("skills/optimize-prompt/references/prompt-execution-dataset.md"),
    Path("skills/optimize-prompt/scripts/prompt_execution_evaluator.py"),
    Path("scripts/run-optimize-anything"),
)


def _read(path: str | Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _json(path: str | Path) -> dict:
    return json.loads(_read(path))


def _project_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"$', _read("pyproject.toml"), re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_prompt_skill_and_bundled_resources_exist():
    missing = [str(path) for path in EXPECTED_RESOURCES if not (REPO_ROOT / path).is_file()]
    assert not missing, f"prompt workflow resources missing: {missing}"

    skill = _read("skills/optimize-prompt/SKILL.md")
    assert re.match(
        r"^---\nname: optimize-prompt\ndescription: .+\n---\n",
        skill,
    )
    for source in ("inline", "standalone", "embedded", "independent"):
        assert source in skill.lower()


def test_claude_and_codex_manifests_share_one_skill_tree():
    claude = _json(".claude-plugin/plugin.json")
    codex = _json(".codex-plugin/plugin.json")
    marketplace = _json(".agents/plugins/marketplace.json")

    assert claude["name"] == codex["name"] == "optimize-anything"
    assert codex["skills"] == "./skills/"
    assert marketplace["name"] == "optimize-anything"
    entry = marketplace["plugins"][0]
    assert entry["name"] == "optimize-anything"
    assert entry["source"] == {"source": "local", "path": "./"}
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert entry["category"]


def test_release_versions_match_all_active_metadata():
    claude_marketplace = _json(".claude-plugin/marketplace.json")
    codex_marketplace = _json(".agents/plugins/marketplace.json")
    versions = {
        "pyproject.toml": _project_version(),
        ".claude-plugin/plugin.json": _json(".claude-plugin/plugin.json")["version"],
        ".claude-plugin/marketplace.json metadata": claude_marketplace["metadata"]["version"],
        ".claude-plugin/marketplace.json plugin": claude_marketplace["plugins"][0]["version"],
        ".codex-plugin/plugin.json": _json(".codex-plugin/plugin.json")["version"],
        ".agents/plugins/marketplace.json resolved plugin": _json(
            ".codex-plugin/plugin.json"
        )["version"],
    }
    assert len(set(versions.values())) == 1, f"release versions differ: {versions}"


def test_claude_commands_use_the_bundled_launcher():
    launcher = '"${CLAUDE_PLUGIN_ROOT}/scripts/run-optimize-anything"'
    offenders = []
    for path in sorted((REPO_ROOT / "commands").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        global_invocation = re.search(
            r"(?<!run-)optimize-anything\s+"
            r"(?:optimize|generate-evaluator|intake|explain|budget|score|validate|analyze)\b",
            text,
        )
        if global_invocation or ("optimize-anything" in text and launcher not in text):
            offenders.append(path.name)
    assert not offenders, f"commands bypass bundled launcher: {offenders}"


def test_prompt_workflow_documentation_covers_both_hosts_and_evidence_modes():
    docs = "\n".join(_read(path) for path in ("README.md", "install.md", "SKILL.md"))
    normalized_docs = docs.lower()
    for term in (
        "Claude Code plugin",
        "Codex plugin",
        "CLI installer",
        "optimize-prompt",
        "Fast mode",
        "Rigorous mode",
        "representative",
        "hard constraints",
        "independent",
        "coupled",
    ):
        assert term.lower() in normalized_docs, f"prompt workflow docs missing: {term}"

    assert "$optimize-anything:optimize-prompt" in _read("install.md")
    assert "$optimize-anything:optimize-prompt" in _read(
        "skills/optimize-prompt/agents/openai.yaml"
    )
