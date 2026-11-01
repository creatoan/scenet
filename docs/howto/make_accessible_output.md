# Make a panel a screen reader can read

Every SVG Scenet writes can be read by somebody who cannot see it. Nothing needs turning on: each
panel is an image named with what it shows and then everything said in it, in reading order.
This page says what is in the file, how to give a panel your own words, how to embed the result
so they reach the reader, and how to check it with a screen reader.

## What is in the file

A panel is one image, `role="img"`, named by one `<title>`, its first child:

```xml
<svg xmlns="http://www.w3.org/2000/svg" role="img">
  <title>Long shot. A street at night, in the rain. Alice, left, pointing, looking at Bob; Bob, right, arms crossed. Caption: Midnight. The corner of Fifth. Alice: You forgot your umbrella!</title>
  <!-- the panel, drawn as ever -->
</svg>
```

- **It starts with the panel's description**: yours, when you write one, or a comic script's
  prose; otherwise generated from the shot, the place, the hour and the weather, and each figure
  in reading order — left to right, or from the right in a comic read right to left — with its
  pose, expression and marks and whom it looks at.
- **Then everything said, in reading order**: every balloon, caption and sound effect, each
  saying who and how — `Bob, whispering: I know.` — in the one order
  [Panel Core](../reference/panel_core.md#the-words) keeps. A sound effect is in its place in that
  order, though it is painted under every balloon.
- **All of it is the name, and nothing else.** A screen reader always reads an image's name, and
  often does not read its description, so the words are not left to a description. Nor is
  anything given as one as well: named through `aria-labelledby` by a `<title>` and a `<desc>`,
  the panel was read by NVDA a second time, the `<desc>` as its description, every time a reader
  moved to it graphic by graphic — see the results below.
- **It needs no id**, so several Scenet SVGs inlined in one web page — where `getElementById`
  finds the first match — cannot name one panel with another's words.
- **Nothing inside the panel is named.** An image's children are presentational: a name on a
  balloon in there would never be read. The panel is read whole, as one graphic.
- **Lettering stays outlines.** The words are in the file as what the panel is named by, not as
  `<text>`; with `--live-text`, the text is inside the image and so not read twice.
- **The title is also a tooltip.** A browser shows an SVG's `<title>` when the pointer rests on
  it, so a sighted reader hovering a panel sees its words.

A [strip](compile_a_sequence.md#rendering-the-whole-thing) or a [page](compose_a_page.md) is a named
group, `role="group"`, holding one such image per panel in reading order — insets included, read
first when they say `read: before` — and its own shapes, the sheet and the rings round insets, are
hidden. A page or strip read right to left is drawn from the right and still written in reading
order, so a screen reader takes it in the order a reader of the page does. The screen-reader
results below were recorded on pages read left to right; nothing a screen reader is given depends
on which way the page is drawn. Debug overlays carry none of this: they are diagnostics, and their labels are live text.

```python
from xml.etree import ElementTree

from scenet import compile_source, render

core = compile_source("""
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third, facing: left}
script:
  - say: {by: alice, text: You forgot your umbrella!}
  - say: {by: bob, text: I know., kind: whisper}
""").core

root = ElementTree.fromstring(render(core))
assert root.get("role") == "img"
title = root.find("{http://www.w3.org/2000/svg}title")
assert title is not None
assert title.text.endswith("Alice: You forgot your umbrella! Bob, whispering: I know.")
```

## Write the description yourself

A generated description says what is there; only you can say what is happening. Write it on the
panel:

```yaml
description: Alice tells Bob off on a rainy street corner. He will not meet her eye.
```

In a comic script the panel's prose already is its description. Everything the prose says is
read, a note to the artist included, so when the reader should hear something else write an
`@description:` directive — see
[Prose is never interpreted](write_a_comic_script.md#prose-is-never-interpreted). A description is
never inherited: it describes one panel, and a panel drawn `over:` another is a different picture.

Over a [picture of your own](letter_over_your_own_art.md) this matters most. The picture is part of
the panel's one image and adds nothing to what is read, and a generated description cannot say what
it shows — not the place, not the hour — only the weather Scenet drew on top of it.

Generated text is **templated English**. A French script's prose is read in French, but the words
round its dialogue — `Alice, whispering:` — are English, and the file does not say which language
is which. Write descriptions yourself where that matters.

## Embed it so the words reach the reader

**Inline the SVG** in your page, or open it as a document: that is where its role, title and desc
are read. Several inlined panels are fine; their ids do not collide.

**An `<img src="panel.svg">` exposes only its `alt`** — the SVG's own markup is not read. Give the
`<img>` an `alt` holding the panel's name: its description, a space, and its labels in order,
which are in Panel Core (`scenet build --core`) as `description` and each item's `label`.

EPUB 3 fixed layout and Readium's guided navigation package pages rather than panels, and are not
written yet; what they embed is exactly this SVG.

## Leave it out

```bash
scenet build examples/duel.panel.yaml --no-aria
```

writes the same file without any of it — no `role`, `<title>` or `aria-` attribute —
for a pipeline that post-processes the SVG. It is otherwise byte-identical. From Python it is
`render(core, aria=False)`, and the same on `render_strip`, `render_page` and `render_pages`; the
MCP server's `render` tool takes `aria: false`.

## See what it says

The [playground](https://creatoan.github.io/scenet/playground/)'s **Screen reader** tab shows what
a screen reader is given: each image and group the output names, nested as they are, with the
words of its `<title>`. It walks the SVG the Panel tab shows, skipping what is `aria-hidden` and
never looking inside an image, as a screen reader does. It is what was emitted, not a recording
of a screen reader reading it; that is the check below.

## Check it with a screen reader

What a screen reader says cannot be golden-tested, so it is checked by hand — or by a script,
as below: NVDA run as a portable copy with a silent synthesizer, its speech logged at the
"input/output" level, while key presses are sent to the browser. To check:

1. Build a panel and a page, and open an HTML page that inlines both.
2. **NVDA** with Firefox or Chrome, browse mode: arrow onto the panel. Expect "graphic", then the
   description and every line in order, read once — not the words a second time as a
   description.
3. Press `G` to move graphic by graphic through the page: one stop per panel, in reading order,
   an inset read first where it says `read: before`.
4. **VoiceOver** with Safari on macOS, `VO`-right through the page; on iOS, swipe through it and
   touch a panel.
5. Note anything read twice, cut short or out of order, with the screen reader's, the browser's
   and the operating system's versions.

### Recorded results

| Date | Checked with | Result |
|---|---|---|
| 2026-10-18 | Edge 155.0.4283.45's UI Automation tree — the API Narrator reads, and one of NVDA's — on Windows 11, for two panels and the `26-insets` page inlined in one HTML page | Each panel is one **Image**, its **Name** the description then every line in order, sound effects in their place. The page is a **Group** named `A page of 5 panels.`, its panels in reading order, the clock (`read: before`) first. Nothing inside a panel is exposed. The `<title>` is also the image's tooltip (`HelpText`); its full description could not be read with the managed UIA client |
| 2026-10-18 | NVDA 2026.2 (portable, speech logged) with Edge 155.0.4283.45, Windows 11; the same page; down arrow in browse mode, then `G` | **As emitted now, one `<title>`:** each panel is announced as a graphic with the description and then every line in order, once, both ways; the page as `A page of 5 panels.`, a group, its panels in reading order, the clock first; nothing inside a panel is read |
| 2026-10-18 | The same, for the first version: `aria-labelledby` by a `<title>` and a `<desc>` | Browse mode read it once. **Moving by graphic, NVDA read the `<desc>` a second time as the description**, so every line was heard twice. Of six ways of naming the same panel, three read once: one `<title>` holding everything (now emitted, and needing no id), `aria-description=""`, and `aria-describedby` pointing at an empty element. An empty `aria-describedby` did not help, and a `<title>` beside a `<metadata>` was read again as the description |
| — | VoiceOver, JAWS, NVDA with Firefox | Not yet checked |
