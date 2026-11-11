# `setting`

Where and when the panel happens, drawn as **tonal masses** rather than as geometry, or as a
picture drawn elsewhere.

```yaml
cast: {alice: {reference: alice}}
setting:
  place: docks       # a named place, which expands into masses
  horizon: mid       # high | mid | low
  time: night        # dawn | day | dusk | night
  weather: rain      # clear | rain | fog | snow
```

```{code-block} yaml
:caption: Part of a panel beside art/p01-street.png

setting:
  image: art/p01-street.png   # a PNG or JPEG, relative to this document
  fit: cover                  # cover | contain; left out, cover
  weather: rain               # drawn over the picture, as over masses
```

A panel with no `setting` renders exactly as it always did: figures on white.

## Backdrops are never author-drawn

Two reasons, and the first is structural. Crisp architecture needs a vanishing point, and this is
deliberately a flat, orthographic compiler — a tilted camera does not foreshorten anything — so
drawn buildings would fight the compiler's own model. Soft tonal masses have no perspective to get
wrong.

The second is that this is how comics actually establish place:

- **[Notan](https://mitchalbala.com/the-wisdom-of-notan/)**, the Japanese light/dark mass
  principle, which entered Western art teaching through Arthur Wesley Dow's *Composition* (1899):
  place is read from the *arrangement of masses*, not from rendered detail.
- **Layered silhouette depth**: foreground near-black, each receding plane paler.
- **[Aerial perspective](https://en.wikipedia.org/wiki/Aerial_perspective)** supplies the
  parametric rule for free — with distance, value contrast drops toward the atmosphere. Two numbers
  per hour, monotonic in depth. That is notation, not interpretation, which is why it belongs in a
  compiler.

**Received art is another matter.** The rule is about *drawing* a backdrop in the language, not
about receiving one. A picture drawn elsewhere — painted, pencilled, photographed, rendered — can
stand behind the cast with `image:` ([An image behind the cast](#an-image-behind-the-cast)). Its
perspective is the artist's, and the compiler neither reads nor imitates it: what it takes from the
file is its size, so the solver still never sees artwork, and the
[asset contract](../asset_contract.md)'s promise — the same layout whatever draws it — holds.

## `masses`

A place is a convenience. Underneath it is a list of masses, which stays authorable whenever you
want control — and which is *exactly* what a place expands into:

```yaml
cast: {alice: {reference: alice}}
setting:
  horizon: mid
  masses:
    - {kind: building, plane: far,  spans: full}
    - {kind: plant,    plane: mid,  spans: left}
    - {kind: ground,   plane: near, spans: full}
```

![Two panels of masses written by hand: outdoors, seven kinds of stuff four planes deep, and a room at dusk with its window](../../images/gallery/19-setting.strip.svg)

**In the gallery:** [Masses and planes](../../gallery.md#masses-and-planes) and [In front of the cast](../../gallery.md#in-front-of-the-cast).

| Key | Values | Default | Meaning |
|---|---|---|---|
| `kind` | see below | required | What the mass is made of, which decides its silhouette |
| `plane` | `foreground`, `near`, `mid`, `far` | `mid` | How far back it sits |
| `spans` | `full`, `left`, `center`, `right` | `full` | How much of the width it covers |

**`kind`** is subsetted from the *supercategories* of
[COCO-Stuff](https://arxiv.org/pdf/1612.03716), the canonical taxonomy of **stuff** — "amorphous
background regions" as opposed to *things* with a well-defined shape. Taken from an existing
vocabulary for the same reason the predicates were taken from Visual Genome. Twelve of them, seven
outdoor and five indoor:

| | Kinds |
|---|---|
| Outdoor | `building` `ground` `plant` `sky` `solid` `structural` `water` |
| Indoor | `ceiling` `floor` `furniture` `wall` `window` |

Deliberately *not* COCO-Stuff's leaf names. Its actual classes are `building-other`, `sky-other`,
`wall-brick`, `water-other`; the `-other` suffix marks the catch-all inside a supercategory, and
`building-other` is not a word anyone should have to type. Its `textile`, `food` and `rawmaterial`
supercategories are left out: drapery and objects, not scene-defining masses.

**`plane`** decides two things at once, and neither is a new mechanism. It maps onto the same
integer painter's order `in_front_of` already uses — the three backdrop planes take negative
depths, and `foreground` takes one above the frontmost actor, so a foreground mass draws over the
cast the way a silhouetted doorway does. And it decides **value**: reading front to back, a mass
never gets darker.

Value comes from the plane and from **nothing else** — not from the kind. That is what keeps the
notan reading literal: masses at one distance read as one mass, and their arrangement is what
carries the place. Two kinds sit off their own plane's rung, and both stay on the ladder rather
than beside it: `sky` is at infinite distance so it always takes the atmosphere's value, and
`window` is a hole showing a more distant plane so it takes the rung one step farther back.

A **nearer plane is also drawn larger**, which is size perspective alongside aerial perspective: a
near hill is not merely darker than a far one, it is bigger.

**`spans`** is an absolute extent, and that is not cosmetic. Any construct that would reintroduce a
left/right *disjunction* has to resolve it before the solver — see
[why ordering must be explicit](staging.md#why-ordering-must-be-explicit). A span is an extent rather than a
relation, which is what stops masses becoming an unordered `beside`. `left` and `right` overlap
slightly in the middle so that using both leaves no seam down the centre of the panel.

One authored mass may resolve to **several polygons**: furniture is a few separate blocks, a wall
holds several windows. Joining them into one comb with a zero-height baseline would be a lie about
the shape.

## `place`

The headline surface, because the thing an author wants to write is *where the scene is*, not a
list of shapes.

![Alice in each of the ten places, one panel each: docks, street, alley, room, office, forest, field, shore, desert and mountain](../../images/gallery/20-places.strip.svg)

**In the gallery:** [Ten places](../../gallery.md#ten-places).

| Place | Expands into |
|---|---|
| `alley` | sky·far, building·near·left, building·near·right, ground·near, building·foreground·left |
| `desert` | sky·far, solid·far·right, ground·mid, ground·near |
| `docks` | sky·far, building·far·left, water·mid, structural·mid·right, ground·near |
| `field` | sky·far, plant·far, ground·mid, ground·near |
| `forest` | sky·far, plant·far, plant·near·left, plant·near·right, ground·near |
| `mountain` | sky·far, solid·far, solid·mid·left, plant·mid·right, ground·near |
| `office` | wall·far, window·far·center, ceiling·mid, floor·near, furniture·near |
| `room` | wall·far, window·far·right, ceiling·mid, floor·near, furniture·near·left |
| `shore` | sky·far, water·mid, ground·near |
| `street` | sky·far, building·far, building·mid·left, building·mid·right, ground·near |

**The rule that keeps `place:` honest**: a preset expands into a mass list the author could have
written themselves, and is never a second opaque format. A library for convenience, not a parallel
language. The expansion happens in the frontend, exactly as `alice left_of bob` is expanded into a
relation — so by the time anything downstream sees a backdrop, there is one representation of it.

`place` and `masses` are **mutually exclusive**. A place *is* a mass list; writing both asks two
questions at once, and the compiler will not guess which was meant. An `image` is a backdrop of
its own, so it is written instead of either, never beside one — and never beside a `horizon`,
which says where masses meet the ground; a picture has its own. A panel that inherits a place
from a scene's defaults, or from the panel it is `over`, leaves it out with `place: null`
beside its image. `scenet check` reports any of these pairs as `conflicting-setting`, at the
key other than `image`, and a `fit` with no image as `invalid-field`. See
[An image behind the cast](#an-image-behind-the-cast).

**Free prose is deliberately not offered.** `setting: "a rainy street corner at midnight"` needs
language understanding, and the comic-script frontend already refuses to interpret prose on the
grounds that guessing produces panels that are confidently wrong. A named place is the honest
middle: it reads like a description and resolves deterministically. `scenet check` reports an
unmatched name as `unknown-place`, listing the ones that exist.

## `horizon`

One line for the whole panel, which every mass is composed against: masses of the ground sort start
at it and run down, masses that stand in the world rise from it. A **high** horizon sits nearer the
top of the frame, so more ground is in view.

![The same shore three times, its horizon high, in the middle and low](../../images/gallery/72-three-horizons.strip.svg)

**In the gallery:** [Three horizons](../../gallery.md#three-horizons).

Ground, floor and water all run to the bottom edge, so a near quayside drawn from the horizon would
bury the water behind it. Each starts lower than the plane behind it, and that stack of receding
bands is the depth cue. The exception is the *farthest* one in a panel, which meets the horizon
itself: there is nothing behind it to reveal.

## `time` and `weather`

`time` sets a panel's values. In `mono` it adds no colour, and under [`palette: tinted`](palette.md#palette)
each value takes the hour's colour without changing. It supplies the two ends of the value ladder —
the value of the foreground and the value of the atmosphere — and the planes are spaced evenly between them in
[OKLab](https://bottosson.github.io/posts/oklab/) lightness, which predicts perceived lightness
well. So `night` is a darker, *narrower* ladder, which is what night does to a drawn scene, and the
ladder stays monotonic in depth at every hour by construction rather than by tuning.

![The docks four times: at midnight in the rain, at dawn in fog, at noon, and in snow](../../images/gallery/21-atmosphere.strip.svg)

**In the gallery:** [Time and weather](../../gallery.md#time-and-weather).

`weather` adds a layer over that. `clouds` and `fog` are first-class stuff in COCO-Stuff, so this
vocabulary did not have to be invented either:

| `weather` | What it does |
|---|---|
| `clear` | Nothing. The panel has no atmosphere layer at all |
| `fog` | A dense, low-frequency noise veil, tinted with the atmosphere itself |
| `rain` | The same veil as cloud — nearer, so darker than the sky — plus slanted streaks |
| `snow` | The same veil, plus flecks |

The veil sits over the backdrop and *under* the cast: fog between the reader and the figures would
be the more literal reading and would bury them. Falling weather goes over everything, because it
**is** between the reader and the panel — which is why it crosses the figures.

Rain flips to ink over a bright sky and to paper over a dark one, as inkers do, because a white
streak over noon is invisible and a black one over midnight is too. Snow never flips: snow is
white, and the overcast veil is what gives it something to read against.

## An image behind the cast

`image` names a picture drawn elsewhere — painted, pencilled, photographed or rendered — and the
cast is drawn in front of it, lettered by the same rules as on any other backdrop.

![Alice and Bob in front of a photograph of a harbour, supplied as a JPEG](../../images/gallery/52-a-jpeg.svg)

**In the gallery:** [A JPEG behind the cast](../../gallery.md#a-jpeg-behind-the-cast).

| Key | Values | Default |
|---|---|---|
| `image` | A PNG or JPEG file, relative to the folder the document is in | — |
| `fit` | `cover`: fill the panel, cropping what overhangs, equally on both sides. `contain`: show the whole picture, the panel showing round it | `cover` |

The picture is centred either way and never stretched.

- **The path is read as a font's is**: relative to the folder the document is in, wherever
  `scenet` was run from, with `/` between folders. An absolute path is refused. Text compiled with
  no file behind it has no folder, so it names a picture only when its caller says which folder it
  belongs to, or hands the file over with it.
- **PNG or JPEG**, the two raster formats SVG 2 requires every viewer to draw, told apart by their
  first bytes rather than by the file's name.
- **Only the size is read.** The compiler takes from the file how many pixels it has across and
  down, from its header, and decodes nothing: the solver never sees artwork, here as everywhere.
  Only the print PDF carries the pixels, unchanged, into the file it writes.
- **A picture its EXIF says to turn is refused.** Renderers disagree on obeying that tag —
  Chromium turns an SVG `<image>` by it, others do not — so such a picture would be upright in
  one viewer and on its side in the next. Save it with the pixels turned instead.

`scenet check` reports every way a picture cannot be read as `image-file`, at the line it is named
on, without running the solver. In the [playground](https://creatoan.github.io/scenet/playground/),
**Image…** adds a picture to the document's `art/` folder for as long as the tab is open.

**Time and weather over a picture.** The veil sits over the picture and under the cast, and
falling rain or snow over everything, exactly as over masses; `time` chooses their tint, and
whether rain is drawn in ink or paper. The value ladder — aerial perspective — has nothing to apply
to: a picture's values are the artist's.

**Nothing else moves.** The picture costs a balloon nothing. The compiler does not know what is in
it, so a balloon may sit anywhere on it; the cast's faces are what lettering keeps clear of. The
camera frames the cast exactly as it would in front of masses. When the people are in the picture,
its artwork contract says where — see [Figures the picture draws](#figures-the-picture-draws).

**Linked or embedded.** The SVG names the picture by the path exactly as written, percent-encoded,
so it is found when the SVG sits beside the document — which is where `scenet build` writes it.
`scenet build --embed-images` writes the picture's bytes in as a `data:` URI instead, which an SVG
shown as an `<img>`, turned into a PNG or written anywhere else needs; the playground always embeds.
Either is byte-identical for the same picture. The link is `xlink:href` rather than SVG 2's plain
`href`, because Inkscape still does not load a resource named by plain `href`; see
[prior art](../../explanation/prior_art.md#image-in-svg-renderers-and-editors).

**Read aloud.** The picture is part of the panel's one image, `role="img"`, so it adds nothing to the
accessible name and has no title of its own. A generated description names neither the place nor
the hour over a picture — the compiler has not seen it — only the weather it drew. Write
`description:` to say what the picture shows.

## Figures the picture draws

A picture can draw its own people. Cast them with `figure:` in place of `reference:`, and Scenet
letters them as it letters puppets — balloons in reading order, never over a face, tails to the
mouth — while drawing nothing of them: the picture already has.

![Two panels: Ana and Ben as puppets in a street at night, then the same two as a picture draws them, lettered from its artwork contract](../../images/gallery/51-puppets-to-figures.strip.svg)

**In the gallery:** [From puppets to figures](../../gallery.md#from-puppets-to-figures).

```{code-block} yaml
:caption: Part of a panel beside art/p01-street.png and art/p01-street.art.yaml

setting: {image: art/p01-street.png}
cast:
  ana: {figure: ana}          # in place of reference:
  ben: {figure: ben}
script:
  - say: {by: ana, text: "Where are we?"}
  - say: {by: ben, text: "Somewhere they won't look."}
```

Where each face, mouth and body is, the panel does not say — it never writes a coordinate. The
picture's [artwork contract](../asset_contract.md#artwork-contracts) does: a file beside the picture,
named after it, `art/p01-street.art.yaml`, measured once in the picture's own pixels and
committed with it. `figure:` names a figure it declares. The contract is read only for a panel
whose cast names a figure, and its geometry goes through the picture's `fit`, so a face is
excluded exactly where the picture draws it, under `cover` and `contain` alike.

**Everybody the contract declares is in the picture.** A face nobody cast is as forbidden to
lettering as a speaker's, and a body as costly to cover: a crowd of five can be declared and two of
them cast. The other way round, a cast figure the panel's picture does not draw is simply not in
that panel — as a member written `(OP)` is not — so a script's front matter or a scene's defaults
can cast every figure of a chapter, and each panel holds those its own picture draws. A line spoken
there by one it does not draw is `unknown-figure`, listing who the picture does draw; that is where
a misspelt name is caught. A figure in a panel with no picture is `unknown-figure` too.

**What does not apply.** The artist already framed, posed and staged everybody in the picture:

- **No camera.** The shot is whatever the picture shows. `camera:` on a panel whose cast is all
  figures is refused, as `figure-staging`, a key with no effect; a panel that inherits one writes
  `camera: null`. A generated description says no shot.
- **No staging.** A relation naming a figure — `left_of`, `looking_at` and the rest — is refused,
  as `figure-staging`.
- **No posing.** `pose`, `expression`, `marks`, `at` and `facing` are a puppet's, and refused beside
  `figure`, as is `reference`: a member is one or the other (`conflicting-cast`). A member inherited
  as a puppet becomes a figure with `reference: null` beside its `figure`.
- **No gaze.** A contract declares none, so nothing keeps a balloon out of a figure's line of sight.
- **No mixed casts.** A cast is all puppets or all figures (`conflicting-cast`): staging and the
  camera would place a puppet over a painted face they cannot see. One figure is one person, played
  by one member.

**Keep-out regions** in the contract are ground lettering pays to cover, weighted as emanata are —
a sign, a hand, what the panel is about — and never forbidden: a crowded panel covers one before it
fails.

**A `cover` crop** can push a face or a mouth out of the panel. Lettering stays inside the panel as
always, and a face is kept clear for whatever part of it is in view. A tail to a mouth cropped
away ends on the frame, aimed at it, and `scenet build` says so in a note; `fit: contain` shows the
whole picture.

`scenet check` reads the contract without running the solver, and reports a missing or malformed one
as `artwork-contract`: in the contract itself, at the line of the fault, when the document is checked
as a file; at the line naming the picture when it is checked as text, as in the playground or over
MCP. The debug overlay (`scenet build --debug`) draws every face, mouth, body and keep-out over the
panel, which is how a contract is checked against its picture.
