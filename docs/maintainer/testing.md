# Testing

The suite has three layers, and each catches what the one before cannot.

| Layer | Where | What it checks |
|---|---|---|
| Examples | `tests/test_*.py`, docstrings, the Markdown docs | One input, one expected answer |
| Properties | `tests/properties/` | A rule, against every input a generator can draw |
| Invariants | `tests/invariants.py` | What a correct panel is, shared by both layers above |

Coverage says which lines ran, not whether anything checked what they did. The bugs
that prompted these tests were in code the suite already ran, at 95% coverage; nobody had
written the input that broke it. The properties exist for that gap: the checks that used to run on five hand-written panels now
run on every panel `tests/strategies.py` can draw.

Coverage, branches included, is measured by `uv run pytest` and must reach 90%. In CI only
the Linux Python 3.14 job measures it; the 3.12, 3.13 and Windows jobs run the same tests
with `--no-cov`. Before 3.14, coverage cannot use `sys.monitoring` for branches and falls
back to a tracer, which made the 3.12 job, a required check, the slowest of every pull
request. Pass `--no-cov` locally too when the number is not what you are after.

## The properties

`tests/properties/test_panel_properties.py` compiles generated single-panel documents and
checks four kinds of property, the kinds that have found real bugs in numerical code
(*Falsify your Software*, SciPy 2020):

- **Determinism.** Compiling twice gives byte-identical Core JSON and SVG, with and
  without live text, and the debug overlay.
- **Invariants.** A compiled panel satisfies everything in `tests/invariants.py`:
  - balloons and captions stay inside the margin, off every face, out from under any
    exclusion, and clear of each other;
  - each one reads after **every** box before it, not only the last;
  - every tail runs from its balloon to its speaker;
  - the SVG parses, its ids are unique and every reference resolves, no number in it is
    `nan` or `inf`, its `viewBox` is the panel's size, and every glyph is drawn at the
    scale it was measured at.
- **Round trip.** Panel Core reads back equal, and writes back the same bytes.
- **Oracle.** `scenet check --deep` is clean exactly when the panel compiles, and
  otherwise reports one finding whose rule names how it failed. A compile may fail only
  with `BalloonPlacementError` or `LayoutError`; anything else escaping is a bug.

`tests/properties/test_page_properties.py` does the same for books:

- **Reading order.** Frames come out tier by tier, left to right, down each column, each
  inset before or after its parent as `read` says. The expected order is worked out from
  the authored pages by `tests.strategies.scenes`, never by asking the solver.
- **Frames.** Every frame stays inside the page margins, and no two overlap, compared as
  the shapes they are drawn as, so a slanted tier's shared cuts count. The exception is an
  inset, which lies wholly inside its parent. Each panel is compiled at its frame's size.
- **Round trip and determinism.** Page Core reads back equal and writes back the same
  bytes, and compiling twice gives the same pages.
- **SVG.** Pages, a book of pages and a strip all pass the SVG checks, ids included:
  unique across every page, not only within one.
- **Comic scripts lose nothing.** As many panels as were written, each holding as many
  balloons and captions as it had lines, whether panel numbers run on or start again on
  each page.

`tests/properties/test_broken_documents.py` holds `scenet check` to its purpose:

- **One mistake, one finding.** A valid generated document with exactly one mistake from
  the catalogue in `tests.strategies.MISTAKES` -- a misspelled key, a missing field, a
  wrong type, `.nan`, an unknown actor, a cycle, a duplicate key and the rest -- gives
  exactly one finding, under the right rule, at the right path, on a line that holds the
  mistake, in a SARIF document that serialises. Every entry runs against its own examples.
  Scenes add a page naming a missing panel, a panel placed twice, two stacks side by side
  and a missing `over:` parent; scripts add a repeated PANEL heading.
- **Two mistakes, two findings.** Independent mistakes in fields are reported
  independently.
- **Never a traceback.** Arbitrary documents, arbitrary text and arbitrary scripts get
  findings, never an exception and never the `internal` rule, and `scenet check` exits 0
  or 1.

A cross-reference check, such as an unknown actor, runs only once every field is valid,
so a document with a broken field and an unknown actor reports the field first. That is
by design: the reference cannot be checked against a cast that did not validate.

## Golden outputs

`tests/test_golden.py` checks the promise in the reference that two machines produce files
`cmp` calls equal, which compiling twice in one process cannot see. It builds the whole
gallery through `scenet build`, in every CI job -- Linux on 3.12, 3.13 and 3.14, and Windows -- and
compares the bytes on disk with what is committed:

- `tests/golden/core/` holds every Panel Core and Page Core, so a layout change is reviewed
  coordinate by coordinate in the diff;
- `tests/golden/digests.json` holds the SHA-256 of every SVG: panels, overlays, live text,
  strips and pages; and of every print PDF;
- `docs/images/gallery/` holds what the documentation shows of each gallery example: its pages,
  or else its strip, or else its one panel, written whole. An example lettered over a picture
  of its own is built once more with `--embed-images` for it, since an SVG shown as an image
  loads nothing from outside itself. `tests/test_docs_gallery.py` holds each picture to its
  digest;
- `tests/golden/findings.json` holds every finding `scenet check` gives, with and without
  `--deep`, on every gallery example, every document of `tests/rule_corpus/` and its fixed
  twins, and every document of `tests/finding_corpus/`: its rule, level, message, path, file,
  region and fingerprint. The rule corpus says which rule a document breaks; this says
  everything else, and the gallery is there for what it does not say -- a check that lost the
  document's folder or its puppets would find fault with it;
- `tests/golden/parsed.json` holds the SHA-256 of what the front ends read from each of the
  same documents -- every panel's IR, a script's lines, notes and page layout -- or of how they
  refused it: what is read on the way to a Core, which a Core does not show.

`tests/finding_corpus/` is one document for each way of reaching a finding or a refusal that
neither the gallery nor the rule corpus takes: a fault inherited over a panel, a default no
panel overrides, a script's every refusal. Mutation testing is what found each of them
missing ([#345](https://github.com/creatoan/scenet/issues/345)); a new way of refusing a
document adds one.

It also builds the gallery in two processes with different `PYTHONHASHSEED`s, and one scene
and one script from a relative path, an absolute one and another directory; each must
write the same bytes, and none may hold the path it was built from.

After a change that is meant to move the output, regenerate the goldens and read the diff:

```bash
uv run python scripts/update_golden.py
```

`--check` exits 1 and names every stale golden without writing anything.

## The print plates

`tests/test_print_separations.py` renders the print PDF ([#80](https://github.com/creatoan/scenet/issues/80)) to its plates with
Ghostscript's `tiffsep` device, one per ink, and checks the black-plate rule in ink: lettering
on K alone, an overprinting line leaving the colour under it, the paper and reversed captions
knocking out, the night foreground rich black. `qpdf --check` reads every gallery PDF. Both
are external tools, installed in CI's Python 3.14 job, where `SCENET_REQUIRE_PRINT_TOOLS` makes
a missing one fail; elsewhere the tests skip without them. To run them locally, install
Ghostscript (`gs`, or `gswin64c` on Windows) and qpdf, then:

```sh
SCENET_PLATES_DIR=print-plates uv run pytest tests/test_print_separations.py
```

`SCENET_PLATES_DIR` keeps the plates, which CI also uploads as the `print-plates` artifact.
They are looked at, never kept as goldens: the determinism contract is on the PDF's bytes.

## The reference as a contract

`docs/reference/cli.md` is the specification, so `tests/test_reference_contract.py`
holds the code to it, failing in both directions -- documented and missing, or present and
undocumented:

- each command's options, their choices and the values marked as defaults, against
  `scenet.cli.build_parser()`;
- each command's exit-status table, against a scenario that produces every code in it;
- each command's and each option's release, against `docs/reference/cli.since.toml`, which
  `scripts/mine_cli_since.py` mines from the tags, and each option against a `bash` example
  in its command's section that uses it;
- the extension table, against the frontends `build` reads with;
- every rule except `internal`, against a document in `tests/rule_corpus/` named after it
  that must produce exactly one finding of that rule, read beside `examples/gallery` as the
  playground reads a document, and the rule objects SARIF emits against the catalogue;
- the behavioural sentences -- output naming, clashes, `--quiet`, what `check` writes,
  SARIF on stdout -- one test each.

`docs/reference/diagnostics.md` is generated from the catalogue and the same corpus by
`scripts/build_diagnostics.py`, and `tests/test_diagnostics_reference.py` holds it to them:
an entry for every rule and every compile note, each document giving exactly its diagnostic,
each fixed twin in `tests/rule_corpus/fixed/` giving nothing, and the cards and the entries
linking each other.

The `scenet` lines of every `bash` block in the documentation run as well, in-process in a
copy of `examples/` (`tests/shell_examples.py`). `pip`, `uv`, `git` and the like never run.
A block that needs a file the reader creates along the way is marked `<!--- skip: next -->`.

A new rule needs a corpus document; a new option needs a definition in the reference. The
tests say which.

## Examples a reader can paste

A reader copies an example into a fresh file and runs it, and it must work. The suite runs
every example that way ([#317](https://github.com/creatoan/scenet/issues/317)), and fails on each way it could not:

- **A missing import.** `--doctest-modules` runs a docstring's examples in a copy of its
  module's globals, where an example could call the function it documents without importing
  it. A hook in the root `conftest.py` empties them first: each docstring runs with builtins
  only, as a pasted script does.
- **A block that leans on an earlier one.** Sybil runs every example of a page in one
  namespace. The root `conftest.py` gives each Python block a namespace of its own; the
  `>>>` lines of one block still share it, as the lines of one session do.
- **A public name imported from a submodule.** `from scenet.ir import Mass` works, and teaches
  an import path the API does not promise. A name in `scenet.__all__` is imported from
  `scenet`; any other class or function from the module that defines it, not one that only
  imports it.
- **A document that does not compile.** Every `yaml` and `scenet-script` block in `docs/` and
  `README.md` is compiled as the kind of document it shows: a scene when it holds `panels:` or
  `pages:`, a script when it is a `scenet-script` block, and a panel otherwise. A comic script
  in a `text` or untagged block fails, since it would never be compiled.

A block that is only a part of a document says so where the reader sees it, in a caption:

````markdown
```{code-block} yaml
:caption: Part of story.scene.yaml

pages:
  - tiers: [{panels: [arrival, door]}]
```
````

A caption of `Part of <document>` is not compiled, on purpose; a YAML part is still read as
YAML. A caption that is a file name says what the block is when its contents cannot: a
`*.puppet.yaml` is loaded as a puppet, a `*.art.yaml` as an artwork contract, and a file
Scenet does not read, such as `.github/workflows/comic.yml`, is only read as YAML. Any other
caption is an error. The README holds no caption, since GitHub and PyPI render no MyST: every
block of it is complete. A block that is an example file word for word, as each one on the
gallery page is, is compiled by `tests/test_gallery.py` beside the files it names.

`tests/doc_examples.py` holds the mechanisms and `tests/test_doc_examples.py` the tests,
including one per mistake above, on an example written to make it.

## Profiles

A property failure has to replay identically, so **the default is derandomized
everywhere**, on a laptop as in CI. The profiles are in `tests/conftest.py`, chosen with
`HYPOTHESIS_PROFILE`:

| Profile | Examples | Seeds | Use |
|---|---|---|---|
| `fixed` (default) | 20 | fixed | every run, locally and in CI |
| `ci` | 20 | fixed | the same as `fixed`; replaces Hypothesis's own `ci` profile, which runs 100 |
| `explore` | 300 | random, remembered in `.hypothesis/` | hunting for new failures |

```bash
uv run pytest tests/properties --hypothesis-show-statistics
HYPOTHESIS_PROFILE=explore uv run pytest tests/properties --no-cov
```

`--hypothesis-show-statistics` prints, for each property, how many examples compiled, how
many failed for lack of room, and how many balloons and captions they held. A generator
whose examples mostly fail, or mostly hold no lettering, tests far less than its example
count suggests, so check those numbers after changing a strategy.

## When a property fails

Hypothesis shrinks the failure to the smallest document it can and prints it, along with
a `@reproduce_failure` line. Under `fixed` the same example comes back on every run, so
re-running the test is enough to replay it.

A failure found under `explore` is different: its seed was random. Pin the document it
printed as an `@example(...)` on the property, so the fixed run covers it from then on,
and then fix the bug in its own pull request with its own failing test.

## Adding a strategy

Strategies live in `tests/strategies.py` and return a `Drawn`, which keeps the authored
document as a dict. Tests derive their expectations from what was authored, such as the
margin, never from what the compiler made of it.

- **Draw the vocabulary from the code.** Enums, puppet poses and expressions, places and
  font coverage are all read from the package, so a new shot type is generated the day it
  lands. Never copy a list of values into a strategy.
- **Build valid documents by construction** rather than drawing and filtering. Pydantic v2
  has no Hypothesis plugin, and the model validators would reject most of what
  `st.builds(PanelIR)` drew.
- **Keep the failure rate low.** A panel that is valid but has no room for its lettering
  tests only the failure path. `panels()` holds the tightest shots to one line or none for
  that reason.

## How sensitive the properties are

A property that cannot fail is worth nothing, so each was checked against a deliberate
break in the code it guards. Each break below made a property fail, and the failure
replayed on the next run:

- the solver's reading-order rule disabled, which a caption placed before a balloon
  caught;
- the glyph scale written to two places again, the bug fixed in [#99](https://github.com/creatoan/scenet/issues/99), which the SVG check
  caught at the first panel with lettering.

## What the properties found

Each was fixed in its own pull request, with a failing test first, before the property
that trips on it landed:

| Found | Fixed in |
|---|---|
| A control character in a panel wrote an SVG no XML parser accepts | [#101](https://github.com/creatoan/scenet/issues/101) |
| A document nested a few hundred levels deep ended in `RecursionError` | [#103](https://github.com/creatoan/scenet/issues/103) |
| An inset in a narrow panel was drawn outside it | [#104](https://github.com/creatoan/scenet/issues/104) |
| `a left_of a` was filed under `invalid-field`, not `reflexive-relation` | [#105](https://github.com/creatoan/scenet/issues/105) |
| A misspelled required key was reported twice | [#106](https://github.com/creatoan/scenet/issues/106) |
| A broken `over:` was located at the whole `panels:` block | [#107](https://github.com/creatoan/scenet/issues/107) |
| A syntax error at the end of a file pointed past its last line; a block value at its first field | [#108](https://github.com/creatoan/scenet/issues/108) |
| An unknown speaker was located one step short of its `by:` | [#109](https://github.com/creatoan/scenet/issues/109) |

## Mutation testing

Coverage shows which lines ran, not whether any assertion would notice them changing.
[mutmut](https://github.com/boxed/mutmut) does notice: it makes one small edit at a time to
the solver, the emitters, the front ends, the Core, the IR and the diagnostics -- `<` becomes
`<=`, a constant is nudged, an argument dropped -- and reports every edit the suite still
passes. Each survivor is a behaviour nothing checks.

It runs weekly, and on demand, in `.github/workflows/mutation.yml`, split into **legs**: one
job each, listed in `scripts/mutation.py`, each sized to finish from nothing well inside the
job's time limit. One job mutating everything stopped finishing -- three weekly runs were
cancelled at 120 minutes ([#345](https://github.com/creatoan/scenet/issues/345)). Each leg runs
from nothing, every time: mutmut can resume from a kept `mutants/`, but it re-tests only the
functions whose code changed, so a survivor a new test now kills would stay one, and triage
would be done against a list that is no longer true. A file under a mutated directory belongs to exactly one leg,
and `tests/test_mutation_legs.py` fails on a new one until it is given one.

Each leg's job summary gives its score and lists its survivors. Its `mutmut-results-<leg>`
artifact holds the same list, and `survivors.diff`: every survivor's change, as `mutmut show`
prints it, which is what triage starts from. **A leg fails** when its score falls below its
threshold, in the table below, or when it stopped with mutants it never tried: those count as
survivors, and the list would not be the whole list. A run by hand is a `workflow_dispatch`
on whichever branch holds the tests to try: `legs` runs the named legs, with their
thresholds; `path` mutates one file or glob instead, with none.

Pull requests do not run mutants: a run takes far longer than a review should wait. They run
the check **Mutation clean run** (`ci.yml`): mutmut up to its forced-fail test, every leg's
files mutated together, in four shards of the test files, each a job of its own. Whole, it
ran 22 minutes: it is the suite three times over, and the stats pass three times slower with
every function behind a trampoline. A shard leaves out the coverage pass, which only decides
which lines get mutants. The weekly run broke four times in that step and nowhere else
([#139](https://github.com/creatoan/scenet/issues/139),
[#152](https://github.com/creatoan/scenet/issues/152),
[#193](https://github.com/creatoan/scenet/issues/193), [#345](https://github.com/creatoan/scenet/issues/345)), so it is a required check. What
breaks it:

- **A test that reads a mutated file's text**, to compare it with what a generator writes or
  to scan it: mutmut has rewritten it. Mark it `@reads_the_source`, from
  `tests/under_mutmut.py`, which skips it under mutmut. It holds the text, not the behaviour,
  so no mutant could be killed by it.
- **A file the tests read that `mutants/` does not hold.** `also_copy` in `pyproject.toml`
  is everything git tracks at the top of the repository, and a test holds it to that.
- **A child process of the stats run.** It inherits `MUTANT_UNDER_TEST=stats` and, importing
  a mutated module, looks for mutmut's configuration in its own working directory. The tests'
  `conftest.py` drops the variable in the stats run, which mutmut does not need.

**Why mutmut.** Our imports are slow -- numpy, shapely, kiwisolver, fontTools -- and the suite
takes about 40 seconds. mutmut forks each mutant from a process that has already imported
everything, runs only the tests that reach the mutated function, and resumes where it left
off, re-testing only functions whose code changed. A tool that ran the whole suite once per
mutant would take days.

**Running it.** It is in its own dependency group, so a plain `uv sync` does not install it.
Install every group: its clean run is the whole suite, and `tests/test_site.py` needs `docs`:

```bash
uv sync --all-groups
ulimit -v 2097152
uv run mutmut run --max-children 4
uv run mutmut results
uv run mutmut show <mutant>
```

The `ulimit` caps each process at 2 GiB. A few mutants allocate without bound -- `/` turned
into `*` in the rain or snow density asks for millions of streaks -- and, uncapped, one of
them can fill a 16 GB machine before mutmut's timeout fires. Capped, it ends in a
`MemoryError` and counts as killed. A test process needs under 1 GB.

`[tool.mutmut]` in `pyproject.toml` limits it to `solve/`, `emit/`, `frontends/`, `core.py`,
`ir.py` and `diagnostics.py`, mutates only lines the tests cover, and runs mutants without the
coverage floor, doctests or the documentation examples. To run one leg locally, narrow it
first, as its job does, and restore the file after:

```bash
uv run python scripts/mutation.py matrix          # every leg, its paths and threshold
uv run python scripts/mutation.py narrow src/scenet/core.py
uv run python scripts/mutation.py clean-run --shard 1/4   # one of the pull request's checks
```

**On Windows**, mutmut needs `fork()`, so run it under WSL with a Linux distribution:

```bash
wsl --install -d Ubuntu
```

then, inside WSL, clone the repository and run the commands above. A checkout on the Windows
side, under `/mnt/c/`, works but is several times slower.

**Known blind spot.** mutmut 3 does not mutate a decorated function, other than a plain
`@classmethod` or `@staticmethod`. A pydantic validator is decorated, so each of the sixteen in
`ir.py` and `core.py` holds only its name, docstring and a call: the check itself is a plain
function after its class -- `_check_references_resolve`, `_check_room` -- which is mutated as
usual. What is left is properties and cached loaders, none of them ever mutated. Lines are of
code, the docstring left out:

| Function | Decorator | Lines |
|---|---|---|
| `core.py::Box.right` | `@property` | 1 |
| `core.py::Box.bottom` | `@property` | 1 |
| `core.py::CoreActor.bounds` | `@property` | 3 |
| `core.py::Tail.is_curved` | `@property` | 1 |
| `core.py::PanelCore.bounds` | `@property` | 1 |
| `diagnostics.py::Diagnostic.level` | `@property` | 1 |
| `emit/conditioning.py::Region.sky` | `@property` | 1 |
| `emit/marks.py::Polygon.tag` | `@property` | 1 |
| `emit/marks.py::Mark.is_veil` | `@property` | 1 |
| `emit/pdf.py::_GraphicsState.name` | `@property` | 3 |
| `emit/pdf_fonts.py::refusal` | `@functools.lru_cache` | 16 |
| `emit/pdf_fonts.py::_pdf_font` | `@functools.lru_cache` | 18 |
| `emit/turbulence.py::lattice` | `@functools.lru_cache` | 30 |
| `emit/turbulence.py::_alpha` | `@functools.lru_cache` | 20 |
| `frontends/script_front.py::ScriptDocument.direction` | `@property` | 1 |
| `frontends/yaml_front.py::SceneDocument.direction` | `@property` | 1 |
| `ir.py::PlacementZone.fractions` | `@property` | 4 |
| `ir.py::CaptionKind.is_italic` | `@property` | 1 |
| `ir.py::CaptionKind.is_quoted` | `@property` | 1 |
| `ir.py::Spans.fractions` | `@property` | 6 |
| `ir.py::Horizon.fraction` | `@property` | 1 |
| `ir.py::PanelSpec.width` | `@property` | 1 |
| `ir.py::PanelSpec.height` | `@property` | 1 |
| `ir.py::SettingSpec.is_bare` | `@property` | 1 |
| `ir.py::CastMember.is_figure` | `@property` | 1 |
| `ir.py::PanelIR.drawn_by_its_picture` | `@property` | 1 |
| `ir.py::PageFormat.width` | `@property` | 1 |
| `ir.py::PageFormat.height` | `@property` | 1 |
| `ir.py::Tier.placed` | `@property` | 12 |
| `solve/backdrop.py::_Plot.width` | `@property` | 1 |
| `solve/balloons.py::TailRoute.is_curved` | `@property` | 1 |
| `solve/camera.py::CameraSolution.was_pulled_back` | `@property` | 1 |
| `solve/camera.py::CameraSolution.head_top_y` | `@property` | 1 |
| `solve/figures.py::PlacedFigure.speaker` | `@property` | 1 |
| `solve/speakers.py::Speaker.outline` | `@property` | 9 |
| `solve/staging.py::Placement.origin` | `@property` | 1 |
| `solve/staging.py::_Extent.centre_offset` | `@property` | 1 |
| `solve/text.py::Styled.runs` | `@property` | 7 |
| `solve/text.py::TextBlock.aspect` | `@property` | 1 |
| `solve/text.py::TextBlock.raggedness` | `@property` | 3 |
| `solve/text.py::FontMetrics.extent` | `@property` | 2 |
| `solve/text.py::FontMetrics.data` | `@property` | 1 |
| `solve/text.py::FontMetrics.units_per_em` | `@property` | 1 |
| `solve/text.py::load_metrics` | `@functools.lru_cache` | 1 |

The undecorated methods of the same classes are mutated as usual. The ones that matter most
are the cached loaders -- `lattice` and `_alpha`, the turbulence a PDF's paper is printed from,
and `_pdf_font` and `refusal`, the faces a PDF embeds -- and `Tier.placed`, which reads a
page's panels in order. Lifting a cached loader's body out would not reach it: a mutant runs
in a process whose cache the unmutated code already filled (see the lessons below). Until
mutmut reaches them, the tests named in those lessons, the golden outputs and the
gallery are what guard them.

### Scores and thresholds

| Leg | Files | Mutants | Survivors | Score | Threshold | Run |
|---|---|---|---|---|---|---|
| `solve/balloons` | `solve/balloons.py` | 1,371 | 29 | 97.9% | 97% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `solve/backdrop` | `solve/backdrop.py` | 1,060 | 8 | 99.2% | 99% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `solve/text` | `solve/__init__.py`, `solve/camera.py`, `solve/figures.py`, `solve/speakers.py`, `solve/staging.py`, `solve/text.py` | 1,284 | 96 | 92.5% | 92% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `solve/page` | `solve/describe.py`, `solve/page.py`, `solve/sfx.py` | 1,414 | 46 | 96.7% | 96% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `emit/pdf` | `emit/pdf.py` | 1,388 | 32 | 97.7% | 97% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `emit/pdf parts` | `emit/pdf_fonts.py`, `emit/pdf_images.py` | 979 | 47 | 95.2% | 95% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `emit/svg` | `emit/marks.py`, `emit/svg.py` | 1,370 | 16 | 98.8% | 98% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `emit/drawing` | `emit/debug_svg.py`, `emit/geometry.py`, `emit/page.py`, `emit/strip.py` | 1,093 | 12 | 98.9% | 98% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `emit/other` | `emit/__init__.py`, `emit/boxes.py`, `emit/cmyk.py`, `emit/conditioning.py`, `emit/depth.py`, `emit/export.py`, `emit/mask.py`, `emit/pose.py`, `emit/preview.py`, `emit/semantics.py`, `emit/turbulence.py` | 1,006 | 43 | 95.7% | 95% | [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157) |
| `frontends/script` | `frontends/script_front.py` | 2,182 | 60 | 97.3% | 97% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |
| `frontends/common` | `frontends/__init__.py`, `frontends/common.py` | 502 | 4 | 99.2% | 99% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |
| `frontends/yaml` | `frontends/positions.py`, `frontends/yaml_front.py` | 374 | 4 | 98.9% | 98% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |
| `core` | `core.py` | 351 | 5 | 98.6% | 98% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |
| `ir` | `ir.py` | 683 | 16 | 97.7% | 97% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |
| `diagnostics` | `diagnostics.py` | 1,612 | 74 | 95.4% | 95% | [`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) |

A leg's score is the share of its mutants the tests kill, a timeout counted as a kill; its
threshold is that score in whole percent, rounded down, and the weekly run fails the leg below
it. Survivors are numbered from the run named, and the numbers shift when the function they
are in changes. The first run of the legs, [`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157),
measured them from nothing, each in its own job:

- **`solve/` and `emit/`**, triaged before: their survivors are the accepted lists below, and
  those the code has gained since, in modules that had not run on their own --
  `emit/preview.py`, `solve/speakers.py` and `solve/figures.py` among them. Those are triaged
  in [#472](https://github.com/creatoan/scenet/issues/472).
- **`frontends/`, `core.py`, `ir.py` and `diagnostics.py`**, mutated for the first time: each
  is triaged below, and its threshold raised with what is killed.

`frontends/` was one leg, and ran out of time with 26 of its 859 mutants untried: a mutant of a
function every document goes through runs most of the suite before a test fails, and all of it
when none does. It is two legs now, measured on their own by
[`43429063598`](https://github.com/creatoan/scenet/actions/runs/43429063598).

### Baseline

The first full run with the golden outputs, made locally on four cores in about 57 minutes,
produced 4,094 mutants: **3,761 killed (91.9%)** and 333 survivors. The three that ran out of
memory, described above, are among the killed. By module:

| Module | Survivors | Triage |
|---|---|---|
| `solve/balloons.py` | 123 | done: 16 accepted, below |
| `solve/text.py` | 50 | done: 14 accepted, below |
| `solve/page.py` | 49 | done: 23 accepted, below |
| `solve/backdrop.py` | 32 | done: 7 accepted, below |
| `solve/staging.py` | 22 | done: 9 accepted, below |
| `emit/page.py` | 18 | done: none accepted |
| `emit/svg.py` | 16 | done: 8 accepted, below |
| `emit/debug_svg.py` | 9 | done: none accepted |
| `solve/camera.py` | 7 | done: 1 accepted, below |
| `emit/strip.py` | 7 | done: 6 accepted, below |

Before the golden outputs, the same run left 845 survivors (79.4% killed), 188 of them in
`emit/svg.py`: comparing every emitted byte took most of the emitters' share.

### Triage

Every survivor ends in one of two states:

- **Killed**, by a new assertion in the relevant `tests/test_*.py`.
- **Accepted**, recorded below with a reason: an equivalent mutant that cannot change any
  output, or one whose effect is below what the format can show. `# pragma: no mutate` is
  used only where nothing else works, with a comment saying why.

A triaged module's survivors in the weekly summary should be exactly its accepted list
below. Anything else is new, and is triaged the same way.

### Accepted survivors

**`solve/balloons.py`** -- triaged: of the 123 survivors, 107 are killed by tests in
`tests/test_balloons.py`, and these 16 are accepted. Mutant numbers are mutmut's, from
`uv run mutmut show <name>`, and shift when the function they are in changes.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `_stop_at_face` 35 | `discriminant < 0` to `<= 0` | The mouth is strictly inside the face, so the line through it always crosses the outline twice: the discriminant is never zero. |
| `_stop_at_face` 46, 47 | the second root mutated | The tail starts outside the face -- a balloon may not overlap one -- so the first crossing is always the smaller root, in (0, 1). The second is never chosen. |
| `_stop_at_face` 52 | `t <= 1.0` to `t < 1.0` | `t == 1` would put the mouth on the outline, and the function has already returned unless the mouth is strictly inside. |
| `_stop_at_face` 53 | `t <= 1.0` to `t <= 2.0` | Only a tail that starts inside the face has its first crossing past 1, and none does, for the reason above. |
| `route_tail` 41, 44, 45 | `length` miscomputed, but not zero | `length` divides the normal and multiplies the offset, so it cancels: the control point is `(-dy, dx)` times the bend, whatever `length` is. |
| `route_tail` 46 | `or 1.0` to `or 2.0` | Used only for a zero-length chord, whose normal is `(0, 0)` whatever it is divided by. |
| `route_tail` 59 | `magnitude * sign` to `magnitude / sign` | `sign` is 1 or -1, and dividing by either is multiplying by it. |
| `_score_caption` 55 | `default=0.0` to `default=1.0` | The default applies only when the panel has no actors, and then the loop the reach is for runs zero times. |
| `letter_tone` 5 | `>=` to `>` | Differs only when ink and paper contrast exactly equally with the fill. Contrast is measured on neutral greys, so there are 256 fills to try, and none ties. |
| `_curve_hits` 6 | sampling starts at step 0 | Step 0 adds a zero-length segment at the start; the next segment begins there anyway. |
| `_curve_hits` 2, 8; `_segment_hits_box` 2 | sample count 16 to 17, first sample skipped, 12 to 13 | Sampling resolution, below what the format can show: the chord between samples is within a fraction of a unit of the curve, and faces and boxes are tens of units across. |

Off-panel speech and small type ([#75](https://github.com/creatoan/scenet/issues/75)) added 27 survivors. 16 are killed by `TestOffPanel`
and `TestTheNearerSide` in `tests/test_balloons.py` and by `tests/test_off_panel.py`, and
these 11 are accepted, numbered as in run `38642945474`:

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `_place_off_panel` 87 | `speaker_face=None` dropped | `None` is the parameter's default. |
| `_edge_point` 29, 34 | the line out doubled to tripled | Any end past the rectangle crosses the outline at the same point. |
| `_edge_point` 31 | `or centre.y` to `and centre.y` | For left and right the line's height is the centre's either way. For top and bottom the line collapses to a point, crosses nothing, and falls back to the rectangle's edge -- which is where it would have crossed, because a slant leans only the gutters: a panel's top and bottom stay level. |
| `_edge_point` 47, 53, 54, 57, 60, 64, 66 | the handling of several crossings, or none | The line runs from the balloon, inside the outline, to beyond it, and a panel's outline is convex, so it crosses exactly once: a single point, which has `coords` and no `geoms`. |

**`solve/text.py`** -- triaged twice. The first pass, before kerning, killed 36 of 50
survivors; most were in `FontMetrics`'s constructor, and survived for a reason worth knowing:
`load_metrics` is cached, so a test that measures only through it uses the instance built at
import and never runs the constructor under a mutant. The tests build one of their own.

Kerning, an author's own face and dashes that keep to their word brought it to 81 survivors
in run `39038961474`, whose numbers are the ones below. 37 are killed by tests in
`tests/test_kerning.py` and `tests/test_text.py`. Kerning is the reason most of those exist:
a font in every shape a reader must handle -- Apple's `kern` table, a skipped subtable before
a kept one, a `latn` script beside `DFLT`, two lookups kerning one pair, a class row shorter
than its classes, a font with no `name` table -- is built in the test, since the shipped
faces are none of them. These 44 are accepted:

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `FontMetrics.__init__` 8, 10, 12 | `lazy=True` to `None`, `False`, or left out | Laziness decides when fontTools parses a table, not what it reads from it. |
| `FontMetrics.__init__` 31, 33, 36 | the default for a missing `.notdef` changed | Every TrueType font has a `.notdef`, glyph 0, with an advance in `hmtx`, so the default is never used. |
| `FontMetrics._raw_advance` 5, 7, 9 | the default for a glyph with no advance changed, or always looked up | Every glyph the character map names has an advance in `hmtx`; a character with no glyph looks up `None`, which is not a glyph name, and gets `.notdef` either way. |
| `FontMetrics._pair` 1, 2, 20 | the cache never hit, or written as `None` | The cache only saves work: a miss computes the same sum again. |
| `FontMetrics.glyph_outlines` 20 | `name is None or name not in glyph_set` to `and` | Every glyph the character map names is in the glyph set, so the second test only ever agrees with the first. |
| `Typeface.face` 4 | the regular face loaded through its file path | `SHIPPED_FACES` names the same file `load_metrics()` opens: a second cache entry, the same metrics. |
| `Typeface.measure` 26, 29, 30; `_pair_table` 6, 9, 10 | `strict=True` to `None`, `False`, or left out | A `Styled` refuses faces that do not match its characters one for one, and a PairPos format 1 has one pair set per covered glyph, so neither `zip` has anything to refuse. |
| `_x_advance` 5 | the default `0` to `None` | Followed by `or 0`: a record with no `XAdvance` is zero either way. |
| `_legacy_kerning` 7, 10 | the default for a table with no `kernTables` | fontTools always gives a `kern` table its `kernTables`, an empty list at least. |
| `_legacy_kerning` 20, 29, 32, 35, 40, 43, 46 | the defaults for a subtable's `format`, `coverage` and `apple` | Every subtable fontTools reads has a `format`, and a format 0 one -- the only kind read further -- always has its `coverage` and `apple`. |
| `_legacy_kerning` 52 | the Apple mask `0xC0` to `0xC1` | Bit 0 of Apple's coverage flags is reserved, and zero. |
| `_words` 4 | the first gap's face `None` | A gap is recorded only after whitespace has set its face. |
| `_words` 20 | the last word sliced to `None` instead of the length | The same slice. |
| `_candidates` 17, 19; `candidate_measures` 15, 17 | runs that end before they start, or a gap too many | An empty run measures the one word `_line` starts from, a width already in the set; a gap past the last word is never read. |
| `layout_text` 16 | the line height taken from the regular face | Line height is the size times a fixed factor, the same for every face. |
| `layout_text` 34 | `line_widths=()` left out | `()` is its default. |
| `layout_text` 96 | `score < best_score` to `<=` | An exact tie between two different wrappings needs two different blocks to score the same float; equal wrappings tie, and either is the same block. |
| `layout_text` 101 | the fallback line built with no gaps | The fallback is reached only when every block is 0 wide. With two words or more, the space between them has width, so the fallback only ever sets one word -- and one word has no gap to read. |
| `_keep_marks_with_their_words` 8, 11, 13 | `strict=True` to `None`, `False`, or left out | `_words` gives one gap fewer than words, always, so the two lists never differ in length and `strict` never has anything to refuse. |

**`solve/page.py`** -- triaged: of the 49 survivors, 26 are killed by tests in
`tests/test_page_solver.py`, which call the solver's pieces directly at the edges each one
holds -- an inset that exactly fits, two insets exactly a gutter apart, a lean that leaves
half a unit -- and these 23 are accepted.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `_frame` 1 | `gutter` defaults to 1 | It is read only for an inset's clearance, and every inset passes its gutter. |
| `_fmt` 5, 6 | `rstrip("0")` to `rstrip("XX0XX")`, `rstrip(".")` to `rstrip("XX.XX")` | `rstrip` takes a set of characters, and no number has an `X` in it. |
| `_slanted` 30, 33, 41; `resolve_frames` 26, 30, 34, 75, 79, 83, 118, 122, 126, 140, 144, 148 | `zip(..., strict=True)` to `None`, `False` or left out | Each zip pairs sequences built from the same list of weights, so they are always the same length, and `strict` only matters when they are not. |
| `_slanted` 35 | `spans[:-2:2]` to `spans[:-3:2]` | `spans` has an even length, so both slices stop at the same element. |
| `_slanted` 87, 92 | `<= 0` to `< 0` for the width at the top or bottom | Differs only for a width of exactly 0, which needs the tangent of the slant times a height to land exactly on a gutter's edge; a width half a unit either side is tested. |
| `_slanted` 142, 157 | `corners[0]` to `corners[1]` for the frame's top | Both are top corners, at the same `y`. |
**`solve/backdrop.py`** -- triaged: of the 32 survivors, 25 are killed by tests in
`tests/test_backdrop.py`, most by calling a generator directly with a `_Plot` whose
horizon is half a unit from the top, where a clamp anywhere but the panel's edge shows.
These 7 are accepted.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `seed_for` 7, `_rng` 6, `_atmosphere` 22 | `int.from_bytes(..., "big")` with the byte order left out | Big-endian is the default since Python 3.11, and the floor is 3.12. |
| `seed_for` 14, `_rng` 13 | `encode("utf-8")` to `encode("UTF-8")` | The same codec; Python's codec names are case-insensitive. |
| `_luminance` 15 | `channel <= 0.04045` to `<` | No 8-bit channel is exactly 0.04045, and the sRGB curve is continuous there anyway. |
| `_atmosphere` 63 | `> FALL_CONTRAST_THRESHOLD` to `>=` | The sky under rain cloud is 0.69, 0.83, 0.55 and 0.37 at dawn, day, dusk and night: never exactly 0.5. |
**`solve/camera.py`** -- triaged: of the 7 survivors, 6 are killed by tests in
`tests/test_camera.py`. Both shipped puppets measure from the top of the head at 0, where a
sum and a difference from it agree, so the tests also frame a puppet measured from lower
down, and one drawn a thousand times smaller. This one is accepted.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `CameraSolution.pulled_back_to` 1 | `scale >= self.scale` to `>` | At an equal scale it builds a new solution equal in every field -- pullback 1.0 -- and `CameraSolution` is a dataclass, so the two compare equal. |
**`solve/staging.py`** -- triaged: of the 22 survivors, 13 are killed by tests in
`tests/test_staging.py`. The one that does the most work frames a cast drawn five hundred
times smaller: a puppet's units are its own, so the composition must come out the same,
even with the whole cast less than one unit wide. These 8 are accepted. A ninth,
`_facing_for` 5, is killed since a gaze may be aimed at somebody off panel, who is in no
order (`tests/test_off_panel.py`; run `39038963872`).

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `_fit_cast_across_frame` 8, 16 | widths measured with `facing_right` `None` or `False` | A mirrored silhouette is exactly as wide. |
| `_fit_cast_across_frame` 22, 23 | widths measured from an origin of `(1, 0)` or `(0, 1)` | Moving a silhouette does not change its width. |
| `_fit_cast_across_frame` 40 | `native_total <= 0` to `< 0` | Every part has a positive width or radius, so a cast's total width is never 0. |
| `_facing_for` 10 | `>` to `>=` | Only equal for an actor looking at itself, which the IR refuses as `reflexive-relation`. |
| `solve_staging` 51 | extents measured with the root at `x = 1` | An extent is measured from the root wherever it stands; `TestAnExtentIsMeasuredFromTheRoot` holds that. |
| `solve_staging` 61 | the expression left out when measuring extents | An expression moves the features inside the head, which the silhouette does not include. |
**`solve/describe.py`** ([#76](https://github.com/creatoan/scenet/issues/76)) -- a fresh run,
[`39124930311`](https://github.com/creatoan/scenet/actions/runs/39124930311), tried 177
mutants and left 2, `_figure` 26 and 27: an expression's underscores read as spaces, which no
shipped expression has. `test_a_puppets_own_expression_is_read_with_its_underscores_as_spaces`
kills both. None accepted.

**The emitters** -- triaged together: of their 50 survivors, 36 are killed by
`tests/test_emit_edges.py`. The goldens pin every byte the gallery produces, so what
survived is what the gallery never produces: several pages side by side, a curved tail, a
gaze that is not level, a limb thinner than its outline. A Core is a format people
hand-edit, so the tests edit a compiled one to hold them.

Accessible output ([#76](https://github.com/creatoan/scenet/issues/76)) changed `svg.py`, `strip.py`, `page.py` and `debug_svg.py`: `render`
and `render_debug` became wrappers round `panel_body` and `debug_body`, which `placed_panel`
places instead of cutting text, and every renderer took `aria`. A fresh run of `emit/*`,
[`39124932431`](https://github.com/creatoan/scenet/actions/runs/39124932431), tried 1438
mutants and left 15. Seven are killed in `tests/test_emit_edges.py`,
`tests/test_accessible.py` and `tests/test_lettering_face.py`, each applied by hand to see
its test fail. These 8 are accepted, numbered as in that run -- six of them the same
mutants as before, one renumbered, one new.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `emit/svg.py` `fmt` 7, 8 | `rstrip("0")` to `rstrip("XX0XX")`, `rstrip(".")` to `rstrip("XX.XX")` | `rstrip` takes a set of characters, and no number has an `X` in it. |
| `emit/svg.py` `fmt` 13 | `""` to `"XXXX"` in the set of zeros | A number formatted to fixed places always keeps the digit before its point, so stripping never leaves `""` -- only `"0"` or `"-0"`. |
| `emit/svg.py` `_filter_id` 2, 4 | the id for a missing veil changed | Both callers return before asking when there is no veil. |
| `emit/svg.py` `typeface_of` 2 | `Typeface(regular=metrics)` to `Typeface(regular=None)` | A Core compiled with those `metrics` names their font in `fonts`, and the loop below puts it back as the regular face; shipped metrics are the shipped face either way. |
| `emit/svg.py` `_tail_shape` 47 (now `emit/geometry.py` `pointer`) | `or 1.0` to `or 2.0` | Used only for a zero-length chord, whose normal is `(0, 0)` whatever it is divided by. |

Supplied pictures ([#70](https://github.com/creatoan/scenet/issues/70)) changed `solve/backdrop.py`, `solve/describe.py` and every emitter.
Fresh runs from the stack's emitter branch:

- `solve/describe.py`,
  [`39154486553`](https://github.com/creatoan/scenet/actions/runs/39154486553): 190 mutants, all
  killed.
- `solve/backdrop.py`,
  [`39154483015`](https://github.com/creatoan/scenet/actions/runs/39154483015): 1001 mutants and
  8 survivors -- the 7 accepted above, under the same numbers, and `solve_backdrop` 6, a changed
  message, now killed in `tests/test_image_backdrop.py`.
- `emit/*`, [`39154489426`](https://github.com/creatoan/scenet/actions/runs/39154489426): 1520
  mutants and 13 survivors -- the 8 accepted above, `panel_body` 39 now numbered 49; `image_href`
  11 and `render_pages` 76, killed in `tests/test_emit_image.py`; and these 3, accepted,
  numbered as in that run.

Each mutant killed was applied by hand to see its test fail.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `emit/svg.py` `image_href` 5 | `quote(href, safe="/")` to `quote(href)` | `/` is already `quote`'s default `safe`. |
| `emit/svg.py` `image_href` 6 | `safe="/"` to `safe="XX/XX"` | `quote` never escapes a letter, so adding `X` to what it leaves alone changes nothing. |
| `emit/svg.py` `image_href` 15 | `decode("ascii")` to `decode("ASCII")` | The same codec; Python's codec names are case-insensitive. |

Figures a picture draws ([#71](https://github.com/creatoan/scenet/issues/71)) changed `solve/balloons.py` and `solve/sfx.py` -- the speaker
interface, bystanders, keep-outs, a tail to a cropped mouth -- added `solve/speakers.py` and
`solve/figures.py`, and drew figures in the debug overlay. Fresh runs from the stack's top
branch. The first batch never tried a mutant: two `@given` tests written as methods failed
Hypothesis's `differing_executors` health check in mutmut's clean run, which runs the suite twice
in one process; every property test is a module function now, as the rest of the suite's are.

- `solve/speakers.py`,
  [`39483572899`](https://github.com/creatoan/scenet/actions/runs/39483572899): 26 mutants, all
  killed.
- `solve/figures.py`,
  [`39483587638`](https://github.com/creatoan/scenet/actions/runs/39483587638): 52 mutants, all
  killed.
- `solve/describe.py`,
  [`39483600321`](https://github.com/creatoan/scenet/actions/runs/39483600321): 195 mutants, all
  killed.
- `emit/*`, [`39483612696`](https://github.com/creatoan/scenet/actions/runs/39483612696): 1589
  mutants and 11 survivors, exactly the 11 accepted above under the same numbers. The figures in
  the debug overlay left none.
- `solve/balloons.py`,
  [`39483547250`](https://github.com/creatoan/scenet/actions/runs/39483547250): 1335 mutants and
  51 survivors.
  - 27 are the 27 accepted above. Two are renumbered: `_score_caption` 55 is now 59, and
    `_place_off_panel` 87 is now 89.
  - **Killed in `tests/test_balloons.py`** (`TestTriageForFigures`, `TestASoundInAPanelOfFigures`):
    - bystanders' bodies dropped from `_score` (23) and `_score_caption` (21, 22), or overwritten
      rather than summed in `_occlusion_cost` (33);
    - bystanders not handed to an off-panel balloon (`_place_off_panel` 54, `place_script` 163) or
      to the sound effects (`place_script` 78);
    - the sound effects' `inside`, `marks` -- which hold the keep-outs -- and `blocked` dropped
      (`place_script` 67, 75, 76, 77);
    - the bottom-right corner candidate (`_candidate_positions` 62-65) and the fallback tail's
      start (`route_tail` 83). These two had been killed only by golden panels whose balloons sat
      there before [#71](https://github.com/creatoan/scenet/issues/71)'s speaker fix moved them.
  - **Removed:** `_within_frame` 15, 30, 36, 37, 40 and 43 checked whether a mouth was inside the
    frame first, and walked shapely's result by hand. A convex frame is crossed once by a line to
    a mouth beyond it and never by one to a mouth inside, so the function now only intersects, and
    reads the crossing with `shapely.get_coordinates`. Every golden is unchanged.
- `solve/sfx.py`, [`39483560230`](https://github.com/creatoan/scenet/actions/runs/39483560230):
  489 mutants and 37 survivors. `solve/sfx.py` arrived after the baseline above and had not been
  triaged. [#71](https://github.com/creatoan/scenet/issues/71) changed `_cost` and `place_effects`, and their 21 survivors are triaged here:
  - **18 killed** in `tests/test_sfx.py`: `TestTheCostOfAPosition` pins each term of `_cost`
    exactly, on a footprint smaller than a mutant's area floor; `TestWhereAnEffectMayGo` holds
    `place_effects` to an inset elsewhere, a sliver of one, and a shaped panel.
  - **3 accepted**, below.
  - The other 16, in `layout_effect` (9), `_ring` (6) and `_candidates` (1), are in code [#71](https://github.com/creatoan/scenet/issues/71) did
    not change, and were triaged after it. `TestTheShapeOfAnEffect` and
    `TestWhereAnEffectIsLookedFor` in `tests/test_sfx.py` kill 9: the last pair of letters
    kerned as every other is (`layout_effect` 10), an arc of one degree bowing the same way as
    one of thirty (41), the rings round a source at its reach times each factor (`_candidates`
    16), and every ring starting straight up and going clockwise (`_ring` 5, 8, 10, 16, 21). The
    other 7 are accepted, below. `solve/sfx.py` is triaged: run
    [`39497617662`](https://github.com/creatoan/scenet/actions/runs/39497617662), from that
    branch, left 11 survivors of 489 mutants, exactly the 11 accepted below.

Both files were run again from the triage branch, after the tests and the change to
`_within_frame`: `solve/balloons.py`,
[`39491758453`](https://github.com/creatoan/scenet/actions/runs/39491758453), 1317 mutants and 29
survivors -- the 27 accepted above and the two below; `solve/sfx.py`,
[`39491774024`](https://github.com/creatoan/scenet/actions/runs/39491774024), 489 mutants and 19
survivors -- the three below and the 16 still to triage. The numbers below are those runs'.

Each mutant killed was applied by hand to see its test fail.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `solve/balloons.py` `_within_frame` 29, 31 | `min(points, key=...)` without the key | A convex frame is crossed at most once, so there is never a second point to choose between: the same argument as `_edge_point` 47 and the rest. |
| `solve/sfx.py` `_cost` 12 | the source term `+=` to `=` | It is the first term, added to the `0.0` the cost starts at. |
| `solve/sfx.py` `place_effects` 87 | `cost < best[0]` to `<=` | Differs only on an exact tie, which a later candidate would then win. Candidates are placed by trigonometry, so two that look equally good differ in their last bits -- and which way depends on the platform: a test pinning one, with an inset over the middle and its two mirror points left, passed on Windows and failed on Linux. No test can hold a tie that the arithmetic never makes exact. |
| `solve/sfx.py` `layout_effect` 40 | `arc > 0` to `arc >= 0` for the bow | The bow is read only when the arc is not zero. |
| `solve/sfx.py` `layout_effect` 52, 55, 56 | `zip(..., strict=True)` loosened or dropped | The steps are built one per character of the same text, so the two are always the same length. |
| `solve/sfx.py` `layout_effect` 63, 74 | every glyph's height shifted by 1, or by the arc's radius | The shift is the same for every glyph and corner, and the footprint is re-centred on its hull afterwards, which takes it back out: below what the format can show. |
| `solve/sfx.py` `layout_effect` 153 | the rotation about the hull's centre instead of `(0, 0)` | The hull has just been centred on `(0, 0)`, so the two are the same point. |
| `solve/sfx.py` `_ring` 19 | `sin(-pi / 2 + a)` to `sin(-pi / 2 - a)` | Both are `-cos(a)`. |
| `solve/sfx.py` `place_effects` 42 | `distance < radius` to `<=` | Differs only for a footprint exactly tangent to a face. Footprints are glyph outlines placed at candidate centres a ring step apart, which never land at a face's radius exactly; a balloon's own face test is strict for the same reason. |

Right-to-left reading ([#68](https://github.com/creatoan/scenet/issues/68)) changed `solve/balloons.py`, `solve/page.py`, `solve/describe.py`,
`emit/strip.py`, `emit/page.py` and `emit/debug_svg.py`. Fresh runs from the stack's top branch:

- `solve/balloons.py`,
  [`39836238615`](https://github.com/creatoan/scenet/actions/runs/39836238615): 1356 mutants and
  40 survivors.
  - 29 are the 29 accepted above. One more is renumbered: `_place_off_panel` 89 is now 96.
  - **11 killed** in `tests/test_direction.py`:
    - which way caption zones are tried (`_caption_positions` 41). The mirror test alone could
      not tell the two directions apart, since flipping both still mirrors, so
      `TestTheRuleItself` pins the first zone to where reading starts;
    - the tolerance of the right-to-left rule (`_reading_order_allows` 4, 5), mirrored from the
      left-to-right tests;
    - the direction dropped from the zones, the order and the nearer side of an off-panel balloon
      (`_place_off_panel` 27, 30, 34, 37, 70, 73) and from a caption's zones (`_place_caption`
      24, 27). Most of these change a layout only on an exact tie between mirrored candidates,
      which falls differently by platform and so is never pinned.
      `TestEveryReadingDecisionIsAskedTheWayThePanelReads` watches every reading decision in a
      panel read right to left, and requires each to be asked right to left.
- `solve/page.py`,
  [`39836251923`](https://github.com/creatoan/scenet/actions/runs/39836251923): 542 mutants and
  26 survivors, all accepted above:
  - `_frame` 1, `_fmt` 5 and 6, and `_slanted` 30, 33, 35, 41, 87, 92, 142 and 157, under the
    same numbers;
  - the `zip(..., strict=True)` mutants, renumbered to `resolve_frames` 28, 32, 36, 90, 93, 98,
    137, 140, 145, 159, 163 and 167;
  - three new ones of the same kind in `_across` (5, 8, 12), which pairs the starts and sizes of
    one `_split`.
- `solve/describe.py`,
  [`39836265688`](https://github.com/creatoan/scenet/actions/runs/39836265688): 203 mutants and
  2 survivors, accepted below.
- `emit/*`, [`39836278068`](https://github.com/creatoan/scenet/actions/runs/39836278068): 1643
  mutants and 20 survivors.
  - 11 are the 11 accepted above, under the same numbers.
  - **9 killed** in `tests/test_reading_pages.py` (`TestTwoDirectionsAreRefusedByName`): the
    refusal of panels or pages read two ways, word for word (`reading_direction` 8, 9;
    `render_strip` 7, 10, 11; `render_pages` 7, 10, 11), and the default for nothing to lay out
    (`reading_direction` 11).

Each mutant killed was applied by hand to see its test fail.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `solve/describe.py` `describe` 8, 10 | the sort key scaled by -2 instead of -1, or 2 instead of 1 | Scaling every face's x by one factor of the same sign keeps their order, and keeps a tie a tie for the id to break. |

The second job of each of those runs, exploring with fresh seeds, found the right-to-left page
property compiling the reversed scene in full to compare its frames. That scene's lettering is
read the other way and can find no room where the original did. The property now lays the
reversed pages out without compiling a panel, since frames cannot depend on lettering, and passes
300 examples.

The exports for image models ([#72](https://github.com/creatoan/scenet/issues/72)) added `emit/conditioning.py`, `emit/pose.py`,
`emit/boxes.py`, `emit/semantics.py`, `emit/depth.py`, `emit/mask.py` and `emit/export.py`, moved
the painter's order of `emit/svg.py` into `in_painters_order` ([#221](https://github.com/creatoan/scenet/issues/221): masses past the tenth were
drawn out of order), and took `traits` out of `solve/describe.py`.

A first triage ran before the stack's review: `emit/*`
[`40008532976`](https://github.com/creatoan/scenet/actions/runs/40008532976), 2177 mutants and 17
survivors, which killed `emit/depth.py` `_plane` 2 and 3 (a figure's plane merged with an
actor's, by `test_a_hand_edited_core_with_figures_and_actors_puts_the_figures_in_front`) and
`emit/conditioning.py` `_fraction` 1 (`+ 0.0` to `- 0.0`, by
`test_a_negative_zero_is_written_as_zero`). The review then changed the box clipping, the maps'
canvas and edges, the mask colours, and the semantics, so `emit/*` was run again from the top of
the stack. A cached run of it (40031036460) reported 46 mutants and was discarded; the branch's
`mutants/` caches were deleted and it ran again from nothing:

- `emit/*`, [`40032456101`](https://github.com/creatoan/scenet/actions/runs/40032456101): 2263
  mutants and 27 survivors.
  - 10 are the `emit/svg.py` survivors accepted above, under the same numbers. `panel_body` 39,
    the painter's sort keyed on the whole tuple, is gone with the sort it mutated, and its row
    with it: `in_painters_order` sorts on depth alone.
  - **2 killed**:
    - `emit/mask.py` `colours` 9, a character stepping aside tested at `slot - step` but placed
      at `slot + step`. The two agree unless a third character holds the slot ahead, so
      `test_a_character_stepping_aside_never_lands_on_a_colour_already_taken` builds that
      case: under the mutant two characters share a colour;
    - `emit/conditioning.py` `fraction_box` 21, `area <= 0.0` to `<= 1.0`, by
      `test_a_box_smaller_than_a_unit_is_still_a_box`.
  - 15 accepted below.
- `solve/describe.py`,
  [`40008537043`](https://github.com/creatoan/scenet/actions/runs/40008537043): 210 mutants and
  2 survivors, `describe` 8 and 10, accepted above under the same numbers. The review changed
  nothing in it.

Each mutant killed was applied by hand to see its test fail.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `emit/conditioning.py` `to_json` 5 | `ensure_ascii=False` to `ensure_ascii=None` | `json.dumps` only asks whether it is true, and `None` is not. |
| `emit/mask.py` `mass_colour` 16, 18 | `% 1.0` to `/ 1.0`, or to `% 2.0` | `colorsys.hsv_to_rgb` takes the hue's sixth modulo 6, so a hue and the same hue plus a whole turn give one colour. |
| `emit/mask.py` `mass_colour` 17 | `index * GOLDEN` to `index / GOLDEN` | `1 / 0.618…` is `1.618…`, one more than `0.618…`, so the two hues differ by `index` whole turns -- the same colour, the golden ratio's own identity. |
| `emit/mask.py` `slot_of` 5 | `encode("utf-8")` to `encode("UTF-8")` | The same codec; Python's codec names are case-insensitive. |
| `emit/mask.py` `slot_of` 10 | `int.from_bytes(digest[:8], "big")` without `"big"` | `"big"` is the default since Python 3.11, and the package needs 3.12. |
| `emit/mask.py` `render_mask` 10, 13, 15; `emit/semantics.py` `render_semantics` 9, 12, 14 | `zip(regions, colours(regions), strict=True)` with `strict` dropped, `None` or `False` | `colours` returns one colour per region it is given, so the two always have one length. |
| `emit/export.py` `Conditioning.files` 6, 9, 10 | `zip(suffixes, astuple(self), strict=True)` with `strict` dropped, `None` or `False` | `EXPORTS` and `Conditioning` both have five entries, in one order: a test compares every file with its own export. |

The second job of every run, exploring with fresh seeds, passed every property, the new ones for
the exports included, at 300 examples.

The depth export's receding surfaces ([#227](https://github.com/creatoan/scenet/issues/227)) added `recedes` and a ramped `render_depth` to
`emit/depth.py`, and taught `flat_map` in `emit/conditioning.py` a `Ramp`. Both modules were run
from the pull request's branch, each from nothing (the totals are every mutant of the module):

- `emit/depth.py`, [`40952714050`](https://github.com/creatoan/scenet/actions/runs/40952714050):
  81 mutants and 1 survivor, **killed**: `recedes` 25, a ceiling's run checked against `1.0`
  instead of the top edge, so a horizon less than a unit below the top left it flat.
  `test_a_ceiling_with_a_horizon_just_below_the_top_still_recedes` sets one at `0.5`; the mutant,
  applied by hand, fails it.
- `emit/conditioning.py`,
  [`40952725859`](https://github.com/creatoan/scenet/actions/runs/40952725859): 188 mutants and 1
  survivor, `to_json` 5, accepted above under the same number.

The colour policy ([#244](https://github.com/creatoan/scenet/issues/244)) changed `solve/backdrop.py` (the tinted ladder, `colour_for`, the
twins in `_atmosphere`, and `_luminance` refusing a colour), `solve/balloons.py` (the `warm`
caption's colour), and in `emit/`, `svg.py`, `page.py`, `strip.py` and `semantics.py` (drawing the
colour, `mono=`, and the semantics' `palette`). Fresh runs from the stack's top branch, each from
nothing (the totals are every mutant of the path):

- `solve/backdrop.py`,
  [`41293701148`](https://github.com/creatoan/scenet/actions/runs/41293701148): 1068 mutants and
  12 survivors.
  - 7 are the 7 accepted above: `seed_for` 7 and 14 and `_rng` 6 and 13 under the same numbers,
    and three renumbered: `_luminance` 15 is now 24, `_atmosphere` 22 is now 38, and
    `_atmosphere` 63 is now 55.
  - **1 killed**: `_atmosphere` 106, the snowy sky's colour left out. Rain's was pinned and snow's
    was not, so `test_the_air_it_falls_through_is_tinted` checks the sky and the cloud of a snowy
    panel at every hour.
  - **3 removed**: `_atmosphere` 107, 112 and 114 mutated `fall_colour=colour_for(SNOW_TONE, ...)`,
    which is always `""`, since white snow is not a rung of the ladder. The line is gone and
    snow's `fall_colour` takes its default, which says the same thing.
    `test_snow_stays_white` still holds it.
  - 1 accepted below.
- `solve/balloons.py`,
  [`41293703313`](https://github.com/creatoan/scenet/actions/runs/41293703313): 1371 mutants and
  29 survivors, the 29 accepted above under the same numbers. None is in the caption's colour.
- `emit/*`, [`41293705447`](https://github.com/creatoan/scenet/actions/runs/41293705447): 2349
  mutants and 28 survivors.
  - 25 are the 25 accepted above, under the same numbers: the 10 in `emit/svg.py` and the 15 in
    the exports.
  - **3 killed**: `render_page` 4, `render_pages` 4 and `render_strip` 4, `mono` on by default.
    The gallery test always passes `mono=True` and the command always passes `mono` itself, so
    nothing called them without it.
    `test_without_it_a_page_and_a_strip_draw_the_colour_too` does.

Each mutant killed was applied by hand to see its test fail. `core.py`, where `as_mono` lives, is
outside what the workflow mutates; `as_mono` is held by the gallery test, which compares it with
the mono Core on every example.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `solve/backdrop.py` `_luminance` 2 | `.lower()` to `.upper()` on each channel | The channels are only compared with each other and read as hexadecimal, and both are case-insensitive. |

The print PDF ([#80](https://github.com/creatoan/scenet/issues/80)) added four modules to `emit/`: `geometry.py` and `marks.py`, which the
SVG now draws from, and `pdf.py` and `pdf_images.py`. A run of all of `emit/`,
[`41777653921`](https://github.com/creatoan/scenet/actions/runs/41777653921), reached the
job's time limit with 748 of 4767 mutants untried, all in `geometry.py` and `marks.py`, so each
was run on its own, and `pdf*.py` again once the new tests were in:

- `emit/geometry.py`, [`41791026492`](https://github.com/creatoan/scenet/actions/runs/41791026492):
  199 mutants and 1 survivor, `pointer` 20: the `or 1.0` accepted above as `_tail_shape` 47.
- `emit/marks.py`, [`41795875604`](https://github.com/creatoan/scenet/actions/runs/41795875604):
  590 mutants and 22 survivors. 14 were a `rounded` or a `width` set on a mark with no
  outline, where caps, joins and width mean nothing; the parameters are gone, and with them
  the mutants. `test_the_marks_are_what_the_svg_paints_in_order` now compares every mark's
  fill, stroke, width, caps, opacity and dash with the SVG's, which kills the colour mutants
  of the first run, and the paper caption and the snow have tests of their own.
- `emit/pdf*.py`, [`41792992306`](https://github.com/creatoan/scenet/actions/runs/41792992306):
  1603 mutants and 52 survivors. 10 are killed since -- a JPEG's single fill byte, and the
  page boxes' fourth decimal place -- each applied by hand to see its test fail.

Accepted, by what makes them equivalent:

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `marks.py` `_lettering`: `strict=True` | `None`, `False`, or no `strict` | The three sequences zipped come from one run's text, so they are always as long. |
| `pdf.py` `_page_content`: the sheet's and rings' owner | `"page"` changed or `None` | The owner names a mark for tests; the PDF writer never reads it. |
| `pdf.py` `_state` 2, 3 | the default opacity changed | Every call passes a fill or a stroke, whose opacity replaces it. |
| `pdf.py` `_path` 23, `_Document.write` 126 | `closed=None`, a content stream's entries `None` | Both are read as false, as `False` and `""` are. |
| `pdf.py` `_linear` 5, `ink` 7 | `<=` to `<` at the sRGB knee and at L 0.10 | Both sides of the knee give the same value there, and no `#rrggbb` grey has an OKLab L of exactly 0.10. |
| `pdf.py` `_embedded` 6 | 13 digits of the digest in the message | A message, which says the same thing. |
| `pdf_images.py` `_jpeg` 3, `_chunks` 5 | `False` to `None`, `b""` to `None` | Read only for truth, and `None` is false as they are. |
| `pdf_images.py` `_jpeg` 6, 7, 42; `_chunks` 10, 11, 38 | a loop's bound or a slice one byte wider | A frame, a chunk header and an IHDR body are longer than the slack, so each still ends where the format says. |
| `pdf_images.py` `_chunks` 18, 37 | unsigned fields read as signed | No chunk is 2 GB, and no width, depth or type in a header reaches a sign bit. |
| `pdf_images.py` `_decoded` 41, 44, 45, 75; `_expanded` 3 | bit-depth tests moved by one, or a default that is never read | At depth 8 the scale is 1 and the sub-byte path packs one sample a byte; alpha is only written when there is a mask; a palette with no `tRNS` writes no mask. |
| `pdf_images.py` `_packed` 8, `_samples` 2, 9, 22, `_repacked` 2, 11 | `"big"` left out, depth 8 to 9, a longer range | Python's default byte order is big-endian; depth 8 takes the one-sample-a-byte path either way; samples past a row's count are never read. |
| `pdf_images.py` `_unfiltered` 30 | a row one byte longer | The extra byte is past every index a filter reads. |
| `pdf_images.py` `_paeth` 12 | `<=` to `<` between left and up | They tie only when they are equal, so which is returned cannot be told apart. |
| `pdf_images.py` `_deinterlaced` 4, 11, 17, 21, 27 | the grid's fill, or a pass's empty test changed | Every cell is written by some pass, and a pass that starts past the edge counts 0 either way. |

The print follow-ups ([#280](https://github.com/creatoan/scenet/issues/280)–[#284](https://github.com/creatoan/scenet/issues/284)) added `emit/pdf_fonts.py` and `emit/turbulence.py`, changed
`emit/pdf.py` and `emit/geometry.py`, and made `solve/page.py` bleed. Each file was run on its own
from the stack's top ([#310](https://github.com/creatoan/scenet/issues/310)):

| File | Run | Mutants | Survivors | Killed since | Accepted |
|---|---|---|---|---|---|
| `emit/pdf.py` | [`42006878954`](https://github.com/creatoan/scenet/actions/runs/42006878954) | 1380 | 52 | 27 | 25: 13 above, 12 below |
| `emit/pdf_fonts.py` | [`42006883885`](https://github.com/creatoan/scenet/actions/runs/42006883885) | 306 | 51 | 35 | 16, below |
| `emit/turbulence.py` | [`42006888799`](https://github.com/creatoan/scenet/actions/runs/42006888799) | 143 | 5 | 3 | 2, below |
| `solve/page.py` | [`42006894798`](https://github.com/creatoan/scenet/actions/runs/42006894798) | 715 | 52 | 17 | 35: 26 above, 9 below |
| `emit/geometry.py` | [`42006899872`](https://github.com/creatoan/scenet/actions/runs/42006899872) | 237 | 5 | 1 | 4: 1 above, 3 below |

Each mutant killed was applied by hand to see its test fail. Two lessons from it:

- **A cache outlives a mutant.** mutmut forks each mutant from a process that has already run
  the suite, so a function behind an `lru_cache` -- `lattice`, `_pdf_font` -- answers from what
  the unmutated code put there. `park_miller` 7, 9 and 11 survived that way, and
  `test_the_lattice_is_the_reference_codes` could not see them. They are killed by tests of
  `park_miller` itself: every number stays between 1 and M - 1, and the step that gives 1
  gives 1. Schrage's step is right modulo M whichever way it corrects, so the 10,000th number
  alone cannot tell.
- **A run's test selection can miss a test that kills.** `render_pdf` 54, which prints every
  panel's pictures rather than the printed ones, fails `test_a_picture_on_no_page_is_not_carried`
  when applied by hand.

Killed since, by what the tests now hold:

- **Faces unlike the gallery's**, which are all 1000 units per em, upright, proportional and
  fully named. A 2048-unit face scales its box, ascent, descent, cap height and widths to
  thousandths (`_descriptor` 66, 81, 83, 85; `_widths` 15, 20). A kern in it is written to the
  millionth (`_shown` 29, 45). Other cases:
  - italic by its angle or its selection, and fixed pitch (`_descriptor` 25, 30, 32, 33, 35,
    36, 40, 78, 79);
  - a cap height stated at `OS/2` version 2, or of 0 or 1 (`_descriptor` 52-55);
  - no `OS/2`, which takes a regular stem (`_descriptor` 61);
  - names that need cutting, missing, or absent (`_postscript_name` 1, 2, 13, 16, 26-30);
  - a CFF font's CIDFont, which maps no glyphs (`objects` 31);
  - a face that may not be subset, which goes in byte for byte, or, from a WOFF, unwrapped
    with its date (`_sfnt` 2, 6, 7, 11, 14).
- **Faces print may not embed**, in two files and two runs of a line: each glyph outlined
  exactly as outline mode outlines it, in every run, and each face said (`_outlined_run` 9,
  22, 24, 25, 27-30; `_text` 5, 11; `_faces_lettered` 13).
- **Hand-edited colours** in the rain, the veil and a caption are said, and air with no veil
  says nothing (`_colours_not_owned` 4, 6, 8-13).
- **The ends of the greys**: `#050505` on CIELAB's straight part, a grey lighter than black's
  first step, and one between its last two (`_linear` 4, `_star` 9, `black_for` 12, 16).
- **A picture with alpha**: its soft mask is an object, and the profile's number counts it
  (`_shared` 8).
- **Where a bleed mistake is said** -- a column, a slanted tier, a panel that reaches no edge --
  and a slanted outline whose every corner moves only on the sides that bleed
  (`resolve_frames` 75, 76, 199-203; `_bled` 28, 31, 34, 35, 86, 87, 89, 92, 96, 99).
- **A border round three sides** is one line, wherever the open side is listed
  (`border` 17).

Accepted above, under new numbers: in `pdf.py`, `_linear` 5, `ink` 22 (was 7), `_embedded` 6,
`_page_content` 3, 9, 10, 29, 35 and 36, `_state` 2 and 3, `_path` 23 and `_Document.write` 131
(was 126); in `solve/page.py`, `_frame` 1, `_fmt` 5 and 6, `_slanted` 30, 33, 35, 41, 87, 92, 142
and 157, the `zip(..., strict=True)` mutants now `resolve_frames` 30, 34, 38, 96, 99, 104, 146,
149, 154, 168, 172 and 176, and `_across` 5, 8 and 12; in `geometry.py`, `pointer` 20. Accepted
here:

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `pdf.py` `_star` 8, `_luminance` 1, `black_for` 11, 20 | `>` to `>=`, `<=` to `<` at CIELAB's knee and between two steps of the ramp | Both sides give the same value there: the two parts of CIELAB's curve meet at the knee, and interpolating at a step gives that step's percent from either segment. |
| `pdf.py` `ink` 5 | the CMYK table read for a grey too | No key of the table is a grey, so a grey finds no twin either way. |
| `pdf.py` `_text` 24 | a type size written to 2 places, not 6 | Core rounds every type size to 2 places (`pipeline.py`). |
| `pdf.py` `_outlined_run` 4, 7, 8 | `zip(..., strict=True)` relaxed | A run has one origin per character. |
| `pdf.py` `_outlined_run` 12, 13 | a glyph's metrics or character `None` | `_glyph_transform` reads only its origin, baseline, scale and angle. |
| `pdf.py` `_Document._shared` 15 | `tagged = None` | Read only for truth. |
| `pdf_fonts.py` `_subset` 3, 4, 14; `_sfnt` 3, 4, 5, 9, 13 | `False` to `None`, `lazy` changed | Read only for truth; lazy loading only decides when a table is decompiled. |
| `pdf_fonts.py` `_subset` 16 | `layout_features = None` | `GSUB` and `GPOS` are dropped before any feature is read. |
| `pdf_fonts.py` `_sfnt` 8, 12 | boxes recalculated when a WOFF is unwrapped | Read lazily, `glyf` is never decompiled, so there is nothing to recalculate from; a test with a wrong box keeps it either way. |
| `pdf_fonts.py` `_saved` 1 | `flavor = ""` | fontTools reads the flavour for truth, so an empty one writes a plain font file. |
| `pdf_fonts.py` `_descriptor` 20, 23 | the italic angle when there is no `post` table | `post` is a table every OpenType face must have. |
| `pdf_fonts.py` `_character_map` 17, 38 | `UTF-16-BE`, `ASCII` | Python's codec names are not case-sensitive. |
| `turbulence.py` `park_miller` 10 | `<= 0` to `< 0` | A result is 0 only for a seed that is a multiple of M, and no seed between 1 and M - 1 is. |
| `turbulence.py` `fractal_noise` 2 | `zeros_like(None)` | A 0-d zero, which broadcasts to the same sums; the alpha is cast to bytes either way. |
| `solve/page.py` `_bled` 9, 13, 16, 20, 85, 90, 95, 100 | `< REACH` to `<= REACH` | An edge on the margin is within float noise of it; one that is not is a gutter or more away, never exactly a hundredth. |
| `solve/page.py` `_bled` 97 | every corner not on the top moved to the bottom line | A slanted tier's corners all lie on its top or its bottom edge. |
| `geometry.py` `border` 16 | `range(4)` to `range(5)` | A panel whose border is drawn open has a side open and a side kept, so a start is found before the fifth. |
| `geometry.py` `border` 22, 38 | the current line `None` instead of empty | `current or [...]` and `if current` read both as empty. |

### Past `solve/` and `emit/`

`frontends/`, `core.py`, `ir.py` and `diagnostics.py` were mutated for the first time by
[`43410981157`](https://github.com/creatoan/scenet/actions/runs/43410981157)
([#345](https://github.com/creatoan/scenet/issues/345)). Two things kept mutants from
`ir.py` before a test could see them, and both are lessons for any module:

- **A decorated function is never mutated.** A pydantic validator is one, and the IR's
  checks -- every reference resolving, no ordering cycle, a page with room for its panels --
  were all in validators. Each validator now calls a plain function after its class, which
  holds the check and is mutated as usual; see the blind spot above.
- **A function that only runs at import runs before the mutant is chosen.** mutmut forks each
  mutant from a process that has imported everything, so `tag_by`, which builds a union's
  discriminator once as `ir.py` is imported, ran unmutated in every mutant's process: its 14
  mutants survived whatever the tests did. The closure it builds now calls `_tag_of`, which
  runs on every value a union validates. The mutants of `tag_by`'s own body are still built
  at import, and are accepted with the rest of `ir.py`'s survivors.

#### The definitive run

[`43478921809`](https://github.com/creatoan/scenet/actions/runs/43478921809) ran the six legs of these modules from nothing, on the commit that holds every test
below. It is the run their survivors are numbered from, and every survivor it left is in a
table here: each is a change no output can show. Each mutant killed before it was also applied
by hand to see a test fail, on the way.

#### `core.py`

351 mutants and 5 survivors, 98.6% killed. `tests/test_core_documents.py` kills what the first run left: the path and
the rule a hand-edited picture or puppet file is refused under when a Core is read back, the
kind of Core a refusal names, a Page Core's text beyond ASCII, an unknown actor's message, a
tail aimed at the face of a puppet with no mouth, and a monochrome copy of weather with no veil.

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `_check_runs` 7, 10, 11 | `zip(..., strict=True)` relaxed | The line before refuses runs that are not one per line, so the two sequences are always as long. |
| `PanelCore.to_json` 138 | `ensure_ascii=False` to `None` | `json.dumps` only asks whether it is true, and `None` is not. |
| `PageCore.to_json` 25 | `ensure_ascii=False` to `None` | `json.dumps` only asks whether it is true, and `None` is not. |

#### What holds the rest

Most survivors of the other three modules were what a refusal or a finding says -- its
message, its rule, its path, the file it names, where it points -- or what a front end reads
on the way to a Core. Two goldens hold all of that for every document of the gallery, the rule
corpus and `tests/finding_corpus/`; see [Golden outputs](#golden-outputs). The finding corpus
holds a document for each way of reaching a refusal that no other document took: a fault
inherited over a panel, a default no panel overrides, a script's every refusal, a file that is
not what it is named. What no document can reach -- an IR check the front ends always refuse
first, a page's room to the unit, the words a script is read by -- has a test of its own:
`tests/test_page_room.py`, `tests/test_ir_checks.py`, `tests/test_diagnostics_library.py`,
`tests/test_locating.py`, `tests/test_summaries.py` and `tests/test_script_words.py`.

Checking with a library of one puppet the shipped one lacks, which
`tests/test_diagnostics_library.py` does at every step, found a bug: a puppet that draws
nothing but a face crashed balloon placement. It is fixed in `solve/speakers.py`.

Twelve `locate(text, path) or locate(text, prefix) or DOCUMENT_START` in `diagnostics.py` were
two lookups where one decides: `locate` is `None` only for text that does not compose, and then
no path in it is found. The second lookup is gone, and with it a dozen mutants no test could
see.

#### `ir.py`

683 mutants and 16 survivors, 97.7% killed.

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `_names_a_puppet_or_a_figure` 23, 28 | the title of the error a wrap validator raises | pydantic re-raises it under the model's own title. |
| `tag_by` 1, 2, 3, 4, 5 | the closure `tag_by` builds | `tag_by` runs once, as `ir.py` is imported, before a mutant is chosen; what it builds only calls `_tag_of`, which is mutated. |
| `_tag_of` 5, 9 | the attribute read from a member that is not a mapping | A value that is not a mapping is already a member of the union, which the plain union accepts as the tagged one does. |
| `_check_references_resolve` 19 | `continue` to `break` after an off-panel voice is looked at | Only the object of a relation can be looked at, and it is the last of the two roles. |
| `_check_ordering_is_consistent` 27 | a finished node marked `None` | Every test of a node's colour reads `None` as it reads `_DONE`: not unvisited, not on the stack. |
| `_check_ordering_is_consistent` 44, 46, 47 | the cycle's path without a culprit | Every edge of the ordering is written by a relation, so a cycle always has one. |
| `_check_figures` 71 | `next(..., None)` without its default | Every relation's subject is in the cast, which is all figures by then, so one is always found. |
| `check_placements` 32 | where a placement was first seen, kept as `None` | Only whether a panel was placed is read, never where. |

#### `diagnostics.py`

1,612 mutants and 74 survivors, 95.4% killed.

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `Diagnostic.fingerprint` 17 | `"utf-8"` to `"UTF-8"` | Python's codec names are not case-sensitive. |
| `_uri_for` 11 | `if path.parts` always true | A file's path always has a part. |
| `_rule_for_scenet_error` 9 | `and` to `or` | Every rule an error names is in the catalogue: `test_every_rule_named_in_the_source_is_in_the_catalogue`. |
| `_path_for_scenet_error` 4, 7, 11 | an error's `loc` read with another default, or none | Every error that reaches it carries a tuple `loc`; one that did not would give the prefix either way. |
| `_message_of` 1 | `and` to `or` | Every exception that reaches it has one argument, which is its text. |
| `_diagnose_setting` 4, 8, 9, 10, 11 | the `loc` given to `load_image` | The finding's path is the function's own; the error's `loc` is never read. |
| `_diagnose_figures` 15, 19, 20, 21, 22 | the `loc` given to `load_image` | The finding's path is the function's own; the error's `loc` is never read. |
| `_diagnose_lettering` 11, 14, 17, 18, 19, 20 | the path a font error without one is given | Every font error carries the path the font was named at. |
| `_over_the_word_limits` 29 | the panel's note inserted second, not first | Findings are sorted into source order before they are returned. |
| `_diagnose_panel` 1 | `deep` defaults to true | Both callers pass it. |
| `_diagnose_panel` 4, 6 | `settle` without where a left-out voice stood | That only puts the voice's balloon on its side, which no check reads. |
| `_diagnose_scene` 104, 105, 107 | a panel's own `direction:` kept, or stripped from the others | It is reported where it is written, and a panel's direction changes no other finding of it. |
| `_diagnose_scene` 112, 113 | the path of a composition error with none | Every composition error is at the `over:` it is about. |
| `_diagnose_scene` 164 | `if defaults` always true | Merging no defaults into a panel gives the panel. |
| `_diagnose_scene` 169, 170, 171, 186, 194 | where a left-out voice stood, lost or read without the defaults | That only puts the voice's balloon on its side, which no check reads. |
| `_diagnose_scene` 199 | a path inside another file read as the document's | No path inside a puppet file or a contract is a path the document's defaults hold. |
| `_diagnose_scene` 235, 236, 239, 240 | `compile_book` without the file or the folder | Given a file and no folder, it reads from the file's folder, which is the folder given. |
| `_has_path` 9 | an index one past the end | A path inherited from a default is never longer than the default's list. |
| `_in_source_order` 7, 8, 9, 10, 11, 12, 13 | the place a finding with no region sorts at | Every finding has a region. |
| `diagnose_script` 8, 10 | the parser not told the file | The file only prefixes the text of its errors, which a finding leaves out. |
| `diagnose_script` 78 | the notes replacing the findings before them | Those are errors only, and with an error the notes are never reached. |
| `diagnose_script` 101 | `len(path) > 1` to `> 2` | A word count's path is `("script",)` or four steps long. |
| `diagnose_script` 123, 124, 127, 128 | `compile_script` without the file or the folder | Given a file and no folder, it reads from the file's folder, which is the folder given. |
| `diagnose_script` 144, 147 | a compile error with no panel | A script has no pages yet, so every compile error is a panel's and names it. |
| `_script_line` 3, 5 | a line past the end | No finding is on a line past the end. |
| `_script_front_matter` 6, 13, 28 | an empty front matter written, counted from `None`, or not a mapping | Without front matter no finding is located in it; counting from `None` is counting from the start; front matter that is not a mapping is refused first. |
| `_diagnose_script_setting` 24, 42, 44 | `continue` to `break`, or the heading's line as no line | `_diagnose_setting` gives at most one finding a panel; a picture a panel does not declare is named by its `@setting:`. |
| `_diagnose_script_figures` 27, 30, 32 | `continue` to `break`, or a path's head or index read otherwise | A panel's figure faults are one fault of its picture or contract, or faults of its lines, never both; and none is at an index outside `script`. |
| `diagnose_file` 3 | the file read in the default encoding | That is UTF-8 where mutmut runs; on Windows, where it is not, the findings golden of the gallery's French scripts fails in the Windows job. |
| `diagnose_file` 5 | `"utf-8"` to `"UTF-8"` | Python's codec names are not case-sensitive. |

#### `frontends/`

`frontends/common`: 502 mutants and 4 survivors, 99.2% killed. `frontends/yaml`: 374 mutants and 4 survivors, 98.9% killed.
`frontends/script`: 2,182 mutants and 60 survivors, 97.3% killed.

| Mutants | Change | Why it cannot change an output |
|---|---|---|
| `_figures_stand_alone` 55 | `next(iter(camera), None)` without its default | An empty camera returns before it, so the mapping always has a first key. |
| `_merge_misspellings` 53, 56 | `n=1` left out, or 2 | Only the first match is read, and `get_close_matches` puts the best first. |
| `normalise_layout` 16 | a page that is not a mapping kept as `None` | pydantic refuses `None` in the words it refuses any page that is not a mapping. |
| `_validate_panels` 73, 80 | `if defaults` always true | Merging no defaults into a panel gives the panel. |
| `syntax_error_region` 24 | `getattr(mark, "buffer")` without its default | Every PyYAML mark has a `buffer`, `None` when it holds no text. |
| `syntax_error_region` 30 | `rstrip("\0")` to `rstrip("XX\0XX")` | An `X` goes too only off a buffer whose last line has no newline, and the mark of an error at its end is then on that line, so the count of lines is never read. |
| `_PanelDraft.line_of` 5, 6, 7, 15 | a fault's event index read otherwise | No fault of a script panel is at `("script",)`, at `("script", i)` or past its last event. |
| `_PanelDraft.line_of` 19, 21 | `max(..., key=len)` without its key | The directives a fault falls under are prefixes of its path, so the longest is also the greatest. |
| `_split_front_matter` 7, 19 | `count("\n", 0, ...)` from `None` | Counting from `None` is counting from the start. |
| `_split_front_matter` 65, 66 | the branch with no line | Every YAML error has a mark. |
| `_check_prose` 4 | words joined by `"XX XX"` | `unholdable` names the first character it cannot hold, and the join adds none. |
| `_recognisable` 7, 9 | `count=1` left out, or 2 | The heading pattern is anchored at the start, so it matches once at most. |
| `_read_page_heading` 30 | a note of `"XXXX"` | A note of `"XXXX"` is no count. |
| `_read_panel_heading` 37, 38 | `"CASE"` spelled otherwise | `_is_a_panel_label` only asks whether the keyword is `PANEL`. |
| `_Reader.__init__` 10, 11, 16 | a first value | A panel heading clears the cue and the speech, a page heading the count, before either is read. |
| `_Reader.heading` 7 | a page's line kept as `None` | A page's line is never read. |
| `_Reader.caption` 24 | `if speaker` always true | A missing speaker is `None` either way. |
| `_Reader.end_of_page` 3 | the page heading cleared to `""` | Every page heading sets it again before it is read. |
| `default_tiers` 2, 11 | the entry for one panel, or four, moved | The rows computed for one panel and for four are `[1]` and `[2, 2]`. |
| `_modifiers` 8 | `parentheticals or "XXXX"` | No parenthesis is found in `"XXXX"`. |
| `_unquoted` 3, 4 | `len(text) > 1` moved by one | A text of one or two characters that opens and closes with a quote has nothing inside to keep. |
| `_panel_casts` 2 | a panel before any PAGE heading looked up by page | Without pages, every panel is named by its label, which the lookup falls back to; with pages, a panel before the first is refused. |
| `_panel_casts` 14, 15, 19 | the line or page given to `_read_panel_heading` | The pre-scan reads only a heading's label, which neither decides. |
| `_panel_casts` 50 | `continue` to `break` after a `@cast:` that is not YAML | That panel is refused at that line when it is read, before any later panel is. |
| `_inherited_casts` 11, 14, 15 | `zip(..., strict=True)` relaxed | The names are made from the panels, one each. |
| `_inherited_casts` 22, 28 | a panel before any PAGE heading looked up by page | Without pages, every panel is named by its label, which the lookup falls back to; with pages, a panel before the first is refused. |
| `_read_script` 1 | `offset` defaults to 1 | Its one caller passes it. |
| `_apply_directive` 94 | `key == "cast"` always true | Every other directive's value is not a mapping, which `_reserved_name` reads as no name. |
| `_camera_word` 25 | French words of more than four letters, not three | No French shot or angle is four letters long. |
| `_check_direction` 6 | the front matter's length `None` | Then every line is searched, and the key's first line is the front matter's. |
| `parse_script_document` 25, 45 | the front matter's length `None` | Then every line is searched, and the key's first line is the front matter's. |
| `_off_panel` 67, 69, 84, 86 | who leaves read otherwise, or a missing script defaulted | A voice nobody casts is in no relation but `looking_at`, which stays either way; a panel somebody leaves from off panel has a script. |
| `_over_target` 15, 16 | the composition error's path written otherwise | Only the name in the path is read. |
| `_composed` 17, 20, 21, 22, 25 | the composition error's path read otherwise | Every composition error is at `("panels", name, "over")`, and only the name in it is read. |
| `_composed` 37, 38 | the branch with no line | Every `@over:` has a line. |
| `_first_fault` 18, 20 | `min` without its key | The faults are tuples that start with their line, so the first line is the least either way. |
| `_first_fault` 28, 29 | the branch with no path | Every fault of a panel's IR names a field. |

### Exploring with fresh seeds

The same workflow's second job runs the property tests under the `explore` profile: random
seeds, 300 examples each. A failure prints the shrunk document and a `@reproduce_failure`
line. Pin the document as an `@example(...)` on the property, so the fixed run covers it from
then on, and fix the bug in its own pull request.
