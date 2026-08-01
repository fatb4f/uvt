from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def template_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    source = Path(__file__).parents[1]
    repository = tmp_path_factory.mktemp("template-source")
    shutil.copy2(source / "copier.yml", repository / "copier.yml")
    shutil.copytree(source / "template", repository / "template")
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    for key, value in (
        ("user.name", "Template Test"),
        ("user.email", "template@example.test"),
    ):
        subprocess.run(
            ["git", "config", key, value],
            cwd=repository,
            check=True,
            text=True,
            capture_output=True,
        )
    subprocess.run(
        ["git", "add", "--all"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--message", "template under test"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    return repository


@pytest.fixture(autouse=True)
def reset_factory_sequences() -> Iterator[None]:
    from .factories import CopierAnswersFactory

    CopierAnswersFactory.reset_sequence()
    yield
