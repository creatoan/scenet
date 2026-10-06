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
