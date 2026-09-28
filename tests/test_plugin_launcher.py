"""Tests for the self-locating plugin runtime launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from optimize_anything.llm_backends.codex_backend import _SDK_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "run-optimize-anything"
INSTALLER = REPO_ROOT / "install.sh"


def test_codex_extra_matches_runtime_sdk_version():
    project = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    assert f'codex = ["openai-codex=={_SDK_VERSION}"]' in project
    assert f"openai-codex=={_SDK_VERSION}" in installer


def _write_fake_uv(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def test_launcher_resolves_relocated_root_and_forwards_arguments(tmp_path: Path):
    relocated = tmp_path / "relocated plugin"
    launcher = relocated / "scripts" / LAUNCHER.name
    launcher.parent.mkdir(parents=True)
    shutil.copy2(LAUNCHER, launcher)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "uv-args.txt"
    _write_fake_uv(
        bin_dir / "uv",
        'if [ "$1" = "python" ]; then exit 0; fi\n'
        'printf "%s\\n" "$@" > "$UV_ARGS_FILE"\n',
    )
    env = os.environ.copy()
    env.update({"PATH": f"{bin_dir}:/usr/bin:/bin", "UV_ARGS_FILE": str(args_file)})

    result = subprocess.run(
        ["/bin/bash", str(launcher), "score", "prompt.txt", "--objective", "Clear"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "run",
        "--project",
        str(relocated),
        "--locked",
        "--no-dev",
        "--extra",
        "codex",
        "optimize-anything",
        "score",
        "prompt.txt",
        "--objective",
        "Clear",
    ]
    assert shutil.which("optimize-anything", path=env["PATH"]) is None


def test_launcher_reports_missing_uv(tmp_path: Path):
    env = os.environ.copy()
    env["PATH"] = str(tmp_path)
    result = subprocess.run(
        ["/bin/bash", str(LAUNCHER), "--help"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 127
    assert "Install uv" in result.stderr


def test_launcher_reports_missing_supported_python(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_uv(bin_dir / "uv", 'if [ "$1" = "python" ]; then exit 1; fi\nexit 99\n')
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"

    result = subprocess.run(
        ["/bin/bash", str(LAUNCHER), "--help"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "Python 3.10 or newer" in result.stderr


def test_global_installer_codex_flag_adds_sdk_to_tool_environment(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "uv-args.txt"
    _write_fake_uv(
        bin_dir / "uv",
        'if [ "$1" = "--version" ]; then echo "uv 0.0.0"; exit 0; fi\n'
        'printf "%s\\n" "$@" > "$UV_ARGS_FILE"\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "UV_ARGS_FILE": str(args_file),
            "OPTIMIZE_ANYTHING_REPO": str(REPO_ROOT),
        }
    )

    result = subprocess.run(
        ["/bin/bash", str(INSTALLER), "--codex"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "tool",
        "install",
        str(REPO_ROOT),
        "--with",
        "openai-codex==0.156.0",
        "--force",
    ]
