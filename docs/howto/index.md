# How-to guides

Recipes for one job each, grouped by what you are doing. Each assumes you know roughly what
Scenet is; if you do not, [the tutorial](../tutorial/index) is the place to start.

Every Python and bash code block here is executed by the test suite, so examples cannot
quietly lose an import or drift. Workflow examples are illustrative; the suite does not
run them.

## Writing

- **[Compile a sequence of panels](compile_a_sequence.md)** — panels that say only what changed
  from the one before, and a strip of them.
- **[Compose a page](compose_a_page.md)** — tiers, columns, insets and slants, with one type size
  across the page.
- **[Write a panel as a comic script](write_a_comic_script.md)** — the format writers already use,
  in Dark Horse's layout, in French, or kept in Markdown.

## Art and characters

- **[Add your own character](add_your_own_character.md)** — a puppet file: a skeleton, its parts,
  a face, poses and expressions.
- **[Letter over your own art](letter_over_your_own_art.md)** — a picture behind the cast,
  linked or embedded.
- **[Letter the people in your own art](letter_the_figures_in_your_art.md)** — figures a picture
  draws, declared in an artwork contract and lettered around.
- **[Letter in your own font](letter_in_your_own_font.md)** — a face beside the document,
  measured and drawn exactly.

## Output

- **[Print a comic](print_a_comic.md)** — a PDF with its trim and bleed, lettering on the black
  plate, and what to tell the printer.
- **[Make a panel a screen reader can read](make_accessible_output.md)** — descriptions written,
  kept from a script or generated, and read in reading order.
- **[Export a panel's staging for image models](export_for_image_models.md)** — a pose, boxes, a
  depth map, a mask and the semantics, from the same layout.

## Tooling

- **[Install Scenet](install.md)** — with pip, uv or pipx, its extras, and nothing to configure.
- **[Use the playground](use_the_playground.md)** — every button of the browser playground, which
  runs the real compiler without installing anything.
- **[Get completion and validation in your editor](editor_support.md)** — the VS Code extension,
  or any editor that reads JSON Schema.
- **[Work out why a panel looks wrong](debug_a_layout.md)** — the debug overlay, Panel Core, and
  what the compiler's notes say.
- **[Build and check a comic in CI](build_in_ci.md)** — `scenet check` in a workflow, its
  findings as SARIF, and the built pictures kept.

## Integration

- **[Use Scenet as a library](use_as_a_library.md)** — the Python API, from a document to its
  pictures, inside a program of your own.
- **[Drive Scenet from a model](drive_from_a_model.md)** — the spec pack, the Agent Skill and the
  MCP server, for a chat app, an agent or an MCP client.

```{toctree}
:hidden:
:caption: Writing

compile_a_sequence
compose_a_page
write_a_comic_script
```

```{toctree}
:hidden:
:caption: Art and characters

add_your_own_character
letter_over_your_own_art
letter_the_figures_in_your_art
letter_in_your_own_font
```

```{toctree}
:hidden:
:caption: Output

print_a_comic
make_accessible_output
export_for_image_models
```

```{toctree}
:hidden:
:caption: Tooling

install
use_the_playground
editor_support
debug_a_layout
build_in_ci
```

```{toctree}
:hidden:
:caption: Integration

use_as_a_library
drive_from_a_model
```
