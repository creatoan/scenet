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
gallery through `scenet build`, in every CI job -- Linux on 3.12 and 3.14, and Windows -- and
compares the bytes on disk with what is committed:

- `tests/golden/core/` holds every Panel Core and Page Core, so a layout change is reviewed
  coordinate by coordinate in the diff;
- `tests/golden/digests.json` holds the SHA-256 of every SVG: panels, overlays, live text,
  strips and pages.

It also builds the gallery in two processes with different `PYTHONHASHSEED`s, and one scene
and one script from a relative path, an absolute one and another directory; each must
write the same bytes, and none may hold the path it was built from.

After a change that is meant to move the output, regenerate the goldens and read the diff:

```bash
uv run python scripts/update_golden.py
```

`--check` exits 1 and names every stale golden without writing anything.

## The reference as a contract

`docs/reference/cli.md` is the specification, so `tests/test_reference_contract.py`
holds the code to it, failing in both directions -- documented and missing, or present and
undocumented:

- each command's options, their choices and the values marked as defaults, against
  `scenet.cli.build_parser()`;
- each command's exit-status table, against a scenario that produces every code in it;
- the extension table, against the frontends `build` reads with;
- every rule except `internal`, against a document in `tests/rule_corpus/` named after it
  that must produce exactly one finding of that rule, and the rule objects SARIF emits
  against the catalogue;
- the behavioural sentences -- output naming, clashes, `--quiet`, what `check` writes,
  SARIF on stdout -- one test each.

The `scenet` lines of every `bash` block in the documentation run as well, in-process in a
copy of `examples/` (`tests/shell_examples.py`). `pip`, `uv`, `git` and the like never run.
A block that needs a file the reader creates along the way is marked `<!--- skip: next -->`.

A new rule needs a corpus document; a new option needs a definition in the reference. The
tests say which.

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
- the glyph scale written to two places again, the bug fixed in #99, which the SVG check
  caught at the first panel with lettering.

## What the properties found

Each was fixed in its own pull request, with a failing test first, before the property
that trips on it landed:

| Found | Fixed in |
|---|---|
| A control character in a panel wrote an SVG no XML parser accepts | #101 |
| A document nested a few hundred levels deep ended in `RecursionError` | #103 |
| An inset in a narrow panel was drawn outside it | #104 |
| `a left_of a` was filed under `invalid-field`, not `reflexive-relation` | #105 |
| A misspelled required key was reported twice | #106 |
| A broken `over:` was located at the whole `panels:` block | #107 |
| A syntax error at the end of a file pointed past its last line; a block value at its first field | #108 |
| An unknown speaker was located one step short of its `by:` | #109 |

## Mutation testing

Coverage shows which lines ran, not whether any assertion would notice them changing.
[mutmut](https://github.com/boxed/mutmut) does notice: it makes one small edit at a time to
the solver and the emitters -- `<` becomes `<=`, a constant is nudged, an argument dropped --
and reports every edit the suite still passes. Each survivor is a behaviour nothing checks.

It runs weekly, and on demand, in `.github/workflows/mutation.yml`. The only pull request
it runs on is one that changes the workflow itself: a full run takes far longer than a review
should wait. The job summary gives the score and lists the survivors. The `mutmut-results`
artifact holds the same list, and `survivors.diff`: every survivor's change, as `mutmut show`
prints it, which is what triage starts from. A run on one file is a `workflow_dispatch` with
`path` set, on whichever branch holds the tests to try. It is not a required check, and there is no threshold until the baseline
below has been worked down.

**Why mutmut.** Our imports are slow -- numpy, shapely, kiwisolver, fontTools -- and the suite
takes about 40 seconds. mutmut forks each mutant from a process that has already imported
everything, runs only the tests that reach the mutated function, and resumes where it left
off, re-testing only functions whose code changed. A tool that ran the whole suite once per
mutant would take days.

**Running it.** It is in its own dependency group, so a plain `uv sync` does not install it:

```bash
uv sync --group mutation
ulimit -v 2097152
uv run mutmut run --max-children 4
uv run mutmut results
uv run mutmut show <mutant>
```

The `ulimit` caps each process at 2 GiB. A few mutants allocate without bound -- `/` turned
into `*` in the rain or snow density asks for millions of streaks -- and, uncapped, one of
them can fill a 16 GB machine before mutmut's timeout fires. Capped, it ends in a
`MemoryError` and counts as killed. A test process needs under 1 GB.

`[tool.mutmut]` in `pyproject.toml` limits it to `src/scenet/solve/` and `src/scenet/emit/`,
mutates only lines the tests cover, and runs mutants without the coverage floor, doctests or
the documentation examples. To try one file, run the workflow by hand with its `path` input.

**On Windows**, mutmut needs `fork()`, so run it under WSL with a Linux distribution:

```bash
wsl --install -d Ubuntu
```

then, inside WSL, clone the repository and run the commands above. A checkout on the Windows
side, under `/mnt/c/`, works but is several times slower.

**Known blind spot.** mutmut 3 does not mutate decorated functions. In `solve/` and `emit/`
those are nine `@property` accessors and one cached loader, and none of them is ever mutated:

| Function | Decorator | Lines |
|---|---|---|
| `solve/camera.py::CameraSolution.was_pulled_back` | `@property` | 8 |
| `solve/camera.py::CameraSolution.head_top_y` | `@property` | 3 |
| `solve/balloons.py::TailRoute.is_curved` | `@property` | 7 |
| `solve/text.py::TextBlock.aspect` | `@property` | 7 |
| `solve/text.py::TextBlock.raggedness` | `@property` | 5 |
| `solve/text.py::FontMetrics.units_per_em` | `@property` | 3 |
| `solve/text.py::load_metrics` | `@functools.lru_cache` | 3 |
| `solve/backdrop.py::_Plot.width` | `@property` | 3 |
| `solve/staging.py::Placement.origin` | `@property` | 3 |
| `solve/staging.py::_Extent.centre_offset` | `@property` | 2 |

The undecorated methods of the same classes are mutated as usual. `was_pulled_back` and
`head_top_y` are the ones that matter: they are part of the framing geometry, and until
mutmut reaches them the shot-type tests in `tests/test_camera.py` and the golden Cores are
what guard them.

### Baseline

The first full run with the golden outputs, made locally on four cores in about 57 minutes,
produced 4,094 mutants: **3,761 killed (91.9%)** and 333 survivors. The three that ran out of
memory, described above, are among the killed. By module:

| Module | Survivors | Triage |
|---|---|---|
| `solve/balloons.py` | 123 | done: 16 accepted, below |
| `solve/text.py` | 50 | done: 14 accepted, below |
| `solve/page.py` | 49 | done: 23 accepted, below |
| `solve/backdrop.py` | 32 | |
| `solve/staging.py` | 22 | |
| `emit/page.py` | 18 | |
| `emit/svg.py` | 16 | |
| `emit/debug_svg.py` | 9 | |
| `solve/camera.py` | 7 | |
| `emit/strip.py` | 7 | |

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

**`solve/text.py`** -- triaged: of the 50 survivors, 36 are killed by tests in
`tests/test_text.py`, and these 14 are accepted. Most of the 36 were in `FontMetrics`'s
constructor, and survived for a reason worth knowing: `load_metrics` is cached, so a test
that measures only through it uses the instance built at import and never runs the
constructor under a mutant. The tests now build one of their own.

| Mutant | Change | Why it cannot change an output |
|---|---|---|
| `FontMetrics.__init__` 4, 6, 8 | `lazy=True` to `None`, `False`, or left out | Laziness decides when fontTools parses a table, not what it reads from it. |
| `FontMetrics.__init__` 27, 29, 32 | the default for a missing `.notdef` changed | Every TrueType font has a `.notdef`, glyph 0, with an advance in `hmtx`, so the default is never used. |
| `FontMetrics.advance` 6, 8, 10 | the default for a glyph with no advance changed, or always looked up | Every glyph the character map names has an advance in `hmtx`; a character with no glyph looks up `None`, which is not a glyph name, and gets `.notdef` either way. |
| `FontMetrics.glyph_outlines` 6 | `name is None or name not in glyph_set` to `and` | Every glyph the character map names is in the glyph set, so the second test only ever agrees with the first. |
| `candidate_measures` 16 | runs end one word further | The extra run repeats `words[start:]`, a width already in the set. |
| `layout_text` 18 | `line_widths=()` left out | `()` is its default. |
| `layout_text` 73 | `score < best_score` to `<=` | An exact tie between two different wrappings needs two different blocks to score the same float; equal wrappings tie, and either is the same block. |
| `layout_text` 91 | the fallback joins words with `XX XX` | The fallback is reached only when every block is 0 wide. With two words or more, the space between them has width, so the fallback only ever sets one word. |
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

### Exploring with fresh seeds

The same workflow's second job runs the property tests under the `explore` profile: random
seeds, 300 examples each. A failure prints the shrunk document and a `@reproduce_failure`
line. Pin the document as an `@example(...)` on the property, so the fixed run covers it from
then on, and fix the bug in its own pull request.
