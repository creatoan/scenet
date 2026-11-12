# Design decisions

Non-obvious decisions, with reasoning, so they can be revisited rather than rediscovered. They
are grouped by theme, and each says what was chosen, why, and what it costs.

## The language

What a document can say, and what it is never asked to say.

### Shot types are crop landmarks, not panel fractions

The tempting definition of a medium shot is "the figure fills about 60% of panel height". It is
wrong. A shot type names **where the frame cuts the body** — waist, chest, shoulders. What fraction
of the panel the figure then occupies is a *consequence*, and it differs for a child versus an
adult, or a seated versus a standing pose. Encoding the fraction bakes in one body and one pose.

See [shot_types.md](../reference/shot_types.md), which is normative.

### Cassowary is linear, so the language must resolve disjunctions

Non-overlap between two actors is a disjunction — A left of B, **or** B left of A — and no linear
solver can express a choice. Rather than reaching for a mixed-integer solver, the DSL resolves
ordering at parse time, so the solver always receives a linear system.

This is a *language* constraint, not merely an implementation detail: it is why there is no
unordered `beside` predicate. Any future construct that reintroduces a disjunction must resolve it
in the frontend.

### An off-panel speaker is not in the cast

Off-panel speech needs a speaker who is not drawn, and every speaker used to have to be in the cast
— which is the list of who *is* drawn. So `off_panel` lets `by` name anybody, and forbids naming a
cast member: somebody both drawn and off panel in one panel contradicts themselves, and is
`off-panel-speaker`. The tail ends on the frame (Blambot), never nowhere: a tailless balloon was
considered and set aside, since a balloon with no pointer has no attributed speaker. Panel Core
records the side the solver settled on, so a reader of the Core knows the tail's end is on the
frame and the speaker is not an actor; the field is left out when unset, and every Core written
before it is unchanged.

### Notes report a house limit; errors a contradiction

Every finding was an error, and any finding failed `scenet check`. That was right while every
rule was a contradiction — an actor not in the cast, staging that loops — which no compile
can get past. Dark Horse's "approximately 25 words per balloon, and about 50 words per panel,
max" is a different kind of thing: a limit a letterer works to, which a panel can exceed and
still be drawn. Failing a check over it would make the check lie about whether the document
builds, and CI would key off the lie.

So a rule has a level. An **error** fails the check, and is exactly what stops `build`; the
seam between the two is tested as "no errors if and only if the build succeeds". A **note** is
reported with its rule and its place, as SARIF `note`, so an editor shows it as information,
and never fails anything. `--deep` runs on a document with notes, since notes do not stop the
compile it would run.

## Placement

How the solver decides where things go, and what it pays for.

### Balloon placement: candidate scoring, not a grid sweep

Discretising the panel into a cost grid and scanning every cell is the obvious approach, and is both
slower and worse. Balloons belong in a small number of sensible positions relative to their speaker.
So candidates are generated map-labelling style — a ring of directions and radii around the
speaker's head, plus the panel corners — and scored. Fewer evaluations, more natural results.

### Emanata are a soft cost, not part of the hull

Plewds, squeans, grawlixes and briffits are drawn outside the head circle, which is exactly where
balloons go, so they had to mean something to the solver. There were three choices:

- **Enter the hull.** The simplest, and wrong. The hull is also what staging spaces characters by
  and what the camera fits, so a character who started sweating would stand further from everyone
  else, and the framing could retreat. A mark would move people the author never asked to move.
- **Forbid them outright, as a face is.** A face exclusion is affordable because a face is one small
  disc that tails already route around. Emanata ring the head and sit on the ground behind it; making
  all of that illegal turns a crowded panel into `BalloonPlacementError` over a drop of sweat.
- **A cost of their own.** Each mark has a zone, and a balloon or caption pays for the fraction of
  its box that covers one — the same normalisation as hull occlusion, weighted above it, because a
  balloon over a shoulder hides a shoulder and a balloon over a plewd deletes what the panel was
  saying. The speaker gets no discount: their balloon over their own sweat still hides it.

The third is what shipped. Its proof is in `tests/test_emanata.py`: every example in the repository,
recompiled with every mark on every cast member, puts every figure exactly where it was and still
compiles; and a panel without marks is byte-identical to one compiled before marks existed.

The cost of not moving anybody is that the camera makes no room either, so marks over the tallest
head can be cropped at a tight shot. That is reported as a note rather than silently drawn off the
page.

### Sound effects are picture: placed first, exempt from reading order, paid for by balloons

A sound effect is lettering treated as art, so three decisions follow from treating it as art.

- **Reading order.** Balloons and captions share one hard sequence. Dark Horse's format wants sound
  effects listed in it too, but a sound sits where the sound is, and holding it to above-and-left
  would make many panels impossible to letter. Of the three options weighed — in the sequence under
  the rule, in it but exempt from the geometry, or outside it — the second shipped: an effect takes
  its `order`, which a reader of the text and accessible output follow, and is placed with no
  geometric constraint against any box.
- **When it is placed.** Before every balloon and caption, as the art is: lettering is placed over
  the picture, knowing where it is. An effect is placed after staging and the camera, from the
  figures they produced, and reaches neither, so nobody moves for one — the same proof as emanata.
- **What it costs.** Its footprint joins the emanata as ground a balloon or caption pays to cover,
  at the same weight, and is never forbidden to. A balloon over a sound effect deletes what the panel
  was saying, which is the argument emanata already made; forbidding it would turn a crowded panel
  into a placement error over a sound. It is drawn under the lettering for the same reason: when a
  balloon does cover one, the words stay readable.

Its own hard rules are a box's — never a face, never out of the frame, never under an inset — plus
never over another effect. It is set in a display face, bent and turned as transforms of the glyph
outlines Scenet already draws, so an arc comes out the same in every renderer; SVG's `<textPath>`
would have handed the layout back to the renderer and to installed fonts.

## Characters and art

What Scenet needs to know about a picture someone else drew.

### Figures a picture draws come with a contract, beside the picture

When the people are in a supplied picture, the solver still needs each face, mouth and body,
and still may not look at the picture. An [artwork contract](../reference/asset_contract.md#artwork-contracts)
declares them, as a puppet's contract declares its skeleton. What the contract leaves open was decided this way:

- **The contract is found beside its picture, by name.** `art/p01.png` has `art/p01.art.yaml`. The
  issue sketched `setting.image` naming the contract, and the contract naming its picture; that
  overloads `image`, joins two paths into Core's `href`, and breaks when a picture is renamed. A
  `contract:` key beside `image` lets the two name different pictures. By name, the pairing cannot
  drift, and the playground's renaming of uploads treats both alike. It is read only for a panel
  whose cast names a figure, so a file beside a picture never changes output by being there.
- **The size is the picture's, exactly.** A contract measured on another export would put every face
  elsewhere, and scaling it to fit would need a tolerance that hides a re-export. It is refused, and
  says to measure again or to scale the coordinates.
- **Every declared face is in the panel, cast or not**, because a painted face is a face. A cast
  figure the panel's picture does not draw is simply not in that panel, so a script's front matter
  can cast a chapter's figures over many pictures; a line it speaks there is the finding, and is
  where a misspelt name surfaces.
- **The camera and staging do not run, and are refused when written.** The artist framed and staged
  the picture; a `camera:` or a relation naming a figure would be a key with no effect, which this
  language reports, as it reports a horizon beside a picture. Gaze is not declared — a detector
  could not propose it reliably, and nothing else needs it — so the gaze term costs a figure
  nothing; an optional key could add it later without a format change.
- **Casts are not mixed.** A puppet staged in front of painted people would be placed by a solver
  that cannot see them, and could stand on a face. That is the hard half of a mixed cast, so it is
  refused rather than half-supported.
- **A cropped mouth is not a finding.** Under `cover` a mouth can fall outside the panel; whether it
  does depends on a frame size a page imposes, which the cheap pass does not know. Lettering stays
  inside the panel as it always does, the tail ends on the frame aimed at the mouth, and the build
  notes it.
- **Core gets a figure of its own**, `figures` beside `actors`, not optional `CoreActor` fields that
  would let a puppet Core with no transform validate. Empty, it is left out, so `format_version`
  stays 1.
- **A fault in a contract is reported in it** when the document is checked as a file — the editor
  and SARIF already file a result by its uri — and at the line naming the picture when it is checked
  as text, where the author can only see the document.
- **Detection is a helper, and not built.** A contract is a handful of numbers, and the debug overlay
  checks them against the picture. A detector inside the compiler would make output depend on a
  model and a platform, and could not run in the playground; see
  [prior art](prior_art.md#magi-a-helper-that-could-propose-a-contract).

## Reading

The order a panel is read in, by eye and by screen reader.

### A panel is one image, read whole, in reading order

Accessible output makes each panel `role="img"`, named by one `<title>`: the description,
then every balloon, caption and sound effect's label, in `order`. The sources behind it are in
{ref}`prior art <accessible-svg>`, and the screen-reader results in
[the how-to](../howto/make_accessible_output.md#recorded-results).

- **One image, not a document of named parts.** The issue held up Vega-Lite's per-mark labels as
  the precedent, and Vega's own output is a `graphics-document` with `graphics-symbol` marks. That
  was examined and not taken. No published test says what NVDA, JAWS or VoiceOver do with
  those roles, the ACT rule calls their support inconsistent, and Firefox reduces the document
  to a plain one. With a group of named parts, document order would be reading order — and a
  sound effect is painted under every balloon, so it cannot be in its place in that order
  without changing the picture. As one image, the panel is read in the one order Core keeps,
  whatever the paint order. Its children are presentational, so nothing inside it is named.
- **The words are in the name, and in nothing else.** A description is often not spoken —
  Lembree's NVDA and JAWS results, NVDA's own guide — so `aria-describedby` alone would leave the
  dialogue unread. The first version named the panel through `aria-labelledby` by a `<title>`
  and a `<desc>`, the most-tested pattern in the published results. NVDA 2026.2 with Edge 155 read
  it in full, once, in browse mode — and a second time, the `<desc>` as the description, every
  time it moved to the panel by graphic. Of six ways of naming it tried in the same session, one
  `<title>` holding everything read once both ways, and needs no id, so a page that inlines
  several panels cannot name one with another's words. The cost is a long tooltip.
- **Strips and pages are groups of panels.** `role="group"` is what every engine computes; the
  panels are its images, in reading order — which is why a page now writes its panels in reading
  order and cuts each inset's parent around it rather than painting the inset last.
- **The words are resolved in the pipeline**, in `solve/describe.py`, and carried in Panel Core;
  the emitter copies them. Generated text is templated English, and says so.
- **`aria=False` is exactly the SVG written before.** A golden variant holds every gallery
  document built `--no-aria`, and its digests are those the default build had before.

### Right to left mirrors the reading, never the picture

`direction: rtl` is decided by one test: compile the mirror image of a panel right to left,
and every balloon and caption lands at the mirror of where left to right puts it in the original.
Everything reading decides is mirrored to pass it, and nothing the picture decides is touched.

- **The document's, not a panel's.** EPUB and ComicInfo say it once per book, and a page read one
  way holding a panel read the other has no order a reader could follow. So a panel's own
  `direction` is `panel-direction`, and a scene's or script's panels inherit the document's.
- **The order.** Never above-and-right of a predecessor, the exact mirror of the left-to-right
  test, still checked against every predecessor.
- **Tiebreaks are mirrored, not just the rule.** The first candidate wins an exact tie. The ring
  around a head used to try up-right first and the corners top-left first, so with the rule alone
  flipped, a right-to-left panel would have been a mirrored-but-different layout. Each candidate
  list is now built so that, read right to left, candidate *i* is the mirror of candidate *i* read
  left to right. The tests check the order, never a tie, since a near-tie can fall differently on
  another platform.
- **A written zone is a place; an unwritten one is where reading starts.** `prefer:` names a
  region of the panel and means it either way. A caption with none sat top left because that is
  where a locale caption conventionally sits, which is where reading starts. So `CaptionEvent.prefer`
  is `None` until the solver reads the direction. An off-panel voice with no side named starts
  there too, and a balloon dead centre goes to that side.
- **Sound effects stay put.** They are picture, placed first and exempt from the order. They keep
  their number in the one sequence, and their own tiebreaks, because the scene is not mirrored.
- **Tails and staging stay put.** A tail bends toward the side of its own line first, which has
  nothing to do with the page. Staging breaks a tie by anchor and id, never by "given to new" (see
  [prior art](prior_art.md)).
- **Text is not progression.** Lettering stays Latin, left to right, and captions stay flush left.
- **No disjunction comes back.** Reading order is a filter over candidates, not a Cassowary
  constraint, and the direction is known when the document is read.

## Lettering

Words measured in the face they are drawn in.

### Text metrics are a hard dependency, not a detail

A balloon's size is a function of its text, wrapped at some measure, in a specific font. Nothing
downstream — placement, occlusion, reading order — can be computed until that size is known. The
font is therefore bundled rather than referenced, and measurement uses `fontTools` against that
exact file. If renderer and measurer disagree even slightly, output stops being deterministic.

### A font is a file beside the document, and Core names it by its bytes

An author's lettering face is declared as a path, read relative to the folder the document is in,
and an absolute path is refused. Three things follow from that one rule. A document and its fonts
move together and compile the same anywhere. A server that compiles documents it is sent cannot be
pointed at files of its own. And no path reaches any output: Panel Core records a face by its
family, style and the SHA-256 of its bytes, which is the same on every machine — `tests/test_golden.py`
already holds the output to not depending on where a document is.

The digest is also what keeps measurement and drawing together once they are separate steps. A
renderer is handed fonts by digest and refuses a Core that names one it was not given, rather than
drawing lettering in a face it was not measured in. Fonts are cached by digest too, so a file
replaced in place is read again.

The path rule lives in `scenet/paths.py`, written to be shared, and a picture to letter over is
read by it too: the same paths and the same refusals, and in Panel Core the same identity, a digest
of its bytes. A caller with no folder — text compiled with nothing behind it — may hand over the
files themselves instead, by the path the document writes; they are read from memory, never
written to a folder of the server's.

### The default face stays Source Sans Pro

Comic Neue (Craig Rozynski, SIL OFL 1.1) was the candidate to replace it, as a face with a lettering
feel that can be shipped. It was not adopted here. The choice is to be made on legibility at balloon
sizes rather than taste, which is a comparison of pictures, and the change that makes it cheap to
run is this one: declare the face beside a document and compile the gallery in both. Switching the
default would also move every example's output a second time and needs the face packaged, since no
PyPI package carries it. Until a comparison says otherwise, an author who wants it names it.

### Kerning is applied, because the outlines are positioned here

Pair kerning was ignored at first, on a sound argument: SVG renderers do not agree on whether to
kern `<text>`, and a measurement the renderer will not reproduce is worse than a slightly generous
one. That argument is about `--live-text`. The default emits glyph outlines, and Scenet positions
every one of them itself, so no renderer has a say: a pair adjustment that is measured is drawn,
exactly. So kerning is applied, to measurement and outlines through one function, and live text in
the SVG is the best-effort mode it always was. In the print PDF it is exact, because there Scenet
embeds the face and places every glyph itself.

The pairs are read with `fontTools` from the GPOS `kern` feature, or from a legacy `kern` table in a
font with no GPOS kerning. HarfBuzz would shape the text for us, but Pyodide does not ship it and the
playground installs the same wheel as the CLI, so it is a dev dependency instead — the **oracle**.
`tests/test_kerning.py` checks every ordered pair of the characters the tests letter, in all three
faces, against HarfBuzz's advances. A hand-picked pair would not have caught the rules that matter:
the first subtable that covers a pair answers for it, and a class pair applies even when its value is
zero.

Only pair adjustments are applied: no ligatures, no contextual alternates, no mark positioning. That
is all a Latin line of lettering needs, and all that measurement can promise to reproduce. Two faces
are two fonts, so a stressed word in bold italic is not kerned against its roman neighbours.

Adopting it moved every example once: box widths changed by between −1.4% and +0.4%, since a pair can
loosen as well as tighten, one two-line balloon
fit on one line, and a few balloons whose candidate positions had scored nearly equal chose
differently.

### Small and weak lettering are one size

Dark Horse names `(small)` and `(weak)` beside `(burst)`. Blambot defines small dialogue by its
effect — "a reduced font size is used when a character mutters something" — and the balloon stays
the size it would have been, so the line reads as said quietly rather than as a small balloon.
`say.size: small` is exactly that: type at three quarters of the panel's dialogue size, padded as
normal type would be. Blambot's script guide reads `(WEAK)` as "dialogue should be diminished", so
a weak line is small too. Comicraft also letters weak dialogue in an erratic hand; that is not
drawn, since no source fixes what the hand should be, and drawing an invented one would be worse
than drawing none.

## Colour and print

The value ladder, its colour twin, and the PDF a printer takes.

### Colour is a twin of value, never a replacement

The compiler drew only greys until 0.13, and the colour policy it settled then keeps every reason the
greys were chosen for. A notan reading of masses, an aerial-perspective ladder monotonic in depth,
contrast floors a test can check, lettering on a printer's black plate: none of them may depend on
which palette a panel is drawn in.

- **A colour has its grey's lightness.** Each value of the tinted ladder is the twin of a rung: the
  same OKLab lightness, to within 0.005, at the same hour. In monochrome a tinted panel is the mono
  one, so `mono` is not a separate rendering to keep in step but the same panel with its colours
  taken out.
- **Every decision is made on the grey.** The solver settles every value first and only then looks
  up its twin (`colour_for`, `caption_colour`). The runtime's `lightness` and `contrast_ratio` are
  exact only for a neutral, and refuse a colour, so a decision cannot be made on one by accident.
  A property test compiles every place, weather and hour both ways and finds the tinted Core with
  its colours taken out byte-identical to the mono Core.
- **The colour sits beside the value, in Core.** `tone` and `fill` keep their keys and their
  meaning, and the colour is a new key left out when unused. Replacing `tone` with the colour and
  adding a `value` key would have changed a published key's meaning and moved every golden. A
  panel-level map from grey to colour was rejected too: the day sky and a `warm` caption share a
  grey and not a colour.
- **The table is generated and hardcoded.** Two hues and two chromas per hour, in
  `scripts/make_palette.py`, give twenty colours, capped at the sRGB gamut and rounded to the
  nearest `#rrggbb` that keeps the lightness. They were signed off by eye on the setting sheet. No
  colour library is a dependency, for the reason the ladder has none.
- **`mono` is the default.** No panel written before palettes draws differently, and the first
  tuning of the hues can be revised without moving anybody's output who did not opt in. Turning
  colour on by default later is a decision for a minor release; turning it back off would not be.
- **Monochrome at two levels.** `palette: mono` is the author's, and lets one panel be the flashback
  on a page in colour. `--mono` is the output's: a black-and-white edition without editing a
  document. A test holds the two byte-identical on every gallery example.
- **Lettering is never coloured.** Balloon text and borders, caption text and sound effects stay
  neutral in every palette, so a print emitter can keep them on the black plate.
- **Only the ladder and `warm`, for now.** Colour for puppets needs material slots in the asset
  contract and a vocabulary for skin that deserves its own discussion. Colour for sound effects
  raises which plate they print on. Local colour by kind of mass would give each of twelve kinds a
  hue, where a kind decides a mass's shape and never its value. Each is its own issue.

### Print is an emitter from Core, not a converter

A printer takes a PDF; the SVG was already there. Converting one into the other was ruled out:
an SVG has lost what each path *is* -- a converter cannot tell a balloon's lettering from a
figure's outline, so it cannot put one on the black plate and leave the other alone -- and SVG has
no overprint to convert. So the PDF is a third emitter beside the SVG, drawing from the same Panel
Core.

- **The same drawing, from one computation.** `scenet.emit.geometry` works out what Core names
  but does not spell out -- a burst's spikes, a tail's corners, where each letter lands -- and
  `scenet.emit.marks` lists what a panel paints, in order (no relation to the
  `marks` key, the emanata). Both emitters draw from them, and a
  test holds the marks to the SVG for every gallery panel.
- **No dependency.** ReportLab, the one PDF library that passed the licence gate, was compared on
  a real page and set aside: both were deterministic and both could overprint, but the direct
  writer needs nothing, so the PDF exists wherever the compiler runs -- the browser playground
  included -- and every byte is the project's own.
- **No dates in the file.** PDF writers stamp a creation date and derive the document's `/ID`
  from it. Reading `SOURCE_DATE_EPOCH`, as reproducible builds do, would make the bytes depend on
  the environment they were built in; so the PDF carries no date, and its `/ID` is a digest of
  its content.
- **Nothing compressed.** zlib-ng and zlib write different bytes for the same data, and a
  platform picks one. Content streams are written plain, and a picture's own compressed data is
  carried as it is, never re-deflated.

### Lettering prints on the black plate

Comics have a convention a generic converter cannot know: **small type is 100% K and
overprints**, so it stays sharp when the colour plates drift out of register, and never cuts a
white hole in the art under it. Every paint is set by what it is, never by converting its hex --
ink is `#111111`, which a conversion would make 93% K.

- **Ink overprints; the paper knocks out.** A shape that is both filled and outlined -- a
  balloon -- knocks out its white fill and overprints its border, so the outline also hides the
  tail's stroke where they meet.
- **Greys are black tints, and the night is rich black.** A grey prints on black alone, at the K
  that prints its lightness under the same condition the colours print under (below); a
  mass dark enough to be the night foreground prints C40 K100, for even coverage within any
  printer's ink limit.
- **A tinted palette prints its CMYK twins**, below; `--mono` prints the greys.

### A colour prints as its twin under one printing condition

Every colour the compiler owns -- the tinted ladder's twenty and the `warm` caption's -- has a
CMYK twin, in a table print reads (`scenet.emit.cmyk`), generated by `scripts/make_palette.py`.

- **In the print emitter, keyed by the colour.** CMYK belongs to a printing condition, not to a
  scene: Core stays the same for every emitter, and no golden moved for it. Keyed by the sRGB
  colour, never by grey, since the day sky and a `warm` caption share a grey and not a colour.
  A colour no table holds -- a hand-edited Core -- prints its grey, and a note says so.
- **One registered condition, CGATS21-2-CRPC6** (GRACoL 2013, coated #1 sheetfed): the registry's
  reference for US coated print, the gallery's print page being a US comic, with a profile whose
  licence lets it be shared unaltered (`scripts/profiles/`). A printer on another condition
  re-separates, as it would any artwork.
- **Relative colorimetric, with black point compensation**, through littleCMS, which is how layout
  programs convert artwork. Compared on a proof sheet, soft-proofed back through the same profile,
  every twin came back within a few levels of its colour; perceptual greyed the pale rungs. A test
  reads each twin back through the profile and finds its colour's lightness, once black point
  compensation has put the screen's black on the press's: the twin rule, on paper.
- **littleCMS at generation, never at run time.** Pillow's `ImageCms` is a dev dependency, pinned
  exactly so its bundled engine cannot move a value on a half percent; print reads a table and
  converts nothing. (Pillow was refused for a JPEG encoder Scenet could write itself; a colour engine
  with black point compensation is not that.)
- **Every tinted paint prints its twin, a night mass included**: one rule, so the tinted night
  foreground prints the condition's own black, not C40 K100. Lettering and lines stay on the black
  plate over it.
- **Not proofed on paper.** No printer was within reach; the how-to says so.
- **Greys follow the same condition.** A grey printed as K = 1 - L, its OKLab lightness, with no
  press curve. Measured through the condition's profile, that printed far lighter than the screen
  -- `#707070`, L* 47, at K 45% prints L* 67.5 -- so a tinted panel and its mono twin would have
  differed in value on paper, the twin rule broken where it matters most. So `make_palette.py`
  also measures black's ramp, what each whole percent of K alone prints, and a grey prints at the
  K, read between them, whose lightness is its own after the same black point compensation the
  twins get (`#707070` at K 69%); one darker than black alone can print takes it all. Still one
  plate: the black-plate rule is about lettering and lines, and a grey stays on black too.

### The veil prints as the same noise

The fog and cloud veil is `feTurbulence` in the SVG, and PDF has no such filter. Leaving it
out changed a panel's values most -- the near ground of a foggy dawn went much darker -- and a
flat tint at the veil's mean opacity kept the values but lost the fog. So print computes the
noise itself and carries it as a raster, a luminosity soft mask over the veil's ink, compared on
proofs against the SVG as Edge draws it.

- **SVG 1.1's algorithm, which browsers run.** SVG 1.1 gives C code as "the exact algorithm used
  for this filter effect"; the Filter Effects draft has since changed how it draws its gradients,
  and browsers have not followed. Print follows the screen.
- **A zero gradient stays zero.** For 243 of the 65,536 seeds Scenet writes, the reference code
  draws a (0, 0) gradient and divides by its length. Chromium keeps it (0, 0), and so does print.
- **127 dpi.** One sample every two units: about fifteen across the finest octave of fog, and no
  different printed from 254 dpi at a quarter of the bytes and time.
- **Deterministic arithmetic.** float64 addition, subtraction, multiplication and `floor`, octaves
  summed in order, nothing a platform or a vector unit could reorder; the same veil is the same
  bytes, in the playground too. The test oracle is the C code transliterated line by line.
- **It knocks out.** A black tint that overprinted could only darken; the SVG's veil fades what is
  under it towards its tone, lightening a dark scene and greying a picture.

### Live text in print is exact, and asked for

`--live-text` letters the print PDF in text as it letters the SVG: one flag, one meaning,
lettering as text rather than outlines in every output that letters. Outlines stay the default, so
no PDF changes unless asked, and a document never depends on its fonts' licences unless it asks
for live text.

- **Exact, unlike the SVG's.** The SVG names a family and trusts the reader to have it. The PDF
  embeds the face, as a subset of the glyphs drawn and those they are built from, and places
  every glyph itself: each run starts at its first glyph's origin, and each adjustment is the
  glyph's width as the font's `W` array writes it, less the step the solver measured. A reader's
  arithmetic then lands every glyph on its outline's origin, which a test checks for every
  gallery panel.
- **The font says whether it may go in.** Its `OS/2` `fsType` is read as the OpenType
  specification says, least restrictive bit first. A face that may not go in keeps its lettering
  in outlines, and print says so, rather than the PDF silently carrying a font it has no right
  to.
- **One kind of font.** Each glyph is kept at its own id, so the code a PDF draws it by is that
  id: Type0, Identity-H, for TrueType and CFF alike. Nothing a reader would lay text out with
  goes in -- no `GSUB`, no `GPOS`, no hinting -- since every position is the PDF's.
- **Deterministic as the rest.** Fixed subsetting options, the face's date never rewritten, a
  subset tag taken from what it holds, nothing compressed. The playground's own fontTools may
  subset to other bytes; that is said, not promised away.

### Print claims no PDF/X, and says what its colours are

A printer may ask for PDF/X-4. Scenet's print PDF does not claim it, because nothing
free can check the claim: veraPDF validates PDF/A and PDF/UA, PDFBox PDF/A-1b, and the free
X-1a checkers do not read X-4. A claim no preflight has checked is worse than none, since a
RIP or a printer trusts it. Writing one would also take what the determinism contract rules
out or the package should not carry: creation and modification dates, which would have to be
given as input, and the condition's 3.5 MB profile embedded in every PDF.

What the file does carry is true of it whatever a preflight would say:

- **An output intent naming the printing condition**, `CGATS21-2-CRPC6`, by the ICC registry's
  identifier, without its profile: valid PDF for a registered condition, and a statement of what
  the CMYK twins were made for. Preflight tools read PDF/X from `GTS_PDFXVersion`, never from the
  intent, so it claims nothing.
- **RGB pictures in `ICCBased` sRGB**, the ICC's own profile, shipped in the package and written
  once per file. Untagged, a picture was already read as sRGB by every viewer; tagged, a RIP no
  longer guesses. A grey picture stays `DeviceGray` and a CMYK JPEG `DeviceCMYK`, so black stays K
  alone. A picture's own embedded profile is not carried: it would need reassembling and
  validating, and could be one PDF cannot hold.
- **Every page blends in CMYK.** Without a page group, a RIP picks the blending space, and one
  that blends in RGB turns rain over a K-only grey into four-colour black. With it, Ghostscript's
  plates are the same as before, which a test checks.
- **`/Trapped /False`**: Scenet traps nothing.

A test checks every gallery PDF against the PDF/X-4 requirements the writer can meet -- boxes,
embedded fonts, no forbidden filter, version -- and that what a claim would need stays absent. A
printer finishes the file with Acrobat Pro's "Convert to PDF/X-4", callas pdfToolbox or Enfocus
PitStop, given GRACoL 2013's profile.

### A panel bleeds to the bleed line, framed to the trim

A placement's `bleed` runs its frame past the trim, out to the bleed line, with no border there.
It is `true`, for every side that reaches the page's margin, or a list of the page's own
sides, never mirrored right to left: a side that does not reach the margin is an error, not a
guess.

- **Three boxes, so the trim cuts nothing that matters.** The frame to the bleed line is the
  panel's size and what its art covers. Shot types are normative, and a full shot's feet are 4% of
  the frame from its bottom: composed to the bleed line, they would be cut off. So the cast is
  staged and the camera framed in the frame out to the trim, then moved into place. Lettering
  keeps inside the frame as it was, inside the panel margin, so the page margin stays the safe
  area for words, as a printer's live area is.
- **Nothing else moves.** A panel that does not bleed compiles byte for byte as before; Core
  gains `open`, `lettering` and a frame's `bleed`, each left out where nothing bleeds.
- **Drawn as cut.** The SVG page stays at its trim, clipped there, and only the debug view shows
  the sheet. A page with no bleed of its own still lets panels bleed to the trim, with a print
  note, rather than refusing a layout that is right for screen.
- **Not in comic scripts**, which have no per-placement keys; a scene's `pages:` writes it.

## Exports for image models

What a panel hands to a model, and what it does not.

### Staging leaves as text, never as a picture or a prompt

`--conditioning` hands a panel's staging to image models as five files. Each is decided by
what the consumer already reads, and by one rule: an export reads Panel Core and nothing else, so
it can make no layout decision and no model ever runs inside Scenet.

- **Core grew what the exports needed**, rather than the exports reaching past it: every joint
  and face feature point, the camera's verdict, whom each actor looks at, and a backdrop's place
  and hour. Each is left out of the JSON when unused, so an older Core still writes back byte for
  byte.
- **Left and right are the subject's.** Scenet names a joint by its side of the screen in the
  rest pose; OpenPose by the subject's side. Every Scenet body faces the reader, so the subject's
  right is the reader's left: `_l` facing right, `_r` facing left. A test pins both.
- **A point outside what the panel draws is missing.** Outside the frame or a slanted outline,
  an ear, a joint the puppet does not name: `0, 0, 0`, as OpenPose writes a part it did not
  detect. A joint behind a foreground mass, another actor or an inset is kept: the body is still
  there, and a pose model is better told where.
- **Regions are the geometric contract, not the mannequin.** Boxes, depth and masks use an
  actor's hull, a mass's polygon and a figure's body and face: where a character is, never
  Scenet's stand-in drawing of it, which a model would copy. Marks and sound effects are drawn
  around a figure and are in none of them.
- **Depth is a painter's order, said as one.** Even grey steps by rank, white nearest, black for
  the paper, the sky and a supplied picture: there is no metric depth to give, and the backdrop's
  own ladder runs the other way.
- **A surface that lies flat recedes.** A ground, floor or water is a straight ramp from its
  own step at the horizon to the farthest figure's step at the bottom edge, and a ceiling the same
  ramp upward. Through a pinhole camera, a flat surface's inverse depth is linear in screen height,
  so the straight ramp is perspective's own shape. This bends "ranks, not distances" a little: the
  ramp claims that the surface recedes to its horizon, which its kind already says, and still no
  distance between two regions. Its ends keep the ladder: never darker than its own step, never
  paler than a figure standing on it.
- **A character keeps its mask colour across panels**, from a digest of its id, unless another
  character in the same panel has the same hue, in which case the later id (in sorted order)
  takes the next free one. Masses take a less saturated band, so a wall is never a character.
  The semantics repeats each actor's and figure's colour, taken from the mask's own code, so a
  tool maps colour to character without the SVG, and the two cannot disagree. Every map
  is on the pose's canvas, one unit to a pixel, with crisp edges, so no pixel holds a colour or
  grey that belongs to no region.
- **Figures a picture draws** get boxes, mask regions and one depth plane in front of their
  picture, but no pose and no camera: nobody posed or framed them.
- **The semantics is structure, not a prompt.** Prompt dialects change with every model, and
  prose is the language step prior art leaves to whatever is in the loop. Where Core already has
  words — the description and labels accessible output reads — they are copied, never rephrased.
- **Per panel, not per page.** A panel's Core is compiled at its frame's exact size, so its units
  are the page's shifted by the frame, which Page Core records; DiffSensei, the one consumer that
  takes a layout, generates panel by panel. A page-level depth map would have to decide what a
  gutter is in depth — a composition decision the page emitter owns.
- **A flag and a parameter, not a command or a tool.** `build` already grows sibling outputs with
  `--core` and `--debug`; MCP `render` takes `conditioning` and stays one of five tools. The file
  is `.semantics.json`, not `.scene.json` as first sketched: "scene" already names the
  multi-panel document.
- **Nothing is rasterised.** A renderer in the runtime dependencies is what MCP `render` already
  declines for PNG; the playground's own rasteriser, and every SVG tool, turn the maps into
  pictures.

## Toolchain and documentation

How the project is checked, and how its site is built.

### `ty` gates the build; `basedpyright` advises

[`ty`](https://docs.astral.sh/ty/) is Astral's type checker: fast, and consistent with `uv` and
`ruff`. It is also **pre-1.0 and in beta**.

Gating CI on a beta usually risks an upstream change reddening the build unbidden — but `uv.lock`
pins `ty` to an exact version, so it changes only when deliberately bumped. That objection does not
apply here.

The risk pinning does *not* solve is coverage: pre-1.0 `ty` is documented to miss advanced typing
patterns Pyright catches — Protocols, `ParamSpec`, recursive types, complex overloads. Since the IR
is pydantic models throughout and the solver will lean on Protocols, that is the wrong blind spot to
accept silently. So `basedpyright --strict` runs as a **second, non-blocking** job. Anything it
reports that `ty` missed is signal. Delete that job once `ty` reaches 1.0 and closes the gap.

### `TC001`-`TC003` are disabled deliberately

Ruff's flake8-type-checking rules want annotation-only imports moved into `if TYPE_CHECKING` blocks.
Declined, for two reasons:

1. **Pydantic resolves annotations at runtime** to build validators. An import hidden behind
   `TYPE_CHECKING` makes the model fail to build — and the IR is pydantic models throughout, so the
   rule is an active hazard rather than a style preference.
2. The import-time saving it exists for is largely gone in Python 3.14, which already evaluates
   annotations lazily (PEP 649/749).

That same PEP pair is why `from __future__ import annotations` is banned here: forward references
work unquoted, and the future import is on a deprecation path.

### License gate checks runtime dependencies only

Dev tooling is never distributed, so it is out of scope — which matters concretely, because
`hypothesis` is MPL-2.0 and would otherwise fail a permissive-only allowlist for no good reason. CI
therefore syncs with `--no-dev` first.

One trap worth recording: a bare `uv run` **re-syncs the project**, silently reinstalling the dev
dependencies `--no-dev` just pruned, so the gate checks the wrong environment and passes
meaninglessly. `uv run --no-sync` is required. This was caught by running the gate and reading its
output, not by reasoning about it — which is the general lesson.

### The documentation site serves every release from the site attached to it

The site's root used to be `main`, rebuilt on every push. So between releases it described
language a released `scenet` refused, the playground ran an unreleased compiler, and an
editor validating against `schemas/panel.schema.json` was checked against unreleased models.
Now the root is the latest release, `main` is under `/dev/`, and each minor version is under
`/vX.Y/`. The layout is the one
pandas uses: stable at the root, development under it, old versions beside it.

**Where old versions come from.** A Pages deployment replaces the whole site and keeps
nothing, so every deploy must contain every version. Each release builds its site once, from
the wheel it publishes and before it publishes anything, and attaches it to the GitHub Release
as `scenet-X.Y.Z-site.zip`. `pages.yml` downloads those. The alternatives each failed on
something concrete:

- *Rebuilding every tag at deploy time.* The playground's build downloads the newest font
  wheels from PyPI, so a rebuild is not what shipped. Old lockfiles also rot.
- *A `gh-pages` branch.* At about 40 MB per version, it puts into history what every clone
  fetches. It also needs a workflow write token, and changes the Pages source setting.
- *A separate repository* needs a credential reaching across repositories.
- *Workflow artifacts* expire.
- *Read the Docs* moves the documentation to another domain, breaking every stable URL.
  It also injects its own script into a site whose playground's Content-Security-Policy says
  `'self'` and means it.

**What moves the root.** `pages.yml` runs on `workflow_run` when the Release workflow
completes, and only for runs a push started.

- `release: published` never fires, because the release is created with `GITHUB_TOKEN`,
  and events that token causes start no workflow.
- A deploy from the tag's ref is refused, because the `github-pages` environment allows
  only `main`.
- `workflow_run` runs on the default branch and needs no new permission.
- It is limited to push-started runs because a pull request can add a workflow with the
  same name, and its runs would set it off too.
- It is not limited to successful runs. A registry listing that fails after the release
  is out must not keep the root on the previous release.

Every deploy is a function of `main` and the releases' attachments. So a push rebuilds
`/dev/`, and everything else comes out byte-identical to the previous deploy.

**One build, at two paths.** A release's site is served at the root and at its `/vX.Y/`
unchanged, so nothing in it may depend on where it is:

- The playground's Vite base is relative.
- The documentation's links are relative already.
- The version switcher reads `/scenet/switcher.json`. The theme advises a fully resolved
  URL so that no build reads a stale copy of its own. A site-absolute path cannot do that
  either, and with it the local preview, served under `/scenet/` as Pages serves it, shows
  the real switcher before anything is deployed.
- The theme's build-time check of that file is off: it would fetch it over the network, and
  fail the build with `-W` whenever it is not there yet.

What a build does carry, `scripts/site_versions.py` checks on every page. That is which
version it documents, where the switcher is, and its canonical link.

**`main` says it is `dev`.** The theme hides its warning banner when a build's
`version_match` equals the preferred entry's `version`. Otherwise it calls the version an
unstable development one when the release string contains "dev", or an old one when it
compares lower. Between releases `main` carries the last release's version number, so it
would compare equal and get no banner. `SCENET_DOCS_VERSION=dev` labels it.

**Canonical links, not `noindex`.** Every page of every copy names its counterpart at the
root as canonical, as docs.python.org does from its 3.12 and development pages to `/3/`.
`/dev/` is not marked `noindex`: Google advises against using it to steer canonical
selection within a site. A project site cannot have a `robots.txt` either, since one is only
read at the host's root, `creatoan.github.io/robots.txt`. A page that has no counterpart at
the root — one removed since — points at a missing page, which a search engine ignores.

**By minor version.** Below 1.0 a minor version is where this project's language may change
(see [Releasing](../maintainer/releasing.md#versioning)), and a patch release is a fix to it.
So `/v0.11/` serves the highest 0.11 patch, and fixing a release's documentation means
cutting a patch release. numpy and pandas version their documentation by minor too.

**Old playgrounds retire.**

- A version's site is about 40 MB, of which the playground is 28 MB and Pyodide 22 MB.
- Pages caps a site at 1 GB, and its artifact may contain no links, so versions cannot
  share a copy.
- The root, `/dev/` and the three newest minor versions keep their playground.
- An older version keeps its documentation, schemas and spec pack. Its `playground/`
  becomes a page pointing at the latest playground, and at the complete site attached to
  its release.
- The assembly fails above 1 GB, before Pages would.

**Releases before 0.8 are not on the site.** Releases up to 0.11.0 predate the attachment,
and `scripts/backfill_site.py` builds one for them: the release's own sources and lockfiles,
the wheel it published, and only the files that version a build laid over them. That needs
the release's site tooling to be v0.11.0's, which holds from v0.8.0. Before that, the
documentation configuration itself differs. Those versions' documentation stays readable at
their tags on GitHub.

**Every version's playground shares one origin.** So a draft saved in one version's
playground opens in another's, where a construct from `/dev/` may not compile. A shared link
carries its document in the URL and is not affected.

**A playground learns its version from its address.** The page is the same in every version
and its build is not told which it is, but `switcher.json` names each version's address, and a
version's playground is `playground/` under it. Matching the address against the file needs no
label baked into the build, and shows nothing — rather than something wrong — wherever the page
is served without the file, as under `npm run dev`.

**Links to the playground are written absolute and built relative.** The Markdown links it by
its full address, the only kind that works where GitHub renders these pages. A transform in
`docs/conf.py` makes each such link relative in the built site, so every version's
documentation opens its own version's playground.

Sources:

- pydata-sphinx-theme, [version switcher](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/version-dropdown.html)
  and [warning banner](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/announcements.html)
- GitHub,
  [triggering a workflow from a workflow](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow),
  [`workflow_run`](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_run)
  and [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [upload-pages-artifact](https://github.com/actions/upload-pages-artifact) on links
- Vite, [relative base](https://vite.dev/guide/build.html#relative-base)
- Google, [consolidating duplicate URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [RFC 9309 §2.3](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3) on where
  `robots.txt` is read
- numpy's and pandas' switcher data:
  [numpy](https://numpy.org/doc/_static/versions.json),
  [pandas](https://pandas.pydata.org/versions.json)

### The documentation's pictures are golden outputs, committed

Every picture of a gallery example in the documentation is the file `scenet build` writes for
it, copied from the golden build by `scripts/update_golden.py` into `docs/images/gallery/` and
held to its digest by a test. It was
that or rendering them while Sphinx builds, which would commit nothing. Copying won:

- **GitHub renders these pages.** The documentation is Markdown so that a reader who lands in
  the repository reads it without a build step, and a picture that exists only on the site is
  a broken image there.
- **The README needs a committed picture anyway**: GitHub and PyPI render it, not Sphinx.
- **It is the mechanism the goldens already have.** `update_golden.py --check` and
  `tests/test_golden.py` name a stale picture with the other goldens, and the docs build stays
  a Markdown render that compiles nothing.
- **A pull request that changes a drawing shows it**, as GitHub's image diff of the SVG.

The price is the repository's size: 3.9 MB of SVG, 0.8 MB compressed, rewritten whenever
the drawing of an example changes, as its Core golden is. One set of pictures per example
keeps it down, and every page that shows an example shows that set, the README included.

An example lettered over a picture of its own is shown as `--embed-images` builds it. An SVG
shown as an image, as every page shows these, loads nothing from outside itself, so a picture
the SVG only links would be missing from it.
