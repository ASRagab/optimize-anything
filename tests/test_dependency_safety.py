from __future__ import annotations

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPROMISED_LITELLM_VERSIONS = {Version("1.82.7"), Version("1.82.8")}


def _project_dependencies() -> dict[str, Requirement]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    requirements = [Requirement(value) for value in data["project"]["dependencies"]]
    return {requirement.name: requirement for requirement in requirements}


def _locked_version(package_name: str) -> Version:
    data = tomllib.loads((REPO_ROOT / "uv.lock").read_text())
    for package in data["package"]:
        if package["name"] == package_name:
            return Version(package["version"])
    raise AssertionError(f"{package_name} is not present in uv.lock")


def test_optimizer_dependency_constraints_exclude_compromised_litellm_versions():
    dependencies = _project_dependencies()

    assert Version("0.1.1") in dependencies["gepa"].specifier
    assert Version("0.2.0") not in dependencies["gepa"].specifier

    litellm_specifier = dependencies["litellm"].specifier
    assert Version("1.83.0") in litellm_specifier
    for version in COMPROMISED_LITELLM_VERSIONS:
        assert version not in litellm_specifier


def test_uv_lock_pins_litellm_after_compromised_versions():
    locked_litellm = _locked_version("litellm")

    assert locked_litellm >= Version("1.83.0")
    assert locked_litellm not in COMPROMISED_LITELLM_VERSIONS
