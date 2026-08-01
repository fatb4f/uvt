from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import yaml
from copier import run_copy

from .factories import CopierAnswersFactory


def write_valid_wheel(path: Path) -> None:
    dist_info = "example_project-0.1.0.dist-info"
    contents = {
        "example_project/__init__.py": b'"""Example."""\n',
        "example_project/py.typed": b"",
        f"{dist_info}/METADATA": (
            b"Metadata-Version: 2.4\nName: example-project\nVersion: 0.1.0\n"
        ),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record_path = f"{dist_info}/RECORD"
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for member, content in contents.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow((member, f"sha256={digest}", len(content)))
    writer.writerow((record_path, "", ""))
    contents[record_path] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in contents.items():
            archive.writestr(member, content)


def test_release_workflow_permissions_and_order(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory(publishing=True).to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )

    workflow_path = destination / ".github" / "workflows" / "publish.yml"
    workflow = workflow_path.read_text()
    parsed = yaml.safe_load(workflow_path.read_text())
    publish_action = "pypa/gh-action-pypi-publish@106e0b0b7c337fa67ed433972f777c6357f78598"
    upload_action = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    download_action = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
    build = parsed["jobs"]["build"]
    publish = parsed["jobs"]["publish"]
    assert build["permissions"] == {"contents": "read"}
    assert publish["permissions"] == {"id-token": "write"}
    assert "environment" not in build
    assert publish["environment"] == "pypi"
    assert publish["needs"] == "build"
    assert build["steps"][-1]["uses"] == upload_action
    assert build["steps"][-1]["with"] == {
        "name": "dist",
        "path": "dist/",
        "if-no-files-found": "error",
        "retention-days": 1,
    }
    assert publish["steps"][0]["uses"] == download_action
    assert publish["steps"][0]["with"] == {"name": "dist", "path": "dist/"}
    assert publish["steps"][-1]["uses"] == publish_action
    assert all("run" not in step for step in publish["steps"])
    assert all("actions/checkout" not in step.get("uses", "") for step in publish["steps"])
    assert workflow.index("just qualify") < workflow.index(upload_action)
    assert workflow.index(download_action) < workflow.index(publish_action)
    assert 'test "$GITHUB_REF_NAME" = "v$version"' in workflow

    checker = subprocess.run(
        [sys.executable, "scripts/release_workflow_check.py"],
        cwd=destination,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(checker.stdout)["assertions"]["publish.trusted"] is True

    workflow_path.write_text(
        workflow.replace(
            "    steps:\n      - uses: actions/download-artifact@",
            "    steps:\n      - run: echo project-controlled\n"
            "      - uses: actions/download-artifact@",
        )
    )
    mutated_checker = subprocess.run(
        [sys.executable, "scripts/release_workflow_check.py"],
        cwd=destination,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(mutated_checker.stdout)["assertions"]["publish.trusted"] is False


def test_wheel_metadata_drives_release_version(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory(publishing=True).to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )
    dist = destination / "dist"
    dist.mkdir()
    wheel = dist / "example_project-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "example_project-0.2.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: example-project\nVersion: 0.2.0\n",
        )

    result = subprocess.run(
        [sys.executable, "scripts/artifact-version.py", "dist"],
        cwd=destination,
        check=True,
        text=True,
        capture_output=True,
    )

    version = result.stdout.strip()
    assert f"v{version}" == "v0.2.0"
    assert "v0.2.1" != f"v{version}"


def test_artifact_qualification_failure_blocks_release(template_root: Path, tmp_path: Path) -> None:
    answers = CopierAnswersFactory(publishing=True).to_copier_data()
    destination = tmp_path / answers["distribution_name"]
    run_copy(
        src_path=str(template_root),
        dst_path=destination,
        data=answers,
        defaults=True,
        quiet=True,
        skip_tasks=True,
    )
    (destination / "dist").mkdir()

    result = subprocess.run(
        [sys.executable, "scripts/package_check.py", "dist", answers["import_package_name"]],
        cwd=destination,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "exactly one wheel and one sdist" in result.stderr


def test_artifact_checker_rejects_missing_record(template_root: Path, tmp_path: Path) -> None:
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
    dist = destination / "dist"
    dist.mkdir()
    wheel = dist / "example_project-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "example_project-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: example-project\nVersion: 0.1.0\n",
        )
        archive.writestr(
            "example_project-0.1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
    with tarfile.open(dist / "example_project-0.1.0.tar.gz", "w:gz"):
        pass

    result = subprocess.run(
        [sys.executable, "scripts/package_check.py", "dist", answers["import_package_name"]],
        cwd=destination,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "METADATA, WHEEL, and RECORD" in result.stderr


def test_artifact_checker_rejects_wrong_sdist_name(template_root: Path, tmp_path: Path) -> None:
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
    dist = destination / "dist"
    dist.mkdir()
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl")
    with tarfile.open(dist / "wrong_name-0.1.0.tar.gz", "w:gz"):
        pass

    result = subprocess.run(
        [sys.executable, "scripts/package_check.py", "dist", answers["import_package_name"]],
        cwd=destination,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "does not match the wheel" in result.stderr
