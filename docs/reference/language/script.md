# `script`

<!-- facts: script -->
What is said and heard, in the order it is read: `say` for a balloon, `caption` for a box, `sfx` for a sound effect.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: the panel's cues, captions and sound effects, in the order written |
| Type | a list of mappings |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `balloon-placement`, `word-limit` |
| In the gallery | [Reading order](../../gallery.md#reading-order) |
<!-- /facts -->

An ordered list of what is said and heard, each entry tagged by a verb: [`say`](#say) puts a line
in a balloon, [`caption`](#caption) puts one in a box, and [`sfx`](#sfx) letters a sound effect
into the picture. **Order is meaningful**: it is the order the reader reads them, and it
constrains where each box may be placed.

![Four balloons, First, Second, Third and Fourth, placed so that they read in that order](../../images/gallery/06-reading-order.svg)

**Reading order is enforced, not suggested.** Balloons and captions are placed in script order, in
one pass, and a box may never sit above-and-left of the one before it -- above-and-*right* in a
comic read right to left (see [`direction`](direction.md#direction)). Violating this is not a
cosmetic flaw: it makes the panel read in the wrong order, which is a correctness bug in a comic.
The constraint is therefore hard, and a panel whose boxes cannot be placed without breaking it is
refused as `balloon-placement` rather than rendered wrongly. That is the {term}`reading order`.

Captions take their turn in that sequence rather than being placed first as a layer: a caption
written between two lines of dialogue is read between them. A sound effect takes its number in the
same sequence -- the order a reader of the text, or a screen reader, follows -- but is exempt from
the geometric rule: a sound sits where the sound is, and holding it to above-and-left would make
many panels impossible to letter. Read right to left, it stays exempt, and stays where it was: a
sound is part of the picture, which is not mirrored.

That sequence is what a screen reader hears. Every SVG names each panel with its
[description](description.md#description) and then every balloon, caption and sound effect in this
order -- `Caption: Midnight. Alice: You forgot your umbrella! Bob, whispering: I know.` --
whatever order they are painted in; see [accessible output](../../howto/make_accessible_output.md).
A panel with more words than a letterer fits well gives a `word-limit` note.

```{scenet-example}
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third, facing: left}
script:
  - caption: {text: "Midnight. The docks.", kind: locale}
  - say: {by: alice, text: "You forgot your umbrella!"}
  - say: {by: bob, text: "I know.", kind: whisper}
```

**See also:** [When constraints conflict](index.md#when-constraints-conflict),
[Write a panel as a comic script](../../howto/write_a_comic_script.md).

## `say`

<!-- facts: say -->
A line of dialogue, in a balloon whose tail points at the speaker.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: a cue in capitals, `ALICE`, with the line under it or after a colon |
| Type | a mapping |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `unknown-key`, `duplicate-key` |
<!-- /facts -->

A line of dialogue: a balloon, with a tail to the speaker's mouth. Its keys say who speaks, what,
how, and from where.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - say: {by: alice, text: "Hello."}
```

**See also:** [`caption`](#caption), words nobody in the panel says.

## `say.by`

<!-- facts: say.by -->
Who speaks: an actor id in the cast, whose mouth the tail points at. With `off_panel`, the name of somebody nobody draws.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: the cue's name, `ALICE` |
| Type | text |
| Default | none: required |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `missing-field`, `unknown-actor`, `off-panel-speaker` |
<!-- /facts -->

The tail of the balloon points at this actor's mouth -- the `mouth` anchor of their puppet, or of
the figure in a picture's contract. A name not in the cast is `unknown-actor`, unless the line is
spoken [from off panel](#sayoff_panel), when it must **not** be in the cast: a line marked
`off_panel` by somebody who is drawn is `off-panel-speaker`.

```{scenet-example}
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third, facing: left}
script:
  - say: {by: bob, text: "It was me."}
```

**See also:** [`cast`](cast.md#cast), [`caption.by`](#captionby).

## `say.text`

<!-- facts: say.text -->
The line, as one string; the compiler breaks it into lines. A word between underscores, `_word_`, is stressed, and lettered in bold italic.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: the lines under the cue, or after `ALICE:` |
| Type | text |
| Default | none: required |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `missing-field`, `unbalanced-emphasis`, `word-limit`, `balloon-placement` |
| In the gallery | [How lines break](../../gallery.md#how-lines-break), [Emphasis](../../gallery.md#emphasis) |
<!-- /facts -->

`text` is never pre-wrapped by the author. Wrapping is computed from real font metrics during
compilation, because a balloon's size determines whether it fits where it is wanted -- so the
compiler must decide the line breaks before it can place anything.

![Alice and Bob, with a long line of Alice's broken across several lines of her balloon](../../images/gallery/14-lettering.svg)

A double dash, a dash or an ellipsis written as a word of its own -- `out --`, `... maybe` -- is
never a place to break. [Blambot](https://blambot.com/articles_grammar.shtml) sets one with no
space before or after it, so it belongs to its word: it stays on the line of the word before it,
or of the word after it when it opens the balloon. The space is still lettered as written. A line
of text, a caption and an actor id may not contain a control character other than tab, line feed
and carriage return: XML has no way to write one, so a panel holding one is refused with the
character named.

**Emphasis.** A word written between underscores is stressed, and lettered in **bold italic**, the
letterers' convention: Blambot's *Comic Book Grammar & Tradition* notes there is almost no plain
bold in comics dialogue. The underscore stands in for the underline a script uses, as Dark
Horse's script format asks. It works the same in `say` and `caption`, in YAML and in a comic
script; in an italic caption the stressed word is bold italic too.

![Alice, angry, says: I told you it would rain, with told lettered in bold italic](../../images/gallery/28-emphasis.svg)

The stressed word is **measured** in bold italic, not just drawn in it, so it widens its balloon,
or pushes the next word onto another line, by exactly as much as it is drawn wider. The rules are
Markdown's for an underscore:

- An underscore **opens** emphasis when nothing alphanumeric is before it and something other
  than a space is after it. Inside emphasis, one **closes** it when something other than a space
  is before it and nothing alphanumeric is after it. A span may run across words: `_told you_`.
- Any other underscore is just an underscore, so `file_name` and `__init__` are lettered as
  written, and `\_` writes one anywhere. In a double-quoted YAML string `\_` is YAML's own escape
  for a no-break space, so write `\\_` there, or use single quotes.
- Emphasis opened and never closed is refused as `unbalanced-emphasis`, located at the line,
  rather than guessed at.

**Why not `*told*`.** Markdown's other marker starts an alias when it opens a YAML value:
`text: *told* you` does not parse at all. A document that trips on it is told to quote the value
and use underscores, but `*` is never read as emphasis, because it is also what a typed grawlix
such as `@#*%!` is made of. {term}`Panel Core` keeps each line as the plain text it reads as, and records
where the face changes beside it; see [Panel Core](../panel_core.md).

```{scenet-example}
cast: {alice: {reference: alice, expression: angry}}
script:
  - say: {by: alice, text: "I _told_ you it would rain."}
```

**See also:** [`lettering.font.bold_italic`](lettering.md#letteringfontbold_italic),
[`lettering.size`](lettering.md#letteringsize).

## `say.prefer`

<!-- facts: say.prefer -->
Where the balloon would like to sit, one of nine zones of the panel. The weakest placement term: face avoidance and reading order override it.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a name |
| Values | `top_left`, `top_center`, `top_right`, `middle_left`, `middle_center`, `middle_right`, `bottom_left`, `bottom_center`, `bottom_right` |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field` |
| In the gallery | [Placement zones](../../gallery.md#placement-zones), [The other five zones](../../gallery.md#the-other-five-zones) |
<!-- /facts -->

A zone is one of nine places in the panel: three across -- `left`, `center`, `right` -- in three
rows, `top`, `middle` and `bottom`. It is the **weakest** of all the placement terms: face avoidance,
the margin and reading order override it freely, and a balloon is placed elsewhere rather than
cover a face to sit in its zone. Left out, a balloon sits where its speaker and the line before it
leave room, which is usually high.

![Alice in a full shot with four balloons, each in the corner it asked for: top left, top right, bottom left and bottom right](../../images/gallery/05-placement-zones.svg)

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - say: {by: alice, text: "Down here.", prefer: bottom_right}
```

**See also:** [`caption.prefer`](#captionprefer), [`sfx.prefer`](#sfxprefer).

## `say.kind`

<!-- facts: say.kind -->
The balloon the line is carried in: `speech`, `thought`, `whisper` or `shout`.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: a parenthetical: `BOB (whisper)`, `(shout)`, `(thought)` |
| Type | a name |
| Values | `speech`, `thought`, `whisper`, `shout` |
| Default | `speech` |
| Since | 0.1 |
| Diagnostics | `invalid-field` |
| In the gallery | [Every balloon kind](../../gallery.md#every-balloon-kind) |
<!-- /facts -->

The kind changes the outline and the tail, never the placement: a whisper is held to exactly the
same face avoidance and reading order as a shout.

![Alice and Bob in four balloons: a dashed whisper, a spiked shout, a speech balloon and a cloud for a thought](../../images/gallery/04-balloon-kinds.svg)

| Kind | Outline | Tail |
|---|---|---|
| `speech` | rounded rectangle | tapered pointer |
| `thought` | ellipse | trail of bubbles |
| `whisper` | dashed rounded rectangle | tapered pointer |
| `shout` | jagged burst | tapered pointer |

A `monologue` caption is the other way to letter an inner voice, and has largely replaced the
thought balloon in modern comics. Both are correct: they are different eras of one convention.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - say: {by: alice, text: "Watch out!", kind: shout}
```

**See also:** [`caption.kind`](#captionkind).

## `say.size`

<!-- facts: say.size -->
`small` for a line muttered, said under the breath or weakly: smaller type, in a balloon that keeps its room.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `BOB (small)` or `BOB (weak)` |
| Type | a name |
| Values | `normal`, `small` |
| Default | `normal` |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

Dark Horse lists "(small)" and "(weak)" among the common indications for modified lettering.
Blambot: a reduced size is used when a character mutters, says something to themself, or speaks
sheepishly. So `small` is smaller type in the balloon the line would have had, which reads as
quieter rather than as a smaller balloon.

```{scenet-example}
cast: {bob: {reference: bob}}
script:
  - say: {by: bob, text: "...sorry.", size: small}
```

**See also:** [`lettering.size`](lettering.md#letteringsize), the size `small` is smaller than.

## `say.off_panel`

<!-- facts: say.off_panel -->
The speaker is outside the panel: `true`, or the side of the frame they are on. The tail ends on the frame there.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `ALICE (OP)`, or `ALICE (OP, left)` with a side |
| Type | `true` or `false`, or a name |
| Values | `left`, `right`, `top`, `bottom` |
| Default | `false` |
| Since | 0.11 |
| Diagnostics | `invalid-field`, `off-panel-speaker` |
| In the gallery | [Off-panel speech](../../gallery.md#off-panel-speech), [Looking off panel](../../gallery.md#looking-off-panel) |
<!-- /facts -->

A speaker who is not drawn has no mouth to point at, so their balloon's tail ends on the frame, on
their side -- Blambot: "the tail of the balloon generally butts against the panel border". Name the
side, or write `off_panel: true` and the compiler takes the nearer of left and right to where it
put the balloon -- which it puts high on the side reading starts from, top left, or top right in a
comic read right to left. A side you name is a side of the panel, whichever way it is read. Top and
bottom are only ever named: balloons sit high, so "the nearest edge" would aim most tails at the
top border, which reads as a speaker above.

![Bob in a room at night, answering voices from off panel whose balloons' tails run to the edge of the frame](../../images/gallery/32-off-panel.strip.svg)

The balloon is placed as a caption is -- no mouth to stay near -- under the same rules: never over
a face, inside the margin, in reading order. Its tail reaches past the margin to the frame itself,
or to the panel's outline when it is slanted.

**Somebody heard from off panel may be looked at**, and by `looking_at` only -- nothing else can be
staged against a figure nobody draws. `bob looking_at carol` turns Bob toward Carol's side of the
frame, left or right, and aims his eyes straight out of it, up or down for `top` and `bottom`. With
`off_panel: true` and no side named, Carol is heard from the side Bob faces, so the tail and his
look agree.

A panel that shares a cast, through `over:` or a scene's defaults, leaves a member out with `null`:
`cast: {carol: null}`, and Carol is not drawn there -- so she may speak from off panel in it. Of the
relations the panel shares that name her, `bob looking_at carol` still holds while she does, and her
`off_panel: true` ends on the side she was written to stand on, `at: left_third` being the left,
unless her line names one; every other relation goes. A comic script does it with `(OP)`.

```{scenet-example}
cast: {bob: {reference: bob}}
script:
  - say: {by: caller, text: "Open up!", off_panel: left}
  - say: {by: bob, text: "Who is it?"}
```

**See also:** [`staging[].object`](staging.md#stagingobject), [`null`](scene.md#null-leaves-something-out).

## `caption`

<!-- facts: caption -->
A caption: a box in which the panel speaks in its own voice, with no tail.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `CAPTION:` or `CAP:` |
| Type | a mapping |
| Default | none |
| Since | 0.4 |
| Diagnostics | `invalid-field`, `unknown-key`, `duplicate-key` |
<!-- /facts -->

A caption is the panel speaking in its own voice. It is what lets a panel say *where* and *when* it
happens without a character having to explain it out loud -- which is the thing writers are told
not to do. Comics solved this long before they had reliable backgrounds.

It is placed by the same machinery as balloons -- the same face avoidance, the same silhouette
cost, the same hard reading order -- because the placement principles for floating text are the
ones the balloon solver already implements. What differs is the pull toward the frame: a balloon
mildly dislikes hugging the panel edge, and a caption is looking for exactly that corner. A caption
has no tail and no speaker to point at, which is why it is not a fifth kind of balloon.

**Text is set flush left.** This is a *convention*, not a rule the way reading order is: the
lettering references describe left alignment as the norm while calling it a house preference.
Balloons, by contrast, centre their text. Both hold in a comic read right to left: its text still
reads left to right.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "Midnight. The docks."}
```

**See also:** [`say`](#say).

## `caption.text`

<!-- facts: caption.text -->
What the box says, as one string; line breaks are computed. A word between underscores, `_word_`, is stressed.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: after `CAPTION:`, or the lines under `CAP:` |
| Type | text |
| Default | none: required |
| Since | 0.4 |
| Diagnostics | `invalid-field`, `missing-field`, `unbalanced-emphasis`, `word-limit`, `balloon-placement` |
<!-- /facts -->

As for dialogue, line breaking is computed, and a word between underscores is stressed; see
[`say.text`](#saytext). Captions are lettered at 30 parts in 35 of the dialogue size.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "_Later._ The same corner."}
```

**See also:** [`lettering.size`](lettering.md#letteringsize).

## `caption.kind`

<!-- facts: caption.kind -->
What the box is doing: `locale` for a place and time, `monologue` for an inner voice, `spoken` for speech from off panel, `editorial` for the writer's voice.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: a parenthetical: `CAPTION (monologue):` |
| Type | a name |
| Values | `locale`, `monologue`, `spoken`, `editorial` |
| Default | `locale` |
| Since | 0.4 |
| Diagnostics | `invalid-field` |
| In the gallery | [Captions](../../gallery.md#captions) |
<!-- /facts -->

The four kinds are the letterers' own vocabulary, taken from Blambot's *Comic Book Grammar &
Tradition* rather than invented -- for the same reason the predicates were taken from Visual
Genome. Note that "narration", the obvious guess, is not one of them.

![Alice and Bob on the docks with four captions: a place and time, an inner voice, a line spoken off panel, and an editor's note](../../images/gallery/16-captions.svg)

| Kind | What it is | How it is set |
|---|---|---|
| `locale` | Location and time -- "Midnight. The docks." | Italic |
| `monologue` | A character's inner voice | Italic |
| `spoken` | Off-panel dialogue | Roman, in quotation marks |
| `editorial` | The voice of the writer or editor | Italic |

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "She had walked since dawn.", kind: monologue}
```

**See also:** [`caption.by`](#captionby), [`say.kind`](#saykind).

## `caption.tone`

<!-- facts: caption.tone -->
What the box is filled with: `paper`, `pale`, `ink`, which is lettered in paper, or `warm`, yellow under `palette: tinted`.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a name |
| Values | `paper`, `pale`, `ink`, `warm` (since 0.13) |
| Default | `paper` |
| Since | 0.6 |
| Diagnostics | `invalid-field` |
| In the gallery | [Caption tones](../../gallery.md#caption-tones), [A yellow caption](../../gallery.md#a-yellow-caption) |
<!-- /facts -->

A caption box is opaque, so its lettering is never the thing at risk -- the text sits on the fill
whatever is behind it. What a tone changes is whether the **box** reads. Against the value ladder
the `setting` block produces, a white box on a noon sky is 1.16:1: legible, and invisible.

![Alice in a field under a noon sky, with three captions in three corners: a white box that all but vanishes into the sky, a grey one, and a black one lettered in white](../../images/gallery/22-caption-tones.svg)

| Tone | Fill | Where it comes from | Lettered in |
|---|---|---|---|
| `paper` | `#ffffff` | the paper the panel is printed on -- **the default** | ink |
| `pale` | `#adadad` | the `day` row of the value ladder, far plane | ink |
| `ink` | `#090909` | the `day` row of the value ladder, foreground | paper |
| `warm` | `#eeeeee` | the `day` row of the value ladder, atmosphere -- yellow under `tinted` | ink |

Three of the four are rungs of the ladder in `solve/backdrop.py`, taken by index rather than
restated as literals, so lettering and backdrop cannot drift apart as either is tuned. A tone is
**fixed, not a function of the panel's `time`**: a caption's value is a property of the caption.
`ink` produces what letterers call reversed type, and **the inversion is decided by the compiler**,
by contrast, and travels in Panel Core as a resolved value -- the same rule as falling rain, which
is inked over a bright sky and papered over a dark one.

Two floors, and only the first is a rule every tone must meet:

- **Lettering, 4.5:1.** A caption's text against its own fill, WCAG AA for body text. Every tone
  clears it with room -- 18.9:1, 8.4:1, 19.9:1 and 16.3:1 respectively, and `warm` 16.4:1 on its
  yellow.
- **Separation, 3:1.** The box against the plane behind it. *No tone is required to clear this on
  every rung*, and the default does not: white on a noon sky is the case that motivated the
  feature. What the palette owes you is an escape from every background the compiler can produce
  -- at least one tone above 3:1 for every rung of every hour -- and that is what the test suite
  checks.

`warm` is the classic yellow `locale` caption. Its value is a rung of the ladder like the others,
and its lettering is chosen on that grey; under [`palette: tinted`](palette.md#palette) its box is
drawn in the grey's twin, the pale yellow `#fef0a1`, of the same lightness. In `mono` it is the
grey, which is what a black-and-white reprint does to a yellow caption. `paper`, `pale` and `ink`
stay neutral in every palette. There is no free-form `fill:`: an open colour field would be this
language's one open vocabulary and would let you produce an unreadable box.

```{scenet-example}
setting: {place: field, time: day}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "Noon. Nothing for miles.", tone: ink}
```

**See also:** [`setting.time`](setting.md#settingtime), [`palette`](palette.md#palette).

## `caption.prefer`

<!-- facts: caption.prefer -->
Where the box would like to sit, one of nine zones of the panel. Left out, where reading starts: `top_left`, or `top_right` read right to left.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a name |
| Values | `top_left`, `top_center`, `top_right`, `middle_left`, `middle_center`, `middle_right`, `bottom_left`, `bottom_center`, `bottom_right` |
| Default | none |
| Since | 0.4 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

The same nine zones as a balloon's [`prefer`](#sayprefer), and as weak. Left out, a caption goes
where a `locale` caption conventionally does: where reading starts, the top left, or the top right
in a comic read right to left.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "Continued next issue.", kind: editorial, prefer: bottom_right}
```

**See also:** [`direction`](direction.md#direction).

## `caption.by`

<!-- facts: caption.by -->
Who is speaking, for a `spoken` caption only: any name, in the cast or not.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `CAP/ALICE`, or `ALICE (V.O.)` |
| Type | text |
| Default | none |
| Since | 0.4 |
| Diagnostics | `invalid-field`, `caption-speaker` |
<!-- /facts -->

**`by` is the one place an actor id is allowed not to resolve.** Everywhere else, naming somebody
who is not in `cast` is an error. A `spoken` caption's speaker is *off panel* by definition, so
requiring them to be cast would defeat the purpose. It is accepted only on `spoken`; on any other
kind it is `caption-speaker`.

**Quotation marks are applied by the compiler**, not by you. In a run of consecutive `spoken`
captions by one speaker, each opens with a quote and only the last one closes -- the run is one
continuous line of off-panel speech, and closing every box would read as a series of
interruptions. A change of speaker ends the run, so each speaker's last box closes, as Blambot
asks. Write the words; the marks are lettering.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - caption: {text: "Don't look back.", kind: spoken, by: mother}
```

**See also:** [`say.off_panel`](#sayoff_panel), a balloon spoken from off panel.

## `sfx`

<!-- facts: sfx -->
A sound effect: letters lettered into the picture, with no balloon.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `SFX: BLAM` |
| Type | a mapping |
| Default | none |
| Since | 0.11 |
| Diagnostics | `invalid-field`, `unknown-key`, `duplicate-key`, `sfx-placement` |
| In the gallery | [Sound effects](../../gallery.md#sound-effects) |
<!-- /facts -->

A sound effect is letters treated as picture. `BLAM` is not dialogue: comics letter sound big,
angled and outlined, near where it happens, with no balloon. It is lettered in the **display
face**, Bangers unless [`lettering.font.display`](lettering.md#letteringfontdisplay) names
another. A solid effect is ink with a paper outline around every letter, so it reads over light art
and dark alike. The arc and the rotation are applied to the glyph outlines, so they come out the
same in every viewer.

![Alice and Bob with three sound effects lettered into the picture: KRAK, tok tok tok and WHOOSH](../../images/gallery/30-sound-effects.svg)

**It is placed, never positioned.** As with every box, the compiler tries candidate positions --
around the actor it comes from, around the zone it prefers, the middle of every zone -- and keeps
the cheapest. It **never covers a face**, never leaves the panel or lies under an inset, and two
effects never overlap; it may cover a figure, and prefers its own source's to anyone else's. When
nothing fits, it is `sfx-placement`.

**Balloons pay to cover it, and nobody moves for it.** Effects are placed before any balloon or
caption, since they are part of the picture; a balloon or caption then pays to cover one, exactly
as it pays to cover emanata, and is never forbidden to. No figure and no framing changes.

```{scenet-example}
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third, facing: left}
script:
  - say: {by: alice, text: "Get down!"}
  - sfx: {text: BLAM, from: bob, size: large, rotate: -14}
```

**See also:** [`cast.<id>.marks`](cast.md#castidmarks), the other picture a balloon pays to cover.

## `sfx.text`

<!-- facts: sfx.text -->
The sound, lettered exactly as written, in the display face.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: after `SFX:`, or the line under it |
| Type | text |
| Default | none: required |
| Since | 0.11 |
| Diagnostics | `invalid-field`, `missing-field` |
<!-- /facts -->

Nothing is added to the text: no exclamation mark, since sound effects are not exclamations, and no
emphasis -- an underscore here is just an underscore. Write it in capitals or not, as the sound
should read.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: tok tok tok, size: small}
```

**See also:** [`sfx.size`](#sfxsize).

## `sfx.from`

<!-- facts: sfx.from -->
Written `from`: the actor id the sound comes from, which it is placed near.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `SFX (BOB): KRAK` |
| Type | text |
| Default | none |
| Since | 0.11 |
| Diagnostics | `invalid-field`, `unknown-actor` |
<!-- /facts -->

Written `from`, the actor the sound comes from. The effect is tried around them first, and prefers
to cover its own source's figure over anyone else's. Left out, the effect is placed by its
`prefer`, or anywhere it fits.

```{scenet-example}
cast: {bob: {reference: bob}}
script:
  - sfx: {text: KRAK, from: bob}
```

**See also:** [`sfx.prefer`](#sfxprefer).

## `sfx.prefer`

<!-- facts: sfx.prefer -->
Where the effect would like to sit, one of nine zones of the panel: on its own, or as a pull on an effect that has a `from`.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a name |
| Values | `top_left`, `top_center`, `top_right`, `middle_left`, `middle_center`, `middle_right`, `bottom_left`, `bottom_center`, `bottom_right` |
| Default | none |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
| In the gallery | [A sound pulled to a zone](../../gallery.md#a-sound-pulled-to-a-zone) |
<!-- /facts -->

With no `from`, the zone the effect would like to sit in. With one, a pull: the effect stays near
its source and leans toward the zone.

![A sound placed by who makes it but pulled toward the zone it prefers, turned clockwise or the other way](../../images/gallery/43-sound-pulled-to-a-zone.svg)

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: WHOOSH, from: alice, prefer: top_right}
```

**See also:** [`say.prefer`](#sayprefer), every zone.

## `sfx.size`

<!-- facts: sfx.size -->
How loud: `small`, `medium` or `large`, lettered at 1.6, 2.6 or 4 times the dialogue type size.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `SFX (large): KRAK` |
| Type | a name |
| Values | `small`, `medium`, `large` |
| Default | `medium` |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

A multiple of the type size, not of the figure, so an effect reads at a long shot as well as at a
close-up: a sound does not get quieter because the camera stepped back. Three steps, not a number,
for the reason every other size in the language is named -- the author says how loud, the compiler
says how big.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: BOOM, size: large}
```

**See also:** [`lettering.size`](lettering.md#letteringsize).

## `sfx.rotate`

<!-- facts: sfx.rotate -->
How far the effect is turned clockwise, in degrees, from -45 to 45.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a number |
| Values | -45 to 45 |
| Default | `0` |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

Comics angle their sound effects; the default is level, and the angle is the author's. Positive
turns the effect clockwise, negative the other way.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: SLAM, rotate: 20}
```

**See also:** [`sfx.arc`](#sfxarc).

## `sfx.arc`

<!-- facts: sfx.arc -->
How far the line of letters bends, in degrees, from -120 to 120: positive bows its middle up, negative down.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | a number |
| Values | -120 to 120 |
| Default | `0` |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

The line of letters bends through this many degrees: positive bows its middle up, negative down.
The letters are bent as outlines, each set along the curve.

```{scenet-example}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: BOING, arc: 60}
```

**See also:** [`sfx.rotate`](#sfxrotate).

## `sfx.hollow`

<!-- facts: sfx.hollow -->
`true` letters the effect as an outline with no fill, so the art shows through: an open effect.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. Not in a comic script |
| Type | `true` or `false` |
| Default | `false` |
| Since | 0.11 |
| Diagnostics | `invalid-field` |
<!-- /facts -->

An open effect is all outline, in ink, and no fill, so the art behind shows through the letters --
what letterers draw for a sound that should not hide the picture.

```{scenet-example}
setting: {place: street, time: night}
cast: {alice: {reference: alice}}
script:
  - sfx: {text: WHOOSH, hollow: true}
```

**See also:** [`sfx`](#sfx).
