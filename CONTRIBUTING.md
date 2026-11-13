# Contributing

Thanks for looking. Please read the [AI disclosure](README.md) first — it explains what this
project is for.

This page is what a pull request needs. [The maintainer guide](docs/maintainer/index.md) is
the rest: why each gate exists, every check CI runs, [how the suite is built](docs/maintainer/testing.md),
and [how a release is cut](docs/maintainer/releasing.md).

## Setup

Everything goes through [uv](https://docs.astral.sh/uv/), which manages the Python version too.
Install every dependency group, as CI does: the documentation build needs its own.

```bash
uv sync --all-groups
```

The floor is Python 3.12: CI runs the suite on 3.12, 3.13 and 3.14, and on Windows. `uv`
develops on the version `.python-version` names, the newest.

## Before opening a pull request

Run what CI runs:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check
uv run basedpyright
uv run pytest
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
uv run python scripts/site_versions.py check docs/_build/html
uv run python scripts/check_gallery.py
```

`pytest` takes about 25 minutes in full. While you work, run the files you touched
(`uv run pytest tests/test_cli.py --no-cov`), and the whole suite before you push.

`pytest` includes property-based tests, which check generated panels rather than
hand-written ones. If one fails, it prints the document that broke and fails the same way
on every run. [The testing guide](docs/maintainer/testing.md) explains how to replay it
and how to add a generator.

If you changed the playground or the editor extension, CI's TypeScript job also runs, in
`playground/` and in `editor/`:

```bash
npm ci
npm run typecheck
npm run test
npm run build
```

## When the output moves

Some committed files are generated, and a test fails while one is stale. After a change
that is meant to move what they hold, regenerate them and read the diff before committing
it. Each script takes `--check`, which exits 1 if anything it writes is stale.

| Regenerate | When you changed |
|---|---|
| `uv run python scripts/update_golden.py` | what the compiler writes for the gallery: SVG, Core, exports; what `scenet check` says and what the front ends read |
| `uv run python scripts/build_spec.py` | the language or the gallery: the spec pack, the agent skill, the Gallery page |
| `npm run schemas`, in `editor/` | a model of the language: the JSON Schemas the editor ships |
| `uv run python scripts/build_language_pages.py` | a key, its type or default: the language reference's key cards |
| `uv run python scripts/build_api_pages.py` | a public name or its docstring: the Python reference's pages |
| `uv run python scripts/build_diagnostics.py` | a rule or a compile note: the diagnostics reference |
| `uv run python scripts/mine_cli_since.py` | a command or a flag: the release each appeared in |
| `uv run python scripts/make_palette.py` | the tinted ladder: its colours and their print twins |

Then add a line to [`CHANGELOG.md`](CHANGELOG.md), under `[Unreleased]`, in the section of
its kind — Added, Changed, Fixed, Security — and in words a reader of the release notes
understands: the notes are the CHANGELOG, verbatim.

## House rules

[`CLAUDE.md`](CLAUDE.md) states them for an agent, and they bind people just the same.

- **Everything is typed.** `ruff`'s `ANN` rules are on, and `ty` and `basedpyright` both run as
  blocking gates. A bare `# type: ignore` is rejected (`PGH003`) — use a specific error code and
  say why.
- **No `from __future__ import annotations`.** Pydantic resolves annotations at runtime to
  build its validators, and the future import is on a deprecation path.
- **Quote self- and forward-references:** `-> "Point"` inside `class Point`. Python 3.14
  evaluates annotations lazily (PEP 649), but on the 3.12 floor an unquoted one raises
  `NameError` at import. `ruff` targets `py312` so that `UP037` does not strip the quotes, and
  the 3.12 CI job catches what slips through.
- **TypeScript, never plain JavaScript**, wherever JS is involved — including small glue scripts.
- **The compiler is deterministic.** The same input must always yield byte-identical output. No
  wall-clock time, no unseeded randomness, no dictionary-ordering dependence, no absolute paths in
  output.
- **Tests before implementation.** Each module's tests land first.
- **Every example works pasted into a fresh file.** A docstring example or a Python block in the
  docs imports every name it uses, a public one from `scenet` (`from scenet import Mass`, not
  `from scenet.ir import Mass`) and anything else from the module that defines it. It leans on no
  other block. Every `yaml` and `scenet-script` block in `docs/` and the README compiles as the
  document it shows, or carries a caption that says it is a part of one:
  ```` ```{code-block} yaml ```` with `:caption: Part of story.scene.yaml`. `pytest` fails on
  each; [the testing guide](docs/maintainer/testing.md#examples-a-reader-can-paste) has the
  details.
- **No personal information in committed files.** Package metadata is attributed to
  "Scenet contributors"; keep real names, emails and local machine paths out of the tree.
- **English** in the code, the documents, commits, issues and pull requests.

## Commits and pull requests

A pull request is squash-merged, so its title becomes the one commit on `main`. Write it as
a sentence saying what is now true, with the issue it closes in parentheses:
`Every diagnostic has an entry: why, how to fix it, and a document fixed (#320)`. GitHub adds
the pull request's number when it merges. Two kinds keep a prefix of their own: a release
is `chore: release 0.12.0`, and Dependabot titles its updates `deps: bump …`. The description says what changed and why, and
anything a reviewer should look at first.

Versioning follows [SemVer](https://semver.org/); the changelog follows
[Keep a Changelog](https://keepachangelog.com/).
