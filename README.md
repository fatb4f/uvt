# uvt

`uvt` is a Copier template for a small, typed Python package using uv, just,
Ruff, ty, pytest, and GitHub Actions.

Generate a project with Copier, review the generated answers and lockfile, then
commit both. The generated README documents its repository command contract.

The template deliberately treats `lazyjust` and Neovim as workstation tools:
they are never Python dependencies and are not required in CI.

## Template development

```sh
uv sync --locked --group dev
just qualify
```

## Provenance

See `docs/provenance.md` and the generated `standards/packaging.toml` for the
standards contract and its executable evidence.
