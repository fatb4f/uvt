from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_packaging_standards_reference_named_probes() -> None:
    data = tomllib.loads((ROOT / "standards" / "packaging.toml").read_text())
    probes = {probe["id"] for probe in data["probe"]}
    assert probes
    for item in data["standard"]:
        if item["status"] != "deferred":
            for assertion in item["assertions"]:
                assert assertion.partition(".")[0] in probes


def test_conditional_standards_declare_conditions() -> None:
    data = tomllib.loads((ROOT / "standards" / "packaging.toml").read_text())
    for item in data["standard"]:
        if item["status"] == "conditional":
            assert item["condition"]
