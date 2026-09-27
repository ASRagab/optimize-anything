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
        if "Cannot overwrite a value" in str(exc):
            section = ""
            scalar_roles: set[str] = set()
            table_roles: set[str] = set()
            for line in spec_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and "]" in stripped:
                    section = stripped[1:stripped.index("]")]
                    if section in {"model.proposer", "model.judge"}:
                        table_roles.add(section.removeprefix("model."))
                elif section == "model" and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in {"proposer", "judge"}:
                        scalar_roles.add(key)
            for role in ("proposer", "judge"):
                if role in scalar_roles & table_roles:
                    raise SpecLoadError(
                        f"model.{role} scalar conflicts with [model.{role}] table; choose one"
                    ) from exc
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
        "parallel": None,
        "workers": None,
        "proposals_per_iteration": None,
        "cache": None,
        "cache_from": None,
        "early_stop": None,
        "early_stop_window": None,
        "early_stop_threshold": None,
        "evaluator_command": None,
        "evaluator_url": None,
        "evaluator_cwd": None,
        "judge_model": None,
        "proposer_model": None,
        "judge_backend": None,
        "proposer_backend": None,
        "judge_api_fallback": None,
        "proposer_api_fallback": None,
        "judge_api_fallback_model": None,
        "proposer_api_fallback_model": None,
        "task_model": None,
        "intake": None,
    }

    result.update(_normalize_optimization_section(opt, spec_dir=spec_dir))
    result.update(_normalize_evaluator_section(evaluator, spec_dir=spec_dir))
    result.update(_normalize_model_section(model))

    if intake_section:
        result["intake"] = dict(intake_section)

    return result


def _normalize_optimization_section(
    opt: dict[str, Any],
    *,
    spec_dir: Path,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    if "seed_file" in opt:
        normalized["seed_file"] = str(
            _resolve_path(_require_string(opt, "seed_file", "optimization"), base=spec_dir)
        )

    for key in ("objective", "background", "output", "task_model"):
        if key in opt:
            normalized[key] = _require_string(opt, key, "optimization")

    for key in (
        "budget",
        "workers",
        "proposals_per_iteration",
        "early_stop_window",
    ):
        if key in opt:
            normalized[key] = _require_positive_int(opt, key, "optimization")

    for key in ("parallel", "cache", "early_stop"):
        if key in opt:
            normalized[key] = _require_bool(opt, key, "optimization")

    if "cache_from" in opt:
        normalized["cache_from"] = str(
            _resolve_path(_require_string(opt, "cache_from", "optimization"), base=spec_dir)
        )

    if "early_stop_threshold" in opt:
        normalized["early_stop_threshold"] = _require_non_negative_number(
            opt,
            "early_stop_threshold",
            "optimization",
        )

    return normalized


def _normalize_evaluator_section(
    evaluator: dict[str, Any],
    *,
    spec_dir: Path,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    if "command" in evaluator:
        normalized["evaluator_command"] = _require_string_list(
            evaluator,
            "command",
            "evaluator",
        )
    if "url" in evaluator:
        normalized["evaluator_url"] = _require_string(evaluator, "url", "evaluator")
    if "cwd" in evaluator:
        normalized["evaluator_cwd"] = str(
            _resolve_path(_require_string(evaluator, "cwd", "evaluator"), base=spec_dir)
        )

    return normalized


def _normalize_model_section(model: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    if "judge" in model:
        normalized.update(_normalize_model_role(model["judge"], role="judge"))
    if "proposer" in model:
        normalized.update(_normalize_model_role(model["proposer"], role="proposer"))

    return normalized


def _normalize_model_role(value: Any, *, role: str) -> dict[str, Any]:
    if isinstance(value, str):
        return {f"{role}_model": value, f"{role}_backend": "api"}
    if not isinstance(value, dict):
        raise SpecLoadError(f"model.{role} must be a string or table")
    unknown = set(value) - {"backend", "model", "api_fallback", "api_fallback_model"}
    if unknown:
        raise SpecLoadError(f"model.{role} has unknown keys: {', '.join(sorted(unknown))}")
    backend = value.get("backend", "api")
    if backend not in ("api", "codex", "claude"):
        raise SpecLoadError(f"model.{role}.backend must be api, codex, or claude")
    normalized: dict[str, Any] = {f"{role}_backend": backend}
    if "model" in value:
        normalized[f"{role}_model"] = _require_string(value, "model", f"model.{role}")
    if "api_fallback" in value:
        normalized[f"{role}_api_fallback"] = _require_bool(
            value, "api_fallback", f"model.{role}"
        )
    elif backend != "api":
        normalized[f"{role}_api_fallback"] = True
    if "api_fallback_model" in value:
        normalized[f"{role}_api_fallback_model"] = _require_string(
            value, "api_fallback_model", f"model.{role}"
        )
    return normalized


def _require_string(section: dict[str, Any], key: str, section_name: str) -> str:
    value = section[key]
    if not isinstance(value, str):
        raise SpecLoadError(f"{section_name}.{key} must be a string")
    return value


def _require_positive_int(section: dict[str, Any], key: str, section_name: str) -> int:
    value = section[key]
    if not isinstance(value, int) or value <= 0:
        raise SpecLoadError(f"{section_name}.{key} must be a positive integer")
    return value


def _require_bool(section: dict[str, Any], key: str, section_name: str) -> bool:
    value = section[key]
    if not isinstance(value, bool):
        raise SpecLoadError(f"{section_name}.{key} must be a boolean")
    return value


def _require_non_negative_number(
    section: dict[str, Any],
    key: str,
    section_name: str,
) -> float:
    value = section[key]
    if not isinstance(value, (int, float)) or value < 0:
        raise SpecLoadError(f"{section_name}.{key} must be a non-negative number")
    return float(value)


def _require_string_list(
    section: dict[str, Any],
    key: str,
    section_name: str,
) -> list[str]:
    value = section[key]
    if not isinstance(value, list) or not value:
        raise SpecLoadError(f"{section_name}.{key} must be a non-empty list of strings")
    if not all(isinstance(item, str) for item in value):
        raise SpecLoadError(f"{section_name}.{key} must be a list of strings")
    return value


def _resolve_path(path_str: str, *, base: Path) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = base / path
    return path
