## What this changes

<!-- What is now true, and why. Link the issue it closes: "Closes #N". -->

## Checklist

The commands are in [CONTRIBUTING.md](https://github.com/creatoan/scenet/blob/main/CONTRIBUTING.md#before-opening-a-pull-request).

- [ ] Tests were written before the implementation
- [ ] `uv run ruff format .` and `uv run ruff check .` pass
- [ ] `uv run ty check` and `uv run basedpyright` pass
- [ ] `uv run pytest` passes
- [ ] `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` passes
- [ ] Output remains deterministic (no clock, unseeded randomness, or absolute paths)
- [ ] Generated files regenerated, if the change moves what they hold, and their diff read:
  - `uv run python scripts/update_golden.py` (the golden files)
  - `uv run python scripts/build_spec.py` (the spec pack, the skill, the Gallery page)
  - `uv run python scripts/build_language_pages.py` (the language reference's key cards)
  - `uv run python scripts/build_api_pages.py` (the Python reference's pages)
  - `uv run python scripts/build_diagnostics.py` (the diagnostics reference)
  - `uv run python scripts/mine_cli_since.py` (the release each command and flag came in)
  - `uv run python scripts/make_palette.py` (the tinted ladder)
  - `npm run schemas`, in `editor/` (the JSON Schemas)
- [ ] Docs updated if the language, the Python API, the CLI or the Panel Core format changed
- [ ] A line in `CHANGELOG.md`, under `[Unreleased]`, in the section of its kind
