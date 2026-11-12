# Use the playground

The [playground](https://creatoan.github.io/scenet/playground/) is Scenet in a browser: the
document on the left, what it compiles to on the right, redrawn as you type. Nothing is
installed, and nothing you type leaves the page.

## Open an example

The playground opens on the gallery's tour. Its **Example** menu holds every example in the
[gallery](../gallery.md), grouped as the [author's tour](../tutorial/index.md) is, and the
**Previous example** and **Next example** arrows walk them in that order. Under the editor, a
sentence says what the example shows, with a link to the page that explains it.

An address ending in `#example=` and a gallery file name opens that example:
[`#example=01-two-characters.panel.yaml`](https://creatoan.github.io/scenet/playground/#example=01-two-characters.panel.yaml)
opens the umbrella panel. Choosing an example puts its link in the address bar, until your first
edit.

Your edits survive a reload: the playground keeps them in your browser. **Reset to example**
throws them away and brings the example back.

## Write, and read what the compiler says

The editor knows the language: it completes keys and values and shows each key's documentation
on hover, from the same JSON Schema the VS Code extension reads. The picture follows as you type.

Every finding is underlined at the line it is about, and listed under the output, a click away
from its line. **Notes** are listed over the picture: what `scenet check` notes, each under its
rule, then what the compiler decided that you did not ask for, each under its name. Each is
explained, under that id, in [the diagnostics reference](../reference/diagnostics.md). The examples of
*What Scenet tells you* end with a line commented out that makes them an error; **Try it**
uncomments it, as one edit that Ctrl+Z takes back.

## Look at the output

The tabs over the output show the same document several ways:

- **Panel**: the picture, as `scenet build` writes it.
- **Overlay**: the geometry the solver worked against, for a panel or a whole scene, as
  [`--debug`](debug_a_layout.md) draws it.
- **Panel Core**: the resolved layout, read-only, with folding.
- **Depth**, **Mask**, **Pose**, **Boxes** and **Semantics**: the
  [exports for image models](export_for_image_models.md), every panel's side by side under its
  name. They are made only while one of these tabs is open, so typing stays fast. The pose and the
  boxes are JSON; the tab draws their picture.
- **Screen reader**: what a screen reader is given, every image and group the SVG names, nested,
  with its words. See [Make a panel a screen reader can read](make_accessible_output.md).
- **Print**: the PDF `scenet build --pdf` writes, in the browser's own viewer, with what print
  leaves out listed above it. Where a browser shows no PDF in a frame, as on a phone, its link
  opens the file. See [Print a comic](print_a_comic.md).
- **Files**: the files beside the document: the gallery's pictures, artwork contracts and
  puppets, and whatever **Font…**, **Image…** and **Puppet…** added.

**Zoom in**, **Zoom out**, **Fit** and **100%** size the picture; so do scrolling or pinching,
about the pointer, and dragging pans it. Double-click for Fit or 100%. With the picture focused,
`+`, `-`, `0`, `1` and the arrow keys do the same. Editing keeps the zoom; opening another
document fits it. **Full screen** gives the output the whole screen, and the divider between the
editor and the output can be dragged, or moved with the arrow keys.

The **Output** menu says how the output is written, as `scenet build` would be told on the
command line: lettering as live text (`--live-text`), and a document of several panels shown as
its pages, as a strip (`--strip`), or each panel on its own. The choice is kept in your browser;
a share link does not carry it.

## Bring your own files

Three buttons add a file to the document's folder, for as long as the tab is open. Neither a
reload nor a share link keeps them.

- **Font…** adds a `.ttf` or `.otf` file to `fonts/`, so `lettering: {font: fonts/Name.ttf}`
  letters in it. See [Letter in your own font](letter_in_your_own_font.md).
- **Image…** adds a `.png` or `.jpg` to `art/`, to letter over with `setting: {image: art/Name.png}`,
  and its `art/Name.art.yaml` beside it, to cast the figures it draws. See
  [Letter over your own art](letter_over_your_own_art.md).
- **Puppet…** adds a `.puppet.yaml` character to `puppets/`, to cast with
  `reference: puppets/Name.puppet.yaml`. The status line says the reference to write. See
  [Add your own character](add_your_own_character.md).

## Keep and share

**Download** saves what the output shows, named as `scenet build` names it: the panel as SVG or
as a PNG at twice its size, the overlay, the Panel Core, each export for image models, the print
PDF, or the source. A document of several panels has its exports in one ZIP. Ctrl+S saves the
source.

**Share** copies a link with the whole document compressed into the part of the address after
the `#`. That part never reaches a server, so there is no server to keep it: the link is the
document.

## Which version it runs

Every version of Scenet has its own playground: the latest release's at the root of the site,
`main`'s under `/dev/`, and each minor version's under `/vX.Y/`. The switcher beside the title
moves between them, keeping the document, and `main`'s and an old release's say which they are.
A link from these pages opens the playground of the version you are reading.

## The compiler it runs

The playground does not reimplement Scenet. It runs the real compiler, the same Python,
unmodified, under WebAssembly via [Pyodide](https://pyodide.org/): the page installs the exact
wheel `uv build` produces. So there is no second copy of the geometry to drift out of step with
the command line, and every example it offers is a gallery file the test suite compiles.
Everything is served from one origin: no CDN, no analytics, nothing fetched from anywhere else.

How the page is built is in
[the playground's README](https://github.com/creatoan/scenet/blob/main/playground/README.md).
