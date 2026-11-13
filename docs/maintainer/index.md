---
orphan: true
---

# Maintainer guide

For anyone with commit rights, and for the future version of yourself who has forgotten
how any of this works. What a pull request needs — the setup, the commands, what to
regenerate and the house rules — is in
[the contributor's guide](https://github.com/creatoan/scenet/blob/main/CONTRIBUTING.md);
this guide says why, and what happens after.

| | |
|---|---|
| [Releasing](releasing.md) | How to cut a release, and what happens when you do |
| [Credentials](secrets.md) | Which secrets exist (almost none), and why |
| [Dependencies](dependencies.md) | Who looks at Dependabot alerts, how often, and what to do when Dependabot cannot fix one |
| [Testing](testing.md) | The suite's layers: golden outputs, the reference as a contract, examples a reader can paste, properties, mutation testing |

## The gates

Everything below runs in CI on every push and pull request. Run them locally first.

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run basedpyright
uv run pytest
uv run python scripts/check_gallery.py
```

`basedpyright` is the second type checker, and it blocks as `ty` does: the
[design decisions](../explanation/design_decisions.md#ty-and-basedpyright-both-gate-the-build)
say why both. `check_gallery.py` is `scenet check` over the gallery, less the notes its
examples give on purpose.

`pytest` runs more than the unit tests. It also executes every example in every docstring
and every fenced Python block in the Markdown documentation, so a documented example that
has drifted fails the build. That is deliberate: the commonest complaint about Python
library documentation is examples that do not run, and the only durable fix is to run
them.

Coverage is gated at 90%, branches included. `pytest` measures it on every run, locally
as in CI's Python 3.14 job. The 3.12, 3.13 and Windows jobs pass `--no-cov`: before 3.14,
coverage cannot use `sys.monitoring` for branches, and its tracer doubled the time of the
required 3.12 check. They run everything else.

The documentation build is a separate gate:

```bash
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
uv run python scripts/site_versions.py check docs/_build/html
```

`-W` turns warnings into errors, so a broken cross-reference or a page missing from a
table of contents fails rather than quietly producing a worse site. `site_versions.py`
then checks that every page says which version it documents, where the version
switcher's data is, and its canonical address at the root.

## The checks a pull request runs

| Check | Required | What it runs |
|---|---|---|
| `Lint, types and tests (Python 3.12)` | Yes | The suite on the floor, without coverage |
| `Lint, types and tests (Python 3.13)` | No | The suite, without coverage |
| `Lint, types and tests (Python 3.14)` | Yes | Format, lint, `ty`, and the suite with its coverage gate |
| `Tests on Windows` | No | The suite, where writing text can change line endings |
| `Mutation clean run` | Yes | mutmut up to its forced-fail test: the suite in the mutants tree, every leg's files mutated |
| `Documentation` | Yes | The Sphinx build with `-W`, and `site_versions.py check` |
| `Dependency licenses` | Yes | The runtime dependencies against `.github/allowed-licenses.txt` |
| `Strict type check` | Yes | `basedpyright` |
| `Gallery diagnostics` | No | `check_gallery.py`, uploaded to code scanning |
| `Package` | No | The sdist and wheel, `twine check --strict`, the wheel smoke test |
| `TypeScript` | Yes | The playground and the editor extension: typecheck, tests, build, `vsce package` |
| `Editor end to end` | Yes | The extension in a real VS Code |
| `Analyze (python)` | No | CodeQL, on the Python |
| `Analyze (javascript-typescript)` | No | CodeQL, on the TypeScript |
| `Analyze (actions)` | No | CodeQL, on the workflows |
| `Dependency review` | Yes | A new dependency with a known high or critical vulnerability |

The first twelve rows are `ci.yml`, the next three `codeql.yml`, and the last
`dependency-review.yml`. A test holds this table to the workflows, so a new job fails it
until it has a row. Which checks are required is the ruleset's, on GitHub, which no test
can read. A check marked *No* still runs on every pull request, and a red one is fixed
before merging all the same.

## How a change reaches main

`main` is protected by a repository ruleset. **Direct pushes are rejected** — including
by the maintainer, deliberately, because a rule with an exception for the person most
likely to be in a hurry is not a rule.

```bash
git switch -c fix/whatever
# ... work ...
git push -u origin fix/whatever
gh pr create --fill
gh pr checks --watch      # the required ones must pass
gh pr merge --squash --delete-branch
```

The ruleset requires:

| Rule | Why |
|---|---|
| Pull request required | Nothing reaches `main` without a diff somebody could have read |
| Eight status checks green | The checks marked *Required* above |
| Branch up to date before merge | A green check against a stale base proves nothing |
| Linear history | `main` stays bisectable; a regression can be found by halving |
| No force push, no deletion | History is evidence |

**Approvals are set to zero, on purpose.** GitHub does not let you approve your own pull
request, so on a single-maintainer repository requiring even one approval would make
`main` permanently unmergeable. The status checks are the gate; the pull request is the
record. Add a review requirement the day a second person has commit rights.

Tags matching `v*` are protected too: they cannot be deleted, moved or force-pushed. A
released version number is a promise, and PyPI enforces the same thing from the other
side — a version can never be re-uploaded.

## Non-negotiables

These are enforced by tests, not by good intentions:

- **Determinism.** Identical input produces byte-identical output, as
  [the language promises](../reference/language/index.md#determinism): no clock, no
  randomness that is not seeded, no order that depends on a set or a dict, no absolute path
  in the output. Golden-file tests are meaningless without it.
- **The solver never sees artwork.** It sees a geometric contract only — bounding boxes,
  named anchors, exclusion polygons, gaze vectors. Rendering stays swappable.
- **Everything is typed.** `ty` is a blocking gate. A bare `# type: ignore` is rejected;
  use a specific code and give a reason.
- **Everything public is documented.** `ruff`'s pydocstyle rules are blocking, and a test
  asserts that every name in `scenet.__all__` has a docstring.
- **TypeScript, never plain JavaScript**, wherever JS appears — including build scripts.
- **No personal information in committed files.** Attribution is to "Scenet contributors".
  Commit metadata is a separate matter and carries whatever the author's git config says.

## Python version floor

The floor is **3.12**, and CI runs the suite on 3.12, 3.13 and 3.14 -- every version
`pyproject.toml` lists as supported, which a test holds it to. The floor is not
decoration. Before Python 3.14 and PEP 649, annotations are evaluated at definition time,
so a self-referential `-> Point` inside `class Point` raises `NameError` at import.
Developing only on 3.14 hides that completely — it first surfaced in the browser, where
Pyodide ran an older Python, and cost an afternoon.

Self- and forward-references are therefore quoted (`-> "Point"`), and `ruff` targets
`py312` so that `UP037` does not helpfully strip the quotes back off.

Do not reach for `Self` to dodge the quoting unless the body really does use `cls(...)`.
Otherwise it promises subclass-preserving behaviour the code does not deliver, and `ty`
will say so.

```{toctree}
:hidden:
:maxdepth: 1

releasing
secrets
dependencies
testing
```
