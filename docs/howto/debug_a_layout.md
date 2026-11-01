# Work out why a panel looks wrong

A panel that compiles but looks wrong is the common case, and the SVG is the worst place
to investigate it. Three tools, roughly in the order you should reach for them.

## 1. Read the notes

The compiler tells you when it did something you did not ask for:

```python
from scenet import compile_source

result = compile_source("""
panel: {size: [600, 400]}
camera: {shot: close_up}
cast:
  alice: {reference: alice}
  bob:   {reference: bob}
staging: [alice left_of bob]
""")

for note in result.notes:
    assert isinstance(note, str)

assert any("camera retreated" in note for note in result.notes)

# The same notes, each with the name of what kind it is.
(note,) = result.compile_notes
assert note.rule == "camera-retreated"
assert note.message == result.notes[0]
```

Each note is a sentence, and each has a name that says what kind it is:
{attr}`result.compile_notes <scenet.pipeline.CompileResult.compile_notes>` gives both. The
name stays when the sentence is reworded, so it is the thing to match on, and it is how a
gallery example that shows a note declares it.

| Name | What happened | What to do |
|---|---|---|
| `camera-retreated` | The cast would not fit across the panel at the shot you asked for, so the camera stepped back, by the share the note gives | Widen the panel, ask for a looser shot, or accept it |
| `curved-tail` | A straight tail would have gone through somebody's head, so it bends around it | Usually a sign the panel is crowded: let the balloon sit nearer its speaker, or give the panel more room |
| `cropped-mouth` | A picture's `fit: cover` crops a speaking figure's mouth out of the panel, so the tail stops on the frame, aimed at it | `fit: contain` shows the whole picture; or reshape the panel |
| `cropped-marks` | Emanata run off the panel: the camera frames by the body and makes no room for them | A looser shot, or the marks on somebody they fit around |
| `inset-covers-face` | An inset is drawn over a face, and the art does not move for it | Put the inset in another corner, or reframe the panel |
| `slant-cuts-face` | A slanted gutter cuts across a face: the panel is cropped to its outline, as by a margin | Lean the tier less, or frame the shot so the face is clear of it |
| `italic-stand-in` | `lettering.font` names no italic face, so italic captions are set in the regular one | Name one as `italic:` |
| `bold-italic-stand-in` | `lettering.font` names no bold italic face, so stressed words are set in the italic one, or the regular | Name one as `bold_italic:` |

On the command line these print as `note:` lines. `--quiet` suppresses them, which you
should not normally want. The playground lists them under the picture, after what
`scenet check` notes, and its gallery shows each in an example of its own, under *What
Scenet tells you*.

## 2. Look at the debug overlay

```bash
scenet build duel.panel.yaml --debug
```

That writes `duel.debug.svg`, drawing what the solver was actually working against:

| Overlay | What it shows |
|---|---|
| Silhouette hulls | The convex outline used for the balloon occlusion cost |
| Face exclusion discs | The regions no balloon may overlap, at all |
| Named anchors | `mouth`, `eyes`, and anything else the puppet declares |
| Gaze vectors | Where each character is looking, and how far that reaches |
| Tail routes | Including the control point, when a tail had to bend |
| Figures a picture draws | Each figure's face disc, mouth and body, from its [artwork contract](../reference/asset_contract.md#artwork-contracts), labelled with the part it plays or `(not cast)` |
| Keep-out regions | Dashed: what the picture's contract asks lettering to stay off, at a cost |

Most "why is the balloon *there*?" questions answer themselves the moment you see the face
discs and the gaze vectors drawn.

The overlay never draws a supplied picture, only the rectangle it was placed in. To check an
artwork contract against its picture, lay the overlay over the panel's SVG: every face disc
should ring a face, and every mouth sit on one. `examples/gallery/35-figures.scene.yaml` is
lettered that way, over a contract written from the same numbers its picture was painted
from.

From Python it is {func}`render_debug <scenet.emit.debug_svg.render_debug>`:

```python
from scenet import compile_source, render_debug

result = compile_source("cast: {a: {reference: alice}}")
overlay = render_debug(result.core)
assert overlay.lstrip().startswith("<?xml")
```

## 3. Read the Panel Core

```bash
scenet build duel.panel.yaml --core
```

`duel.core.json` is every decision the compiler made, in a format you can read and diff.
When a layout changes unexpectedly between two versions of your source, diffing two Core
documents tells you exactly what moved. Diffing two SVGs does not — a reordered attribute
or a different path-rounding produces an enormous diff that means nothing.

```python
from scenet import compile_source

result = compile_source("""
cast:
  alice: {reference: alice, at: left_third}
script:
  - say: {by: alice, text: "Why am I here?"}
""")

alice = result.core.actor("alice")
balloon = result.core.balloons[0]

# Where the figure landed, and at what scale.
assert alice.transform.scale > 0

# Where the balloon landed, and where its tail attaches.
assert balloon.box.width > 0
assert balloon.tail.start != balloon.tail.end

# Whether the tail had to bend.
assert balloon.tail.is_curved in (True, False)
```

## Common causes

**"The balloon is nowhere near the speaker."** Check the face discs in the overlay. Every
position near the mouth was probably illegal — covering a face is a hard rule, not a cost
— so the search fell back to a panel corner, which is an ordinary comics solution and
looks deliberate on the page.

**"My `at:` anchor was ignored."** Anchors are *weak*. Non-overlap and declared ordering
are required and will override them without comment. Two actors both asking for `center`
get pushed apart around it.

**"My `prefer:` zone was ignored."** `prefer` is the weakest term in the whole system. It
loses to occlusion, to gaze blocking, and to reading order.

**"The figures are smaller than I asked for."** The camera retreated. Check `result.notes`
— it says so explicitly.

**"A figure is half off the edge."** Panel bounds are *strong*, not required. Letting a
figure bleed past the edge is ordinary comics practice and much better than refusing to
compile a crowded panel. Widen the panel or loosen the shot.

**"Reading order looks wrong."** It cannot be, in the sense the compiler means: a balloon
is never allowed above *and* left of one that precedes it — above and *right*, in a panel
written `direction: rtl`, whose overlay says "read right to left". If it reads wrong anyway, the
script order is probably not what you intended — script order *is* reading order.

## When it will not compile at all

Two error types, and which one you get tells you where to look:

```python
from scenet import SolverError, SourceError, compile_source

# SourceError: the document is wrong. Fix the panel source.
try:
    compile_source("staging: [alice left_of bob]")
except SourceError as exc:
    assert "unknown actor" in str(exc)
```

`SolverError` is the other branch — the document is valid but no layout satisfies it. In
practice that means either a genuinely contradictory ordering, or far too much dialogue
for the panel size. Widen the panel, shorten the line, or split it across two panels.
