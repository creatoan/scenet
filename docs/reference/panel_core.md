# Panel Core

The resolved intermediate format, between the authored source and emitted SVG.

```
*.panel.yaml   →   IR   →   *.core.json   →   *.svg
authored           validated   resolved         rendered
```

## Why this tier exists

Vega-Lite compiles a high-level grammar into a lower-level one before emitting SVG, rather than
going straight to pixels. The same split pays for itself here, in four ways:

1. **Tests target stable numbers, not markup.** Golden-file tests compare Panel Core JSON, which
   changes only when layout genuinely changes. Diffing SVG text is brittle: reordered attributes or
   a changed path-rounding convention produce enormous diffs that mean nothing.
2. **Layouts can be adjusted by hand.** An artist who wants one balloon two millimetres left can
   edit the Core file, without touching the source or re-running the solver.
3. **One input, several emitters.** SVG, the debug overlay, and later formats all consume the same
   resolved tier.
4. **The high-level grammar stays a strict subset of the low-level one**, so nothing expressible in
   the source is inexpressible after resolution.

## Properties

- **Fully numeric.** Every position, size and scale is an absolute number in panel units. No
  `left_third`, no `medium_shot` — those are resolved away. The camera records the shot it was
  asked for beside what it made of it, but nothing is drawn from the name.
- **Still named.** Actors, balloons, captions and anchors keep their source identifiers, so a Core
  file is readable and diffable. This is what separates it from SVG.
- **Deterministic.** Floats are rounded to a fixed precision on emission, so identical input yields
  byte-identical Core output on any platform.

## The format

This page is normative: a Panel Core is what it says here, and a reader or a writer that differs
is wrong. The key words MUST, MUST NOT and MAY are used as RFC 2119 uses them.

### What every document says first

Every Core document, of every kind, starts with four keys, which a writer MUST write:

```json
{
  "$schema": "https://creatoan.github.io/scenet/schemas/core/2.0/panel.schema.json",
  "format": "scenet.panel",
  "format_version": "2.0",
  "units": "0.1mm"
}
```

- **`$schema`** is the address of the JSON Schema the document was written to, one folder per
  format version, so it is the schema of the version `format_version` names and stays so. A Page
  Core says `…/core/2.0/page.schema.json`.
- **`format`** says which document this is: `scenet.panel`, `scenet.page` or `scenet.book`. This
  Scenet reads the first two; the third is named so that its name is not taken.
- **`format_version`** is `"major.minor"`, in quotes. This page documents **2.0**.
- **`units`** is `0.1mm`: one unit of every length, position and size is a tenth of a millimetre,
  which is what a unit prints as. A reader MUST refuse any other value.

### The coordinates

- **Units** are `units`, above. A `width` of `1800` is 180 mm.
- **y is down and the origin is the top left** of the panel (of the page, in a Page Core): `x`
  grows to the right and `y` grows down.
- **Angles are in degrees, clockwise** as the reader sees them on the page: a glyph's `angle` of
  `15` leans it to the right.
- **Winding.** A silhouette -- an actor's `hull`, a mass's `polygon`, a panel's `outline` and a
  figure's `body` -- runs **clockwise as displayed**, the order a rectangle `(0,0) (w,0) (w,h)
  (0,h)` is written in. No other polygon has an orientation a reader may rely on.
- **Rounding.** Every number a compile writes is rounded to two decimal places
  (`scenet.geom.PRECISION`), half to even, and never written as negative zero, so a document is
  byte-identical on any platform. A reader MUST NOT depend on a number having been rounded.

### Reading: which versions, and what to do with what it does not know

`format_version` is `major.minor`. The major changes what a reader must understand to read a
document at all; the minor only adds what a reader that does not know it can leave out.

| A document that is… | A reader of 2.0 |
|---|---|
| format 1 (`"format_version": 1`, or no version and no `format`) | Upgrades it: the key words below are added, and each actor's `capsules`, `blobs`, `face_marks` and `emanata` move under `drawing`. What it draws does not change. |
| of a major it does not know (`3.0`, `99`) | Refuses it, naming the version the document says and the version this reads. |
| of this major and this minor (`2.0`) | Reads it. An unknown key is a typo and is refused, where it is. |
| of this major and a newer minor (`2.3`) | Reads it. A key it does not know is left out and reported once -- *written by a newer Scenet (2.3); this reads 2.0* -- not refused; every other mistake is refused as it is at 2.0. Written back, it is 2.0. |
| not `major.minor`, or naming a `format` that is not the one asked for | Refuses it, saying which. |
| requiring an extension it does not implement | Refuses it, naming the extension. |

A minor release of Scenet reads every Core of its format's major, and a release that changes the
major ships the upgrade from the one before it or refuses with a message that says so.

### What Scenet does not interpret: `extras` and `extensions`

Every object of a Core -- a document, an actor, a balloon, a box -- may carry two more keys, which
are read and written back as they were and never drawn from:

- **`extras`**: an object holding anything JSON can. For a tool that wants to keep a note on a
  thing, as glTF's `extras` does.
- **`extensions`**: an object of objects, each under the reverse-DNS name of whoever defines it
  (`com.example.lighting`). For data a renderer reads. A reader that does not know an extension
  ignores it.

A *document* may also carry **`extensions_required`**, the names, in `extensions`, a reader must
implement to draw the document as it was meant. A reader that implements none of them -- which is
what every renderer built from this package is -- refuses a document that lists one.

Both are left out when empty. Every other key of every object is still checked: an unknown one,
at the document's own minor version, is refused, because a hand edit that did nothing should say
so.

### Names the language knows, and a Core does not check

The language says which places, shots, angles, hours and marks there are, and it grows. A Core
only says which one a panel was made with: `backdrop.place`, `backdrop.time`,
`backdrop.atmosphere.time`, a mass's `kind`, `camera.shot`, `camera.angle` and an actor's `marks`
are **any string**. The language checks them when it compiles; this reader does not, and nothing is
drawn from them, so a Core naming a place a newer Scenet added still renders. The published schema
lists the names it knows as `examples`.

### A field at its default is left out

Each field with a default is written only when it is not that default, and the default is the one
the schema declares: a writer MUST leave out a field equal to it and a reader MUST read an absent
one as it. That is the whole rule, and it is why a field added with a default changes no document
that does not use it. A field with no default, and the four keys above, are always written.

### The drawing of an actor

An actor's **contract** -- `transform`, `anchors`, `joints`, `features`, `hull`,
`face_exclusion`, `gaze`, `gaze_aim` and `emanata_zones` -- is the same whatever the actor is drawn
as, and is what lettering was placed around. How it is drawn is its **`drawing`**, an object whose
`kind` says what the rest means. The only kind this Scenet writes is `mannequin`, whose members are
`capsules`, `blobs`, `face_marks` and `emanata`. A reader that does not know a `kind` keeps the
object, draws nothing for the actor, and reads the contract as it always does; a puppet drawn some
other way adds a kind and touches nothing else. An actor with no `drawing` is a contract alone.

## Validating a Core

A Core is read back as hand-edited text, so it has a [JSON Schema](https://json-schema.org/)
like the documents people write. `scenet schema --core` writes the Panel Core's and
`scenet schema --page-core` the Page Core's. The site serves both at the address a Core names in
its `$schema`, `schemas/core/2.0/panel.schema.json` and `schemas/core/2.0/page.schema.json`, each
with that address as its `$id`, from every release. They are generated from the models that read
a Core back, so the two cannot disagree, and every Core the gallery compiles to is checked
against them.

Every string that reaches the SVG is checked when a Core is read, and a Core that fails is
refused where it is, with the key's path:

- a **colour** (`tone`, `colour`, `fill`, `stroke`, `ink`, `fall_tone`, `fall_colour`) is
  `#rrggbb`; a sound effect's `fill` and `stroke` may also be `none`, and a colour the palette
  did not add is `""`;
- an **id** (an actor's, a balloon's, a caption's, a sound effect's, a mass's, a drawn mark's)
  is an [identifier](language/identifiers.md).

The emitter writes every attribute it did not compute from numbers through one escaping
helper, so a value that is not a colour could not leave its attribute even if it were let in.

## Shape

```json
{
  "$schema": "https://creatoan.github.io/scenet/schemas/core/2.0/panel.schema.json",
  "format": "scenet.panel",
  "format_version": "2.0",
  "units": "0.1mm",
  "width": 1000.0,
  "height": 1000.0,
  "actors": [
    {
      "id": "alice",
      "reference": "alice",
      "pose": "pointing",
      "transform": { "x": 208.33, "y": 140.0, "scale": 0.72, "mirrored": false },
      "anchors": { "mouth": [263.1, 268.4], "eyes": [259.0, 251.2], "feet": [270.0, 680.0] },
      "face_exclusion": { "cx": 259.0, "cy": 255.0, "r": 46.8 },
      "gaze": [1.0, 0.0],
      "hull": [[180.2, 140.0], [340.5, 140.0], "..."],
      "drawing": {
        "kind": "mannequin",
        "capsules": [{ "start": [282.88, 237.49], "end": [282.88, 497.71], "width": 94.63 }],
        "blobs": [{ "centre": [282.88, 129.71], "radius": 65.71 }],
        "face_marks": ["..."]
      }
    }
  ],
  "balloons": [
    {
      "id": "b0",
      "speaker": "alice",
      "order": 1,
      "kind": "speech",
      "box": { "x": 60.0, "y": 55.0, "width": 330.0, "height": 118.0 },
      "lines": ["You forgot your", "umbrella!"],
      "font_size": 28.0,
      "line_height": 35.0,
      "tail": { "start": [225.0, 173.0], "end": [263.1, 268.4] }
    }
  ],
  "captions": [
    {
      "id": "c0",
      "order": 0,
      "kind": "locale",
      "box": { "x": 19.0, "y": 19.0, "width": 147.0, "height": 96.0 },
      "lines": ["Midnight.", "The docks."],
      "italic": true
    }
  ],
  "backdrop": {
    "horizon": 341.0,
    "seed": 3062117294,
    "masses": [
      {
        "id": "m0",
        "kind": "sky",
        "plane": "far",
        "depth": -3,
        "tone": "#4d4d4d",
        "polygon": [[0.0, 0.0], [1000.0, 0.0], [1000.0, 341.0], [0.0, 341.0]]
      }
    ],
    "atmosphere": {
      "time": "night",
      "weather": "rain",
      "tone": "#4d4d4d",
      "veil": { "tone": "#222222", "opacity": 0.3, "frequency": 0.0016, "octaves": 3, "seed": 52939 },
      "streaks": [{ "start": [88.4, 12.0], "end": [99.7, 55.4] }],
      "streak_width": 1.4,
      "fall_tone": "#4d4d4d"
    }
  }
}
```

A caption's `fill` and `ink` and a balloon's `tail.width` are not shown: each is at its default
(`#ffffff`, `#111111`, `14.0`), so it is left out, as every field at its default is.

`lines` is the *resolved* line breaking, not the source string. Wrapping is decided during
compilation using real font metrics, so the emitter never re-measures and never disagrees with the
solver about how wide a balloon needs to be. For a `spoken` caption the quotation marks are part of
those lines for the same reason: marks added afterwards would not fit the box drawn for them.

A line with [emphasis](language/script.md#saytext) in it is still plain text in `lines`, the text as it
reads. Beside `lines`, the balloon or caption then carries `runs`: every line cut wherever its face
changes, so the emitter draws each run in the face it was measured in. The runs of a line must
spell it exactly, and a Core whose runs do not is refused.

```json
"lines": ["I told you it", "would rain."],
"runs": [
  [{ "text": "I ", "face": "regular" }, { "text": "told", "face": "bold_italic" }, { "text": " you it", "face": "regular" }],
  [{ "text": "would rain.", "face": "regular" }]
]
```

`face` is `regular`, `italic` or `bold_italic`. A balloon or caption with no emphasis has no
`runs` key at all: it is empty by default, so it is left out.

A panel lettered in an [author's face](language/lettering.md#letteringfont) carries `fonts`: each face set in a
font other than the shipped one, by its family and style as the font names them, and the SHA-256 of
the file. Never a path — where the file was is a fact about one machine. A font whose `name`
table gives no family is called by the first twelve characters of that digest, so the same bytes
have the same family in every document and every process.

```json
"fonts": {
  "regular": { "family": "Comic Neue", "style": "Regular", "sha256": "4c1f…" },
  "italic": { "family": "Comic Neue", "style": "Regular", "sha256": "4c1f…" }
}
```

The renderer is handed fonts by digest and refuses a Core naming one it was not given, so a Core is
never drawn in a face it was not measured in. A face not listed is the shipped one; a panel in the
shipped family has no `fonts` key at all.

`italic` is recorded rather than re-derived from `kind`, so the emitter cannot draw a box in a face
the solver did not measure it in. `fill` and `ink` are there for the same reason: a caption's tone
resolves to a value here, and the ink is chosen against it by contrast — so a dark box arrives at the
emitter already lettered in paper, and the emitter is left with no decision about which mark reads.
Both default to white and near-black, the colours every caption had before tones existed, so a
caption in them has neither key.

**`order` is one sequence across both lists.** Balloons and captions are placed in a single pass in
script order, so a caption between two lines of dialogue takes the number between theirs and a
balloon list can have gaps in it.

**A balloon spoken from [off panel](language/script.md#sayoff_panel) carries `off_panel`**, the side
of the frame its speaker is on, as the solver settled it: `left`, `right`, `top` or `bottom`. When
it is set, `speaker` names somebody who is not an actor, so it is not looked up among `actors`, and
the tail's `end` lies on the frame on that side — on `outline`, when the panel has one. A balloon
whose speaker is drawn has no `off_panel` key.

`backdrop` is absent on a panel that says nothing about where it is. Its masses carry **fully resolved numeric polygons and tone values**, the same
discipline as `capsules`, `blobs` and `face_marks`: the emitter is left with no layout decision, and
a backdrop can be read, diffed and hand-adjusted like everything else in this tier. `depth` is the
same painter's order the actors use, so masses and figures sort into one sequence.

A backdrop that is a [supplied picture](language/setting.md#settingimage) has an `image` in
place of masses, and no `horizon`: the compiler does not know where the picture's horizon is, and
does not pretend to. The solver was told the picture's size and nothing else; what it resolved is
`box`, the rectangle the picture is drawn in — centred, overhanging the panel under `cover`,
inside it under `contain`. Change `box` and the picture moves.

```json
"backdrop": {
  "seed": 3062117294,
  "image": {
    "href": "art/p01-street.png",
    "media_type": "image/png",
    "sha256": "9f2c…",
    "pixels": [960, 640],
    "fit": "cover",
    "preserve_aspect_ratio": "xMidYMid slice",
    "box": { "x": 0.0, "y": -100.0, "width": 1200.0, "height": 800.0 }
  }
}
```

`href` is the path exactly as the document wrote it, relative to the document: the one fact about
where the file was that reaches any output, because a linked SVG needs it. `sha256` is what the
picture is known by, as a font is — a renderer asked to embed it is handed bytes by digest and
refuses a Core naming bytes it was not given. `preserve_aspect_ratio` is the fit in SVG's own
words, recorded so the emitter copies it. A backdrop of masses has no `image` key.

A picture that draws its own people has an [artwork contract](asset_contract.md#artwork-contracts)
beside it, and what the contract declares is recorded here in the panel's units, mapped from the
picture's pixels through the same fit as `box`. The people are `figures`, beside `actors`; the
regions to stay off are the picture's `keep_out`.

```json
"figures": [
  {
    "figure": "ana",
    "actor": "ana",
    "face_exclusion": { "cx": 413.33, "cy": 103.33, "r": 50.0 },
    "mouth": [423.33, 133.33],
    "body": [[350.0, 73.33], [483.33, 73.33], [500.0, 566.67], [333.33, 566.67]]
  },
  { "figure": "ben", "face_exclusion": { "cx": 736.67, "cy": 93.33, "r": 46.67 } }
],
"backdrop": {
  "image": {
    "...": "...",
    "keep_out": [[[133.33, 300.0], [300.0, 300.0], [300.0, 466.67], [133.33, 466.67]]]
  }
}
```

A figure is not an actor: nobody posed it, so it has no transform, no skeleton and nothing to
draw — the picture draws it, and an emitter draws nothing for it. What it has is what lettering
worked around. `figure` is its name in the contract; `actor` is the cast member it plays, which a
balloon's `speaker` and a sound effect's `source` name, and is left out for a figure nobody cast,
whose face lettering kept clear of just the same. `mouth` is where a tail to it aims, left out when
the contract declares none, so a tail aims at the face's centre; `body` is left out when it declares
none. `keep_out` holds what balloons, captions and sound effects paid to cover and were never
forbidden to. They are resolved numbers, like everything here: change `box` by hand and the picture
moves, and the figures stay where they were resolved.

A panel with no figures has no `figures` key, and a picture with no keep-out regions no `keep_out`.

An actor with `marks` carries three more things. `marks` names what was asked for; `emanata`, in
its `drawing`, is the drawing, in the same `stroke` and `disc` primitives as `face_marks`, with ids
numbered per mark (`plewd_0`, `plewd_1`, ...); and `emanata_zones` holds one polygon per mark,
which is what balloon and caption placement paid to avoid. The zones are recorded so a Core
document says why a balloon is where it is. An actor without marks has none of them.

```json
"marks": ["plewds"],
"drawing": {
  "kind": "mannequin",
  "emanata": [{ "mark": "stroke", "id": "plewd_0", "points": [[171.2, 98.6], "..."], "width": 5.9, "closed": true }],
  "...": "..."
},
"emanata_zones": [[[150.3, 61.0], [205.8, 70.4], "..."]]
```

A panel with [sound effects](language/script.md#sfx) carries `sfx`, one entry per effect in script
order: its `id` (`s0`, `s1`, ...), its `order` in the one sequence it shares with balloons and
captions, its `text`, its `source`, its `font_size`, and every letter as a `glyph` — the character,
the `origin` its baseline starts at, and the `angle` it is turned by. The arc and the rotation are
already in those numbers, so the emitter draws each letter's outline where it is told. `zone` is the
footprint balloons and captions paid to avoid and no face was allowed inside; `fill`, `stroke` and
`stroke_width` are resolved, with `fill` `none` for a hollow effect.

```json
"sfx": [{
  "id": "s0", "order": 0, "text": "KRAK", "source": "bob", "font_size": 106.4,
  "glyphs": [{ "char": "K", "origin": [716.07, 486.47], "angle": -14.0 }, "..."],
  "zone": [[688.18, 392.21], "..."], "fill": "#111111", "stroke": "#ffffff", "stroke_width": 8.51, "hollow": false
}]
```

A panel with no effects has no `sfx` key.

`seed` is kept so that a Core document explains itself: two panels with the same masses and
different skylines differ here, and here is where to look.

A panel read right to left carries `"direction": "rtl"`, the reason its lettering is where it
is: see [`direction`](language/direction.md#direction). A panel read left to right has no `direction` key.

A panel drawn in [`palette: tinted`](language/palette.md#palette) carries `"palette": "tinted"`, and beside
each value the palette tints, that value's colour: `colour` on each mass, on the atmosphere and on
its veil, `fall_colour` for rain, and `colour` on a `warm` caption.

```json
"palette": "tinted",
"backdrop": {
  "masses": [{ "id": "m0", "kind": "sky", "plane": "far", "depth": -3, "tone": "#868686", "colour": "#b07750", "polygon": "..." }],
  "atmosphere": { "tone": "#868686", "colour": "#b07750", "fall_tone": "#060606", "fall_colour": "#080410", "...": "..." }
}
```

**The value keeps its key and its meaning.** `tone` and `fill` are always the grey, and every
decision was made on them: the colour has the grey's lightness and is only what the grey looks like
in this palette. So a renderer draws `colour` where there is one and `tone` or `fill` where there is
not, `--mono` draws the greys and ignores the colours, and `PanelCore.as_mono()` takes the colours
out — which gives exactly the Core the panel compiles to in `mono`. Snow has no colour: it is white
by convention, not a rung of the ladder. A `mono` panel has none of these keys.

### The staging

What the solver used and once threw away is recorded too, so that an
[export for image models](../howto/export_for_image_models.md), reading only this tier, can say
how the panel is staged. From `examples/gallery/01-two-characters.panel.yaml`, and a backdrop
set in a street at night:

```json
"camera": { "shot": "medium_shot", "angle": "eye_level", "reference": "alice", "scale": 1.94,
            "headroom": 0.1, "footroom": 0.0, "pullback": 0.71 },
"actors": [{
  "id": "alice",
  "joints": { "neck": [96.87, 355.74], "shoulder_l": [31.0, 367.37], "...": "..." },
  "features": { "eye_l": [58.12, 173.62], "eye_r": [135.62, 173.62], "nose": [96.87, 204.62], "...": "..." },
  "looking_at": "bob",
  "...": "..."
}],
"backdrop": { "place": "street", "time": "night", "...": "..." }
```

- **`camera`** is the camera's verdict: the shot asked for and the angle, the puppet it was
  composed on, the one scale every actor shares, the headroom and footroom as fractions of the
  panel's height, and `pullback`, below 1 when the camera retreated to fit the cast. A panel whose
  cast a picture draws has none: the artist framed it.
- **`joints`** is where every joint of the skeleton landed, by the puppet's name for it. `_l` and
  `_r` are the sides of the screen in the puppet's rest pose, so on a figure facing left
  `shoulder_l` is on the right.
- **`features`** is where each face feature point sits: the anatomy, not the marks, so the same
  whatever the expression and present when the face is too small to draw.
- **`looking_at`** is whom the actor looks at — an actor id, or somebody heard from off panel —
  where `gaze_aim` is the direction.
- **`place`** names the place the masses are, whether `place:` wrote them or an author wrote the
  same list out, as any string; **`time`** is the hour the values were chosen for, which `atmosphere` records too
  but only when something is in the air. Over a picture neither is known, and both are left out.

None is read to draw the panel. Each is left out of a document that does not use it.

### The words

A panel is also read, by somebody who cannot see it, and the words it is read in are resolved here
like everything else, so the emitter copies them and decides nothing:

```json
"description": "Medium shot. A street at night, in the rain. Alice, left, pointing, angry, looking at Bob; Bob, right, arms crossed, sweating.",
"balloons": [{ "id": "b0", "order": 1, "label": "Alice: You forgot your umbrella!", "...": "..." }],
"captions": [{ "id": "c0", "order": 0, "label": "Caption: Midnight.", "...": "..." }],
"sfx": [{ "id": "s0", "order": 2, "label": "Sound effect, from Bob: BLAM.", "...": "..." }]
```

- **`description`** is the panel's [`description`](language/description.md#description) when it has one —
  written, or a comic script's prose — and otherwise generated from what it holds: the shot and
  angle, the place, the hour and the weather, then each figure in reading order (from the right in
  a panel read right to left), by thirds of the panel
  at the centre of its face, with its pose, expression and marks, whom it looks at, and whom it
  stands in front of or behind. A panel with nothing in it is `An empty panel.`
- **`label`**, on every balloon, caption and sound effect, is who says it, how, and the words:
  `Bob, whispering, quietly: I know.`, `Caption, inner voice: …`, `Carol, off panel: …`. The words
  are the author's with emphasis markers off — never `lines`, which are broken to fit and, on a
  spoken caption, carry quotation marks that are lettering, not speech. Each is a sentence: a line
  that does not end gets a full stop, so two lines are heard as two.

Read in `order`, the labels are the panel's text in the order its reader takes it, sound effects
included. Generated text is **templated English**; a French script's prose stays French, but the
words round its dialogue do not. Both are left out of a document that has none, and neither
may hold a character an SVG cannot, since Core is hand-edited and both go into the SVG.

### Determinism is on this text, and on the SVG text — not on pixels

The atmosphere's `veil` is a set of `feTurbulence` parameters rather than an image, and the filter
is reproducible by specification. What browsers paint from it agrees only approximately. See
[the language reference](language/index.md#the-contract-is-on-the-svg-text-not-on-pixels), where the
boundary is stated in full; golden-file tests target this tier, the SVG text and the print PDF's
bytes, never a raster.

## Every field

Each key of a Panel Core and of a Page Core, its type, and what it holds: made from the
models themselves, so it cannot drift from what is written. The nested types are on [the
Panel Core types](api/public/core-types.md) page.

<!-- begin: field table, generated by scripts/build_api_pages.py; do not edit -->

### A Panel Core

| Key | Type | What it holds |
|---|---|---|
| `extras` | `dict[str, JsonValue]` | Anything a tool wants to keep on the document, never interpreted. Left out when empty. |
| `extensions` | `dict[Annotated[str, StringConstraints(strip_whitespace=None, to_upper=None, to_lower=None, strict=None, min_length=None, max_length=None, pattern='^[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)+$', ascii_only=None)], JsonValue]` | Data for a renderer, under its reverse-DNS name. Left out when empty. |
| `format_version` | `str` | The version of the format, `major.minor`. |
| `units` | `Literal['0.1mm']` | Always `0.1mm`: a unit is a tenth of a millimetre. |
| `extensions_required` | `tuple[Annotated[str, StringConstraints(strip_whitespace=None, to_upper=None, to_lower=None, strict=None, min_length=None, max_length=None, pattern='^[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)+$', ascii_only=None)], ...]` | The extensions a reader must implement to draw this document as it was meant, by reverse-DNS name. A reader that does not refuses it. Left out when empty. |
| `schema_url` | `str` | `$schema` in the file: the versioned address of the schema it is written to. |
| `format` | `Literal['panel']` | Always `scenet.panel`. |
| `width` | `float` | Panel width in panel units. |
| `height` | `float` | Panel height in panel units. |
| `actors` | `tuple[CoreActor, ...]` | Resolved characters, back to front by `depth`, and at one depth left to right as staged. The SVG draws them back to front too, but breaks a tie at one depth by id (:func:`in_painters_order <scenet.emit.svg.in_painters_order>`). |
| `balloons` | `tuple[CoreBalloon, ...]` | Resolved balloons, in reading order. |
| `captions` | `tuple[CoreCaption, ...]` | Resolved caption boxes, in reading order. Balloons and captions share one `order` sequence, since the reader takes them in one sequence. |
| `backdrop` | `CoreBackdrop \| None` | Where the panel is, or None when it says nothing about that -- which is every panel written before the setting layer existed. |
| `exclusions` | `tuple[Box, ...]` | Areas the lettering kept clear of because something is drawn over them: on a page, the insets set into this panel, ringed by a gutter. The art under them is drawn as if they were not there. Left out of the JSON when empty, so a panel with no inset reads and writes exactly as it always did. |
| `outline` | `tuple[tuple[float, float], ...] \| None` | For a panel in a slanted tier, the shape of its border: four corners, clockwise from the top left, in panel units. The panel is drawn clipped to it, and its lettering stays inside it. Left out of the JSON for a rectangle. |
| `fonts` | `dict[Face, CoreFont]` | The faces lettered in a font other than the shipped one, by face. A face not listed is the shipped family's. Left out of the JSON when every face is the shipped one. |
| `sfx` | `tuple[CoreSfx, ...]` | Sound effects, in script order. Left out of the JSON when there are none. |
| `description` | `str \| None` | What the panel shows, in words, for a reader who cannot see it: the author's, or generated from what it holds. With the labels in `order`, it is what accessible output reads. Left out of the JSON when unset. |
| `figures` | `tuple[CoreFigure, ...]` | The figures a supplied picture draws, as its artwork contract declares them, whether cast or not. Left out of the JSON when there are none, so every panel without them reads and writes as it always did. |
| `direction` | `Direction` | Which way the panel is read, which is why its lettering is where it is. Left out of the JSON for `ltr`, so every panel written before it reads and writes as it always did. |
| `camera` | `CoreCamera \| None` | What framed the panel, or None when a supplied picture draws the cast: the artist framed it, and the camera did not run. Left out of the JSON when None. |
| `palette` | `Palette` | What the panel is drawn in. Each value it tints keeps its grey, and gains its colour beside it. Left out of the JSON for `mono`, so every panel written before it reads and writes as it always did. |
| `open` | `tuple[Side, ...]` | For a panel that bleeds past the trim, the sides its frame runs out to the bleed line on: no border is drawn there. Left out of the JSON when empty. |
| `lettering` | `Box \| None` | For a panel that bleeds, the box its balloons, captions and sound effects keep inside: its frame as it was before bleeding, inset by its margin, so the page's margin stays the live area. Left out of the JSON otherwise. |

### A Page Core

| Key | Type | What it holds |
|---|---|---|
| `extras` | `dict[str, JsonValue]` | Anything a tool wants to keep on the document, never interpreted. Left out when empty. |
| `extensions` | `dict[Annotated[str, StringConstraints(strip_whitespace=None, to_upper=None, to_lower=None, strict=None, min_length=None, max_length=None, pattern='^[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)+$', ascii_only=None)], JsonValue]` | Data for a renderer, under its reverse-DNS name. Left out when empty. |
| `format_version` | `str` | The version of the format, `major.minor`. |
| `units` | `Literal['0.1mm']` | Always `0.1mm`. |
| `extensions_required` | `tuple[Annotated[str, StringConstraints(strip_whitespace=None, to_upper=None, to_lower=None, strict=None, min_length=None, max_length=None, pattern='^[a-z0-9][a-z0-9-]*(?:\\.[a-z0-9][a-z0-9-]*)+$', ascii_only=None)], ...]` | The extensions a reader must implement to draw this document as it was meant, by reverse-DNS name. A reader that does not refuses it. Left out when empty. |
| `schema_url` | `str` | `$schema` in the file: the versioned address of the schema it is written to. |
| `format` | `Literal['page']` | Always `scenet.page`. |
| `width` | `float` | Page width, in page units. |
| `height` | `float` | Page height. |
| `lettering_height` | `float` | The height every panel on the page took its type size from, in place of its own -- so that a short panel and a tall one letter alike. |
| `frames` | `tuple[CoreFrame, ...]` | One per panel, in reading order: tier by tier, left to right, or right to left for a page read that way. |
| `direction` | `Direction` | Which way the page is read. Left out of the JSON for `ltr`, so every page written before it reads and writes as it always did. |
| `bleed` | `float` | How far the printed sheet runs past the trim on every side, in page units. Left out of the JSON when 0, as `direction` is when `ltr`. |

<!-- end: field table -->

## Page Core

A scene with `pages:` gets one more document per page, alongside each panel's Panel Core. It holds
where each panel's frame is, and nothing drawn:

```json
{
  "$schema": "https://creatoan.github.io/scenet/schemas/core/2.0/page.schema.json",
  "format": "scenet.page",
  "format_version": "2.0",
  "units": "0.1mm",
  "width": 1500.0,
  "height": 2250.0,
  "lettering_height": 700.0,
  "frames": [
    { "panel": "establishing", "x": 75.0, "y": 75.0, "width": 880.0, "height": 628.12 },
    { "panel": "reply", "x": 985.0, "y": 75.0, "width": 440.0, "height": 628.12 }
  ]
}
```

`frames` are in reading order: tier by tier, left to right — right to left, for a page whose
`direction` is `rtl` — and down each column of a tier of
columns, with an inset right after the panel it is set into or, for `read: before`, right before
it. An inset's frame also carries `inset_of`, the panel it sits in, and `clearance`, the area it
covers with its ring of white; the page paints that white under it. Neither field is written for
a panel that is no inset.

The parent's own Core then carries `exclusions`: each inset's clearance, moved into the parent's
coordinates, which no balloon or caption was allowed to touch. Nothing else in the parent moved
for it, so the art under an inset is exactly the art of the panel compiled alone. A panel with no
inset has no `exclusions` key at all.

A panel in a slanted tier carries `outline`, its four corners clockwise from the top left, on its
frame in page units and in its own Core in panel units; the frame is the outline's bounding box.
The panel is drawn clipped to it, and bordered by it. A rectangle has no `outline` key. Each panel's own Core was compiled at
exactly its frame's `width` and `height`, so a panel's Core reads the same on a page as it would
alone at that size, and a page adds no layout decision to a panel.

A page read right to left carries `"direction": "rtl"` as its panels do; one read left to right
has no `direction` key.

A page with a `bleed` carries it, in page units: how far the printed sheet runs past the trim on
every side. A page with none has no `bleed` key: it is left out when it is 0.

A frame that bleeds carries `bleed` too, but as a list: the sides it runs past the trim on,
to the bleed line. Its panel's Core carries `open`, the same sides, where no border is drawn, and
`lettering`, the box its balloons, captions and sound effects keep inside: its frame as it was
before bleeding, inset by the panel margin, in panel units. Each is left out where nothing bleeds,
so no Core written before them changed.

`lettering_height` is the one thing every panel on the page shares: the height their type sizes are
a fraction of, in place of each panel's own. It is recorded so that a Page Core says why two panels
of different heights letter at the same size.

`scenet build --core` writes it as `stem.page-<n>.core.json`; `compile_book` returns it as
`Book.pages`.
