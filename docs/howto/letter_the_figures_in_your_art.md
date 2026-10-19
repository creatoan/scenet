# Letter the people in your own art

[Letter over your own art](letter_over_your_own_art.md) puts a picture behind Scenet's own cast.
When the people are already in the picture — pencils from an artist, a painted scene, a still from
a film — cast *them* instead, and Scenet letters around them by its usual rules: balloons in
reading order, never over a face, tails to the mouth. It never looks at the picture to do it. You
tell it, once, where each face and mouth is, in a file beside the picture.

## Keep the picture and its contract together

```text
comic/
├── chapter-one.scene.yaml
└── art/
    ├── p01-street.png
    └── p01-street.art.yaml
```

The contract is named after its picture, its extension replaced: `p01-street.png` has
`p01-street.art.yaml`. Nothing in the panel names it, so the two cannot be paired wrongly, and
they move together.

## Measure the picture

Open the picture in any image editor that shows pixel coordinates, `x` rightward and `y` downward
from the top left, and write down what it draws:

```yaml
# art/p01-street.art.yaml
size: [3000, 2000]                     # the picture's size, exactly
figures:
  ana:
    face: {center: [1240, 610], radius: 150}
    mouth: [1270, 700]
    body: [[1050, 520], [1450, 520], [1500, 2000], [1000, 2000]]
  ben:
    face: {center: [2210, 580], radius: 140}
    mouth: [2180, 670]
keep_out:
  - [[400, 1200], [900, 1200], [900, 1700], [400, 1700]]   # the shop sign
```

- **`face`** is a disc no balloon, caption or sound effect may cover. Make it generous: the whole
  head and a little air. A tail stops on its edge.
- **`mouth`** is where a tail aims — or wherever the sound comes from: a radio, a hand over a
  mouth. Without one, a tail aims at the face's centre.
- **`body`** is optional: the silhouette a balloon pays to cover. A balloon may rest on its own
  speaker's shoulder for half the price.
- **`keep_out`** is optional: what the panel is about, which lettering should stay off — a sign, a
  hand, a clue. It is a cost, not a rule; a crowded panel covers one before it fails.

Declare everybody the picture draws, not only those who speak. A face nobody casts is still a face,
and still kept clear.

`size` must be the picture's own. A contract measured on another export of the picture is refused:
measure again on this one, or scale every coordinate by the same factor and change `size` with
them. The [schema](editor_support.md) completes and checks the keys as you type, and the full
format is in the [asset contract](../reference/asset_contract.md#artwork-contracts).

## Cast them

```yaml
setting: {image: art/p01-street.png}
cast:
  ana: {figure: ana}
  ben: {figure: ben}
script:
  - say: {by: ana, text: "Where are we?"}
  - say: {by: ben, text: "Somewhere they won't look."}
```

`figure:` takes the place of `reference:`. The cast id is yours; the figure's name is the
contract's. Nothing else a puppet takes applies — no `pose`, no `at`, no `facing`, no `camera`, no
`staging` — because the artist already framed and posed everyone; `scenet check` says so if one is
written. See [what does not apply](../reference/language.md#figures-the-picture-draws).

In a scene or a comic script, the defaults or the front matter can cast every figure of a chapter.
Each panel holds those its own picture draws; a line spoken in a panel by somebody its picture does
not draw is the finding, and lists who it does.

## Check it against the picture

```bash
scenet check examples/gallery/35-figures.scene.yaml
scenet build examples/gallery/35-figures.scene.yaml -o out/ --debug --embed-images
```

`scenet check` reads the contract without the solver. A contract that cannot be read is reported in
the contract itself, at the line at fault (`artwork-contract`), and a figure the picture does not
draw at the line that names it (`unknown-figure`).

The debug overlay, `out/35-figures.platform.debug.svg`, draws every face, mouth, body and keep-out
the contract declares, in the panel's units. Lay it over the panel's SVG — a page with one image on
top of the other, at half opacity, will do — and every disc should ring a face and every mouth sit
on one. That is the whole check, and the gallery's `35-figures` example passes it by construction:
`scripts/make_gallery_figures.py` paints its picture and writes its contract from the same numbers.

## Fit and crop

The contract's coordinates go through the same `fit` as the picture, so a face is kept clear exactly
where the picture draws it under `cover` and `contain` alike. `cover` crops what overhangs: a face
partly cropped is kept clear for the part in view, and a tail to a mouth cropped away ends on the
frame, aimed at it — `scenet build` notes it. `fit: contain` shows the whole picture.

## In the playground

**Image…** adds the contract the same way as the picture: pick `p01-street.png` and
`p01-street.art.yaml` together, and both land in the document's `art/` folder, where the panel finds
them. They last as long as the tab.

## Over MCP

Send the contract in `files` beside the picture, by the path the document would find it at:
`{"art/p01-street.png": "<base64>", "art/p01-street.art.yaml": "<base64>"}`. A finding in the
contract is then reported at the line naming the picture, with the contract's own line in its
message.

## From Python

Give the text the files it names — the picture and its contract — or the folder they are in:

```python
from scenet import compile_source

png = bytes.fromhex(  # a real PNG, three pixels by two
    "89504e470d0a1a0a0000000d4948445200000003000000020800000000b81f39c6"
    "0000001049444154789c636868686068686800000c0803011cb51d7b"
    "0000000049454e44ae426082"
)
contract = b"size: [3, 2]\nfigures:\n  ana: {face: {center: [1, 1], radius: 0.5}}\n"
result = compile_source(
    "cast: {ana: {figure: ana}}\nsetting: {image: art/a.png}\n"
    "script: [{say: {by: ana, text: Hello.}}]\n",
    base={"art/a.png": png, "art/a.art.yaml": contract},
)
(ana,) = result.core.figures
assert ana.actor == "ana"
assert result.camera is None  # nobody to frame: the artist did
assert result.core.balloons[0].speaker == "ana"
```
