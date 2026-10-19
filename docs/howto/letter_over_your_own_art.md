# Letter over your own art

Scenet draws its own backdrops, as tonal masses. When you already have a picture — a painted
background, pencils from an artist, a render from another tool — name it as the setting, and
Scenet draws the cast in front of it and letters the panel by its usual rules: balloons in
reading order, never over a face, tails to the mouth.

## Keep the picture beside the document

```text
comic/
├── chapter-one.scene.yaml
└── art/
    └── p01-street.png
```

A PNG or a JPEG. The path is read relative to the folder the document is in, as a
[font's](letter_in_your_own_font.md) is: `art/p01-street.png` is found wherever you run `scenet`
from. An absolute path is refused, and so is a backslash.

## Name it

```yaml
setting:
  image: art/p01-street.png
  fit: cover        # or contain
  weather: rain     # optional: drawn over the picture
```

`cover` fills the panel and crops what overhangs, equally on both sides; `contain` shows the whole
picture, and the panel shows round it. Either way the picture is centred and never stretched.
`image` stands instead of a `place` or `masses`, never beside them; a panel that inherits a place
from a scene's defaults leaves it out with `place: null` beside its image.

The compiler reads the picture's size and nothing else. It does not know there is a doorway in
it, so it will happily put a balloon there — the panel's own figures are what balloons avoid.
When the people are in the picture, see
[Letter the people in your own art](letter_the_figures_in_your_art.md): a contract beside the
picture says where each face and mouth is, and keep-out regions mark what lettering should stay
off.

## Build it

Linked, the SVG names the picture by the path you wrote, so it finds it when the SVG is beside
the document — where `scenet build` writes by default:

```bash
scenet check examples/gallery/34-supplied-art.scene.yaml
scenet build examples/gallery/34-supplied-art.scene.yaml
```

Written anywhere else, or put on the web as an `<img>`, or turned into a PNG, a linked picture is
not found — an SVG shown as an image loads no file it links to. `--embed-images` writes the
picture's bytes into the SVG instead, so the file stands alone:

```bash
scenet build examples/gallery/34-supplied-art.scene.yaml -o out/ --embed-images
```

`scenet check` reports a picture that is missing, absolute, not a PNG or JPEG, or turned by its
EXIF orientation as `image-file`, on the line that names it. That last one is refused because
viewers disagree on obeying the tag: save the picture with its pixels turned instead.

## In the playground

**Image…**, above the editor, adds `.png` and `.jpg` files to the document's `art/` folder; name
them as above, `setting: {image: art/Name.png}`. They last as long as the tab: a reload, or a share
link, does not keep them. The preview and every download embed the picture, so a downloaded SVG
or PNG stands alone.

## Say what it shows

A screen reader reads each panel as one image, named by its description and then its lettering
(see [Make a panel a screen reader can read](make_accessible_output.md)). Scenet cannot see your
picture, so a generated description says nothing about it — not the place, not the hour, only the
weather it drew on top. Write the description yourself:

```yaml
description: A brick street at dusk, every window lit. Alice points up at them; Bob shrugs.
```

## From Python

Give text the folder its files are in — or, with no folder at all, the files themselves by the
path the document writes — and hand the pictures the compile returns to the renderer to embed:

```python
from scenet import compile_source, render
from scenet.images import measure

# A real, if tiny, PNG: three pixels by two, all grey.
png = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000003000000020800000000b81f39c6"
    "0000001049444154789c636868686068686800000c0803011cb51d7b"
    "0000000049454e44ae426082"
)
result = compile_source(
    "cast: {alice: {reference: alice}}\nsetting: {image: art/a.png}\n",
    base={"art/a.png": png},
)
assert measure(png) == ("image/png", 3, 2)
assert "data:image/png;base64," in render(result.core, embed=result.images)
assert 'xlink:href="art/a.png"' in render(result.core)
```
