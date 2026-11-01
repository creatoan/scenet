# Command line

```
scenet [--version] <command> [options]
```

Four commands: `build` compiles a document, `check` validates one without compiling it,
`schema` emits the JSON Schema, and `mcp` serves all of that to a model. A bare `scenet` prints help to stderr and exits **2**
— it did nothing, and a script chaining off its status should not read that as success.

## `scenet build`

```
scenet build SOURCE [-o OUTPUT] [--core] [--debug] [--conditioning] [--live-text] [--mono] [--no-aria] [--embed-images] [--strip] [--quiet]
```

Compiles `SOURCE` to SVG. The frontend is chosen by extension:

| Extension | Read as |
|---|---|
| `.panel.yaml`, `.scene.yaml`, `.yaml`, `.yml` | YAML — single panel or a `panels:` sequence |
| `.script` | Comic script |

### Options

`-o`, `--output PATH`
: Where to write. Defaults to the source's name with an `.svg` extension, alongside it.
  Note that `duel.panel.yaml` becomes `duel.svg`, not `duel.panel.svg`. A directory, one that
  exists or one written with a trailing `/` such as `out/`, takes that default name inside
  it, so `-o .` writes `duel.svg` to the current directory. Any other path is the SVG file
  itself, and every other output is named after it.

`--core`
: Also write the resolved Panel Core as JSON — every coordinate the compiler chose, in a
  format you can read, diff and hand-edit. See [Panel Core](panel_core.md).

`--debug`
: Also write a diagnostic overlay showing the geometry the solver was working against:
  silhouette hulls, face exclusion zones, named anchors, gaze vectors and tail routes.
  This is usually the fastest way to see why a panel came out the way it did.

`--conditioning`
: Also export each panel's staging for image models, as five files beside its SVG: the pose as
  OpenPose JSON, boxes with phrases, a depth map, a mask, and the semantics. No model runs:
  each is another emitter reading Panel Core, text, JSON or SVG, and byte-identical like the
  rest. Per panel only; a page's frames are in its Page Core (`--core`). See
  [export for image models](../howto/export_for_image_models.md).

`--live-text`
: Emit selectable `<text>` elements instead of glyph outlines. Smaller files and
  selectable text, but the result depends on the reader having a metrically compatible
  font installed, and on the renderer kerning it as the compiler measured it — browsers
  do by default. The default emits outlines, which makes the file genuinely
  self-contained.

`--mono`
: Draw every value as its grey and ignore its colour: a black-and-white edition of a document
  drawn in [`palette: tinted`](language.md#palette), made without editing it. Every panel, page and
  strip is byte-identical to what the same document writes with `palette: mono`, because a
  palette only ever adds a colour beside a value the compiler had already decided on its grey.
  Panel Core and the exports for image models are unaffected: `--core` still records the
  palette and its colours.

`--no-aria`
: Write no accessibility markup. By default each panel is an image a screen reader can read
  — `role="img"`, named by its `<title>` with what it shows and then everything said in it, in
  reading order — and a strip or a page is a named group of them; see
  [accessible output](../howto/make_accessible_output.md). This leaves all of that out, for a
  pipeline that post-processes the SVG, and is otherwise byte-identical: the same file less
  those attributes and elements. Debug overlays never carry it.

`--embed-images`
: Write each [supplied picture](language.md#an-image-behind-the-cast) into the SVG as a
  `data:` URI, so the file stands alone. By default a picture is linked by the path the
  document wrote, which a viewer reads from beside the SVG: that finds it when the SVG is
  written beside the document, as it is by default. Written anywhere else, the build says so
  in a `note:`, since the link will not resolve there; an SVG shown as an `<img>`, or turned
  into a PNG, loads no linked file at all. Embedding is byte-identical for the same picture.

`--strip`
: For a document of more than one panel, also lay every panel out side by side in reading
  order, as one extra file. Ignored when there is only one panel, a one-panel scene
  included.

`--quiet`
: Suppress the `wrote` and `note:` lines. You do not normally want this: the notes are
  where the compiler tells you it did something you did not ask for. Each kind has a name,
  listed with what to do about it in
  [Work out why a panel looks wrong](../howto/debug_a_layout.md#1-read-the-notes).

### Output naming

A single-panel document writes to the requested name. A multi-panel document suffixes each
panel with its own name, so the mapping back to the source stays obvious:

```
sequence.scene.yaml  →  sequence.establishing.svg
                        sequence.reaction.svg
                        sequence.strip.svg          (with --strip)
```

A document that lays its panels out with `pages:`, or a comic script with `PAGE` headings, also
writes each page beside them, with its Page Core and overlay when `--core` and `--debug` ask for
them. Pages are numbered by position, from 1, whatever a script's headings call them:

```
story.scene.yaml     →  story.page-1.svg
                        story.page-1.core.json      (with --core)
                        story.page-1.debug.svg      (with --debug)
```

With `--conditioning`, each panel's exports for image models are named after its SVG:

```
duel.panel.yaml      →  duel.svg
                        duel.pose.json              (with --conditioning)
                        duel.boxes.json
                        duel.depth.svg
                        duel.mask.svg
                        duel.semantics.json
```

Two outputs that would be the same file are a usage error, exit 2, and nothing is written: a
panel named `page-1` beside a page, `strip` beside the strip, or `x.debug` or `x.depth` beside
panel `x`'s overlay or depth map. One file silently replacing the other is the kind of loss
Scenet refuses everywhere else. Names are compared ignoring case, as Windows and macOS compare them, so a document
writes the same set of files everywhere. A panel name holding `/` or `\` cannot be part of
a file name and is refused the same way.

### Exit status

| Code | Meaning |
|---|---|
| 0 | Compiled |
| 1 | The document could not be compiled — reported as a plain message, not a traceback |
| 2 | Usage error, or the source file does not exist or has an extension no frontend reads |

Every error the compiler raises inherits `ScenetError`, and all of them mean "your panel
cannot be compiled" rather than "scenet broke". They print as one line. A traceback from
`scenet` is a bug worth reporting.

### Examples

```bash
scenet build examples/duel.panel.yaml
```

```bash
scenet build examples/duel.panel.yaml --core --debug
```

```bash
scenet build examples/sequence.scene.yaml --strip
```

```bash
scenet build examples/umbrella.script --strip -o out/umbrella.svg
```

## `scenet check`

```
scenet check SOURCE... [--format {text,sarif}] [-o OUTPUT] [--quiet] [--deep]
```

Reports everything wrong with one or more documents and exits non-zero if anything is an
error. A **note** reports a house limit rather than a contradiction — a balloon over the
words a publisher asks for, say — so the document still builds, and a note alone never
fails the check.
Nothing is written unless you ask for it — no SVG, no Panel Core.

Unlike `build`, this does not stop at the first fault. pydantic reports every field error
at once and several files are reported together, because whoever is fixing them — a person
or an agent — wants the whole list rather than one round trip per mistake.

Beyond validating the IR, `check` resolves every cast member's `reference`, `pose` and
`expression` against the puppet library — the IR alone cannot tell `pointing` from
`smirking`, since both are just strings until something looks them up. The library is
read once per document, only when there is a cast to check against it, so a document
with no cast pays nothing extra. This is still the cheap pass: no solver, no font
metrics, no balloon placement — those are what `--deep` adds.

### Why this exists

**No JSON Schema can catch the errors that matter most here.** The interesting checks are
`model_validator`s: every actor id in `staging` and `script` resolving to a cast member,
and the `left_of`/`right_of` graph being acyclic. Neither is expressible in JSON Schema,
and both are exactly what a generator gets wrong. So structured diagnostics — not the
published schema — are what make a generate/validate/repair loop work.

### Options

`--format text` (default)
: One line per finding on stderr, `file:line:column: rule: message`, or
  `file:line:column: note: rule: message` for a note, where GCC and Clang put a
  severity. What a person reads. `file: ok` follows on stdout for each document when
  none has an error, notes or not.

`--format sarif`
: [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html), the
  OASIS standard GCC, Clang and MSVC emit and GitHub code scanning ingests directly.
  Nothing but the document reaches stdout, so redirecting it produces a file a parser
  accepts. To see the findings in VS Code, see
  [Findings the schema cannot see](../howto/editor_support.md#findings-the-schema-cannot-see).

`-o`, `--output PATH`
: Write the report to this file instead of the terminal, in either format. In text format
  the file holds the findings, one per line, and is empty when every document is valid.
  It names a file, so a directory is refused.

`--quiet`
: Suppress the per-file `ok` line. Findings are always reported — this hides the
  reassurance, never the diagnosis.

`--deep`
: Also run the full compiler on any document that passes every cheap check, to
  additionally catch `layout` and `balloon-placement` — two rules in the catalogue that
  the cheap pass cannot produce, because they only surface once the solver actually
  runs. Off by default: it costs a real compile, including font metrics. Skipped for a
  document the cheap pass already found something wrong with, so a document with a bad
  pose reports that once rather than a second, worse-located finding for the same fault.

### Exit status

| Code | Meaning |
|---|---|
| 0 | No document has an error; notes may have been printed |
| 1 | At least one error |
| 2 | Usage error, or a source file does not exist or has an extension no frontend reads |

The status means the same thing in both formats, so CI can key off it without parsing
anything.

### Rules

Every finding carries a stable `ruleId`. These identifiers **do not change across
releases**: a `ruleId` that moves silently closes every alert that referenced the old one
and opens a duplicate under the new one, so renaming one is a breaking change even though
nothing stops compiling.

A rule's level is part of it too. An **error** is a contradiction the compiler cannot
build past; a **note** is a house limit a document can exceed and still compile. SARIF
carries the level in both `defaultConfiguration` and each result, so an editor shows a
note as information rather than a red squiggle.

| Rule | Level | Raised when |
|---|---|---|
| `scenet/syntax` | error | The file is not valid YAML, or is empty; in a comic script, its front matter. A line indented to match no line above it is said to be |
| `scenet/duplicate-key` | error | A key written twice in one mapping, which YAML would drop silently; in a comic script, a directive written twice in one panel, or `@script:` |
| `scenet/not-a-mapping` | error | The top level is a list or a scalar |
| `scenet/unknown-key` | error | A key the language does not define — usually a typo |
| `scenet/missing-field` | error | A required value was not supplied |
| `scenet/invalid-field` | error | A known key holding the wrong type or an out-of-range value |
| `scenet/panel-geometry` | error | Non-positive size, or margins leaving no usable area |
| `scenet/unknown-actor` | error | An id in `staging` or `script` that is not in `cast` |
| `scenet/off-panel-speaker` | error | A line spoken from off panel by somebody drawn in the panel |
| `scenet/unbalanced-emphasis` | error | An underscore that opens emphasis in a line of `text`, with none to close it |
| `scenet/reflexive-relation` | error | A relation relating an actor to itself |
| `scenet/caption-speaker` | error | `by` on a caption whose `kind` is not `spoken` |
| `scenet/ordering-cycle` | error | `left_of`/`right_of` relations that form a cycle |
| `scenet/composition` | error | An `over:` chain that is missing or cyclic |
| `scenet/panel-direction` | error | A panel of a scene that writes `direction`, or a comic script's `@direction:`: the reading direction is the whole document's |
| `scenet/duplicate-panel` | error | Two panels in a comic script with the same name, even counting pages |
| `scenet/page-layout` | error | A page placing a panel that does not exist, or one twice, two stacked columns side by side, two insets that overlap, an inset too big for its panel, a slant that cannot apply or is too steep, or no room for its tiers |
| `scenet/unknown-puppet` | error | A `reference` naming a character the library lacks |
| `scenet/unknown-place` | error | A setting's `place` naming one the library does not have |
| `scenet/conflicting-setting` | error | A setting that names a `place` and also lists `masses`, or names an `image` beside a place, masses or a `horizon` |
| `scenet/unknown-pose` | error | A `pose` naming one its puppet does not declare |
| `scenet/unknown-expression` | error | An `expression` naming one its puppet does not declare |
| `scenet/image-file` | error | A picture in `setting.image` that is absolute, missing, not a PNG or JPEG, turned by its EXIF orientation, or named by text with no folder |
| `scenet/artwork-contract` | error | A picture whose figures the panel casts has no artwork contract beside it (`art/p01.png` → `art/p01.art.yaml`), or one that is not YAML, repeats or misspells a key, holds a value out of place, puts a point off the picture, or was measured on a picture of another size. Reported in the contract when the document is checked as a file |
| `scenet/unknown-figure` | error | A cast `figure` in a panel that names no picture, or a line spoken or sound made by a figure the panel's picture does not draw |
| `scenet/conflicting-cast` | error | A cast member with both `reference` and `figure`, a puppet's `pose`, `expression`, `marks`, `at` or `facing` on a figure, a cast mixing puppets and figures, or two members playing one figure |
| `scenet/figure-staging` | error | A staging relation naming a figure a picture draws, or a `camera` on a panel whose cast is all figures |
| `scenet/font-file` | error | A font in `lettering.font` that is absolute, missing, not a font, or named by text with no folder |
| `scenet/layout` | error | Valid, but no layout satisfies its required constraints (`--deep` only) |
| `scenet/balloon-placement` | error | No legal position exists for a balloon (`--deep` only) |
| `scenet/sfx-placement` | error | No legal position exists for a sound effect (`--deep` only) |
| `scenet/word-limit` | note | A balloon or caption over about 25 words, or a panel over about 50: Dark Horse's limits |
| `scenet/panel-count` | note | A comic script's `PAGE ONE (five panels)` names a count its panels do not match |
| `scenet/looks-like-dialogue` | note | A cue in a comic script with nothing said under it, or a name in capitals with a line under it outside any panel |
| `scenet/dropped-relation` | note | A shared staging relation left out of a panel its actor is left out of: `(OP)` in a script, or `cast: {name: null}` |
| `scenet/internal` | error | A failure with no more specific rule — worth reporting |

### Source positions

A finding is located in the file it is about, which is usually the document checked. A fault inside
a picture's [artwork contract](asset_contract.md#artwork-contracts) is located in the contract —
its own path, line and column — since that is the file to open to fix it; checked as text, with no
file of its own, the document points at the line naming the picture instead.

`yaml.safe_load` discards the position of every value, so the document is composed a
second time with `yaml.compose`, whose node tree carries `start_mark` and `end_mark`. Those
marks are 0-based and SARIF is 1-based; the conversion happens once, at that boundary.

`ruamel.yaml`'s `.lc` marks would do the same job and are what one usually reaches for.
They were not used: PyYAML is already a dependency, so a second YAML implementation in the
runtime — and in the licence gate — would buy nothing.

Comic scripts are line-oriented, so a finding there carries a line and no column. A script
line is prose, and pointing at a character within it would imply a precision the parser
does not have. SARIF could say "line 5" with `startLine` alone, but GitHub code scanning
requires all four bounds, so the region runs from column 1 to the end of the line, and an
editor underlines the whole line. The text format prints column 1.

Columns count Unicode code points, and the SARIF run says so with `columnKind`. An editor
that counts UTF-16 code units, as VS Code does, converts them.

### Fingerprints

Each result carries a `partialFingerprints` entry under `scenetDiagnostic/v1`, derived
from the rule, the structural path, the message and the file — deliberately **not** from
the line number. A fingerprint keyed on position changes whenever anybody adds a comment
at the top of the file, which turns one long-standing alert into a new alert on every
edit, and de-duplicating alerts is the entire point of the field.

The file enters as the `uri` the result reports, not as you typed it, so `a.panel.yaml`
and its absolute path give one fingerprint.

### Examples

```bash
scenet check examples/duel.panel.yaml
```

```bash
scenet check examples/gallery/*.panel.yaml examples/gallery/*.scene.yaml
```

```bash
scenet check --format sarif examples/duel.panel.yaml > results.sarif
```

```bash
scenet check --deep examples/gallery/*.panel.yaml examples/gallery/*.scene.yaml
```

Uploading to GitHub code scanning, which is how findings become annotations on a pull
request:

```yaml
- run: >-
    uv run scenet check --format sarif -o results.sarif
    examples/gallery/*.panel.yaml examples/gallery/*.scene.yaml
- uses: github/codeql-action/upload-sarif@v4
  with:
    sarif_file: results.sarif
```

### As a library

The same findings are available without the process boundary:

```python
from pathlib import Path

from scenet.diagnostics import diagnose_source, to_sarif

source = """
cast:
  alice: {reference: alice}
script:
  - say: {by: bpb, text: Hello}
"""

found = diagnose_source(source, source=Path("duel.panel.yaml"))
finding = found[0]

assert finding.rule == "unknown-actor"
assert finding.path == ("script", 0, "say", "by")
assert finding.region.start.line == 5

document = to_sarif(found, root=Path.cwd())
assert document["runs"][0]["results"][0]["ruleId"] == "scenet/unknown-actor"
```

The assertions are the point: this block is executed by the test suite, so an example
that stopped being true would fail the build rather than quietly misinform.

`diagnose_file` is the same thing for a path on disk, and picks the frontend by
extension.

`scenet.diagnostics` is a public module. It is not re-exported from the `scenet` package
namespace, because it reads the package version and importing it from `__init__` would
close an import cycle.

## `scenet schema`

```
scenet schema [-o OUTPUT] [--scene | --artwork]
```

Emits the JSON Schema for a panel document, derived from the same pydantic models the
compiler validates against. Editors use it for completion and inline validation, so what
the editor suggests cannot drift from what compiles — see
[editor support](../howto/editor_support.md).

`-o`, `--output PATH`
: Write to this file instead of stdout. It names a file, so a directory is refused.

`--scene`
: Emit the multi-panel scene schema instead of the single-panel one. A scene allows the
  same keys as a panel — where they act as defaults every panel inherits — plus `panels:`,
  whose members may additionally carry `over:`.

`--artwork`
: Emit the schema for an [artwork contract](asset_contract.md#artwork-contracts), the
  `*.art.yaml` file beside a supplied picture that declares the figures it draws. What a
  schema cannot say — every point on the picture, every region a simple polygon, the size
  the picture's own — `scenet check` does.

```bash
scenet schema -o panel.schema.json
scenet schema --scene -o scene.schema.json
scenet schema --artwork -o artwork.schema.json
```

The output is sorted and indented, so it is stable under version control.

## `scenet mcp`

```
scenet mcp [--transport {stdio,streamable-http}] [--host HOST] [--port PORT]
```

Runs an [MCP](https://modelcontextprotocol.io/) server whose tools read the specification,
list the characters, validate, compile and render — so a model can check the panel it
wrote, read what is wrong and fix it, with nobody copying error text between windows. The
tools themselves are documented in [the MCP server reference](mcp.md).

Needs the optional extra, which brings the official `mcp` SDK:

```bash
pip install 'scenet[mcp]'
```

Without it, the command says so on stderr and exits **2**. Every other command works
without the extra.

`--transport stdio` (default)
: For a client that launches the server itself, which is how desktop and editor clients
  run a local server. **Nothing but protocol messages reaches stdout** — the server never
  prints, and the compiler's notes travel inside tool results.

`--transport streamable-http`
: Listens for remote clients over
  [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports).
  There is no authentication, so put it behind something that provides it before
  exposing it beyond your own machine. SSE is not offered: the protocol deprecated it in
  favour of Streamable HTTP.

`--host HOST`, `--port PORT`
: Where Streamable HTTP listens. Defaults to `127.0.0.1` and `8000`, so it is reachable
  only from the same machine unless you say otherwise.

### Exit status

| Code | Meaning |
|---|---|
| 0 | The client disconnected |
| 2 | Usage error, or the `mcp` extra is not installed |

```bash
scenet mcp
scenet mcp --transport streamable-http --port 8765
```

## `scenet --version`

Prints the installed version and exits 0.

## Determinism

The same input always produces byte-identical output — no wall-clock time, no unseeded
randomness, no absolute paths in the output. Two runs on different machines produce files
you can compare with `cmp`.
