# Compose a page

A comic is designed a page at a time: how many tiers, which panel gets the width, where
the page turns. A scene can say that. Its panels stay exactly as you write them, and
`pages:` lays them out.

## Tiers, by weight

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
  closer: {...}
  her: {...}
  him: {...}
```

A page is a list of tiers, top to bottom; a tier is a list of panels, left to right. Write a
panel by its name, or as `{use: name, width: 2}` to give it a bigger share. A tier's
`height` is its share of the page the same way. The margin and the gutters come off first,
and what is left is shared out by weight, the way CSS Grid shares a row between `fr` tracks.

The order you write panels in is the order they are read in: tier by tier, left to right.
That is the reading path readers follow on a grid, so a page built from tiers cannot be read
in the wrong order.

## A tall panel beside a stack

```yaml
pages:
  - tiers:
      - panels: [arrival]
      - height: 2
        columns:
          - {width: 2, panels: [look_up, {use: horror, height: 2}]}
          - {width: 1, panels: [the_fall]}
```

A tier can hold `columns:` in place of `panels:`. The tier is split across into columns by
their `width`, and each column down into its panels by their `height`, with the tier gutter
between them. A column of one panel spans the tier's whole height.

Columns are read one after another, top to bottom in each: `look_up`, `horror`, `the_fall`.
That is what readers do when a tall panel stands beside a stack. It blocks the way across, and
about nine readers in ten go down the stack first. Two stacks side by side have nothing
blocking the way, so readers go across them, and `scenet check` refuses them; write them as
tiers instead.

`examples/gallery/25-columns.scene.yaml` is a page built this way.

`examples/gallery/24-page.scene.yaml` is a whole page, and the playground offers it as
"A page: panels in tiers".

## What the page decides, and what it does not

```python
from scenet import compile_book

book = compile_book("""
cast: {alice: {reference: alice}}
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}
pages:
  - tiers:
      - panels: [wide, {use: tall, width: 2}]
      - {height: 3, panels: [last]}
panels:
  wide: {script: [{say: {by: alice, text: "Hello."}}]}
  tall: {over: wide}
  last: {over: wide, camera: {shot: close_up}}
""")

# Each panel is compiled at the size of its frame...
(page,) = book.pages
assert [(frame.panel, frame.width, frame.height) for frame in page.frames] == [
    ("wide", 350.0, 410.0),
    ("tall", 700.0, 410.0),
    ("last", 1080.0, 1230.0),
]
assert (book.panels["tall"].core.width, book.panels["tall"].core.height) == (700.0, 410.0)

# ...and every panel on the page letters at one size, whatever its height.
wide = book.panels["wide"].core.balloons[0].font_size
last = book.panels["last"].core.balloons[0].font_size
assert wide == last
```

The page decides two things about a panel: the size of its frame, and its type size. Nothing
else. A panel on a page is exactly that panel compiled on its own at that size, so it never
changes because of what sits beside it.

Type size is the one deliberate exception to "a panel letters at a fixed fraction of its own
height". On a page, every panel takes its type size from the same height, as if each were one
tier of a three-tier page. A short wide panel and a tall one then letter alike, as a letterer
would set them.

## Building it

```bash
scenet build story.scene.yaml --core
```

writes each panel, as before, and each page beside them:

```
story.wide.svg  story.tall.svg  story.last.svg
story.page-1.svg               the page, every panel at its frame
story.page-1.core.json         where each frame is (with --core)
```

A panel named `page-1` would be written to the same file as the first page. Rather than one
replacing the other, `scenet build` stops and asks you to rename the panel.

## Mistakes it catches

`scenet check` reports these as `page-layout`, on the line at fault:

- a tier that places a panel `panels:` does not define;
- a panel placed twice, on one page or two;
- a tier with both `panels:` and `columns:`, or with neither;
- two stacks side by side, which readers would read across rather than down;
- a margin and gutters that leave no room for the panels;
- `pages:` in a document that has no `panels:` to lay out.

A panel that is on no page is not a mistake: it compiles as it always did, and may exist only
to be inherited from with `over:`.

## Not yet

Insets and slanted frames; right-to-left reading for manga; a comic
script's `PAGE` headings laying out pages; and print sizes with trim and bleed. See
[the plan](../explanation/status.md).
