from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from copier import run_copy

from .factories import CopierAnswersFactory


def run_checked(
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def add_executable(directory: Path, name: str) -> None:
    executable = directory / name
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)


def test_canonical_generated_project_qualifies(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory().to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        unsafe=True,
    )

    run_checked("git", "init", "--initial-branch=main", cwd=destination)
    run_checked("git", "config", "user.name", "Generated Project Test", cwd=destination)
    run_checked("git", "config", "user.email", "generated@example.test", cwd=destination)
    run_checked("git", "add", "--all", cwd=destination)
    run_checked("git", "commit", "--message", "initial render", cwd=destination)

    run_checked("just", "sync", cwd=destination)
    run_checked("just", "check", cwd=destination)
    run_checked("just", "test-clean-locked", cwd=destination)
    run_checked("just", "check", cwd=destination)
    run_checked("just", "build", cwd=destination)
    package_result = run_checked("just", "package-check", cwd=destination)
    run_checked("just", "standards-check", cwd=destination)

    assert "0.1.0" in package_result.stdout
    run_checked("git", "diff", "--exit-code", cwd=destination)
    assert not run_checked(
        "git", "ls-files", "--others", "--exclude-standard", cwd=destination
    ).stdout


def test_tools_check_detects_required_and_optional_tools(
    template_root: Path, tmp_path: Path
) -> None:
    answers = CopierAnswersFactory().to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )
    checker = destination / "scripts" / "tools-check"
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()

    missing_uv = subprocess.run(
        ["/bin/sh", str(checker)],
        cwd=destination,
        env={**os.environ, "PATH": str(empty_path)},
        check=False,
        text=True,
        capture_output=True,
    )

    assert missing_uv.returncode != 0
    assert "missing: uv" in missing_uv.stderr

    add_executable(empty_path, "uv")
    missing_just = subprocess.run(
        ["/bin/sh", str(checker)],
        cwd=destination,
        env={**os.environ, "PATH": str(empty_path)},
        check=False,
        text=True,
        capture_output=True,
    )
    assert missing_just.returncode != 0
    assert "missing: just" in missing_just.stderr

    add_executable(empty_path, "just")
    optional_lazyjust = subprocess.run(
        ["/bin/sh", str(checker)],
        cwd=destination,
        env={**os.environ, "PATH": str(empty_path)},
        check=True,
        text=True,
        capture_output=True,
    )
    assert "optional: lazyjust not installed" in optional_lazyjust.stdout


def test_offline_package_check_requires_locked_cache_hydration(
    template_root: Path, tmp_path: Path
) -> None:
    answers = CopierAnswersFactory().to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        unsafe=True,
    )
    pyproject = destination / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            'description = "A modern Python package"',
            'description = "A modern Python package"\ndependencies = ["packaging==25.0"]',
        )
    )
    cache = tmp_path / "uv-cache"
    environment = {
        **os.environ,
        "UV_CACHE_DIR": str(cache),
        "UV_PYTHON": sys.executable,
    }
    run_checked("uv", "lock", cwd=destination, env=environment)
    shutil.rmtree(cache)
    cache.mkdir()

    run_checked("just", "test-clean-locked", cwd=destination, env=environment)
    run_checked("just", "build", cwd=destination, env=environment)
    offline = {**environment, "UV_OFFLINE": "1"}
    run_checked("just", "package-check", cwd=destination, env=offline)

    shutil.rmtree(cache)
    cache.mkdir()
    missing_cache = subprocess.run(
        ["just", "package-check"],
        cwd=destination,
        env=offline,
        check=False,
        text=True,
        capture_output=True,
    )
    assert missing_cache.returncode != 0
    assert "cache" in (missing_cache.stdout + missing_cache.stderr).lower()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$UVT_FAKE_UV_LOG"\n'
        'test "$1" = pip && test "$2" = install && test "$3" = --python\n'
        'exec "$4" -m pip install --no-deps "$5"\n'
    )
    fake_uv.chmod(0o755)
    uv_log = tmp_path / "fake-uv.log"
    online = {
        **environment,
        "PATH": f"{fake_bin}:{environment['PATH']}",
        "UV_OFFLINE": "0",
        "UVT_FAKE_UV_LOG": str(uv_log),
    }
    run_checked(
        sys.executable,
        "scripts/package_check.py",
        "--online",
        "dist",
        answers["import_package_name"],
        cwd=destination,
        env=online,
    )
    invocation = uv_log.read_text()
    assert invocation.startswith("pip install --python ")
    assert "--offline" not in invocation


@pytest.mark.online
def test_package_check_online_against_current_index(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory().to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        unsafe=True,
    )
    run_checked("just", "build", cwd=destination)
    run_checked(
        "just",
        "package-check-online",
        cwd=destination,
        env={**os.environ, "UV_OFFLINE": "0"},
    )


def test_version_recipe_updates_metadata_without_sync(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory().to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        unsafe=True,
    )

    run_checked("just", "version", "0.1.1", cwd=destination)

    assert 'version = "0.1.1"' in (destination / "pyproject.toml").read_text()
    assert 'version = "0.1.1"' in (destination / "uv.lock").read_text()
    assert not (destination / ".venv").exists()
