"""Offline coverage for credentialed plugin-regression wiring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import plugin_regression


def test_dry_run_writes_prompt_scenarios_and_all_workflow_fixtures(tmp_path: Path):
    output_dir = tmp_path / "dry-run"
    assert plugin_regression.main(["--dry-run", "--output-dir", str(output_dir)]) == 0

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "DRY_RUN"
    assert set(summary["workflow_fixture_ids"]) == {
        "inline-return",
        "standalone-apply",
        "embedded-apply",
        "rejected-noop",
        "independent-batch",
        "coupled-refusal",
    }
    assert {scenario["scenario"] for scenario in summary["live_scenarios"]} == {
        "inline",
        "repository-apply",
    }
    assert all("$optimize-prompt" in scenario["prompt"] for scenario in summary["live_scenarios"])

    repository_scenario = next(
        scenario
        for scenario in summary["live_scenarios"]
        if scenario["scenario"] == "repository-apply"
    )
    artifact = Path(repository_scenario["artifact"])
    assert artifact.read_text(encoding="utf-8") == plugin_regression.EMBEDDED_BASELINE
    compile(artifact.read_text(encoding="utf-8"), str(artifact), "exec")


def test_live_prompt_scenarios_are_bounded_and_preserve_targeting():
    inline = plugin_regression._inline_prompt()
    fixture = Path("/tmp/prompt_module.py")
    repository = plugin_regression._repository_apply_prompt(fixture)

    assert "budget of 3" in inline
    assert "Do not modify repository files" in inline
    assert "budget of 3" in repository
    assert str(fixture) in repository
    assert "exact string" in repository
    assert "triple-quoted" in repository
    assert "KEEP = 1" in repository


def test_claude_host_regression_uses_bounded_model(tmp_path: Path):
    command = plugin_regression._claude_base(tmp_path)

    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--max-budget-usd") + 1] == "0.75"


def test_analyze_accepts_seed_score_wording(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        plugin_regression,
        "_run_claude",
        lambda *args: {
            "subtype": "success",
            "is_error": False,
            "result": "Seed score 0.3. Improve specificity with optimize-anything optimize.",
            "num_turns": 2,
            "total_cost_usd": 0.1,
            "duration_ms": 1000,
        },
    )

    result = plugin_regression.scenario_analyze(tmp_path, tmp_path, tmp_path / "seed.txt")

    assert result["scenario"] == "analyze"


def test_quick_accepts_compact_score_transition(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    best_path = tmp_path / "runs" / "plugin-eval" / "quick-best.txt"
    best_path.parent.mkdir(parents=True)
    best_path.write_text("Give clear, concise, specific answers with useful context.")
    monkeypatch.setattr(
        plugin_regression,
        "_run_claude",
        lambda *args: {
            "subtype": "success",
            "is_error": False,
            "result": "Done. Score 0.15 → 0.91, 3 iterations, 7 evaluator calls.",
            "num_turns": 3,
            "total_cost_usd": 0.2,
            "duration_ms": 1000,
        },
    )

    result = plugin_regression.scenario_quick(tmp_path, tmp_path, tmp_path / "seed.txt")

    assert result["scenario"] == "quick"


def test_inline_accepts_an_expanded_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        plugin_regression,
        "_run_claude",
        lambda *args: {
            "subtype": "success",
            "is_error": False,
            "result": "Accepted prompt: You are a helpful, accurate assistant. Prompt-quality score improved.",
            "num_turns": 9,
            "total_cost_usd": 0.4,
            "duration_ms": 1000,
        },
    )

    result = plugin_regression.scenario_inline(tmp_path, tmp_path, tmp_path / "seed.txt")

    assert result["scenario"] == "inline"


def test_prompt_scenarios_require_only_the_provider_they_use():
    assert plugin_regression._required_env_names("inline") == ["OPENAI_API_KEY"]
    assert plugin_regression._required_env_names("repository-apply") == ["OPENAI_API_KEY"]
    assert plugin_regression._required_env_names("validate") == [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]


def test_repository_apply_allows_only_the_recorded_prompt_region_to_change():
    fixture = Path("prompt_module.py")
    updated = (
        plugin_regression.EMBEDDED_PREFIX
        + "Give a concise answer."
        + plugin_regression.EMBEDDED_SUFFIX
    )
    assert plugin_regression._validate_repository_apply(updated, fixture) == (
        "Give a concise answer."
    )

    with pytest.raises(
        plugin_regression.PluginRegressionFailure,
        match="outside the recorded prompt region",
    ):
        plugin_regression._validate_repository_apply(updated + "CHANGED = 1\n", fixture)
