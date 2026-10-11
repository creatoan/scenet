# Letter in your own font

Scenet letters in Source Sans Pro, which ships with it. To letter in a face of your own, put the
font files beside your document and name them in `lettering`.

## Keep the fonts beside the document

```text
comic/
├── chapter-one.scene.yaml
└── fonts/
    ├── Comic-Regular.ttf
    ├── Comic-Italic.ttf
    └── Comic-BoldItalic.ttf
```

Paths are read relative to the folder the document is in, so `fonts/Comic-Regular.ttf` is found
wherever you run `scenet` from, and the folder can move as a whole. An absolute path is refused.

## Name the faces

One file for every face:

```yaml
lettering: {font: fonts/Comic-Regular.ttf}
```

Or a file per face — `regular` for dialogue, `italic` for captions, `bold_italic` for
[emphasis](../reference/language.md#emphasis):

```yaml
lettering:
  font:
    regular: fonts/Comic-Regular.ttf
    italic: fonts/Comic-Italic.ttf
    bold_italic: fonts/Comic-BoldItalic.ttf
```

Put `lettering:` beside `panels:` and every panel inherits it. In a comic script, put it in the
front matter. A face you leave out is set in one you named, and `scenet build` says so when that
happens:

```text
note (one): no italic face is named in lettering.font, so italic captions are set in Comic Regular; name one as `italic:`
```

## Build and check

Nothing else changes:

<!--- skip: next -->

```bash
scenet check comic/chapter-one.scene.yaml
scenet build comic/chapter-one.scene.yaml -o out/
```

`scenet check` reports a font that is missing, absolute, or not a TrueType or OpenType file as
`font-file`, on the line that names it. The SVG it writes is self-contained, as it always is: the
lettering is glyph outlines, so whoever opens the file needs no font installed.

## From Python

Compile from a file, or give text the folder its fonts are in, and hand the fonts the compile
returns to the renderer:

<!--- skip: next -->

```python
from pathlib import Path

from scenet import compile_book, render

book = compile_book(Path("comic/chapter-one.scene.yaml").read_text(), base=Path("comic"))
for name, result in book.panels.items():
    Path(f"{name}.svg").write_text(render(result.core, fonts=book.fonts))
```

The Panel Core records each face by family, style and a digest of the file — never where it was —
and `render` refuses a Core whose fonts it was not given, rather than draw its lettering in a face
it was not measured in.

## In the playground

**Font…**, above the editor, adds `.ttf` and `.otf` files to the document's `fonts/` folder; name
them as above. They last as long as the tab: a reload, or a share link, does not keep them.

## Which fonts

Any TrueType or OpenType font you are licensed to use. The faces letterers use are mostly
commercial or free only on their own terms, which is why Scenet cannot ship one and lets you name
yours. Check that your licence allows what you do with the output: lettering drawn as outlines is
a rendering of the font, which most licences allow and some restrict.
