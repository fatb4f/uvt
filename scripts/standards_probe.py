from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe")
    parser.add_argument("assertion")
    parser.add_argument("test")
    args = parser.parse_args()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", args.test],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr, end="")
    print(
        json.dumps(
            {"probe": args.probe, "assertions": {args.assertion: result.returncode == 0}},
            sort_keys=True,
        )
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
