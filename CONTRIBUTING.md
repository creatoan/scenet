# Contributing

Thanks for looking. Please read the [AI disclosure](README.md) first — it explains what this
project is for.

## Setup

Everything goes through [uv](https://docs.astral.sh/uv/), which manages the Python version too:

```bash
uv sync
uv run pytest
```

## Before opening a pull request

Run what CI runs:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check
uv run pytest
```

`pytest` includes property-based tests, which check generated panels rather than
hand-written ones. If one fails, it prints the document that broke and fails the same way
on every run. [The testing guide](docs/maintainer/testing.md) explains how to replay it
and how to add a generator.

## House rules

- **Everything is typed.** `ruff`'s `ANN` rules are on and `ty` runs as a blocking gate. A bare
  `# type: ignore` is rejected (`PGH003`) — use a specific error code and say why.
- **No `from __future__ import annotations`.** Python 3.14 evaluates annotations lazily by default
  (PEP 649/749), so forward references work unquoted and the future import is on a deprecation path.
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

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), e.g. `feat(solver): add rule-of-thirds
anchoring`. Versioning follows [SemVer](https://semver.org/); the changelog follows
[Keep a Changelog](https://keepachangelog.com/).
