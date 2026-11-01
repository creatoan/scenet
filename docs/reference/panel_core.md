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

## Shape

```json
{
  "panel": { "width": 1000, "height": 1000 },
  "actors": [
    {
      "id": "alice",
      "reference": "alice",
      "pose": "pointing",
      "transform": { "x": 208.33, "y": 140.0, "scale": 0.72, "mirrored": false },
      "anchors": { "mouth": [263.1, 268.4], "eyes": [259.0, 251.2], "feet": [270.0, 680.0] },
      "face_exclusion": { "cx": 259.0, "cy": 255.0, "r": 46.8 },
      "gaze": [1.0, 0.0],
      "hull": [[180.2, 140.0], [340.5, 140.0], "..."]
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
      "tail": { "start": [225.0, 173.0], "end": [263.1, 268.4], "control": null, "width": 14.0 }
    }
  ],
  "captions": [
    {
      "id": "c0",
      "order": 0,
      "kind": "locale",
      "box": { "x": 19.0, "y": 19.0, "width": 147.0, "height": 96.0 },
      "lines": ["Midnight.", "The docks."],
      "italic": true,
      "fill": "#ffffff",
      "ink": "#111111"
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
      "flecks": [],
      "streak_width": 1.4,
      "fall_tone": "#4d4d4d"
    }
  }
}
```

`lines` is the *resolved* line breaking, not the source string. Wrapping is decided during
compilation using real font metrics, so the emitter never re-measures and never disagrees with the
solver about how wide a balloon needs to be. For a `spoken` caption the quotation marks are part of
those lines for the same reason: marks added afterwards would not fit the box drawn for them.

A line with [emphasis](language.md#emphasis) in it is still plain text in `lines`, the text as it
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
`runs` key at all, so every Core written before emphasis existed reads, and is written, byte for
byte as before — which is why it needed no `format_version` bump.

A panel lettered in an [author's face](language.md#font) carries `fonts`: each face set in a
font other than the shipped one, by its family and style as the font names them, and the SHA-256 of
the file. Never a path — where the file was is a fact about one machine.

```json
"fonts": {
  "regular": { "family": "Comic Neue", "style": "Regular", "sha256": "4c1f…" },
  "italic": { "family": "Comic Neue", "style": "Regular", "sha256": "4c1f…" }
}
```

The renderer is handed fonts by digest and refuses a Core naming one it was not given, so a Core is
never drawn in a face it was not measured in. A face not listed is the shipped one; a panel in the
shipped family has no `fonts` key at all, so no `format_version` bump either.

`italic` is recorded rather than re-derived from `kind`, so the emitter cannot draw a box in a face
the solver did not measure it in. `fill` and `ink` are there for the same reason: a caption's tone
resolves to a value here, and the ink is chosen against it by contrast — so a dark box arrives at the
emitter already lettered in paper, and the emitter is left with no decision about which mark reads.
Both are defaulted to the white and near-black every caption had before tones existed, which is why
adding them needed no `format_version` bump either.

**`order` is one sequence across both lists.** Balloons and captions are placed in a single pass in
script order, so a caption between two lines of dialogue takes the number between theirs and a
balloon list can have gaps in it. A panel with no captions is unaffected, which is why this did not
need a `format_version` bump.

**A balloon spoken from [off panel](language.md#off-panel-speech) carries `off_panel`**, the side
of the frame its speaker is on, as the solver settled it: `left`, `right`, `top` or `bottom`. When
it is set, `speaker` names somebody who is not an actor, so it is not looked up among `actors`, and
the tail's `end` lies on the frame on that side — on `outline`, when the panel has one. A balloon
whose speaker is drawn has no `off_panel` key, so no existing Core changes.

`backdrop` is absent on a panel that says nothing about where it is, which is why adding it did not
need a bump either. Its masses carry **fully resolved numeric polygons and tone values**, the same
discipline as `capsules`, `blobs` and `face_marks`: the emitter is left with no layout decision, and
a backdrop can be read, diffed and hand-adjusted like everything else in this tier. `depth` is the
same painter's order the actors use, so masses and figures sort into one sequence.

A backdrop that is a [supplied picture](language.md#an-image-behind-the-cast) has an `image` in
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
words, recorded so the emitter copies it. A backdrop of masses has no `image` key, and every Core
written before pictures existed reads and writes byte for byte as it did, so neither `image` nor a
missing `horizon` needed a `format_version` bump.

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

A panel with no figures has no `figures` key, and a picture with no keep-out regions no `keep_out`,
so every Core written before them reads and writes byte for byte as it did, and neither needed a
`format_version` bump.

An actor with `marks` carries three more fields. `marks` names what was asked for; `emanata` is the
drawing, in the same `stroke` and `disc` primitives as `face_marks`, with ids numbered per mark
(`plewd_0`, `plewd_1`, ...); and `emanata_zones` holds one polygon per mark, which is what balloon and
caption placement paid to avoid. The zones are recorded so a Core document says why a balloon is
where it is. All three default to empty, so an actor without marks serialises with `[]` in each and
nothing else changes — which is why they needed no `format_version` bump either.

```json
"marks": ["plewds"],
"emanata": [{ "mark": "stroke", "id": "plewd_0", "points": [[171.2, 98.6], "..."], "width": 5.9, "closed": true }],
"emanata_zones": [[[150.3, 61.0], [205.8, 70.4], "..."]]
```

A panel with [sound effects](language.md#sfx) carries `sfx`, one entry per effect in script
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

A panel with no effects has no `sfx` key, so no `format_version` bump.

`seed` is kept so that a Core document explains itself: two panels with the same masses and
different skylines differ here, and here is where to look.

A panel read right to left carries `"direction": "rtl"`, the reason its lettering is where it
is: see [`direction`](language.md#direction). A panel read left to right has no `direction` key,
so every Core written before it reads, and is written, byte for byte as before — no
`format_version` bump.

A panel drawn in [`palette: tinted`](language.md#palette) carries `"palette": "tinted"`, and beside
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
by convention, not a rung of the ladder. A `mono` panel has none of these keys, so every Core
written before palettes reads, and is written, byte for byte as before — no `format_version` bump.

### The staging

What the solver used and once threw away is recorded too, so that an
[export for image models](../howto/export_for_image_models.md), reading only this tier, can say
how the panel is staged (#72). From `examples/duel.panel.yaml`, and a backdrop
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
  same list out; **`time`** is the hour the values were chosen for, which `atmosphere` records too
  but only when something is in the air. Over a picture neither is known, and both are left out.

None is read to draw the panel. Each is left out of a document that does not use it, so a Core
written before them reads and writes back byte for byte — no `format_version` bump.

### The words

A panel is also read, by somebody who cannot see it, and the words it is read in are resolved here
like everything else, so the emitter copies them and decides nothing:

```json
"description": "Medium shot. A street at night, in the rain. Alice, left, pointing, angry, looking at Bob; Bob, right, arms crossed, sweating.",
"balloons": [{ "id": "b0", "order": 1, "label": "Alice: You forgot your umbrella!", "...": "..." }],
"captions": [{ "id": "c0", "order": 0, "label": "Caption: Midnight.", "...": "..." }],
"sfx": [{ "id": "s0", "order": 2, "label": "Sound effect, from Bob: BLAM.", "...": "..." }]
```

- **`description`** is the panel's [`description`](language.md#description) when it has one —
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
words round its dialogue do not. Both are left out of a document that has none, so a Core written
before them is still valid and writes back byte for byte — no `format_version` bump — and neither
may hold a character an SVG cannot, since Core is hand-edited and both go into the SVG.

### Determinism is on this text, and on the SVG text — not on pixels

The atmosphere's `veil` is a set of `feTurbulence` parameters rather than an image, and the filter
is reproducible by specification. What browsers paint from it agrees only approximately. See
[the language reference](language.md#the-contract-is-on-the-svg-text-not-on-pixels), where the
boundary is stated in full; golden-file tests target this tier and the SVG text, never a raster.

## Page Core

A scene with `pages:` gets one more document per page, alongside each panel's Panel Core. It holds
where each panel's frame is, and nothing drawn:

```json
{
  "format_version": 1,
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
inset has no `exclusions` key at all, so every Core written before insets existed reads, and is
written, byte for byte as before.

A panel in a slanted tier carries `outline`, its four corners clockwise from the top left, on its
frame in page units and in its own Core in panel units; the frame is the outline's bounding box.
The panel is drawn clipped to it, and bordered by it. A rectangle has no `outline` key. Each panel's own Core was compiled at
exactly its frame's `width` and `height`, so a panel's Core reads the same on a page as it would
alone at that size, and a page adds no layout decision to a panel.

A page read right to left carries `"direction": "rtl"` as its panels do; one read left to right
has no `direction` key.

`lettering_height` is the one thing every panel on the page shares: the height their type sizes are
a fraction of, in place of each panel's own. It is recorded so that a Page Core says why two panels
of different heights letter at the same size.

`scenet build --core` writes it as `stem.page-<n>.core.json`; `compile_book` returns it as
`Book.pages`.
