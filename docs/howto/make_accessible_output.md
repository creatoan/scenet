# Make a panel a screen reader can read

Every SVG Scenet writes can be read by somebody who cannot see it. Nothing needs turning on: each
panel is an image named with what it shows and then everything said in it, in reading order.
This page says what is in the file, how to give a panel your own words, how to embed the result
so they reach the reader, and how to check it with a screen reader.

## What is in the file

A panel is one image, `role="img"`, named through `aria-labelledby` by its `<title>` and its
`<desc>`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="scenet-5afdd6267a90-title scenet-5afdd6267a90-desc">
  <title id="scenet-5afdd6267a90-title">Long shot. A street at night, in the rain. Alice, left, pointing, looking at Bob; Bob, right, arms crossed.</title>
  <desc id="scenet-5afdd6267a90-desc">Caption: Midnight. The corner of Fifth. Alice: You forgot your umbrella!</desc>
  <!-- the panel, drawn as ever -->
</svg>
```

- **The `<title>` is the panel's description**: yours, when you write one, or a comic script's
  prose; otherwise generated from the shot, the place, the hour and the weather, and each figure
  left to right with its pose, expression and marks and whom it looks at.
- **The `<desc>` is everything said, in reading order**: every balloon, caption and sound effect,
  each saying who and how — `Bob, whispering: I know.` — in the one order
  [Panel Core](../reference/panel_core.md#the-words) keeps. A sound effect is in its place in that
  order, though it is painted under every balloon.
- **Both are in the name.** A screen reader always reads an image's name, and often does not read
  its description, so the words are not left to the description alone.
- **Nothing inside the panel is named.** An image's children are presentational: a name on a
  balloon in there would never be read. The panel is read whole, as one graphic.
- **Lettering stays outlines.** The words are in the file as what the panel is named by, not as
  `<text>`; with `--live-text`, the text is inside the image and so not read twice.
- **The ids are a hash of the text they name**, so several Scenet SVGs inlined in one web page —
  where `getElementById` finds the first match — still each name themselves.

A [strip](compile_a_sequence.md#rendering-the-whole-thing) or a [page](compose_a_page.md) is a named
group, `role="group"`, holding one such image per panel in reading order — insets included, read
first when they say `read: before` — and its own shapes, the sheet and the rings round insets, are
hidden. Debug overlays carry none of this: they are diagnostics, and their labels are live text.

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
named = root.get("aria-labelledby").split()
found = {element.get("id"): element.text for element in root.iter() if element.get("id")}
assert " ".join(found[name] for name in named).endswith(
    "Alice: You forgot your umbrella! Bob, whispering: I know."
)
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

writes the same file without any of it — no `role`, `<title>`, `<desc>` or `aria-` attribute —
for a pipeline that post-processes the SVG. It is otherwise byte-identical. From Python it is
`render(core, aria=False)`, and the same on `render_strip`, `render_page` and `render_pages`; the
MCP server's `render` tool takes `aria: false`.

## Check it with a screen reader

What the browser hands a screen reader can be read without one — and has been, see below — but
what a screen reader then says cannot be golden-tested. To check by hand:

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
| — | NVDA, VoiceOver | Not yet checked by hand: whether either reads the description after the name, which would repeat the scene |
