from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
TIMEOUT_SECONDS = 120


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", action="append", default=[])
    args = parser.parse_args()
    conditions: dict[str, bool] = {}
    for item in args.condition:
        name, separator, value = item.partition("=")
        if not separator or value not in {"true", "false"} or name in conditions:
            fail(f"invalid condition: {item}")
        conditions[name] = value == "true"

    manifest = tomllib.loads((ROOT / "standards" / "packaging.toml").read_text())
    probes = manifest.get("probe", [])
    probe_map = {probe.get("id"): probe for probe in probes}
    if len(probe_map) != len(probes) or None in probe_map:
        fail("duplicate or invalid probe identifier")
    required: list[tuple[str, str]] = []
    seen: set[str] = set()
    for standard in manifest.get("standard", []):
        standard_id = standard.get("id")
        if not isinstance(standard_id, str) or standard_id in seen:
            fail("duplicate or invalid standard identifier")
        seen.add(standard_id)
        status = standard.get("status")
        if status == "deferred":
            continue
        if status == "conditional":
            condition = standard.get("condition")
            if not isinstance(condition, str) or condition not in conditions:
                fail(f"missing or unknown condition for {standard_id}")
            if not conditions[condition]:
                continue
        elif status != "required":
            fail(f"invalid status for {standard_id}")
        assertions = standard.get("assertions")
        if not isinstance(assertions, list) or not all(
            isinstance(item, str) for item in assertions
        ):
            fail(f"invalid assertions for {standard_id}")
        required.extend((standard_id, assertion) for assertion in assertions)

    reports: dict[str, dict[str, object]] = {}
    for probe_id in sorted({assertion.partition(".")[0] for _, assertion in required}):
        probe = probe_map.get(probe_id)
        if not isinstance(probe, dict) or not isinstance(probe.get("argv"), list):
            fail(f"unknown probe: {probe_id}")
        result = subprocess.run(
            probe["argv"],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
        if result.returncode:
            fail(f"probe failed: {probe_id}\n{result.stderr}")
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            fail(f"probe did not emit JSON: {probe_id}: {error}")
        if report.get("probe") != probe_id or not isinstance(report.get("assertions"), dict):
            fail(f"invalid report from probe: {probe_id}")
        reports[probe_id] = report["assertions"]

    for standard_id, assertion in sorted(required):
        probe_id, separator, assertion_id = assertion.partition(".")
        if not separator or reports.get(probe_id, {}).get(assertion_id) is not True:
            fail(f"failed assertion: {standard_id}: {assertion}")
        print(f"PASS {standard_id}: {assertion}")


if __name__ == "__main__":
    main()
