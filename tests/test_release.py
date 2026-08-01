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


def write_valid_wheel(
    path: Path,
    *,
    import_name: str = "example_project",
    typed_name: str | None = None,
    include_init: bool = True,
    metadata_version: str = "2.4",
) -> None:
    dist_info = "example_project-0.1.0.dist-info"
    contents: dict[str, bytes] = {
        f"{dist_info}/METADATA": (
            f"Metadata-Version: {metadata_version}\nName: example-project\nVersion: 0.1.0\n".encode()
        ),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    if include_init:
        contents[f"{import_name}/__init__.py"] = b'"""Example."""\n'
    contents[f"{typed_name or import_name}/py.typed"] = b""
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


def write_valid_sdist(
    path: Path,
    *,
    root: str | None = None,
    metadata_version: str = "2.4",
    include_pyproject: bool = True,
    build_requires: str = '"packaging>=25"',
) -> None:
    root = root or path.name.removesuffix(".tar.gz")
    contents = {
        f"{root}/PKG-INFO": (
            f"Metadata-Version: {metadata_version}\nName: example-project\nVersion: 0.1.0\n".encode()
        ),
    }
    if include_pyproject:
        contents[f"{root}/pyproject.toml"] = (
            f'[build-system]\nrequires = [{build_requires}]\nbuild-backend = "example.build"\n'.encode()
        )
    with tarfile.open(path, "w:gz") as archive:
        for member, content in contents.items():
            info = tarfile.TarInfo(member)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def check_package(destination: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/package_check.py", *args],
        cwd=destination,
        check=False,
        text=True,
        capture_output=True,
    )


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

    mutations = (
        workflow.replace("permissions: {}", "permissions: write-all", 1),
        workflow.replace(
            "  publish:\n",
            "  sidecar:\n"
            "    runs-on: ubuntu-latest\n"
            "    permissions:\n"
            "      id-token: write\n"
            "    steps:\n"
            "      - run: echo privileged\n\n"
            "  publish:\n",
            1,
        ),
        workflow.replace(
            "    steps:\n      - uses: actions/download-artifact@",
            "    steps:\n"
            "      - uses: actions/cache@a8c9b5f3b1b1eb85c3c0c8cb2fa6cce50bd48d2b\n"
            "      - uses: actions/download-artifact@",
            1,
        ),
    )
    for mutation in mutations:
        workflow_path.write_text(mutation)
        mutated_checker = subprocess.run(
            [sys.executable, "scripts/release_workflow_check.py"],
            cwd=destination,
            check=True,
            text=True,
            capture_output=True,
        )
        assert json.loads(mutated_checker.stdout)["assertions"]["publish.trusted"] is False

    workflow_path.write_text(
        workflow.replace(
            "  publish:\n",
            "  sidecar:\n    uses: ./.github/workflows/publish.yml\n\n  publish:\n",
            1,
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
    write_valid_wheel(
        dist / "example_project-0.1.0-py3-none-any.whl",
        import_name=answers["import_package_name"],
    )
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


def test_artifact_checker_binds_typed_marker_to_import_package(
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
    dist = destination / "dist"
    dist.mkdir()
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl", typed_name="other")
    write_valid_sdist(dist / "example_project-0.1.0.tar.gz")

    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "example_project/py.typed" in result.stderr


def test_artifact_checker_requires_import_package_init(template_root: Path, tmp_path: Path) -> None:
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
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl", include_init=False)
    write_valid_sdist(dist / "example_project-0.1.0.tar.gz")

    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "example_project/__init__.py" in result.stderr


def test_artifact_checker_rejects_stdlib_import_resolution(
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
    dist = destination / "dist"
    dist.mkdir()
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl", import_name="json")
    write_valid_sdist(dist / "example_project-0.1.0.tar.gz")

    result = check_package(destination, "--online", "dist", "json")

    assert result.returncode != 0
    assert "candidate environment site-packages" in result.stderr


def test_artifact_checker_rejects_invalid_core_metadata(
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
    dist = destination / "dist"
    dist.mkdir()
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl", metadata_version="banana")
    write_valid_sdist(dist / "example_project-0.1.0.tar.gz", metadata_version="banana")

    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "wheel METADATA is not valid core metadata" in result.stderr

    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl")
    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "sdist PKG-INFO is not valid core metadata" in result.stderr


def test_artifact_checker_requires_rooted_sdist_with_build_system(
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
    dist = destination / "dist"
    dist.mkdir()
    write_valid_wheel(dist / "example_project-0.1.0-py3-none-any.whl")
    write_valid_sdist(dist / "example_project-0.1.0.tar.gz", root="wrong-root")

    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "rooted at the sdist filename" in result.stderr

    write_valid_sdist(dist / "example_project-0.1.0.tar.gz", include_pyproject=False)
    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "pyproject.toml" in result.stderr

    write_valid_sdist(dist / "example_project-0.1.0.tar.gz", build_requires='"not a requirement"')
    result = check_package(destination, "dist", "example_project")

    assert result.returncode != 0
    assert "invalid requirement" in result.stderr
