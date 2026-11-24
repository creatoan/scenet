# Command line

```
scenet [--version] [--traceback] <command> [options]
```

Four commands: `build` compiles a document, `check` validates one without compiling it,
`schema` emits the JSON Schema, and `mcp` serves all of that to a model. A bare `scenet` prints help to stderr and exits **2**
— it did nothing, and a script chaining off its status should not read that as success.

## Exit status

Every command exits with one of these. Each command's own table says what its 0, 1 and 2
mean for it.

| Code | Meaning |
|---|---|
| 0 | It did what was asked |
| 1 | A document has an error, or a file could not be read or written |
| 2 | Usage error |
| 70 | An internal error: a bug in Scenet |
| 130 | Stopped by Ctrl-C |

No traceback reaches the terminal. A document's fault is one line saying what is wrong
with it. A file the system will not read or write is one line naming the file and the
system's reason — a folder that is read-only, a disk that is full, an output name that is a
folder. Ctrl-C stops the command at once, with nothing printed. Anything else is a bug, and
says so in one line, with the exception's type and message and where to report it:

```text
scenet: internal error (RuntimeError: …) -- this is a bug; please report it at https://github.com/creatoan/scenet/issues
scenet: run it again with --traceback, or with SCENET_DEBUG=1, to see where it happened
```

`--traceback`
: Print the traceback of an internal error, above its line, for the report. Setting the
  environment variable `SCENET_DEBUG` to anything but empty or `0` does the same. The status
  is 70 either way.
  *Since 0.14.*

## `scenet build`

*Since 0.1.*

```
scenet build SOURCE [-o OUTPUT] [--core] [--debug] [--conditioning] [--live-text] [--mono] [--no-aria] [--embed-images] [--strip] [--pdf] [--quiet] [--watch] [--root DIR]
```

Compiles `SOURCE` to SVG. The frontend is chosen by extension:

| Extension | Read as |
|---|---|
| `.panel.yaml`, `.scene.yaml`, `.yaml`, `.yml` | YAML — single panel or a `panels:` sequence |
| `.panel.json`, `.scene.json`, `.json` | JSON — the same documents, [Scenet JSON](language/json.md) |
| `.script` | Comic script |

### Options

`-o`, `--output PATH`
: Where to write. Defaults to the source's name with an `.svg` extension, alongside it.
  Note that `duel.panel.yaml` becomes `duel.svg`, not `duel.panel.svg`. A folder takes that
  default name inside it, and is made if it is not there: one that exists, whatever its name,
  one written with a trailing `/` such as `out/`, or a name with no extension such as `out`.
  So `-o .` writes `duel.svg` to the current directory, and `-o out` writes `out/duel.svg`. A
  name ending in `.svg` is the SVG file itself, and every other output is named after it.
  Any other extension is a usage error, exit 2, and nothing is written: every SVG written ends
  in `.svg`, and `-o out.pdf` would put an SVG in a file named for a PDF.
  *Since 0.1.*

`--core`
: Also write the resolved Panel Core as JSON — every coordinate the compiler chose, in a
  format you can read, diff and hand-edit. See [Panel Core](panel_core.md).
  *Since 0.1.*

`--debug`
: Also write a diagnostic overlay showing the geometry the solver was working against:
  silhouette hulls, face exclusion zones, named anchors, gaze vectors and tail routes.
  This is usually the fastest way to see why a panel came out the way it did.
  *Since 0.1.*

`--conditioning`
: Also export each panel's staging for image models, as five files beside its SVG: the pose as
  OpenPose JSON, boxes with phrases, a depth map, a mask, and the semantics. No model runs:
  each is another emitter reading Panel Core, text, JSON or SVG, and byte-identical like the
  rest. Per panel only; a page's frames are in its Page Core (`--core`). See
  [export for image models](../howto/export_for_image_models.md).
  *Since 0.12.*

`--live-text`
: Emit selectable `<text>` elements instead of glyph outlines. Smaller files and
  selectable text, but the result depends on the reader having a metrically compatible
  font installed, and on the renderer kerning it as the compiler measured it — browsers
  do by default. The default emits outlines, which makes the file genuinely
  self-contained. With `--pdf`, the print PDF is lettered in text too, and exactly: each
  face is embedded as a subset where its licence (the font's `OS/2` `fsType`) allows, and
  every glyph lands where its outline would; a face that may not be embedded stays in
  outlines, and a note says so. Sound effects stay outlines in both.
  *Since 0.1.*

`--mono`
: Draw every value as its grey and ignore its colour: a black-and-white edition of a document
  drawn in [`palette: tinted`](language/palette.md#palette), made without editing it. Every panel, page and
  strip is byte-identical to what the same document writes with `palette: mono`, because a
  palette only ever adds a colour beside a value the compiler had already decided on its grey.
  With `--pdf`, the print PDF is printed in the greys too, rather than in the colours' CMYK
  twins: the same file `palette: mono` prints. Panel Core and the exports for image models are
  unaffected: `--core` still records the palette and its colours.
  *Since 0.13.*

`--no-aria`
: Write no accessibility markup. By default each panel is an image a screen reader can read
  — `role="img"`, named by its `<title>` with what it shows and then everything said in it, in
  reading order — and a strip or a page is a named group of them; see
  [accessible output](../howto/make_accessible_output.md). This leaves all of that out, for a
  pipeline that post-processes the SVG, and is otherwise byte-identical: the same file less
  those attributes and elements. Debug overlays never carry it.
  *Since 0.12.*

`--embed-images`
: Write each [supplied picture](language/setting.md#settingimage) into the SVG as a
  `data:` URI, so the file stands alone. By default a picture is linked by the path the
  document wrote, which a viewer reads from beside the SVG: that finds it when the SVG is
  written beside the document, as it is by default. Written anywhere else, the picture is
  copied beside the SVG, at that path — `-o out/` writes `out/art/p01.png` for a document
  that names `art/p01.png` — and a `note:` says so, so the SVG shows it wherever it was
  written. A file already there that is the picture is left alone; one that is not is
  replaced, and the build says so on stderr even with `--quiet`. A picture the document
  reaches with `..` is not copied, since its copy would land outside the folder written to,
  and a `note:` says so. An SVG shown as an `<img>`, or turned into a PNG, loads no linked
  file at all. Embedding is byte-identical for the same picture.
  *Since 0.12.*

`--strip`
: For a document of more than one panel, also lay every panel out side by side in reading
  order, as one extra file. Ignored when there is only one panel, a one-panel scene
  included.
  *Since 0.1.*

`--pdf`
: Also write the document as one print PDF, `stem.pdf`, beside the SVGs: a PDF page per
  page, or per panel for a document with no pages; with pages, a panel on no page is not
  printed. A page unit prints as 0.1 mm, and a page's `bleed` runs the sheet past its trim
  (TrimBox and BleedBox). Lettering, balloon borders and every line are 100% black and
  overprint; the paper knocks out; greys are black tints, the night foreground rich black; a
  tinted palette prints its colours' CMYK twins under GRACoL 2013 (CGATS21-2-CRPC6), and with
  `--mono` its greys; supplied pictures go in with their pixels unchanged; the fog
  and cloud veil is the SVG's noise, rasterised at 127 dpi. It
  letters in outlines, or with `--live-text` in its embedded faces. The other SVG options do
  not change it — it carries its pictures, so `--no-aria`, `--embed-images` and `--strip` leave
  its bytes as they are. Notes say what print leaves out or changes: a colour that is none of
  the palette's, a picture below 300 dpi, a face that may not be embedded. RGB pictures are
  tagged sRGB, and an output intent names the printing condition, but no PDF/X conformance
  is claimed. See
  [Print a comic](../howto/print_a_comic.md).
  *Since 0.13.*

`--quiet`
: Suppress the `wrote` and `note:` lines. You do not normally want this: the notes are
  where the compiler tells you it did something you did not ask for. Each kind has a name,
  listed with what to do about it in
  [Work out why a panel looks wrong](../howto/debug_a_layout.md#1-read-the-notes) — all but
  what the build says about its files: a linked picture copied beside the SVG, or one that
  could not be, and what `--pdf` leaves out. A file a picture's copy replaced is said even so.
  *Since 0.1.*

`--watch`
: Build once, then rebuild when the source, a file read during compilation, or a tracked
  dependency directory changes. Changes are debounced until inputs have stayed still for
  about 300 ms. Failed builds are reported and watching continues; the source and previously
  observed dependencies stay watched so a deleted source or a partial failed build can recover.
  Watch mode does not start a server or reload a browser. It polls with the standard library
  by default; install `scenet[watch]` to use `watchfiles` when available. Ctrl-C exits with 0.
  A `scenet.toml` that chose the root is watched too.
  *Since 0.13.*

`--root DIR`
: The folder every file a document names must be inside: its fonts, pictures, artwork
  contracts and puppet files, once `..` and symbolic links are followed. One outside it is
  refused under the rule of the file it names, before anything outside the folder is opened.
  Without it, the root is the nearest folder at or above the document's that holds a
  `scenet.toml`, else the document's own folder. A `scenet.toml` holds nothing yet: a key in
  it is `not-yet`. A `DIR` that is not a folder, or does not hold the document, is a usage
  error, exit 2. `--root /` reads anything your account can, as 0.13 did; for a document from
  someone else, pass its own folder.
  *Since 0.14.*

### Output naming

Every SVG written ends in `.svg`, and every output is named after the main SVG, which `-o`
names or puts in a folder:

```
duel.panel.yaml -o out.svg  →  out.svg, out.core.json, out.pdf
duel.panel.yaml -o out      →  out/duel.svg, out/duel.core.json, out/duel.pdf
duel.panel.yaml -o out.txt  →  exit 2, nothing written
```

The same holds for `--core`, `--debug`, `--conditioning`, `--pdf` and `--watch`.

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

With `--pdf`, the whole document is one PDF named after the main SVG, and `-o` with a `.pdf`
name is a usage error, since `-o` names the SVG:

```
story.scene.yaml     →  story.pdf                   (with --pdf)
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
| 1 | The document could not be compiled — reported as a plain message, not a traceback — or a file could not be read or written |
| 2 | Usage error, or the source file does not exist or has an extension no frontend reads, or `--root` does not hold it |
| 70 | An internal error |
| 130 | Stopped by Ctrl-C; a `--watch` ends with 0 instead, since that is how it is meant to end |

Every error the compiler raises inherits `ScenetError`, and all of them mean "your panel
cannot be compiled" rather than "scenet broke". They print as one line. Anything else is
an internal error, reported as [above](#exit-status).

### Examples

```bash
scenet build examples/gallery/01-two-characters.panel.yaml
```

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --core --debug
```

```bash
scenet build examples/gallery/12-sequence.scene.yaml --strip
```

```bash
scenet build examples/gallery/13-comic-script.script --strip -o out/umbrella.svg
```

Also export each panel's staging for image models, beside its SVG:

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --conditioning
```

Letter in selectable text rather than outlines:

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --live-text
```

A black-and-white edition of a tinted document, without editing it:

```bash
scenet build examples/gallery/40-tinted-hours.scene.yaml --mono
```

Without the accessibility markup, for a pipeline that post-processes the SVG:

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --no-aria
```

A supplied picture written into the SVG, so the file stands alone:

```bash
scenet build examples/gallery/52-a-jpeg.panel.yaml --embed-images -o out/jpeg.svg
```

The print PDF, beside the SVGs:

```bash
scenet build examples/gallery/12-sequence.scene.yaml --pdf
```

In a script, with nothing printed on success:

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --quiet
```

Rebuilt on every save, until Ctrl-C:

```bash
scenet build examples/gallery/01-two-characters.panel.yaml --watch
```

Reading the files a document names from inside a folder that holds both, here the gallery's:

```bash
scenet build examples/gallery/42-your-own-font.scene.yaml --root examples/gallery
```

## `scenet check`

*Since 0.3.*

```
scenet check SOURCE... [--format {text,sarif}] [-o OUTPUT] [--quiet] [--deep] [--root DIR]
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
read once per document, however many panels it has, and a puppet file a cast names once
per panel that casts it. This is still the cheap pass: no solver, no font
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
  *Since 0.3.*

`--format sarif`
: [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html), the
  OASIS standard GCC, Clang and MSVC emit and GitHub code scanning ingests directly.
  Nothing but the document reaches stdout, so redirecting it produces a file a parser
  accepts. To see the findings in VS Code, see
  [Findings the schema cannot see](../howto/editor_support.md#findings-the-schema-cannot-see).
  *Since 0.3.*

`-o`, `--output PATH`
: Write the report to this file instead of the terminal, in either format. In text format
  the file holds the findings, one per line, and is empty when every document is valid.
  It names a file, so a directory is refused.
  *Since 0.3.*

`--quiet`
: Suppress the per-file `ok` line. Findings are always reported — this hides the
  reassurance, never the diagnosis.
  *Since 0.3.*

`--deep`
: Also run the full compiler on any document that passes every cheap check, to
  additionally catch `layout` and `balloon-placement` — two rules in the catalogue that
  the cheap pass cannot produce, because they only surface once the solver actually
  runs. Off by default: it costs a real compile, including font metrics. Skipped for a
  document the cheap pass already found something wrong with, so a document with a bad
  pose reports that once rather than a second, worse-located finding for the same fault.
  *Since 0.6.*

`--root DIR`
: The folder every file a document names must be inside: its fonts, pictures, artwork
  contracts and puppet files, once `..` and symbolic links are followed. One outside it is
  refused under the rule of the file it names, before anything outside the folder is opened.
  Without it, the root is the nearest folder at or above the document's that holds a
  `scenet.toml`, else the document's own folder. A `scenet.toml` holds nothing yet: a key in
  it is `not-yet`. A `DIR` that is not a folder, or does not hold every document, is a usage
  error, exit 2. `--root /` reads anything your account can, as 0.13 did; for a document from
  someone else, pass its own folder.
  *Since 0.14.*

### Exit status

| Code | Meaning |
|---|---|
| 0 | No document has an error; notes may have been printed |
| 1 | At least one error, or a file could not be read or written |
| 2 | Usage error, or a source file does not exist or has an extension no frontend reads, or `--root` does not hold it |
| 70 | An internal error |
| 130 | Stopped by Ctrl-C |

The status means the same thing in both formats, so CI can key off it without parsing
anything.

### Rules

Every finding carries a stable `ruleId`, and each has an entry in
[the diagnostics reference](diagnostics.md): why it happens, how to fix it, and a document that
gives it beside the same document fixed. SARIF links it from the rule's `helpUri`. These identifiers **do not change across
releases**: a `ruleId` that moves silently closes every alert that referenced the old one
and opens a duplicate under the new one, so renaming one is a breaking change even though
nothing stops compiling.

A rule's level is part of it too. An **error** is a contradiction the compiler cannot
build past; a **note** is a house limit a document can exceed and still compile. SARIF
carries the level in both `defaultConfiguration` and each result, so an editor shows a
note as information rather than a red squiggle.

| Rule | Level | Raised when |
|---|---|---|
| [`scenet/syntax`](diagnostics.md#syntax) | error | The file is not valid YAML, or is empty; in a comic script, its front matter. A line indented to match no line above it is said to be |
| [`scenet/duplicate-key`](diagnostics.md#duplicate-key) | error | A key written twice in one mapping, which YAML would drop silently; in a comic script, a directive written twice in one panel, or `@script:` |
| [`scenet/yaml-tag`](diagnostics.md#yaml-tag) | error | A YAML tag, `!!binary` or any other: [Scenet YAML](language/yaml_profile.md) has none |
| [`scenet/yaml-anchor`](diagnostics.md#yaml-anchor) | error | A YAML anchor or alias, `&name` or `*name`: reuse is a scene's defaults and `over:` |
| [`scenet/yaml-merge-key`](diagnostics.md#yaml-merge-key) | error | A YAML merge key, `<<:` |
| [`scenet/not-a-mapping`](diagnostics.md#not-a-mapping) | error | The top level is a list or a scalar |
| [`scenet/unknown-key`](diagnostics.md#unknown-key) | error | A key the language does not define — usually a typo |
| [`scenet/missing-field`](diagnostics.md#missing-field) | error | A required value was not supplied |
| [`scenet/invalid-field`](diagnostics.md#invalid-field) | error | A known key holding the wrong type or an out-of-range value |
| [`scenet/invalid-identifier`](diagnostics.md#invalid-identifier) | error | An actor id or a panel name outside the [identifier grammar](language/identifiers.md): a space, a reserved character or word |
| [`scenet/language-version`](diagnostics.md#language-version) | error | A document written for a later version of the language than this Scenet reads: its one finding |
| [`scenet/not-yet`](diagnostics.md#not-yet) | error | A key kept for a later version of the language: `include`, `defaults`, `kind: book` |
| [`scenet/document-kind`](diagnostics.md#document-kind) | error | A `kind` the document's shape says it is not: `kind: scene` with no `panels:`, or `kind: panel` with them |
| [`scenet/panel-geometry`](diagnostics.md#panel-geometry) | error | Non-positive size, or margins leaving no usable area |
| [`scenet/unknown-actor`](diagnostics.md#unknown-actor) | error | An id in `staging` or `script` that is not in `cast` |
| [`scenet/off-panel-speaker`](diagnostics.md#off-panel-speaker) | error | A line spoken from off panel by somebody drawn in the panel |
| [`scenet/unbalanced-emphasis`](diagnostics.md#unbalanced-emphasis) | error | An underscore that opens emphasis in a line of `text`, with none to close it |
| [`scenet/reflexive-relation`](diagnostics.md#reflexive-relation) | error | A relation relating an actor to itself |
| [`scenet/caption-speaker`](diagnostics.md#caption-speaker) | error | `by` on a caption whose `kind` is not `spoken` |
| [`scenet/ordering-cycle`](diagnostics.md#ordering-cycle) | error | `left_of`/`right_of` relations that form a cycle |
| [`scenet/composition`](diagnostics.md#composition) | error | An `over:` chain that is missing or cyclic |
| [`scenet/panel-direction`](diagnostics.md#panel-direction) | error | A panel of a scene that writes `direction`, or a comic script's `@direction:`: the reading direction is the whole document's |
| [`scenet/duplicate-panel`](diagnostics.md#duplicate-panel) | error | Two panels in a comic script with the same name, even counting pages |
| [`scenet/page-layout`](diagnostics.md#page-layout) | error | A page placing a panel that does not exist, or one twice, two stacked columns side by side, two insets that overlap, an inset too big for its panel, a slant that cannot apply or is too steep, a bleed on a side that does not reach the margin, or no room for its tiers |
| [`scenet/unknown-puppet`](diagnostics.md#unknown-puppet) | error | A `reference` naming a character the library lacks |
| [`scenet/unknown-place`](diagnostics.md#unknown-place) | error | A setting's `place` naming one the library does not have |
| [`scenet/conflicting-setting`](diagnostics.md#conflicting-setting) | error | A setting that names a `place` and also lists `masses`, or names an `image` beside a place, masses or a `horizon` |
| [`scenet/unknown-pose`](diagnostics.md#unknown-pose) | error | A `pose` naming one its puppet does not declare |
| [`scenet/unknown-expression`](diagnostics.md#unknown-expression) | error | An `expression` naming one its puppet does not declare |
| [`scenet/puppet-file`](diagnostics.md#puppet-file) | error | A `reference` naming a puppet file (`puppets/pip.puppet.yaml`) that is absolute, missing, named by text with no folder, or not a puppet: not YAML, a key repeated or misspelt, a landmark missing or out of order, a joint naming one that does not exist. Reported in the puppet file when the document is checked as a file |
| [`scenet/image-file`](diagnostics.md#image-file) | error | A picture in `setting.image` that is absolute, missing, not a PNG or JPEG, turned by its EXIF orientation, or named by text with no folder |
| [`scenet/artwork-contract`](diagnostics.md#artwork-contract) | error | A picture whose figures the panel casts has no artwork contract beside it (`art/p01.png` → `art/p01.art.yaml`), or one that is not YAML, repeats or misspells a key, holds a value out of place, puts a point off the picture, or was measured on a picture of another size. Reported in the contract when the document is checked as a file |
| [`scenet/unknown-figure`](diagnostics.md#unknown-figure) | error | A cast `figure` in a panel that names no picture, or a line spoken or sound made by a figure the panel's picture does not draw |
| [`scenet/conflicting-cast`](diagnostics.md#conflicting-cast) | error | A cast member with both `reference` and `figure`, a puppet's `pose`, `expression`, `marks`, `at` or `facing` on a figure, a cast mixing puppets and figures, or two members playing one figure |
| [`scenet/figure-staging`](diagnostics.md#figure-staging) | error | A staging relation naming a figure a picture draws, or a `camera` on a panel whose cast is all figures |
| [`scenet/font-file`](diagnostics.md#font-file) | error | A font in `lettering.font` that is absolute, missing, not a font, or named by text with no folder |
| [`scenet/layout`](diagnostics.md#layout) | error | Valid, but no layout satisfies its required constraints (`--deep` only) |
| [`scenet/balloon-placement`](diagnostics.md#balloon-placement) | error | No legal position exists for a balloon (`--deep` only) |
| [`scenet/sfx-placement`](diagnostics.md#sfx-placement) | error | No legal position exists for a sound effect (`--deep` only) |
| [`scenet/word-limit`](diagnostics.md#word-limit) | note | A balloon or caption over about 25 words, or a panel over about 50: Dark Horse's limits |
| [`scenet/panel-count`](diagnostics.md#panel-count) | note | A comic script's `PAGE ONE (five panels)` names a count its panels do not match |
| [`scenet/looks-like-dialogue`](diagnostics.md#looks-like-dialogue) | note | A cue in a comic script with nothing said under it, or a name in capitals with a line under it outside any panel |
| [`scenet/dropped-relation`](diagnostics.md#dropped-relation) | note | A shared staging relation left out of a panel its actor is left out of: `(OP)` in a script, or `cast: {name: null}` |
| [`scenet/internal`](diagnostics.md#internal) | error | A failure with no more specific rule — worth reporting |

### Source positions

A finding is located in the file it is about, which is usually the document checked. A fault inside
a picture's [artwork contract](asset_contract.md#artwork-contracts), or inside a
[puppet file](../howto/add_your_own_character.md) a cast member names, is located in that file —
its own path, line and column — since that is the file to open to fix it; checked as text, with no
file of its own, the document points at the line naming the picture or the puppet instead.

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
scenet check examples/gallery/01-two-characters.panel.yaml
```

```bash
scenet check examples/gallery/*.panel.yaml examples/gallery/*.scene.yaml
```

```bash
scenet check --format sarif examples/gallery/01-two-characters.panel.yaml > results.sarif
```

```bash
scenet check --deep examples/gallery/*.panel.yaml examples/gallery/*.scene.yaml
```

A document from someone else, reading nothing outside its own folder:

```bash
scenet check --root examples/gallery examples/gallery/01-two-characters.panel.yaml
```

The findings in a file, one per line, and only the exit status on the terminal:

```bash
scenet check --quiet -o report.txt examples/gallery/01-two-characters.panel.yaml
```

Uploading to GitHub code scanning, which is how findings become annotations on a pull
request:

```{code-block} yaml
:caption: Part of a GitHub Actions workflow

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

*Since 0.1.*

```
scenet schema [-o OUTPUT] [--scene | --artwork | --puppet]
```

Emits the JSON Schema for a panel document, derived from the same pydantic models the
compiler validates against. Editors use it for completion and inline validation, so what
the editor suggests cannot drift from what compiles — see
[editor support](../howto/editor_support.md).

`-o`, `--output PATH`
: Write to this file instead of stdout. It names a file, so a directory is refused.
  *Since 0.1.*

`--scene`
: Emit the multi-panel scene schema instead of the single-panel one. A scene allows the
  same keys as a panel — where they act as defaults every panel inherits — plus `panels:`,
  whose members may additionally carry `over:`.
  *Since 0.1.*

`--artwork`
: Emit the schema for an [artwork contract](asset_contract.md#artwork-contracts), the
  `*.art.yaml` file beside a supplied picture that declares the figures it draws. What a
  schema cannot say — every point on the picture, every region a simple polygon, the size
  the picture's own — `scenet check` does.
  *Since 0.12.*

`--puppet`
: Emit the schema for a [puppet file](../howto/add_your_own_character.md), the
  `*.puppet.yaml` a cast member names by its path in `reference:`. It requires every
  landmark, a `head_top` of zero and a `standing_neutral` pose; what a schema cannot say —
  landmarks increasing downward, a skeleton that is a tree, every joint a part or a pose
  names declared — `scenet check` does, in the puppet file, on a document that casts it.
  *Since 0.13.*

```bash
scenet schema -o panel.schema.json
scenet schema --scene -o scene.schema.json
scenet schema --artwork -o artwork.schema.json
scenet schema --puppet -o puppet.schema.json
```

The output is sorted and indented, so it is stable under version control.

### Exit status

| Code | Meaning |
|---|---|
| 0 | The schema was written |
| 1 | The file could not be written |
| 2 | Usage error, or `-o` names a directory |
| 70 | An internal error |
| 130 | Stopped by Ctrl-C |

## `scenet convert`

*Since 0.14.*

```
scenet convert FILE --to {json,yaml} [--lists] [-o OUTPUT]
```

Writes a panel, a scene, a puppet file or an artwork contract in the language's other carrier:
[Scenet JSON](language/json.md), which programs and models write, or
[Scenet YAML](language/yaml_profile.md). The two hold one data model, so the document converted
builds what it built. Keys stay in the order written, a number is written as it was (`1.50`, not
`1.5`), and an extension key is kept; a comment is not, since JSON has none. The document is read,
not checked: one that does not compile converts to one that does not compile, at the same place.
A comic script has no JSON form.

`--to {json,yaml}`
: The carrier to write. *Since 0.14.*

`--lists`
: Write `panels` and every `cast` as [lists](language/scene.md#panels), each item with its `id`,
  which no tool that sorts keys can reorder. *Since 0.14.*

`-o`, `--output PATH`
: Write to this file instead of stdout. It names a file, so a directory is refused.
  *Since 0.14.*

```bash
scenet convert examples/gallery/12-sequence.scene.yaml --to json -o sequence.scene.json
scenet convert sequence.scene.json --to yaml --lists
```

### Exit status

| Code | Meaning |
|---|---|
| 0 | The document was written |
| 1 | The file is not YAML or JSON, or not a mapping |
| 2 | Usage error, a file that cannot be read, a comic script, or `-o` names a directory |
| 70 | An internal error |
| 130 | Stopped by Ctrl-C |

## `scenet mcp`

*Since 0.8.*

```
scenet mcp [--transport {stdio,streamable-http}] [--host HOST] [--port PORT] [--allow-remote] [--allow-origin ORIGIN] [--timeout SECONDS] [--root DIR] [--output DIR]
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
  *Since 0.8.*

`--transport streamable-http`
: Listens for remote clients over
  [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports).
  It keeps no session: a request needs no session id. It answers only a `Host` that names it
  and an `Origin` of its own — `http://localhost`, `http://127.0.0.1` or `http://[::1]` at its
  own port — refusing any other with 421 and 403, so no web page reaches it by DNS rebinding.
  A request body over 16 MiB is refused with 413 before it is read. There is no
  authentication and no encryption, so put it behind something that provides both before
  exposing it beyond your own machine. SSE is not offered: the protocol deprecated it in
  favour of Streamable HTTP.
  *Since 0.8.*

`--host HOST`, `--port PORT`
: Where Streamable HTTP listens. Defaults to `127.0.0.1` and `8000`, so it is reachable
  only from the same machine. A `HOST` that is not a loopback address is a usage error, exit
  2, without `--allow-remote`.
  *Since 0.8.*

`--allow-remote`
: Let Streamable HTTP listen beyond this machine, on a `--host` such as `0.0.0.0`. The server
  has no authentication and no encryption: put something that provides both in front of it
  first. A reverse proxy on the same machine needs no such flag; it reaches the server on
  `127.0.0.1`.
  *Since 0.14.*

`--allow-origin ORIGIN`
: An `Origin` a client running in a browser may call Streamable HTTP from, such as
  `http://localhost:6274`, beyond the server's own. May be given more than once.
  *Since 0.14.*

`--timeout SECONDS`
: The most seconds one tool call may take, on either transport; 60 by default. Each call runs
  in a worker process, which is stopped — killed, so its work stops too — when the time is
  up or the client cancels the call. The call is answered with an error, and the server goes
  on serving. A worker's start is not counted.
  *Since 0.14.*

`--root DIR`, `--output DIR`
: A folder a server on stdio may read the files a document names from, contained as
  `scenet build --root` is, and one its `build` tool writes new files in, never replacing one.
  Each is refused over Streamable HTTP, exit 2: any client of an HTTP server could reach the
  server's folders through it. Neither is in this version yet, and each is refused on stdio
  too; without them the server reads and writes no folder of its own.
  *Since 0.14.*

### Exit status

| Code | Meaning |
|---|---|
| 0 | The client disconnected |
| 1 | The server could not start: the port is taken, say |
| 2 | Usage error, or the `mcp` extra is not installed |
| 70 | An internal error |
| 130 | Stopped by Ctrl-C |

```bash
scenet mcp
scenet mcp --transport streamable-http --port 8765
scenet mcp --transport streamable-http --host 127.0.0.1 --port 8765
scenet mcp --transport streamable-http --allow-origin http://localhost:6274 --timeout 30
scenet mcp --transport streamable-http --host 0.0.0.0 --allow-remote
scenet mcp --root comics --output out
```

## `scenet --version`

*Since 0.1.*

Prints the installed version and exits 0.

## Determinism

The same input always produces byte-identical output, as
[Determinism](language/index.md#determinism) says: two runs on different machines produce files
you can compare with `cmp`. The print PDF carries no date and takes its `/ID` from its content,
and compresses nothing: zlib implementations differ from one platform to the next.
