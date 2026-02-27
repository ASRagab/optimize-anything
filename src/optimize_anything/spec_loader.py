"""Load and normalize optimization spec files (TOML format).

Spec files allow saving repeatable optimization run configurations.
All paths in the spec are resolved relative to the spec file's location.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


class SpecLoadError(ValueError):
    """Raised when a spec file cannot be loaded or is invalid."""


def load_spec(spec_path: str | Path) -> dict[str, Any]:
    """Load and normalize a TOML spec file into CLI-compatible argument dict."""
    spec_path = Path(spec_path).expanduser().resolve()
    if not spec_path.exists():
        raise SpecLoadError(f"spec file not found: {spec_path}")

    try:
        with open(spec_path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise SpecLoadError(f"invalid TOML in spec file '{spec_path}': {exc}") from exc

    spec_dir = spec_path.parent
    return _normalize_spec(raw, spec_dir=spec_dir)


def _normalize_spec(raw: dict[str, Any], *, spec_dir: Path) -> dict[str, Any]:
    opt = raw.get("optimization", {})
    evaluator = raw.get("evaluator", {})
    model = raw.get("model", {})
    intake_section = raw.get("intake", {})

    result: dict[str, Any] = {
        "seed_file": None,
        "objective": None,
        "background": None,
        "budget": None,
        "output": None,
        "evaluator_command": None,
        "evaluator_url": None,
        "evaluator_cwd": None,
        "judge_model": None,
        "proposer_model": None,
        "intake": None,
    }

    if "seed_file" in opt:
        seed_raw = opt["seed_file"]
        if not isinstance(seed_raw, str):
            raise SpecLoadError("optimization.seed_file must be a string")
        result["seed_file"] = str(_resolve_path(seed_raw, base=spec_dir))

    for str_key in ("objective", "background", "output"):
        if str_key in opt:
            value = opt[str_key]
            if not isinstance(value, str):
                raise SpecLoadError(f"optimization.{str_key} must be a string")
            result[str_key] = value

    if "budget" in opt:
        budget_raw = opt["budget"]
        if not isinstance(budget_raw, int) or budget_raw <= 0:
            raise SpecLoadError("optimization.budget must be a positive integer")
        result["budget"] = budget_raw

    if "command" in evaluator:
        cmd = evaluator["command"]
        if not isinstance(cmd, list) or not cmd:
            raise SpecLoadError("evaluator.command must be a non-empty list of strings")
        if not all(isinstance(c, str) for c in cmd):
            raise SpecLoadError("evaluator.command must be a list of strings")
        result["evaluator_command"] = cmd

    if "url" in evaluator:
        url = evaluator["url"]
        if not isinstance(url, str):
            raise SpecLoadError("evaluator.url must be a string")
        result["evaluator_url"] = url

    if "cwd" in evaluator:
        cwd_raw = evaluator["cwd"]
        if not isinstance(cwd_raw, str):
            raise SpecLoadError("evaluator.cwd must be a string")
        result["evaluator_cwd"] = str(_resolve_path(cwd_raw, base=spec_dir))

    if "judge" in model:
        judge = model["judge"]
        if not isinstance(judge, str):
            raise SpecLoadError("model.judge must be a string")
        result["judge_model"] = judge

    if "proposer" in model:
        proposer = model["proposer"]
        if not isinstance(proposer, str):
            raise SpecLoadError("model.proposer must be a string")
        result["proposer_model"] = proposer

    if intake_section:
        result["intake"] = dict(intake_section)

    return result


def _resolve_path(path_str: str, *, base: Path) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = base / path
    return path
