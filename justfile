default:
    @just --list

sync:
    uv sync --locked --group dev

test *args:
    uv run --frozen pytest -m "not online" {{args}}

test-online *args:
    uv run --frozen pytest -m online {{args}}

lint:
    uv run --frozen ruff check .

format-check:
    uv run --frozen ruff format --check .

standards-check:
    uv run --locked python scripts/standards_check.py --condition publish_to_pypi=true

check: lint format-check test

qualify: check standards-check
