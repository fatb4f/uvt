from __future__ import annotations

import ast
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest
import yaml
from copier import run_copy
from hypothesis import given
from hypothesis import strategies as st

from .factories import CopierAnswersFactory
from .models import LicenseName

DISTIBUTION_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
IMPORT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_rendered_syntax(destination: Path) -> None:
    for path in destination.rglob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    for path in destination.rglob("*.toml"):
        tomllib.loads(path.read_text())
    for path in destination.rglob("*.yml"):
        yaml.safe_load(path.read_text())
    for path in (destination / "scripts").iterdir():
        if path.is_file() and path.suffix != ".py":
            subprocess.run(["sh", "-n", str(path)], check=True)
    subprocess.run(["just", "--list"], cwd=destination, check=True, capture_output=True, text=True)


@pytest.mark.parametrize(
    ("license_name", "publish"),
    [
        pytest.param(LicenseName.MIT, False, id="mit-local"),
        pytest.param(LicenseName.MIT, True, id="mit-publish"),
        pytest.param(LicenseName.APACHE_2_0, False, id="apache-local"),
        pytest.param(LicenseName.APACHE_2_0, True, id="apache-publish"),
    ],
)
def test_render_matrix(
    template_root: Path,
    tmp_path: Path,
    license_name: LicenseName,
    publish: bool,
) -> None:
    answers = CopierAnswersFactory(license_name=license_name, publish=publish)
    destination = tmp_path / answers.distribution_name

    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers.to_copier_data(),
        defaults=True,
        quiet=True,
        unsafe=True,
    )

    assert (destination / "uv.lock").is_file()
    assert (destination / "src" / answers.import_package_name / "py.typed").is_file()
    assert (destination / ".github" / "workflows" / "publish.yml").exists() is publish
    assert (destination / "LICENSE").read_text().startswith(license_name.value.split("-")[0])
    assert (destination / ".gitignore").is_file()
    assert_rendered_syntax(destination)


@given(invalid_name=st.text().filter(lambda value: DISTIBUTION_NAME.fullmatch(value) is None))
def test_invalid_distribution_names_are_rejected(
    template_root: Path,
    invalid_name: str,
) -> None:
    with (
        tempfile.TemporaryDirectory() as directory,
        pytest.raises(ValueError, match="distribution_name"),
    ):
        run_copy(
            src_path=str(template_root),
            dst_path=Path(directory) / "invalid-output",
            data={
                "distribution_name": invalid_name,
                "import_package_name": "valid_package",
                "author_name": "Raw Author",
                "author_email": "raw@example.test",
                "github_owner": "example",
            },
            defaults=True,
            quiet=True,
            skip_tasks=True,
        )


@given(
    invalid_name=st.text().filter(
        lambda value: (
            IMPORT_NAME.fullmatch(value) is None
            or value
            in {
                "False",
                "None",
                "True",
                "and",
                "as",
                "assert",
                "async",
                "await",
                "break",
                "class",
                "continue",
                "def",
                "del",
                "elif",
                "else",
                "except",
                "finally",
                "for",
                "from",
                "global",
                "if",
                "import",
                "in",
                "is",
                "lambda",
                "nonlocal",
                "not",
                "or",
                "pass",
                "raise",
                "return",
                "try",
                "while",
                "with",
                "yield",
            }
        )
    )
)
def test_invalid_import_package_names_are_rejected(
    template_root: Path,
    invalid_name: str,
) -> None:
    with (
        tempfile.TemporaryDirectory() as directory,
        pytest.raises(ValueError, match="import_package_name"),
    ):
        run_copy(
            src_path=str(template_root),
            dst_path=Path(directory) / "invalid-output",
            data={
                "distribution_name": "valid-project",
                "import_package_name": invalid_name,
                "author_name": "Raw Author",
                "author_email": "raw@example.test",
                "github_owner": "example",
            },
            defaults=True,
            quiet=True,
            skip_tasks=True,
        )


@pytest.mark.parametrize("description", ["", "   ", "\t\n"])
def test_blank_descriptions_are_rejected(template_root: Path, description: str) -> None:
    with (
        tempfile.TemporaryDirectory() as directory,
        pytest.raises(ValueError, match="description"),
    ):
        run_copy(
            src_path=str(template_root),
            dst_path=Path(directory) / "invalid-output",
            data=CopierAnswersFactory(description=description).to_copier_data(),
            defaults=True,
            quiet=True,
            skip_tasks=True,
        )


@pytest.mark.parametrize(
    "answers",
    [
        {
            "description": 'quoted "text"\\path\nUnicode: 包',
            "author_name": 'A "quoted" Author',
            "author_email": 'quoted"@example.test',
            "github_owner": 'owner\n[project.urls]\nInjected = "no"',
        },
    ],
)
def test_adversarial_answers_render_as_structured_syntax(
    template_root: Path, tmp_path: Path, answers: dict[str, str]
) -> None:
    data = CopierAnswersFactory().to_copier_data() | answers
    destination = tmp_path / "adversarial"
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=data,
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )
    assert_rendered_syntax(destination)


def test_private_ui_recipe_is_not_listed(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory()
    destination = tmp_path / answers.distribution_name
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers.to_copier_data(),
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )

    listed = subprocess.run(
        ["just", "--list"], cwd=destination, check=True, text=True, capture_output=True
    ).stdout
    dry_run_result = subprocess.run(
        ["just", "--dry-run", "ui"], cwd=destination, check=True, text=True, capture_output=True
    )
    dry_run = dry_run_result.stdout + dry_run_result.stderr

    assert "    ui" not in listed
    assert dry_run.splitlines()[-1].startswith("lazyjust ")
    assert "just ui" not in dry_run
    assert str(destination) in dry_run


def test_copier_cli_smoke(template_root: Path, tmp_path: Path) -> None:
    destination = tmp_path / "cli-project"

    subprocess.run(
        [
            "copier",
            "copy",
            "--defaults",
            "--trust",
            "--data",
            "distribution_name=cli-project",
            "--data",
            "import_package_name=cli_project",
            "--data",
            "author_name=CLI Author",
            "--data",
            "author_email=cli@example.test",
            "--data",
            "github_owner=example",
            str(template_root),
            str(destination),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert (destination / "uv.lock").is_file()
    assert not (destination / ".github" / "workflows" / "publish.yml").exists()


@pytest.mark.skipif(shutil.which("nvim") is None, reason="Neovim is not installed")
def test_project_local_lazy_spec_loads(template_root: Path, tmp_path: Path) -> None:
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
    lazy_spec = destination / ".lazy.lua"

    subprocess.run(
        [
            "nvim",
            "--headless",
            "-u",
            "NONE",
            "-c",
            f"lua assert(loadfile([[{lazy_spec}]]))()",
            "+qa",
        ],
        cwd=destination,
        check=True,
        text=True,
        capture_output=True,
    )
    assert 'Snacks.terminal.open({ "lazyjust", root }, { cwd = root })' in lazy_spec.read_text()
