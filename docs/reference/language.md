# The Scenet language

> **Status:** this is the specification. It is not a report of what is implemented — see
> [implementation status](../explanation/status.md#implementation-status), which is authoritative on
> what actually runs. Panels, sequences and pages of tiers compile end to end today; the style
> layer does not exist yet.

A panel source is a YAML document describing **what is in a panel**, never **where things are drawn**.
Coordinates do not appear anywhere in the language; producing them is the compiler's entire job.

It is read strictly. An unknown key is an error rather than ignored, and so is a key written twice
in one mapping, such as two cast members called `alice`. YAML requires keys to be unique, but the
usual Python parser keeps the last and drops the first without a word, which would quietly lose a
character or a panel. A merge key's override (`<<: *base`, then the key again) is not a repeat.

## The layers

A panel description has five authored layers. A sixth — resolution — is computed, and a seventh —
rendering — is emitted.

| Layer | Block | What it says |
|---|---|---|
| Frame | `panel` | Size and margins of the panel |
| Camera | `camera` | How the scene is framed |
| Setting | `setting` | Where and when it happens |
| Cast and staging | `cast`, `staging` | Who is present, and how they relate |
| Narrative | `script` | What is said, and in what order |

Layers are separable on purpose. Changing `camera.shot` re-frames the same scene without touching
anything else, exactly as transposing a score changes its key without rewriting the melody.

## A complete example

```yaml
panel:
  size: [1000, 1000]

camera:
  shot: medium_shot
  angle: eye_level

setting:
  place: docks
  time: night
  weather: rain

cast:
  alice: {reference: alice, pose: pointing,     at: left_third,  facing: right}
  bob:   {reference: bob,   pose: arms_crossed, at: right_third, facing: left}

staging:
  - alice left_of bob
  - alice looking_at bob
  - alice ground_shared_with bob

script:
  - say: {by: alice, text: "You forgot your umbrella!", prefer: top_left}
  - say: {by: bob,   text: "I know."}
```

## `panel`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `size` | `[width, height]` | required | Panel dimensions in panel units |
| `margin` | number | `0` | Inset all content by this much |

Panel units are arbitrary and internally consistent; they become SVG user units.

## `camera`

| Key | Values | Default |
|---|---|---|
| `shot` | see [shot types](shot_types.md) | `medium_shot` |
| `angle` | `low`, `eye_level`, `high` | `eye_level` |

`shot` determines the **scale** of every actor, by naming where the frame cuts the body rather than
what fraction of the panel a figure fills. This is the single most consequential value in a panel.

## `setting`

Where and when the panel happens, drawn as **tonal masses** rather than as geometry.

```yaml
setting:
  place: docks       # a named place, which expands into masses
  horizon: mid       # high | mid | low
  time: night        # dawn | day | dusk | night
  weather: rain      # clear | rain | fog | snow
```

A panel with no `setting` renders exactly as it always did: figures on white.

### Backdrops are never author-drawn

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

### `masses`

A place is a convenience. Underneath it is a list of masses, which stays authorable whenever you
want control — and which is *exactly* what a place expands into:

```yaml
setting:
  horizon: mid
  masses:
    - {kind: building, plane: far,  spans: full}
    - {kind: plant,    plane: mid,  spans: left}
    - {kind: ground,   plane: near, spans: full}
```

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
[why ordering must be explicit](#why-ordering-must-be-explicit). A span is an extent rather than a
relation, which is what stops masses becoming an unordered `beside`. `left` and `right` overlap
slightly in the middle so that using both leaves no seam down the centre of the panel.

One authored mass may resolve to **several polygons**: furniture is a few separate blocks, a wall
holds several windows. Joining them into one comb with a zero-height baseline would be a lie about
the shape.

### `place`

The headline surface, because the thing an author wants to write is *where the scene is*, not a
list of shapes.

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
questions at once, and the compiler will not guess which was meant.

**Free prose is deliberately not offered.** `setting: "a rainy street corner at midnight"` needs
language understanding, and the comic-script frontend already refuses to interpret prose on the
grounds that guessing produces panels that are confidently wrong. A named place is the honest
middle: it reads like a description and resolves deterministically. `scenet check` reports an
unmatched name as `unknown-place`, listing the ones that exist.

### `horizon`

One line for the whole panel, which every mass is composed against: masses of the ground sort start
at it and run down, masses that stand in the world rise from it. A **high** horizon sits nearer the
top of the frame, so more ground is in view.

Ground, floor and water all run to the bottom edge, so a near quayside drawn from the horizon would
bury the water behind it. Each starts lower than the plane behind it, and that stack of receding
bands is the depth cue. The exception is the *farthest* one in a panel, which meets the horizon
itself: there is nothing behind it to reveal.

### `time` and `weather`

`time` does not tint a daytime panel. It supplies the two ends of the value ladder — the value of
the foreground and the value of the atmosphere — and the planes are spaced evenly between them in
[OKLab](https://bottosson.github.io/posts/oklab/) lightness, which predicts perceived lightness
well. So `night` is a darker, *narrower* ladder, which is what night does to a drawn scene, and the
ladder stays monotonic in depth at every hour by construction rather than by tuning.

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


## `cast`

A mapping of actor id to properties. Ids are chosen by the author and referenced everywhere else.

| Key | Type | Meaning |
|---|---|---|
| `reference` | asset name | Which puppet to pull from the library |
| `pose` | pose name | A named joint configuration declared by that puppet |
| `expression` | expression name | A named face declared by that puppet |
| `marks` | list of marks | Emanata drawn around the character: `plewds`, `squeans`, `grawlixes`, `briffits` |
| `at` | anchor | Horizontal placement preference |
| `facing` | `left`, `right` | Which way the figure is turned |

`at` accepts `left_third`, `center`, `right_third`, `left_edge`, `right_edge`. It is a
**preference, not a command** — see [conflicts](#when-constraints-conflict).

`expression` is selected by name exactly as `pose` is, because a face is the same kind of thing as a
body: a small closed set of arrangements a character can be in. The shipped puppets declare ten —
`neutral`, `happy`, `laughing`, `coy`, `bored`, `scared`, `sad`, `angry`, `shouting`, `surprise` —
and it defaults to `neutral`. They are a **drawing convention**, the small closed set of faces comics
actually draw, and not a claim about what a person feeling anger looks like. What a face is made of,
and how to give your own puppet one, is in the [asset contract](asset_contract.md#faces).

A character's pupils follow whoever they are `looking_at`. Nothing else about the face depends on the
rest of the panel, and nothing about the face changes the layout: to the solver a face is still one
disc that balloons may not cover.

### `marks`

```yaml
cast:
  alice: {reference: alice, expression: angry, marks: [grawlixes, plewds]}
```

`marks` are what a comic draws *around* a character rather than on them. The vocabulary is Mort
Walker's, from *The Lexicon of Comicana*, and it is closed:

| Mark | What is drawn | What it says |
|---|---|---|
| `plewds` | Droplets flying off the head, mostly off the back | sweating: effort, heat, nerves |
| `squeans` | Little starbursts and circles in an arc over the head | dizzy, drunk, or sick |
| `grawlixes` | A spiral, a star, a bolt and a `#` over the head | swearing |
| `briffits` | Puffs of dust at the feet, behind the figure | gone, fast |

They are a **list**, not a second `expression:`, because they compose: a character can be angry *and*
sweating. Order does not matter, and a mark listed twice is an error. They need nothing from the
puppet — every mark is placed from the face circle, the facing and the feet — so every character can
have every mark. In a scene, `marks: []` under `over:` clears the ones a panel inherited, because
lists replace rather than merge.

Emanata are drawn **outside** the head, in the space balloons are placed in, so unlike a face they
matter to the layout — but only softly:

- **They never move anybody.** They stay out of the hull, so staging, the camera and every figure are
  exactly where they would be without them.
- **A balloon prefers not to cover them.** Each mark has a zone the solver reads as a cost, weighted
  above covering a body, with no forgiveness for the speaker. A crowded panel still compiles: a balloon
  covers a mark before it fails.
- **The camera makes no room for them.** It frames by body landmarks, so a tight shot — or the head of
  the tallest character, which the frame is fitted to — can crop marks over the head, and a shot that
  cuts at the waist leaves briffits below the frame. `scenet build` reports any mark that runs off the
  panel.

At a wide framing a plewd is a dot: below a head size, each mark collapses to a dot where it would
have been drawn, and a character too small to have a face has no marks at all. See the
[asset contract](asset_contract.md#emanata).

An oath written in a balloon — `"@#$%!"` — is dialogue, and already works. `grawlixes` is the other
convention, the symbols over a head.

`reference`, `pose` and `expression` are validated against the puppet library, not just against the
language's own grammar — a misspelled pose is a perfectly good string as far as the grammar is
concerned, so nothing at that level can tell `pointing` from `smirking`. `scenet check` resolves the
library and reports an unmatched name as `unknown-puppet`, `unknown-pose` or `unknown-expression`,
each naming the field and, for `pose` and `expression`, listing the names that puppet does declare.
See [`scenet check`](cli.md#scenet-check).

## `staging`

A list of relations between actors, written `subject predicate object`. This is a scene graph: the
cast are nodes, these are the edges. Predicates come from the spatial subset of the Visual Genome
vocabulary rather than being invented here, so a Scenet scene remains convertible to and from the
scene-graph representations used elsewhere in computer vision.

| Predicate | Effect |
|---|---|
| `left_of`, `right_of` | Fixes horizontal ordering |
| `in_front_of`, `behind` | Fixes draw order and occlusion |
| `looking_at` | Sets the subject's gaze vector toward the object |
| `ground_shared_with` | Places both actors on the same ground line |

### Why ordering must be explicit

`left_of` looks redundant next to `at: left_third`, but it is not. The layout engine is a **linear**
constraint solver, and "A and B must not overlap" is a *disjunction*: A is left of B, **or** B is
left of A. Linear solvers cannot express that choice.

So the language resolves it instead. By the time the solver runs, ordering is already decided — by
`at`, or by an explicit `left_of` — and what reaches the solver is a linear system it can always
solve. This is the reason there is no unordered `beside` predicate, and why any future construct
must resolve its own ordering in the frontend.

## `script`

An ordered list of narrative events, each tagged by a verb. **Order is meaningful**: it is the order
the reader reads them, and it constrains where the boxes may be placed.

There are three verbs. `say` puts a line in a balloon; `caption` puts one in a box; `sfx`
letters a sound effect into the picture.

```yaml
script:
  - caption: {text: "Midnight. The docks.", kind: locale, prefer: top_left}
  - say: {by: alice, text: "You forgot your umbrella!", prefer: top_left}
  - say: {by: bob,   text: "I know.", kind: whisper}
```

### `say`

| Key | Type | Meaning |
|---|---|---|
| `by` | actor id | Who speaks; the tail points at this actor's mouth. With `off_panel`, the name of somebody nobody draws |
| `text` | string | The dialogue. Line breaking is computed, not authored. `_word_` stresses a word; see [Emphasis](#emphasis) |
| `prefer` | zone | A hint about placement, honoured when possible |
| `kind` | `speech`, `thought`, `whisper`, `shout` | Balloon styling |
| `size` | `normal`, `small` | `small` for a line muttered or said weakly: smaller type, in a balloon that keeps its room |
| `off_panel` | `true`, or `left`, `right`, `top`, `bottom` | The speaker is outside the panel; the tail ends on the frame. See [Off-panel speech](#off-panel-speech) |

`text` is never pre-wrapped by the author. Wrapping is computed from real font metrics during
compilation, because a balloon's size determines whether it fits where it is wanted — so the
compiler must decide the line breaks before it can place anything.

A double dash, a dash or an ellipsis written as a word of its own — `out --`, `... maybe` — is
never a place to break. [Blambot](https://blambot.com/articles_grammar.shtml) sets one with no
space before or after it, so it belongs to its word: it stays on the line of the word before
it, or of the word after it when it opens the balloon. The space is still lettered as written.

A line of text, a caption and an actor id may not contain a control character other than tab, line
feed and carriage return. Each one is written into the SVG, and XML has no way to write those
characters at all, not even escaped, so a panel holding one is refused with the character named.

### Off-panel speech

```yaml
cast:
  bob: {reference: bob}
script:
  - say: {by: caller, text: "Open up!", off_panel: left}
  - say: {by: bob, text: "Who is it?"}
```

A speaker who is not drawn has no mouth to point at, so their balloon's tail ends on the frame,
on their side — Blambot: "the tail of the balloon generally butts against the panel border". Name
the side, or write `off_panel: true` and the compiler takes the nearer of left and right to where it
put the balloon. Top and bottom are only ever named: balloons sit high, so "the nearest edge" would
aim most tails at the top border, which reads as a speaker above.

An off-panel speaker is somebody nobody draws, so `by` is any name and must **not** be in the
panel's cast: a line marked `off_panel` by somebody who is drawn is `off-panel-speaker`. The
balloon is placed as a caption is — no mouth to stay near — under the same rules: never over a
face, inside the margin, in reading order. Its tail reaches past the margin to the frame itself, or
to the panel's outline when it is slanted.

A scene whose panels share a cast through `over:` cannot leave one member out of one panel, since an
override cannot delete; write that panel's cast out in full. A comic script can, with `(OP)`.

### `caption`

A caption is the panel speaking in its own voice. It is what lets a panel say *where* and *when* it
happens without a character having to explain it out loud — which is the thing writers are told not
to do. Comics solved this long before they had reliable backgrounds.

| Key | Type | Meaning |
|---|---|---|
| `text` | string | What the box says. Line breaking is computed, as for dialogue |
| `kind` | `locale`, `monologue`, `spoken`, `editorial` | What the box is doing |
| `tone` | `paper`, `pale`, `ink` | What the box is filled with. Defaults to `paper` |
| `prefer` | zone | Where it would like to sit. Defaults to `top_left` |
| `by` | any name | Who is speaking, for a `spoken` caption only |

The four kinds are the letterers' own vocabulary, taken from Blambot's *Comic Book Grammar &
Tradition* rather than invented — for the same reason the predicates were taken from Visual Genome.
Note that "narration", the obvious guess, is not one of them.

| Kind | What it is | How it is set |
|---|---|---|
| `locale` | Location and time — "Midnight. The docks." | Italic |
| `monologue` | A character's inner voice | Italic |
| `spoken` | Off-panel dialogue | Roman, in quotation marks |
| `editorial` | The voice of the writer or editor | Italic |

`monologue` has largely replaced the thought balloon in modern comics, so a panel has two ways to
render an inner voice: a `monologue` caption and a `thought` balloon. Both are correct. They are
different eras of the same convention, not a duplication.

**Quotation marks are applied by the compiler**, not by you. In a run of consecutive `spoken`
captions by one speaker, each opens with a quote and only the last one closes — the run is one
continuous line of off-panel speech, and closing every box would read as a series of interruptions.
A change of speaker (`by`) ends the run, so each speaker's last box closes, as Blambot asks: end
quotes "should appear as each speaker finishes". Write the words; the marks are lettering.

**`by` is the one place an actor id is allowed not to resolve.** Everywhere else, naming somebody
who is not in `cast` is an error. A `spoken` caption's speaker is *off panel* by definition, so
requiring them to be cast would defeat the purpose. It is accepted only on `spoken`; on any other
kind it is a mistake and is rejected.

#### `tone`

A caption box is opaque, so its lettering is never the thing at risk — the text sits on the fill
whatever is behind it. What a tone changes is whether the **box** reads. Against the value ladder
the `setting` block produces, a white box on a noon sky is 1.16:1: legible, and invisible.

| Tone | Fill | Where it comes from | Lettered in |
|---|---|---|---|
| `paper` | `#ffffff` | the paper the panel is printed on — **the default** | ink |
| `pale` | `#adadad` | the `day` row of the value ladder, far plane | ink |
| `ink` | `#090909` | the `day` row of the value ladder, foreground | paper |

Two of the three are rungs of the ladder in `solve/backdrop.py`, taken by index rather than restated
as literals, so lettering and backdrop cannot drift apart as either is tuned. A tone is **fixed, not
a function of the panel's `time`**: a caption's value is a property of the caption, and letting it
follow the hour would make the table below a function of the panel.

`ink` produces what letterers call reversed type. **The inversion is decided by the compiler**, by
contrast, and travels in Panel Core as a resolved value — the same rule and the same reason as
falling rain, which is inked over a bright sky and papered over a dark one.

Two floors, and only the first is a rule every tone must meet:

- **Lettering, 4.5:1.** A caption's text against its own fill, WCAG AA for body text. This is the
  contrast a reader actually gets, and every tone in the palette clears it with room — 18.9:1,
  8.4:1 and 19.9:1 respectively.
- **Separation, 3:1.** The box against the plane behind it. *No tone is required to clear this on
  every rung*, and the default does not: white on a noon sky is the case that motivated the feature.
  What the palette owes you is an escape from every background the compiler can produce — at least
  one tone above 3:1 for every rung of every hour — and that is what the test suite checks.

There is no free-form `fill:`, and no yellow. An open colour field would be this language's one open
vocabulary and would let you produce an unreadable box; the classic yellow `locale` caption would be
the first non-neutral value in the codebase, and there is no colour policy to put it under yet.

**Text is set flush left.** This is a *convention*, not a rule the way reading order is: the
lettering references describe left alignment as the norm while calling it a house preference. It is
the default because it is what letterers do, and it is recorded here as a choice rather than a law —
unlike `shot_types.md`, which is normative. Balloons, by contrast, centre their text.

Captions are placed by the same machinery as balloons — the same face avoidance, the same silhouette
occlusion cost, the same hard reading-order rule — because the placement principles for floating
text are the ones the balloon solver already implements. What differs is the pull toward the frame:
a balloon mildly dislikes hugging the panel edge, and a caption is looking for exactly that corner.

### Emphasis

A word written between underscores is stressed, and lettered in **bold italic**:

```yaml
script:
  - caption: {text: "_Later._ The same corner.", kind: locale}
  - say: {by: alice, text: "I _told_ you it would rain."}
```

Bold italic is the letterers' convention for a stressed word: Blambot's *Comic Book Grammar &
Tradition* notes there is almost no plain bold in comics dialogue. The underscore stands in for
the underline a script uses, as Dark Horse's script format asks. It works the same in `say` and
`caption`, in YAML and in a comic script; in an italic caption the stressed word is bold italic
too.

The stressed word is **measured** in bold italic, not just drawn in it. Bold italic is wider than
roman, so a stressed word widens its balloon, or pushes the next word onto another line, by
exactly as much as it is drawn wider. Bold italic is a real font file of the same family, never a
slant applied to the roman, for the reason the italic caption face is one.

The rules are Markdown's for an underscore:

- An underscore **opens** emphasis when nothing alphanumeric is before it and something other
  than a space is after it. Inside emphasis, one **closes** it when something other than a space
  is before it and nothing alphanumeric is after it. A span may run across words: `_told you_`.
- Any other underscore is just an underscore, so `file_name` and `__init__` are lettered as
  written, and `\_` writes one anywhere. In a double-quoted YAML string `\_` is YAML's own escape
  for a no-break space, so write `\\_` there, or use single quotes.
- Emphasis opened and never closed is refused as `unbalanced-emphasis`, located at the line,
  rather than guessed at.

Panel Core keeps each line as the plain text it reads as, and records where the face changes
beside it; see [Panel Core](panel_core.md).

**Why not `*told*`.** Markdown's other marker starts an alias when it opens a YAML value:
`text: *told* you` does not parse at all. A document that trips on it is told to quote the value
and use underscores, but `*` is never read as emphasis, because it is also what a typed grawlix
such as `@#*%!` is made of.

### `sfx`

A sound effect is letters treated as picture. `BLAM` is not dialogue: comics letter sound big,
angled and outlined, near where it happens, with no balloon.

```yaml
script:
  - say: {by: alice, text: "Get down!"}
  - sfx: {text: BLAM, from: bob, size: large, rotate: -14}
  - sfx: {text: tok tok tok, prefer: top_right, size: small, arc: 30}
```

| Key | Type | Meaning |
|---|---|---|
| `text` | string | The sound, lettered exactly as written |
| `from` | actor id | Who or what it comes from; it is placed near them |
| `prefer` | zone | Where it would like to sit, with no source, or as a pull with one |
| `size` | `small`, `medium`, `large` | How loud: 1.6, 2.6 or 4 times the dialogue type size. Defaults to `medium` |
| `rotate` | degrees, -45 to 45 | Turned clockwise. Defaults to level |
| `arc` | degrees, -120 to 120 | Bent along a curve: positive bows the middle up, negative down |
| `hollow` | `true` or `false` | All outline and no fill, so the art shows through |

It is lettered in the **display face**, Bangers, which ships with Scenet; `lettering.font` can name
another as `display:`. A solid effect is ink with a paper outline around every letter, so it reads
over light art and dark alike; a hollow one is the outline alone, in ink. The arc and the rotation
are applied to the glyph outlines, not handed to a renderer, so they come out the same everywhere.

**It is placed, never positioned.** As with every box, the compiler tries candidate positions —
around the actor it comes from, around the zone it prefers, the middle of every zone — and keeps the
cheapest. It **never covers a face**, never leaves the panel or lies under an inset, and two effects
never overlap; it may cover a figure, and prefers its own source's to anyone else's. When nothing
fits, it is reported as `sfx-placement`.

**Balloons pay to cover it, and nobody moves for it.** Effects are placed before any balloon or
caption, since they are part of the picture; a balloon or caption then pays to cover one, exactly as
it pays to cover emanata, and is never forbidden to. No figure and no framing changes.

Size is a multiple of the type size, not of the figure, so an effect reads at a long shot as well as
at a close-up. Nothing is added to the text: no exclamation mark, since sound effects are not
exclamations, and no emphasis — an underscore here is just an underscore.

### Reading order is enforced, not suggested

Balloons and captions are placed in script order, in one pass, and a box may never sit
above-and-left of the one before it. Violating this is not a cosmetic flaw: it makes the panel read
in the wrong order, which is a correctness bug in a comic. The constraint is therefore hard, and a
panel whose boxes cannot be placed without breaking it is rejected rather than rendered wrongly.

Captions take their turn in that sequence rather than being placed first as a layer. A caption
written between two lines of dialogue is read between them; one written last is read last.

A sound effect takes its number in the same sequence — which is the order a reader of the text, or a
screen reader, follows — but is exempt from the geometric rule. A sound sits where the sound is, and
holding it to above-and-left would make many panels impossible to letter.

## `lettering`

How the lettering is set: its size, and the face it is set in.

```yaml
lettering:
  size: 30
  font: {regular: fonts/Comic-Regular.ttf, italic: fonts/Comic-Italic.ttf}
```

| Key | Type | Meaning |
|---|---|---|
| `size` | number above 0 | The dialogue type size, in panel units. Captions keep their proportion to it, 30 parts in 35 |
| `font` | path, or `regular`, `italic`, `bold_italic`, `display` | The font files to letter in, relative to the document |

Left out, dialogue is lettered at 3.5% of the height the panel letters against and captions at
3% — the panel's own height alone, one tier of a three-tier page on a page. That is a good default
and a bad only choice: a page of tight panels wants smaller type, a children's comic larger, and
neither is something the compiler should guess.

`size` is in the same units as `panel.size`, which on a page are the page's, since a panel there is
compiled at its frame's size. Set beside `panels:`, it is a default every panel inherits, which is
how a whole page letters at one size you chose. Set on one panel, it letters that panel alone. In a
comic script, put it in the front matter for every panel, or in an `@lettering:` directive for one.

The type is measured at exactly this size, so it decides how big every balloon is. A size too large
for the panel leaves a balloon nowhere to go, which `scenet check --deep` reports as
`balloon-placement`.

### `font`

Scenet letters in Source Sans Pro unless you name a face of your own. A font is always a **file you
name**, never a font installed on the machine: what is measured has to be the same everywhere, or the
same document would letter differently on two computers.

```yaml
lettering: {font: fonts/Comic-Regular.ttf}           # one file for every face
lettering:
  font:
    regular: fonts/Comic-Regular.ttf                 # dialogue, and spoken captions
    italic: fonts/Comic-Italic.ttf                   # every other caption kind
    bold_italic: fonts/Comic-BoldItalic.ttf          # emphasis
    display: fonts/Shout.ttf                         # sound effects
```

- **Paths are relative to the document**, the way a link in a web page is: `fonts/x.ttf` is the
  `fonts` folder beside the file, wherever `scenet` was run from, and `../fonts/x.ttf` climbs out of
  it. An absolute path is refused, so a document and its fonts move together, and a server compiling
  documents it is sent cannot be pointed at its own files. Text compiled with no file behind it — by
  the MCP server, say — has no folder, and so can name no font.
- **A face you do not name stands in from one you do.** Italic captions are set in `regular`;
  emphasis in `italic`, or in `regular` when there is no italic. A family from one file stays one
  family, rather than mixing your face with the shipped one. When a stand-in is actually used, the
  compiler says so.
- **TrueType or OpenType**, with a Unicode character map, since every line is measured against it
  — kerning included. A path that is absolute, missing, or not such a font is reported as
  `font-file`, at the face that names it.

Panel Core records each face by its family, style and a digest of its bytes, never by where the file
was; see [Panel Core](panel_core.md). Rendering needs the same files, and refuses a panel whose
fonts it was not given rather than draw its lettering in a face it was not measured in. `scenet
build` and the playground hand them over for you. `--live-text` names your font's family.

The faces letterers use are mostly commercial, or free only on their own terms. You can name one;
Scenet can only ship a face whose licence allows it, which is why Source Sans Pro, under the SIL
Open Font License, is the default. In the [playground](https://creatoan.github.io/scenet/playground/),
**Font…** adds a file to the document's `fonts/` folder for as long as the tab is open.

### Capitals are yours to set

Comics are conventionally lettered in capitals, and Scenet sets exactly what you type. It does not
uppercase for you, because doing it well is not a case conversion: the personal pronoun "I" takes a
crossbar that every other capital I does not, and choosing between the two needs a font with both
forms and the contextual substitution that picks one, which only a full text shaper performs.
Scenet applies no glyph substitution at all, so a face that picks its crossbar "I" contextually will
not pick it here either. Write in capitals if you want them.

## `page` and `pages`

A scene can lay its panels out on pages. `pages:` is a list of pages; each page is a list of
**tiers**, top to bottom; each tier is a list of panels, left to right. `page:` is the format they
share.

A comic script's pages are its `PAGE` headings instead; its front matter takes `page:` but
not `pages:`. See [Write a panel as a comic script](../howto/write_a_comic_script.md#pages).

A panel's name, its key under `panels:`, is text, as a cast member's id is. YAML reads an
unquoted `1:` as a number, so a panel named by its number is written `'1':`.

```yaml
page: {size: [1500, 2250], margin: 75, gutter: 30, tier_gutter: 45}
pages:
  - tiers:
      - panels: [{use: establishing, width: 2}, reply]
      - {height: 1.2, panels: [closer]}
      - panels: [her, him]
panels:
  establishing: {...}
  reply: {...}
```

| Key | Means | Default |
|---|---|---|
| `page.size` | Width and height, in the same abstract units a panel uses | `[2000, 3000]` |
| `page.margin` | The blank border inside the page edge | `100` |
| `page.gutter` | The gap between two panels side by side in a tier | `40` |
| `page.tier_gutter` | The gap between two tiers; wider than `gutter`, as in print | `60` |
| `tiers[].height` | The tier's share of the page's height, relative to the other tiers | `1` |
| `panels[].use` | The name of a panel under `panels:`; writing the name alone means `{use: name}` | |
| `panels[].width` | The panel's share of its tier's width, relative to its neighbours | `1` |
| `tiers[].columns` | In place of `panels`: columns side by side, each a stack of panels | |
| `tiers[].slant` | How far the gutters between its panels lean, in degrees, -30 to 30; positive leans the top right | `0` |
| `columns[].width` | The column's share of its tier's width | `1` |
| `columns[].panels[].height` | The panel's share of its column's height | `1` |
| `insets[].use` | On any panel in a tier or column: a panel set into one of its corners | |
| `insets[].at` | `top_left`, `top_right`, `bottom_left` or `bottom_right` | |
| `insets[].size` | Its width and height, as a fraction of its parent's; above 0, at most 0.5 | |
| `insets[].read` | `after` its parent, or `before` it | `after` |

Shares work like CSS Grid's `fr` tracks: what the margin and gutters leave is divided in
proportion to the weights. A splash page is one tier holding one panel.

A tier holds `panels` or `columns`, never both. **Columns** are how a tall panel beside a stack
of short ones is written: the tier is split across into columns, and each column down into its
panels, with `tier_gutter` between them.

```yaml
- height: 2
  columns:
    - {width: 2, panels: [above, {use: below, height: 2}]}
    - {width: 1, panels: [falling]}   # spans the tier's whole height
```

A tier of columns is read column by column and top to bottom in each: `above`, `below`, then
`falling`. That is the order readers take when a panel spanning the tier blocks the way across
(about nine in ten of them, in Cohn's 2013 experiments). Two stacks side by side have nothing
between them blocking the way, and readers go across those instead, so they are refused as
`page-layout`; write them as tiers, or put a panel that spans the tier between them.

An **inset** is a small panel set into a corner of another and drawn over it:

```yaml
- panels:
    - use: street
      insets:
        - {use: clock, at: top_left, size: 0.2, read: before}
        - {use: face, at: bottom_right, size: 0.3}
```

It sits a gutter in from both edges of its corner, ringed by a gutter's width of white. Readers
split about evenly over whether an inset comes before the panel it sits in or after it (Cohn,
2013), so it is never guessed: an inset is read right after its parent unless it says
`read: before`. Here that is `clock`, `street`, `face`.

The parent's art is drawn exactly as if the inset were not there; only its lettering moves, since
words under an inset could not be read. When an inset covers a character's face, the compiler
notes it. Two insets in one panel must stay a gutter clear of each other, and an inset, a gutter
in from its corner, must fit inside its panel.

A tier of panels can **slant**, for a beat that should not sit square:

```yaml
- {slant: 12, panels: [wind_up, {use: swing, width: 1.3}]}
```

Every gutter in the tier leans by that many degrees about its centre at the tier's mid-height, so
the weights share the width out exactly as they would upright, and neighbours share one cut. A
gutter stays a gutter wide measured across the cut, as paneling tools keep it, and the tier's outer
edges stay upright. Each frame is then a four-sided shape, convex by construction.

A slanted panel is staged and framed in its bounding box, as a rectangle would be, and cropped to
its outline the way a margin crops; its lettering stays inside the outline. When the cut runs
through a character's face, the compiler notes it. A slant needs gutters to lean, so a tier of
columns, a tier of one panel, and a slanted panel with insets are refused, as is a slant so steep
that a panel would have no width left at its top or bottom.

**A panel on a page is compiled at its frame's size**, exactly as it would be compiled alone at that
size: the page decides how big the frame is and nothing about what goes in it. The one other thing
it decides is **type size**. Alone, a panel letters at a fixed fraction of its own height; on a page
every panel letters at the same size, as if each were one tier of a three-tier page, because no
letterer sets a short panel and a tall one at different sizes. A size you set with
[`lettering`](#lettering) takes its place.

A page is read tier by tier, left to right, and down each column, so the order panels are written
in is the order they are read in; that holds by construction. A panel can be on one page once. A panel
on no page is allowed, and compiles as it always did; it may exist only to be inherited from with
`over:`. A placement naming a panel `panels:` does not define, a panel placed twice, a tier with
both `panels` and `columns` or neither, two stacks side by side, two insets that overlap, an inset
too big for its panel, a slant that cannot apply or is too steep, or margins and gutters that leave
no room are reported as `page-layout`.

Not yet: frames of any other shape, such as round panels or ones without borders; right-to-left
reading ([#68](https://github.com/creatoan/scenet/issues/68)), comic-script `PAGE` headings as pages
([#75](https://github.com/creatoan/scenet/issues/75)), and print sizes with trim and bleed
([#80](https://github.com/creatoan/scenet/issues/80)).

## When constraints conflict

Placement values are preferences of differing strength, and the solver resolves conflicts by
priority rather than by failing:

| Strength | Examples |
|---|---|
| **Required** | Actors never overlap; declared `left_of` / `right_of` ordering holds; balloons never cover a face; reading order holds |
| **Strong** | Actors stay inside the panel, but may bleed past its edge when the cast does not fit, which is ordinary comics practice |
| **Weak** | `at:` anchors, `prefer:` balloon hints |

So two actors both asked to stand at `center` will be pushed apart rather than overlapping: the
required non-overlap wins and the weak anchors yield. This is why `at` is documented as a
preference. If you need a guarantee, express it as a relation in `staging`.

## Determinism

The same source always compiles to byte-identical output. No wall-clock time, no unseeded
randomness, no dependence on mapping iteration order. This is what makes a panel description a
durable artifact rather than a prompt: it will render the same in five years as it does today.

It is the same on every platform too. Every file Scenet writes, and every document it prints
for redirecting into one, is UTF-8 with LF line endings, on Windows as on Linux.

Backdrop silhouettes are generated, so they are seeded — from the declared setting and the panel
size, through a content hash. Never a clock, and never Python's `hash()`, which is salted per
process and would agree with itself all day while disagreeing with tomorrow's build.

### The contract is on the SVG text, not on pixels

Worth stating explicitly, because it is exactly the kind of assumption that rots silently.

> **The determinism contract is on the emitted SVG text, which stays byte-identical. It has never
> been on pixels.**

The `feTurbulence` filter that draws fog and cloud is reproducible *by definition* — SVG has Perlin
noise built in, the specification includes reference code, and the `seed` is fixed by the compiler
— so the emitted document is identical every time. In practice browsers agree only
[approximately](https://tympanus.net/codrops/2019/02/19/svg-filter-effects-creating-texture-with-feturbulence/)
on what to paint from it. That is fine, and it was already true of every glyph outline and every
antialiased edge in the file.

Golden-file tests therefore target Panel Core and SVG **text**, never a raster. If a raster check is
ever wanted, [resvg](https://github.com/linebender/resvg) is the candidate: it supports
`feTurbulence`, aims at the whole specification rather than the common cases, and ships around 1600
SVG-to-PNG regression tests — which matters because the W3C SVG test suite was abandoned long ago,
making resvg's the practical conformance reference.
