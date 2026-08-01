from __future__ import annotations

from pathlib import Path

import pytest
from copier import run_copy

from .factories import CopierAnswersFactory
from .models import LicenseName

EXPECTED_KEYS = {
    "distribution_name",
    "import_package_name",
    "description",
    "author_name",
    "author_email",
    "github_owner",
    "license",
    "publish_to_pypi",
}


def test_model_emits_copier_answer_keys() -> None:
    answers = CopierAnswersFactory()

    assert set(answers.to_copier_data()) == EXPECTED_KEYS
    assert answers.import_package_name == "example_project_0"


@pytest.mark.parametrize("license_name", list(LicenseName))
def test_model_license_values_are_accepted_by_template(
    template_root: Path,
    tmp_path: Path,
    license_name: LicenseName,
) -> None:
    answers = CopierAnswersFactory(license_name=license_name)

    run_copy(
        src_path=str(template_root),
        dst_path=tmp_path / answers.distribution_name,
        data=answers.to_copier_data(),
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )


def test_copier_defaults_without_model(template_root: Path, tmp_path: Path) -> None:
    destination = tmp_path / "default-project"

    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data={
            "author_name": "Raw Author",
            "author_email": "raw@example.test",
            "github_owner": "example",
        },
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )

    assert (destination / "src" / "my_package" / "__init__.py").is_file()
    assert 'name = "my-package"' in (destination / "pyproject.toml").read_text()
