from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from copier import run_copy, run_update

from .factories import CopierAnswersFactory

ROOT = Path(__file__).parents[1]
LEGACY_TEMPLATE = ROOT / "tests" / "fixtures" / "legacy-template"


def run_git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


def commit_all(repository: Path, message: str) -> None:
    run_git("add", "--all", cwd=repository)
    run_git("commit", "--message", message, cwd=repository)


def snapshot(root: Path) -> dict[str, tuple[bool, str]]:
    result: dict[str, tuple[bool, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            executable = bool(path.stat().st_mode & 0o111)
            result[relative] = (executable, hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def test_update_converges_with_fresh_candidate_render(tmp_path: Path) -> None:
    template_repository = tmp_path / "template-repository"
    shutil.copytree(LEGACY_TEMPLATE, template_repository)
    run_git("init", "--initial-branch=main", cwd=template_repository)
    run_git("config", "user.name", "Template Test", cwd=template_repository)
    run_git("config", "user.email", "template@example.test", cwd=template_repository)
    commit_all(template_repository, "legacy template")
    run_git("tag", "v0.0.0", cwd=template_repository)

    answers = CopierAnswersFactory(distinct_import_name=True).to_copier_data()
    updated = tmp_path / "updated"
    run_copy(
        src_path=str(template_repository),
        dst_path=updated,
        data=answers,
        vcs_ref="v0.0.0",
        defaults=True,
        quiet=True,
    )
    run_git("init", "--initial-branch=main", cwd=updated)
    run_git("config", "user.name", "Generated Project Test", cwd=updated)
    run_git("config", "user.email", "project@example.test", cwd=updated)
    commit_all(updated, "render legacy project")

    shutil.rmtree(template_repository / "template")
    shutil.copytree(ROOT / "template", template_repository / "template")
    shutil.copy2(ROOT / "copier.yml", template_repository / "copier.yml")
    commit_all(template_repository, "candidate template")

    run_update(
        dst_path=updated,
        vcs_ref="HEAD",
        defaults=True,
        quiet=True,
        unsafe=True,
        overwrite=True,
        conflict="rej",
    )
    assert not list(updated.rglob("*.rej"))

    fresh = tmp_path / "fresh"
    run_copy(
        src_path=str(template_repository),
        dst_path=fresh,
        data=answers,
        vcs_ref="HEAD",
        defaults=True,
        quiet=True,
        unsafe=True,
    )

    updated_snapshot = {
        path: value for path, value in snapshot(updated).items() if not path.startswith(".git/")
    }
    assert updated_snapshot == snapshot(fresh)
    assert not (updated / "noxfile.py").exists()
    assert "qualification" not in (updated / "pyproject.toml").read_text()
    assert "nox" not in (updated / "justfile").read_text()
