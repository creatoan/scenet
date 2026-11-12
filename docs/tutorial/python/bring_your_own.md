# Bring your own

Scenet ships two characters and one font, and reads nothing it was not given. This chapter
gives it more: a character of your own, a font of your own, the files a document names,
handed over from memory, and a picture behind the cast.

## What you will build

A program that compiles documents against assets it chose: a puppet library with a third
character, every panel measured in a font of its own, a document's files supplied as bytes
rather than read from a folder, and a panel drawn over a picture, with the picture written
into the SVG.

The examples use the files in the gallery's folders. Save
[`puppets/pip.puppet.yaml`](https://github.com/creatoan/scenet/tree/main/examples/gallery/puppets),
[`fonts/ComicNeue-Regular.ttf`](https://github.com/creatoan/scenet/tree/main/examples/gallery/fonts)
and [`art/street.png`](https://github.com/creatoan/scenet/tree/main/examples/gallery/art) in
folders of those names, beside your scripts.

## A puppet library

A cast member's `reference` names a puppet in a
[`PuppetLibrary`](../../reference/api/public/PuppetLibrary.md).
[`default_library`](../../reference/api/public/default_library.md) is the two Scenet ships;
[`load_puppet`](../../reference/api/public/load_puppet.md) reads a puppet file as a
[`PuppetSpec`](../../reference/api/public/PuppetSpec.md), which says what the character is
made of and the poses and expressions it can take. A library built by hand holds any puppet
under any name, and `library=` gives it to a compile:

```python
from pathlib import Path

from scenet import PuppetLibrary, compile_source, default_library, load_puppet

pip = load_puppet(Path("puppets/pip.puppet.yaml"))
print(pip.name, list(pip.poses), list(pip.expressions))

shipped = default_library()
library = PuppetLibrary({"alice": shipped.get("alice"), "pip": pip})
print(library.names())

result = compile_source(
    "cast:\n"
    "  alice: {reference: alice, at: left_third}\n"
    "  pip: {reference: pip, at: right_third, facing: left, pose: waving}\n"
    "staging: [alice left_of pip, alice ground_shared_with pip]\n",
    library=library,
)
print([(actor.id, actor.reference, actor.pose) for actor in result.core.actors])
```

```text
pip ['standing_neutral', 'waving', 'arms_up'] ['neutral', 'happy', 'surprise', 'scared', 'sad']
('alice', 'pip')
[('alice', 'alice', 'standing_neutral'), ('pip', 'pip', 'waving')]
```

`PuppetLibrary.from_directory(Path("puppets"))` reads every puppet file in a folder.
`default_library()` reads the shipped puppets on each call, so call it once and pass the
library on. [Add your own character](../../howto/add_your_own_character.md) says how a
puppet file is written.

A document can instead name a puppet file by its path, `reference: puppets/pip.puppet.yaml`,
relative to the document, and needs no library at all. Save this as `docks.panel.yaml`:

```{scenet-example}
:beside: examples/gallery
:file: docks.panel.yaml

panel: {size: [900, 600]}
camera: {shot: full_shot}
cast:
  alice: {reference: alice, at: left_third}
  pip: {reference: puppets/pip.puppet.yaml, at: right_third, facing: left}
staging:
  - alice left_of pip
  - alice ground_shared_with pip
script:
  - say: {by: pip, text: "Is that our boat?"}
```

```python
from pathlib import Path

from scenet import compile_file

core = compile_file(Path("docks.panel.yaml")).core
print([actor.reference for actor in core.actors])
print(core.balloons[0].speaker, core.balloons[0].lines)
```

```text
['alice', 'puppets/pip.puppet.yaml']
pip ('Is that our', 'boat?')
```

## A font of your own: `metrics=`

A balloon is the size its text needs, and that is measured in the font it will be drawn
in. A [`FontMetrics`](../../reference/api/public/FontMetrics.md) is a font file, read and
measured; Scenet never looks a font up on the system, because what is measured has to be
what is drawn, everywhere. Pass it as `metrics=` to the compile and the same one to the
renderer, and every panel is lettered in it without a document naming it:

```python
from pathlib import Path

from scenet import FontMetrics, compile_source, render

neue = FontMetrics(Path("fonts/ComicNeue-Regular.ttf"))
text = "cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: In my own face.}}]"

default = compile_source(text).core.balloons[0]
own = compile_source(text, metrics=neue).core.balloons[0]
print(default.box.width, "->", own.box.width)

svg = render(compile_source(text, metrics=neue).core, metrics=neue)
print(svg.startswith("<?xml"))
print(round(neue.measure("In my own face.", 32.0), 2))
```

```text
189.31 -> 198.06
True
217.79
```

A document can name a font itself, `lettering: {font: fonts/neue.ttf}`, as the
[first chapter](compile_and_render.md#what-a-renderer-is-handed-back-fonts-and-embed) did:
its result's `fonts` hand it to the renderer. [Letter in your own
font](../../howto/letter_in_your_own_font.md) has both, and the faces for italic and bold.

## The files a document reads: `base=`

A document names its files by paths relative to its own folder: a font, a picture, a
puppet. Compiled from text, it has no folder, and `base=` gives it one: a `Path` to read
them from, or a mapping of each path the document writes to the file's bytes. With a
mapping, nothing is read from disk, which is how to compile a document you did not write:
a path in it may climb out of a folder with `../`, and a mapping holds only what you put
in it.

```python
from pathlib import Path

from scenet import compile_source, render

text = (
    "lettering: {font: fonts/neue.ttf}\n"
    "cast: {a: {reference: alice}}\n"
    "script: [{say: {by: a, text: From memory.}}]\n"
)
files = {"fonts/neue.ttf": Path("fonts/ComicNeue-Regular.ttf").read_bytes()}

result = compile_source(text, base=files)
print(len(result.fonts), "font, read from", len(files), "file handed over")
print(render(result.core, fonts=result.fonts).startswith("<?xml"))

from_folder = compile_source(text.replace("neue.ttf", "ComicNeue-Regular.ttf"), base=Path("."))
print(from_folder.core.balloons[0].box == result.core.balloons[0].box)
```

```text
1 font, read from 1 file handed over
True
True
```

A file a document names that is not there is the document's fault, so it is a
`PanelSyntaxError` that says where the document named it, not a `FileNotFoundError`.
[The Guarantees page](../../reference/api/guarantees.md) says exactly what a compile reads.

## A picture behind the cast

`setting: {image: ...}` names a PNG or JPEG to draw behind the cast. The compiler reads its
size, and nothing else of it. The Core names the picture by the digest of its bytes, and
the result's `images` holds the bytes under that digest, for a renderer to embed:

```python
from pathlib import Path

from scenet import compile_source, render

text = (
    "panel: {size: [900, 500]}\n"
    "setting: {image: art/street.png, fit: cover, time: dusk}\n"
    "cast: {a: {reference: alice}}\n"
)
result = compile_source(text, base={"art/street.png": Path("art/street.png").read_bytes()})
print([digest[:12] for digest in result.images])

svg = render(result.core, embed=result.images)
Path("street.svg").write_text(svg, encoding="utf-8")
print("data:image/png;base64," in svg, 'href="art/street.png"' in render(result.core))
```

```text
['ed788ebc79d0']
True True
```

Without `embed=`, the SVG links the picture by its path, `art/street.png`, which a viewer
finds beside the SVG; with it, the SVG carries the picture and stands alone. A book's
`images` go to `render_pdf` as `images=`, and print always carries them. People your
picture already draws can be lettered as figures, with an artwork contract: see
[Letter the figures in your art](../../howto/letter_the_figures_in_your_art.md).

## What you learned

- **Characters are a library**: `default_library`, `load_puppet` and `PuppetLibrary`, passed
  as `library=`; or a puppet file a document names by its path.
- **A font is a file**, measured as a `FontMetrics` and passed as `metrics=` to the compile
  and the renderer, so what is measured is what is drawn.
- **`base=` is the document's folder**: a `Path`, or a mapping of paths to bytes, which reads
  nothing from disk and is the way to compile a document you do not trust.
- **A picture's bytes travel with the result**, as `images`, for `embed=`.

## Where to go next

- [Outputs, batch and CI](outputs_batch_and_ci.md): many documents, golden files, and Scenet
  in CI and in a tool of your own.
- [Your own art and characters](../your_own_art.md), the author's chapter on the same files.
- [The puppet format](../../reference/asset_contract.md), and the reference pages of
  [`PuppetLibrary`](../../reference/api/public/PuppetLibrary.md) and
  [`FontMetrics`](../../reference/api/public/FontMetrics.md).
