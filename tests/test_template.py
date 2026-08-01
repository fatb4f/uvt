from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_template_has_expected_contract() -> None:
    copier = (ROOT / "copier.yml").read_text()
    assert "distribution_name:" in copier
    assert "import_package_name:" in copier
    assert "publish_to_pypi:" in copier

    justfile = (ROOT / "template" / "justfile.jinja").read_text()
    assert "test-clean-locked" in justfile
    assert "--isolated --locked --no-default-groups --group test" in justfile
    assert "standards-check" in justfile
    assert "nox" not in justfile
    assert "[private]" in justfile
    assert "lazyjust" in justfile


def test_standards_manifest_is_rendered() -> None:
    manifest = ROOT / "template" / "standards" / "packaging.toml.jinja"
    assert manifest.is_file()
    content = manifest.read_text()
    assert 'id = "PEP-621"' in content
    assert 'id = "PEP-740"' in content
    assert "[[probe]]" in content


def test_github_actions_are_pinned_to_full_commits() -> None:
    workflows = [ROOT / ".github" / "workflows" / "qualify.yml"]
    workflows.extend((ROOT / "template" / ".github" / "workflows").glob("*.yml.jinja"))

    for workflow in workflows:
        for line in workflow.read_text().splitlines():
            if "uses:" in line:
                assert re.search(r"@[0-9a-f]{40}(?:\s|$)", line), f"{workflow}: {line}"
