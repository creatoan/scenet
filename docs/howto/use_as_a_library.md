# Use Scenet as a library

The `scenet` command is a thin wrapper over the same functions you can call yourself.
This page covers the public API: what is in it, what is not, and how to reach the parts
the command line does not expose.

## The one function you probably want

```python
from scenet import compile_source, render

result = compile_source("""
panel: {size: [900, 600]}
cast:
  alice: {reference: alice}
script:
  - say: {by: alice, text: "Compiled from a string."}
""")

svg = render(result.core)
assert svg.lstrip().startswith("<?xml")
```

## Choosing an entry point

| You have | Call |
|---|---|
| A panel as a string | {func}`compile_source <scenet.pipeline.compile_source>` |
| A `*.panel.yaml` path | {func}`compile_file <scenet.pipeline.compile_file>` |
| A multi-panel string | {func}`compile_scene <scenet.pipeline.compile_scene>` |
| A `*.scene.yaml` path | {func}`compile_scene_file <scenet.pipeline.compile_scene_file>` |
| Any supported file, unknown type | {func}`compile_document <scenet.pipeline.compile_document>` |
| A scene with pages, as a string | {func}`compile_book <scenet.pipeline.compile_book>` |
| A comic script, as a string | {func}`compile_script <scenet.pipeline.compile_script>` |
| Any supported file, and its pages | {func}`compile_book_file <scenet.pipeline.compile_book_file>` |
| Any supported file, its panels alone | {func}`compile_document <scenet.pipeline.compile_document>` |
| An already-validated `PanelIR` | {func}`compile_ir <scenet.pipeline.compile_ir>` |

{func}`compile_book_file <scenet.pipeline.compile_book_file>` dispatches on the file
extension, which is what the CLI uses. It is the right choice when the syntax is the
user's decision rather than yours. Each `parse_*` and `load_*` function stops at the IR,
without compiling: everything an author can get wrong is found there.

## Seven renderers

Every renderer reads a Core and makes no layout decision of its own: what it draws is what
the compiler decided.

| Renderer | Draws | Returns |
|---|---|---|
| {func}`render <scenet.emit.svg.render>` | One panel | SVG text |
| {func}`render_debug <scenet.emit.debug_svg.render_debug>` | One panel's geometry: hulls, face zones, anchors, gaze, tail routes | SVG text |
| {func}`render_strip <scenet.emit.strip.render_strip>` | Several panels side by side, in reading order | SVG text |
| {func}`render_page <scenet.emit.page.render_page>` | One page, each panel at its frame | SVG text |
| {func}`render_pages <scenet.emit.page.render_pages>` | Every page, side by side | SVG text |
| {func}`render_pdf <scenet.emit.pdf.render_pdf>` | Every page, for print | PDF bytes |
| {func}`render_conditioning <scenet.emit.export.render_conditioning>` | The staging, for image models: pose, boxes, depth, mask, semantics | A {class}`Conditioning <scenet.emit.export.Conditioning>` |

```python
from scenet import compile_scene, render, render_debug, render_strip

panels = compile_scene("""
panels:
  wide:  {cast: {a: {reference: alice}}, camera: {shot: full_shot}}
  close: {over: wide, camera: {shot: close_up}}
""")

# One SVG per panel.
each = {name: render(result.core) for name, result in panels.items()}
assert set(each) == {"wide", "close"}

# The diagnostic overlay: hulls, face zones, anchors, gaze vectors, tail routes.
overlay = render_debug(panels["wide"].core)

# All panels laid out side by side, in reading order.
strip = render_strip([(name, result.core) for name, result in panels.items()])
```

`render` takes `live_text=True` if you want selectable `<text>` elements instead of
glyph outlines. The default emits outlines, which makes the file self-contained — no
font to embed and none to be missing — at the cost of a larger file and text you cannot
select.

### What a renderer must be handed back

A Core names its fonts and pictures by the digest of their bytes, and holds neither. What
the compile read, it returns, and a renderer is handed it back:

- **`fonts=`** — every font a document declared, from `result.fonts` or `book.fonts`. A Core
  lettered in a font of its own, drawn without it, raises `RenderError`: drawing the
  lettering in another face would draw text that does not fit the balloons measured for it.
- **`embed=`** — a supplied picture's bytes, from `result.images` or `book.images`, to write
  into the SVG as a `data:` URL. Left out, the SVG links the picture by the path the document
  wrote, which a viewer must then find beside it. The print PDF takes them as `images=` and
  always carries them.

Both are shown in [your own font](#your-own-font) below.

## Pages, and books

A scene with `pages:` lays its panels out on pages. {func}`compile_book
<scenet.pipeline.compile_book>` returns a {class}`Book <scenet.pipeline.Book>`: every
panel, compiled at its frame's shape, and a Page Core per page.

```python
from scenet import compile_book, render_page, render_pages, render_pdf

book = compile_book("""
cast: {a: {reference: alice}, b: {reference: bob, at: right_third, facing: left}}
pages:
  - tiers:
      - panels: [{use: wide, width: 2}, close]
panels:
  wide: {camera: {shot: full_shot}}
  close: {over: wide, camera: {shot: close_up}, script: [{say: {by: a, text: "Hello."}}]}
""")
cores = {name: result.core for name, result in book.panels.items()}

first = render_page(book.pages[0], cores, fonts=book.fonts)
spread = render_pages(book.pages, cores, fonts=book.fonts)
pdf = render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)
assert pdf.startswith(b"%PDF-")
```

A page unit prints as 0.1 mm, and lettering is on the black plate. `live_text=True` letters
the PDF in its embedded faces rather than outlines, and `mono=True` prints the greys rather
than the tinted palette's CMYK twins. See [Print a comic](print_a_comic.md).

{func}`compile_book_file <scenet.pipeline.compile_book_file>` reads any document and its
pages, choosing the frontend by extension — what `scenet build` calls. A comic script has
no pages; {func}`compile_script <scenet.pipeline.compile_script>` returns its panels as a
book.

## Exports for image models

```python
import json

from scenet import compile_source, render_conditioning

exports = render_conditioning(compile_source("cast: {a: {reference: alice}}").core)
pose = json.loads(exports.pose)           # OpenPose COCO-18 keypoints
semantics = json.loads(exports.semantics)  # what the panel holds, as structure
assert exports.depth.lstrip().startswith("<")
```

Each is drawn from the Core alone. See [Export for image models](export_for_image_models.md).

## Handling errors

Everything the compiler can object to inherits `ScenetError`:

```python
from scenet import ScenetError, compile_source

try:
    compile_source("cast: {ghost: {reference: nobody}}")
except ScenetError as exc:
    message = str(exc.args[0])

assert "nobody" in message
```

The middle tier of the hierarchy answers the question you usually have, which is whose
fault it is:

```python
from scenet import ScenetError, SolverError, SourceError, compile_source

# A malformed document: the person who wrote the panel needs to fix it.
try:
    compile_source("panel: {size: [0, 100]}")
except SourceError as exc:
    assert "must be positive" in str(exc)

# Both branches are catchable as one thing when you do not care which.
assert issubclass(SourceError, ScenetError)
assert issubclass(SolverError, ScenetError)
```

Every concrete error also keeps the built-in base you would have reached for before this
hierarchy existed — `SourceError` is a `ValueError`, `UnknownPuppetError` is a `KeyError`,
`MissingFileError` is a `FileNotFoundError` — so existing handlers keep working. Beyond the
document's own faults:

| Error | Raised when | Also a |
|---|---|---|
| `FileReadError`, `MissingFileError` | A file a call names cannot be read, or is not there | `OSError`, `FileNotFoundError` |
| `MalformedAssetError` | A puppet or font file is there and is not one | `ValueError` |
| `RenderError` | A renderer is not handed a font, a picture's bytes, or a panel a page places | `ValueError` |
| `UnknownActorError` | `PanelCore.actor` or `.speaker` is asked for an id the panel lacks | `KeyError` |
| `CoreSyntaxError` | `PanelCore.from_json` or `PageCore.from_json` is given text that is not one | `ValueError` |

A model you build yourself, such as `PanelIR(...)`, raises pydantic's `ValidationError`, as
pydantic does. Every function's entry in the reference lists exactly what it raises.

See {mod}`scenet.errors` for the full tree.

## Reading the layout instead of drawing it

The interesting information is in `result.core`, not in the SVG. Panel Core is fully
resolved and entirely numeric, but every name you wrote survives:

```python
from scenet import PanelCore, compile_source

result = compile_source("""
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third}
staging: [alice left_of bob]
script:
  - say: {by: alice, text: "Look over there."}
""")

alice = result.core.actor("alice")

# Named attachment points, in panel coordinates.
mouth_x, mouth_y = alice.anchors["mouth"]

# The region no balloon may cover.
face = alice.face_exclusion

# Painter's order: higher values are drawn in front.
assert alice.depth >= 0

# And it serialises to something you can diff, edit, and read back.
document = result.core.to_json()
restored = PanelCore.from_json(document)
assert restored == result.core
```

That round trip is the point of the tier. A layout can leave the compiler, be adjusted by
hand or by another tool, and come back for emission without ever touching the source.

## Supplying your own characters

Both the puppet library and the font are injectable:

```python
from scenet import PuppetLibrary, compile_source, default_library

library = default_library()
assert library.names() == ("alice", "bob")

# A library built by hand takes the same shape.
just_alice = PuppetLibrary({"alice": library.get("alice")})

result = compile_source("cast: {a: {reference: alice}}", library=just_alice)
assert result.core.actors[0].reference == "alice"
```

A document can also name a puppet file of its own, `reference: puppets/pip.puppet.yaml`, read
beside it — or, for text, from the files passed as `base=` — with no library to build. See
[add your own character](add_your_own_character.md) for both, and for the file format.

## Your own font

A document names its font as a file beside it, `lettering: {font: fonts/neue.ttf}`. From
Python, the files a document names can be handed over as a mapping with `base=`, so
nothing is read from disk:

```python
from pathlib import Path

from scenet import compile_source, render

neue = Path("examples/gallery/fonts/ComicNeue-Regular.ttf").read_bytes()
result = compile_source(
    "lettering: {font: fonts/neue.ttf}\n"
    "cast: {a: {reference: alice}}\n"
    "script: [{say: {by: a, text: In my own face.}}]",
    base={"fonts/neue.ttf": neue},
)
svg = render(result.core, fonts=result.fonts)
```

To measure every panel against one font without a document naming it, pass a
{class}`FontMetrics <scenet.solve.text.FontMetrics>` as `metrics=` to the compile, and the
same one to the renderer:

```python
from pathlib import Path

from scenet import FontMetrics, compile_source, render

font = FontMetrics(Path("examples/gallery/fonts/ComicNeue-Regular.ttf"))
result = compile_source("cast: {a: {reference: alice}}", metrics=font)
svg = render(result.core, metrics=font)
```

A font is always a file, never a system font: what is measured has to be what is drawn,
everywhere. See [Letter in your own font](letter_in_your_own_font.md).

## Building a panel in Python

The language is the IR's models, and each validates as it is built. Build one by hand and
compile it with {func}`compile_ir <scenet.pipeline.compile_ir>`:

```python
from scenet import CameraSpec, CastMember, PanelIR, Relation, SayEvent, compile_ir

panel = PanelIR(
    camera=CameraSpec(shot="medium_shot"),
    cast={
        "alice": CastMember(reference="alice", at="left_third"),
        "bob": CastMember(reference="bob", at="right_third", facing="left"),
    },
    staging=[Relation(subject="alice", predicate="left_of", object="bob")],
    script=[SayEvent(by="alice", text="Built, not written.")],
)
result = compile_ir(panel)
assert result.core.balloons[0].speaker == "alice"
```

A model built by hand raises pydantic's `ValidationError` for a bad value, as pydantic
does; the frontends turn the same fault into a `PanelSyntaxError` that says where it is.

## The Core object model

A Panel Core is a tree of plain, frozen models. What you will read most:

| Read | Type | What it holds |
|---|---|---|
| `core.width`, `core.height` | `float` | The panel's size, in panel units |
| `core.actors` | `CoreActor` | Each character: transform, anchors, face, hull, pose, depth |
| `core.figures` | `CoreFigure` | Each figure a supplied picture draws |
| `core.balloons` | `CoreBalloon` | Each balloon: box, lines as broken, font size, tail |
| `core.captions` | `CoreCaption` | Each caption box |
| `core.sfx` | `CoreSfx` | Each sound effect, its glyphs placed |
| `core.backdrop` | `CoreBackdrop` | The setting, resolved: masses, atmosphere, a picture |
| `core.camera` | `CoreCamera` | The shot asked for, and what the camera made of it |

Every type is on [the Panel Core types](../reference/api/public/core-types.md) page, and
every field of a Panel Core is in [the format's reference](../reference/panel_core.md).
Import a type from `scenet.core` to annotate with it. A layout read off the Core is the
compiler's own: change it and write it back with `to_json`, and the renderers draw what you
wrote.

## Threads, caches, and the files a compile reads

- **Threads.** Compiles may run in parallel threads; they share only caches of parsed fonts.
  Call {func}`default_library <scenet.assets.contract.default_library>` once and pass the
  library on: it reads the shipped puppets on every call.
- **Files.** A compile reads only the files the document names, from `base` or the folder
  of `source`. Compiling documents you do not trust, hand their files over as a mapping:
  a path a document writes may climb out of a folder with `../`.
- **Dependencies.** `compile_book_file(path, dependencies=set())` fills the set with every
  file the compile read, which is how `scenet build --watch` knows what to watch.

The [Guarantees](../reference/api/guarantees.md) page has the details, and timings.

## What is public

`scenet.__all__` is the contract, and [the reference](../reference/api/index.md) has an
entry for each name in it, with the release it appeared in. Names outside it are internal
and may change in any minor release:

```python
import scenet

assert "compile_source" in scenet.__all__
assert "render" in scenet.__all__

# Reachable, but not promised. Import from these at your own risk.
import scenet.solve.balloons  # noqa: F401
```

If you find yourself needing something that is not exported, that is worth
[raising as an issue](https://github.com/creatoan/scenet/issues) — it usually means the
public surface has a gap.

## Determinism, and what it buys you

The same input always produces byte-identical output. No wall-clock time, no unseeded
randomness, no reliance on dictionary iteration order, no absolute paths in the output.

```python
from scenet import compile_source, render

source = "cast: {a: {reference: alice}}"
assert render(compile_source(source).core) == render(compile_source(source).core)
```

That is what makes golden-file testing possible, and it is why a Scenet panel can live in
version control as a source file rather than as a binary blob.
