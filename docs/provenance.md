# Packaging provenance

`uvt` borrows template lifecycle and update-convergence ideas from
`jlevy/simple-modern-uv`, generated-project engineering patterns from
`johnthagen/python-blueprint`, and optional-feature comparisons from
`osprey-oss/cookiecutter-uv`. It does not copy their implementation.

Generated projects use Copier, uv/uv_build, just, Ruff, ty, and pytest, plus
optional lazyjust/LazyVim integration. Their standards contract is executable:
`standards/packaging.toml` names each applicable PEP, its assertion IDs, and
the executable probes that report them.

`copier.yml` is the authoritative questionnaire. The test suite's Pydantic
`CopierAnswers` model and Factory Boy factory are convenience layers for valid,
unique test inputs; raw mappings and Hypothesis continue to test Copier's own
validation boundary.

The generated `.lazy.lua` was authored and last verified against LazyVim
`c10948c50b18fae7f256433afdef09e432410480`, lazy.nvim
`85c7ff3711b730b4030d03144f6db6375044ae82`, and Snacks.nvim
`882c996cf28183f4d63640de0b4c02ec886d01f2`.
