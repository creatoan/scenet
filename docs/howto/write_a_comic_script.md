# Write a panel as a comic script

Comic writers already have a format. It is not YAML, it has been in use for decades, and
asking someone to abandon it in order to try a compiler is a poor trade.

So Scenet reads it.

```
PAGE ONE

PANEL 1
@shot: full_shot
CAPTION: Midnight. The docks.
Alice and Bob face each other on a rainy street corner. She is exasperated.

ALICE
You forgot your umbrella!

BOB
I know.

PANEL 2
@shot: medium_close_up
Closer now. Bob will not meet her eye.

BOB (whisper)
I left it on purpose.

ALICE (shouting)
You what?!
```

Save that as `umbrella.script` and compile it exactly like any other document:

```bash
scenet build umbrella.script --strip
```

## The rules

| Line | Means |
|---|---|
| `PANEL 1` | Starts a new panel. `PANEL 1:`, `PANEL 1.` and `Panel One` are the same panel. |
| `Panel 1. Alice and Bob on a corner.` | Dark Horse's form: the panel, and its description on the same line. |
| `@shot: full_shot` | A directive. `@shot` and `@angle` set the camera; anything else sets a top-level panel key. Each is written once per panel: a second is reported, not quietly kept. |
| `ALICE` (all caps, alone) | The lines after it, up to a blank line, are one speech by `ALICE`. |
| `BOB (whisper)` | Same, with a balloon kind. `(burst)` is a shout. Several parentheticals, or one with commas, are read together. |
| `ALICE: Hello.` | A cue with its line on the same line. Dialogue when `ALICE` is in the panel's cast; see below. |
| `ALICE (V.O.)` | A voice over: the line is a spoken caption by `ALICE`, not a balloon. |
| `ALICE (OP)` | Dark Horse's off-panel speech: Alice is left out of this panel, and her balloon's tail ends on the frame. `(OFF)`, `(O.S.)` and `(O.C.)` too. |
| `CAPTION: Midnight.`, `CAP: Midnight.` | A caption box, its text on the same line. |
| `CAP:` or `CAPTION` (alone) | Dark Horse's form: the caption's text is on the lines under it, to a blank line. |
| `CAPTION (monologue): ...` | Same, with a caption kind. `(voice over)` is the spoken kind. |
| `CAP/ALICE` | Dark Horse's caption carrying a character's speech: a spoken caption by `ALICE`. |
| `1. ALICE:`, `2) CAP:` | Blambot's numbered lettering items: the number is set aside. |
| `SFX: BLAM` | A sound effect. The sound is on the same line. |
| `SFX (BOB, large): KRAK` | Same, coming from `BOB`, at a size. |
| `SFX:` (alone) | Dark Horse's form: the sound is on the next line. |
| Anything else | Prose. Preserved, never interpreted. |
| `PAGE ONE` | Starts a page. Pages are not laid out yet, but they keep panels apart: see below. |
| `PAGE ONE (five panels)` | Dark Horse's form: the page, and how many panels it has. A count its panels do not match is a `panel-count` note. |
| `## PANEL 2`, `**PANEL 2**`, `---` | Markdown: the markers are stripped and the heading read; a horizontal rule is a blank line. |
| Before the first heading | The title page: the writer's name and address, the title. Kept, never interpreted. |

The one detail that trips people up: **a speaker cue is recognised by the name being all
caps, not the whole line.** `BOB (whisper)` qualifies, because only `BOB` is tested. Capitals
with accents are capitals: `HÉLÈNE` and `ZOË` are cues. The script is read composed (Unicode
NFC), so a name your editor stored as a letter and a separate accent is the same name the
front matter spells, and a byte-order mark at the start of the file is ignored.

**A speech runs until a blank line.** Wrap a long line of dialogue wherever you like; the lines
are joined with a space into one balloon. A line that looks like another cue ends the speech
and starts the next, so two speeches need no blank line between them.

**Underline a word by writing it between underscores**: `I _told_ you.` Scripts underline the
words to stress, and a letterer sets them in bold italic, which is what the compiler does — in
dialogue and in captions alike. The rules are in
[the language reference](../reference/language.md#emphasis).

**Panel numbers may start again on each page**, as publishers' script formats ask. When they
do, every panel is named by its page as well: `PANEL 1` under `PAGE TWO` is panel `2-1`, and
`scenet build` writes it to `name.2-1.svg`. A page spelled out in English is named by its
number (`PAGE TWO` is page `2`, `PAGE TWENTY-ONE` page `21`); anything else is kept as written
(`PAGE 3A`). A script that numbers its panels straight through keeps the plain names. Two
panels that would still share a name, such as `PANEL 1` twice on one page, are reported as
`duplicate-panel` rather than one quietly replacing the other.

**A sound effect is an `SFX` line**, written where it happens in the script, as publishers ask
for everything to be listed in reading order. The parenthetical says who or what it comes from — a
name from the cast — and how loud, `small`, `medium` or `large`, in either order. Dark Horse writes
`SFX:` as a cue with the sound under it; that works too, and the line under it is the sound however
it looks — `BLAM` is in capitals, which would otherwise make it a character's cue. An `SFX:` cue with
nothing under it is reported rather than dropped. Turns, arcs and hollow letters are written in YAML;
see [`sfx`](../reference/language.md#sfx).

`CAP`, `CAPTION` and `SFX` are checked before speaker cues, because as far as the cue pattern
is concerned each is a perfectly good character name. So they are reserved: none can be a cast
member's id. A caption or a sound effect with its text to follow also wins over a cue waiting for
its line — `BOB (whisper)` then `CAPTION: Later.` is a caption, and a note says Bob had nothing
to say.

**A cue may carry its line after a colon**, `ALICE: Hello.`, as Dark Horse's guide itself does. A
writer's note to the artist looks exactly the same — `NOTE: redraw the rain` — so the line is
dialogue only when the name is in the panel's cast: the front matter's, and any `@cast:` in the
panel, wherever in it. A name in capitals that is not in the cast is read as it would otherwise
be — prose, or a wrapped line of the speech above — and a `looks-like-dialogue` note says so, since
a misspelled speaker looks the same. A name in lower case, `Junior: Die, you dirty rat!`, is
dialogue only when it is exactly a cast member's id, and otherwise silent prose.

**A caption can carry speech.** Dark Horse's `CAP/ALICE`, with the words in quotation marks,
is a `spoken` caption by `ALICE`. The compiler letters a spoken caption's quotation marks itself
— one opening each box, one closing the speaker's last — so the writer's are taken off rather
than doubled, and so is one enclosing pair around a balloon's text. A voice over, `ALICE (V.O.)`,
is the same thing written as a cue: [Blambot](https://blambot.com/pages/comic-script-basics)
defines `CAPTION (VOICE OVER)` as a character "speaking, but … not in the location shown".

## A script as publishers ask for it

[Dark Horse's script format](https://images.darkhorse.com/darkhorse08/company/submissions/DHScriptFormatGuides.pdf)
is the reference house format, and Scenet reads its layout as written:

```
Margo Wren
14 Harbour Lane, Port Ellis

PAGE ONE (two panels)

Panel 1. A lighthouse on a cliff at dusk. Maya climbs the last of the steps.

MAYA:
Theo? The lamp is out --

Panel 2. Inside. Theo kneels by the dead lamp.

THEO (whisper):
-- because somebody forgot the oil.
```

- **The title page** is everything before the first heading. It is kept and never read,
  as prose is. A name in capitals with a line under it looks like a cue, so it is pointed
  out as a `looks-like-dialogue` note; a name from the cast there is an error, since it is
  far more likely a missing PANEL heading. A directive, a caption or a sound effect before
  the first heading belongs to no panel, and is an error.
- **A line between a PAGE heading and its first PANEL** belongs to the page, never to the
  last panel of the page before, which is where it used to end up.
- **`PAGE ONE (five panels)`** states the count. When the panels under it number something
  else, a heading has usually been missed, so it is a `panel-count` note. Any other
  parenthetical, `(splash)` say, is a note to the artist, and is not read as a count.
- **`Panel 1.` with its description on the same line** is a heading when the label looks
  like a number — digits, digits and a letter, one letter, or a number in words — so
  that `Panel shows Alice.` stays the sentence it is.
- **`--`**, Dark Horse's mark for a speech carried to the next balloon, is kept as written.
- **A cue with nothing said under it** is a `looks-like-dialogue` note rather than vanishing.

Writers keep scripts in Markdown, so `#` to `######` before a heading, `**` or `__` around
it, and a horizontal rule are tolerated: the markers are stripped and the convention read.
It is not a second format: the text of a line is never rewritten.

## Off-panel speech

Dark Horse writes `CHARACTER (OP):` for a character "speaking from off-panel"; Blambot writes
`(OFF)`, and screenplays `(O.S.)` or the older `(O.C.)`. All four mean the same here: the line is
spoken by somebody who is not drawn, and the balloon's tail ends on the frame, on their side —
see [off-panel speech](../reference/language.md#off-panel-speech).

Off panel means in the scene but out of the frame, and the front matter is the scene's cast. So
`ALICE (OP)` leaves Alice out of **that panel**: out of its cast, and out of every staging relation
that names her — `BOB looking_at ALICE` does not apply there, and a `dropped-relation` note says
so. Her tail ends on the side she was written to stand on, `at: left_third` being the left, unless
the cue names one: `ALICE (OP, right)`. Somebody never cast — `PHONE (OP)` — is heard just the
same, from the side nearer the balloon.

A panel whose own `@cast:` draws her, or in which she speaks both on and off panel, is
`off-panel-speaker`. A panel `@over:` hers does not inherit her absence: it is worked out from each
panel's own lines.

## One panel over another

Consecutive panels share nearly everything — the place, the weather, who stands where — and
restating it is where continuity errors get in. `@over:` writes a panel as a change to another,
exactly as [`over:`](compile_a_sequence.md) does in a YAML scene:

```
PANEL 1
@shot: full_shot
@setting: {place: docks, weather: rain}

PANEL 2
@over: 1
@shot: close_up
```

Panel 2 inherits panel 1's directives and replaces its shot. It never inherits dialogue: each
panel's lines are its own. A label is looked up on the same page first, so `@over: 1` on page two
is panel `2-1`, and then as a panel's whole name, `1-3`. It may name a panel further down. A panel
that does not exist, a cycle, or a panel over itself is one `composition` finding, at the `@over:`
line.

## Prose is never interpreted

"Alice and Bob face each other on a rainy street corner" is not parsed, not
natural-language-processed, and does not affect the output in any way. It is kept because
a script is a document people read, and stripping the description would make the file
worse for its primary audience.

If you want the rain, say so with a directive: `@setting: {weather: rain}` draws it. The
description beside it is never read.

## Front matter

A script is dialogue and camera direction. It has no way to say who `ALICE` *is*, which
puppet she uses, or where she stands. That comes from a YAML preamble between `---`
fences:

```
---
panel:
  size: [900, 700]
cast:
  ALICE: {reference: alice, pose: pointing,     at: left_third}
  BOB:   {reference: bob,   pose: arms_crossed, at: right_third, facing: left}
staging:
  - ALICE left_of BOB
  - ALICE looking_at BOB
  - ALICE ground_shared_with BOB
---

PAGE ONE

PANEL 1
...
```

Everything in the front matter is a default every panel inherits — exactly the same
mechanism as [shared defaults in a sequence](compile_a_sequence.md#shared-defaults).

Note the actor ids are written in caps here, to match the speaker cues. That is a
convention, not a requirement; the ids simply have to agree.

## From Python

```python
from scenet import parse_script

panels = parse_script("""---
cast:
  ALICE: {reference: alice}
---

PANEL 1
@shot: close_up
A quiet room.

ALICE
Is anyone there?

PANEL 2
ALICE (whisper)
Anyone?
""")

# Panels are named by the number in their heading.
assert list(panels) == ["1", "2"]
assert panels["1"].camera.shot.value == "close_up"
assert panels["1"].script[0].text == "Is anyone there?"

# The prose line is preserved in the source and interpreted nowhere.
assert panels["2"].script[0].kind.value == "whisper"
```

Panel names come straight from the heading, so `PANEL 1` becomes `"1"`. The CLI uses
them as filename suffixes: `umbrella.script` compiles to `umbrella.1.svg`,
`umbrella.2.svg`.

{func}`parse_script <scenet.frontends.script_front.parse_script>` gives you IR;
{func}`load_script <scenet.frontends.script_front.load_script>` reads a file; and
{func}`compile_document <scenet.pipeline.compile_document>` dispatches on the `.script`
extension so you do not have to care.

## The front matter is not optional in practice

A script with no cast will not parse at all. Validation is total, so a speaker cue naming
somebody who is not in the cast is an error at parse time rather than a blank balloon
discovered later:

```python
from scenet import ScriptSyntaxError, parse_script

try:
    parse_script("PANEL 1" + chr(10) + "ALICE" + chr(10) + "Hello.")
except ScriptSyntaxError as exc:
    assert "unknown actor" in str(exc)
    assert "ALICE" in str(exc)
```

That is the first error you will hit when adapting an existing script: every speaker cue
needs a matching entry in the front-matter cast.

## Both frontends produce the same IR

This is the point of the whole arrangement. `script_front` computes no coordinates and
knows nothing about geometry; it produces the same
{class}`PanelIR <scenet.ir.PanelIR>` the YAML frontend does, and everything downstream is
unaware that a second syntax exists.

Adding a third syntax means adding a parser and one line in the extension table. Nothing
else changes.
