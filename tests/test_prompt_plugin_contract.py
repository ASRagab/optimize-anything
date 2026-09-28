"""Contracts for the shared prompt workflow and dual-client plugin."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RESOURCES = (
    Path("skills/optimize-prompt/SKILL.md"),
    Path("skills/optimize-prompt/agents/openai.yaml"),
    Path("skills/optimize-prompt/references/prompt-execution-dataset.md"),
    Path("skills/optimize-prompt/scripts/prompt_execution_evaluator.py"),
    Path("scripts/run-optimize-anything"),
)
CLI_SUBCOMMANDS = (
    "optimize", "generate-evaluator", "intake", "explain", "budget", "score", "validate", "analyze"
)
GLOBAL_CLI_RE = re.compile(
    r"(?<!run-)optimize-anything\s+(?:" + "|".join(CLI_SUBCOMMANDS) + r")\b"
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
        global_invocation = GLOBAL_CLI_RE.search(text)
        if global_invocation or ("optimize-anything" in text and launcher not in text):
            offenders.append(path.name)
    assert not offenders, f"commands bypass bundled launcher: {offenders}"


def test_shared_skills_resolve_the_bundled_launcher_for_cli_examples():
    expected = {path.parent.name for path in SKILL_FILES}
    skill_dirs = {path.name for path in (REPO_ROOT / "skills").iterdir() if path.is_dir()}
    assert skill_dirs == expected
    for name in expected:
        skill = _read(f"skills/{name}/SKILL.md")
        assert re.match(
            rf"^---\nname: {name}\ndescription: [^\n]+\n(?:  [^\n]+\n)*---\n",
            skill,
        )
        if GLOBAL_CLI_RE.search(skill):
            pytest.fail(f"{name} assumes a global CLI")
        assert "scripts/run-optimize-anything" in skill


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


# --- R7: host-to-backend pairing --------------------------------------------
#
# Requirement (docs/plans/2026-09-22-1841-feature-subscription-backends-plan.md:48):
# Codex-hosted skills pass Codex backend flags, Claude-hosted skills pass
# Claude backend flags, and unknown hosts keep API defaults; core code must
# not infer the host from ambient markers. These tests parse the real command
# and skill markdown -- not mocked fixtures -- so a doc regression (dropped
# flag, swapped host, missing unknown-host fallback) is caught before it
# ships a host that silently bills the wrong account.

COMMAND_ROLES = {
    # optimize.md's Step 3 also passes `--analysis-backend claude` to a
    # nested `analyze` call, but no sentence there names Claude Code, so
    # listing "analysis" here would fail the R7a check below. Add it once the
    # doc scopes that bullet to a host; until then this omission is
    # deliberate, not an oversight.
    "optimize.md": {"proposer", "judge"},
    "quick.md": {"proposer", "judge", "analysis"},
    "analyze.md": {"analysis"},
    "score.md": {"judge"},
    "compare.md": {"judge"},
    "validate.md": {"validate"},
    "budget.md": set(),
    "explain.md": set(),
    "intake.md": set(),
}

SKILL_FILES = (
    Path("skills/generate-evaluator/SKILL.md"),
    Path("skills/optimization-guide/SKILL.md"),
    Path("skills/evaluator-patterns/SKILL.md"),
    Path("skills/optimize-prompt/SKILL.md"),
)

SHARED_HOST_AWARE_DOCS = (
    Path("SKILL.md"),
    Path("skills/generate-evaluator/SKILL.md"),
    Path("skills/optimization-guide/SKILL.md"),
    Path("skills/optimize-prompt/SKILL.md"),
)

ALL_HOST_TEXT_FILES = (
    (Path("SKILL.md"),)
    + tuple(Path("commands") / name for name in sorted(COMMAND_ROLES))
    + SKILL_FILES
)

# host fixture table: host label -> expected backend value, or None for "no
# flag" (an unknown host keeps the API default). R7b parametrizes over the
# rows with a value; the R7c tests below parametrize over the row(s) without
# one, so this single table drives every host branch.
HOST_BACKEND_FIXTURES = (
    ("codex", "codex"),
    ("claude", "claude"),
    ("unknown", None),
)
_KNOWN_HOST_FIXTURES = tuple(row for row in HOST_BACKEND_FIXTURES if row[1] is not None)
_UNKNOWN_HOST_FIXTURES = tuple(row for row in HOST_BACKEND_FIXTURES if row[1] is None)

_HOST_PATTERNS = {
    "codex": re.compile(r"\bCodex\b"),
    "claude": re.compile(r"\bClaude Code\b"),
}
_BACKEND_VALUE_RE = re.compile(
    r"--(?:proposer|judge|analysis)-backend\s+(codex|claude)\b"
    r"|`(codex|claude)(?::[^`]*)?`"
)
_ROLE_FLAG_SUBSTRING = {
    "proposer": "--proposer-backend",
    "judge": "--judge-backend",
    "analysis": "--analysis-backend",
}
_VALIDATE_ANCHOR_RE = re.compile(r"provider|\bvalidate\b", re.IGNORECASE)
# Matches only the singular per-role flags (never validate's multi-value
# `--providers` selector list), so it can be checked even where no host name
# is nearby without false-flagging validate's legitimate dual-selector prose.
_SINGLE_ROLE_FLAG_VALUE_RE = re.compile(r"--(?:proposer|judge|analysis)-backend\s+(codex|claude)\b")
_UNKNOWN_HOST_RE = re.compile(r"\bunknown hosts?\b", re.IGNORECASE)
_API_DEFAULT_RE = re.compile(r"\b(?:omit|keep|api|do not infer)\b", re.IGNORECASE)


def _split_prose_units(text: str) -> list[str]:
    """Split markdown into blank-line paragraphs, then list items, then
    sentences (splitting only before a capital letter, so a mid-sentence
    period in "..." or a numbered header like "5." cannot fracture a real
    sentence). This reassembles hard-wrapped lines and isolates list items
    and fenced-example blocks from each other, which is what makes the
    host/backend checks below robust to this repo's markdown wrapping."""
    units = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        for item in re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", block):
            item = item.strip()
            if not item:
                continue
            normalized = re.sub(r"\s+", " ", item)
            for sentence in re.split(r"(?<=\.)\s+(?=[A-Z])", normalized):
                sentence = sentence.strip()
                if sentence:
                    units.append(sentence)
    return units


def _host_backend_mismatch(unit: str) -> str | None:
    """Return a description if `unit` cross-wires a host with the wrong
    backend value, else None. A unit naming only one host may carry only that
    host's value; a unit naming both hosts must carry both values, ordered
    the same as the host mentions (so a full codex/claude swap is caught even
    though presence-only checking would miss it)."""
    host_hits = [
        (m.start(), host) for host, pattern in _HOST_PATTERNS.items() for m in pattern.finditer(unit)
    ]
    if not host_hits:
        return None
    value_hits = [(m.start(), m.group(1) or m.group(2)) for m in _BACKEND_VALUE_RE.finditer(unit)]
    if not value_hits:
        return None
    hosts_present = {host for _, host in host_hits}
    values_present = {value for _, value in value_hits}
    if hosts_present == {"codex"} and values_present - {"codex"}:
        return "Codex-only text also carries a claude value"
    if hosts_present == {"claude"} and values_present - {"claude"}:
        return "Claude Code-only text also carries a codex value"
    if hosts_present == {"codex", "claude"}:
        first_host = min(host_hits)[1]
        first_value = min(value_hits)[1]
        if first_host != first_value:
            return "dual-host text orders the host and value mentions inconsistently"
        if values_present != {"codex", "claude"}:
            return "dual-host text is missing one backend value"
    return None


def _role_paired_with_host(unit: str, role: str, host: str) -> bool:
    """True if `unit` names `host`, names `role` (its flag, or -- for
    `validate`, the provider-selector concept), carries `host`'s backend
    value, and is not itself a mismatched pairing."""
    if not _HOST_PATTERNS[host].search(unit):
        return False
    if role == "validate":
        if not _VALIDATE_ANCHOR_RE.search(unit):
            return False
    elif _ROLE_FLAG_SUBSTRING[role] not in unit:
        return False
    values = [m.group(1) or m.group(2) for m in _BACKEND_VALUE_RE.finditer(unit)]
    if host not in values:
        return False
    return _host_backend_mismatch(unit) is None


def test_r7a_claude_commands_instruct_claude_backend_for_their_llm_roles():
    """R7a: every Claude Code command that runs a built-in LLM role must
    instruct the `claude` backend for that role -- otherwise the host silently
    bills the user's API key instead of reusing the subscription."""
    command_files = {p.name for p in (REPO_ROOT / "commands").glob("*.md")}
    assert command_files == set(COMMAND_ROLES), (
        "commands/*.md changed; update COMMAND_ROLES to classify: "
        f"{command_files ^ set(COMMAND_ROLES)}"
    )

    missing = []
    for name, roles in COMMAND_ROLES.items():
        units = _split_prose_units(_read(f"commands/{name}"))
        for role in roles:
            if not any(_role_paired_with_host(unit, role, "claude") for unit in units):
                missing.append(f"{name}: no claude backend instruction for role {role!r}")
    assert not missing, f"commands missing claude backend instructions: {missing}"


def test_r7a_non_llm_commands_carry_no_backend_flags():
    """R7a: budget/explain/intake run no built-in LLM role, so they are not
    required to carry backend flags. Asserting they carry none (rather than
    silently skipping them) confirms that classification by reading, and
    guards against an unreviewed backend flag being added to one later."""
    offenders = [
        name
        for name, roles in COMMAND_ROLES.items()
        if not roles and _BACKEND_VALUE_RE.search(_read(f"commands/{name}"))
    ]
    assert not offenders, f"non-LLM commands unexpectedly reference a backend: {offenders}"


@pytest.mark.parametrize("role", ["proposer", "judge", "analysis"])
@pytest.mark.parametrize("host, backend", _KNOWN_HOST_FIXTURES)
def test_r7b_codex_visible_skills_pair_host_with_matching_backend(role, host, backend):
    """R7b: the skills/ tree Codex actually loads (.codex-plugin/plugin.json
    "skills": "./skills/") must instruct the matching backend for every
    built-in LLM role -- otherwise a Codex or Claude Code session silently
    bills the user's API key instead of reusing the subscription."""
    codex_manifest = _json(".codex-plugin/plugin.json")
    codex_skills_root = (REPO_ROOT / codex_manifest["skills"]).resolve()
    assert not (REPO_ROOT / "SKILL.md").resolve().is_relative_to(codex_skills_root), (
        "root SKILL.md is now inside the Codex manifest's skills path; "
        "add it to SKILL_FILES so this test covers it"
    )

    units = [unit for path in SKILL_FILES for unit in _split_prose_units(_read(path))]
    assert any(_role_paired_with_host(unit, role, host) for unit in units), (
        f"no skills/*/SKILL.md sentence pairs the {host} host with {backend} for role {role!r}"
    )


@pytest.mark.parametrize("host, backend", _UNKNOWN_HOST_FIXTURES)
def test_r7c_shared_skill_docs_guide_unknown_hosts_to_the_api_default(host, backend):
    """R7c: shared skill docs must tell an unknown host to omit backend flags
    and keep the API default -- otherwise a host the runtime cannot identify
    could be steered toward a subscription backend it has no credentials
    for."""
    assert backend is None, f"fixture row for {host!r} should carry no backend value"
    missing = [
        str(path)
        for path in SHARED_HOST_AWARE_DOCS
        if not any(
            _UNKNOWN_HOST_RE.search(unit) and _API_DEFAULT_RE.search(unit)
            for unit in _split_prose_units(_read(path))
        )
    ]
    assert not missing, f"missing {host}-host API-default guidance: {missing}"


@pytest.mark.parametrize("host, backend", _UNKNOWN_HOST_FIXTURES)
def test_r7c_no_instruction_sends_an_unknown_host_to_a_specific_backend(host, backend):
    """R7c: no sentence may pair "unknown host(s)" with a codex/claude backend
    value -- an unknown host must never be steered to a specific subscription
    backend it may not be authenticated for."""
    assert backend is None, f"fixture row for {host!r} should carry no backend value"
    offenders = [
        f"{path}: {unit!r}"
        for path in ALL_HOST_TEXT_FILES
        for unit in _split_prose_units(_read(path))
        if _UNKNOWN_HOST_RE.search(unit) and _BACKEND_VALUE_RE.search(unit)
    ]
    assert not offenders, f"{host} host paired with a specific backend: {offenders}"


def test_r7d_no_sentence_pairs_a_host_with_the_wrong_backend():
    """R7d: no sentence may pair the Claude Code host with a codex value, or
    the Codex host with a claude value -- a swapped pairing would bill the
    wrong provider's key, or attempt a subscription call the host cannot
    authenticate."""
    mismatches = [
        f"{path}: {reason}: {unit!r}"
        for path in ALL_HOST_TEXT_FILES
        for unit in _split_prose_units(_read(path))
        if (reason := _host_backend_mismatch(unit))
    ]
    assert not mismatches, f"cross-wired host/backend pairing: {mismatches}"


def test_r7d_unscoped_command_bullets_never_carry_a_non_claude_value():
    """R7d: commands/*.md is Claude Code's exclusive command surface --
    .codex-plugin/plugin.json only declares "./skills/", so Codex never loads
    these files. `_host_backend_mismatch` above only judges sentences that
    name a host; this test covers the complement -- a bullet with no host
    named at all -- because a bare `codex` value there would still steer a
    Claude Code session at a backend it cannot authenticate for."""
    offenders = []
    for name in COMMAND_ROLES:
        for unit in _split_prose_units(_read(f"commands/{name}")):
            if any(pattern.search(unit) for pattern in _HOST_PATTERNS.values()):
                continue  # host-named sentences are already covered above
            values = set(_SINGLE_ROLE_FLAG_VALUE_RE.findall(unit))
            if values - {"claude"}:
                offenders.append(f"commands/{name}: {unit!r}")
    assert not offenders, f"unscoped command bullet carries a non-claude value: {offenders}"


def _paragraph_blocks(text: str) -> list[str]:
    """Coarser than `_split_prose_units`: paragraphs and list items only, with
    no sentence split. Used so a host named earlier in the same paragraph
    still scopes a bare backend value mentioned later in it -- unlike
    `commands/*.md`, these dual-host docs have no single value that is always
    correct, so scope can only come from a host name in the same block."""
    blocks = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        for item in re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", block):
            item = item.strip()
            if item:
                blocks.append(re.sub(r"\s+", " ", item))
    return blocks


def test_r7d_dual_host_docs_never_carry_an_unscoped_backend_value():
    """R7d: SKILL.md and skills/*/SKILL.md discuss both hosts side by side, so
    file scope alone (unlike commands/*.md) cannot tell a reader which host a
    bare codex/claude value is for. Every paragraph or list item that carries
    a backend value must name at least one host in that same block, or an
    edit could silently steer an unspecified host at a subscription backend
    it has no credentials for."""
    offenders = []
    for path in (Path("SKILL.md"),) + SKILL_FILES:
        for block in _paragraph_blocks(_read(path)):
            has_value = _BACKEND_VALUE_RE.search(block)
            has_host = any(pattern.search(block) for pattern in _HOST_PATTERNS.values())
            if has_value and not has_host:
                offenders.append(f"{path}: {block!r}")
    assert not offenders, f"unscoped backend value with no host named in its block: {offenders}"
