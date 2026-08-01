from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_standards_manifest_has_normalized_probes() -> None:
    data = tomllib.loads((ROOT / "standards" / "packaging.toml").read_text())
    standards = data["standard"]
    probes = {probe["id"]: probe for probe in data["probe"]}
    assert len(probes) == len(data["probe"])
    assert {item["status"] for item in standards} <= {"required", "conditional", "deferred"}

    for item in standards:
        if item["status"] == "deferred":
            continue
        if item["status"] == "conditional":
            assert item.get("condition")
        assert item.get("assertions")
        for assertion in item["assertions"]:
            assert assertion.partition(".")[0] in probes

    for probe in probes.values():
        assert probe["argv"]
        assert all(isinstance(argument, str) for argument in probe["argv"])
