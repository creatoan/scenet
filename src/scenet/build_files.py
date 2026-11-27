r"""The files a build writes, and what each is called: one list for `scenet build` and for MCP.

`scenet build` writes them where `-o` says, and the MCP server's `build` tool writes the
same files into the folder `scenet mcp --output` names. Both ask this module which files a
document makes and how each is named, so the two cannot disagree on a name or on a byte.
Nothing here writes: each file's content is a deferred call, so that the whole set can be
checked -- for two files with one name, or one already there -- before any of it is rendered.

Example:
    >>> from pathlib import Path
    >>> from scenet import compile_book
    >>> from scenet.build_files import build_outputs
    >>> book = compile_book("cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: Hi}}]")
    >>> [path.name for path, _ in build_outputs(book, Path("out/cover.svg"), single=True)]
    ['cover.svg']
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path

from scenet.emit.debug_svg import render_debug
from scenet.emit.export import EXPORTS
from scenet.emit.page import render_page
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.pipeline import Book

__all__ = ["Output", "build_outputs"]

#: One file a build will write, and how to produce what goes in it -- deferred, so that
#: the whole set can be checked for clashes before any of it is rendered.
Output = tuple[Path, Callable[[], str | bytes]]


def build_outputs(
    book: Book,
    base: Path,
    *,
    single: bool,
    pdf: bytes | None = None,
    embed_images: bool = False,
    live_text: bool = False,
    mono: bool = False,
    aria: bool = True,
    core: bool = False,
    debug: bool = False,
    conditioning: bool = False,
    strip: bool = False,
) -> list[Output]:
    """Every file a build writes, in the order it writes them.

    A single-panel document writes to the requested name; a sequence suffixes each panel
    with its own name, so the mapping back to source is obvious. A strip needs more than
    one panel to lay out. Each page goes to `stem.page-<n>.svg`, beside the panels. The
    exports for image models are per panel only: a page adds no layout to a panel, and its
    Page Core says where every frame is. The print PDF, already rendered, is one file for
    the whole document, `stem.pdf`.

    Args:
        book: The compiled document.
        base: The main SVG's path; every other file is named after it.
        single: Whether the document is one panel, named `panel`.
        pdf: The print PDF, already rendered, or `None` for none.
        embed_images: Write each picture into the SVGs, rather than link it.
        live_text: Selectable `<text>` rather than glyph outlines.
        mono: Draw every value as its grey.
        aria: Make each panel an image a screen reader can read.
        core: Also write each panel's and page's Core, as JSON.
        debug: Also write each panel's and page's debug overlay.
        conditioning: Also write each panel's exports for image models.
        strip: Also write the panels side by side, when there are two or more.

    Returns:
        Each file's path and the call that produces its content.
    """
    outputs: list[Output] = []
    embed = book.images if embed_images else None
    for name, result in book.panels.items():
        panel_core = result.core
        target = base if single else base.with_name(f"{base.stem}.{name}{base.suffix}")
        outputs.append(
            (
                target,
                partial(
                    render,
                    panel_core,
                    fonts=book.fonts,
                    live_text=live_text,
                    mono=mono,
                    aria=aria,
                    embed=embed,
                ),
            )
        )
        if core:
            outputs.append((target.with_suffix(".core.json"), panel_core.to_json))
        if debug:
            outputs.append(
                (target.with_name(f"{target.stem}.debug.svg"), partial(render_debug, panel_core))
            )
        if conditioning:
            outputs.extend(
                (target.with_name(f"{target.stem}{suffix}"), partial(export, panel_core))
                for suffix, export in EXPORTS
            )

    if strip and len(book.panels) > 1:
        panels = [(name, result.core) for name, result in book.panels.items()]
        outputs.append(
            (
                base.with_name(f"{base.stem}.strip.svg"),
                partial(
                    render_strip,
                    panels,
                    live_text=live_text,
                    mono=mono,
                    fonts=book.fonts,
                    aria=aria,
                    embed=embed,
                ),
            )
        )

    cores = {name: result.core for name, result in book.panels.items()}
    for number, page in enumerate(book.pages, start=1):
        target = base.with_name(f"{base.stem}.page-{number}{base.suffix}")
        outputs.append(
            (
                target,
                partial(
                    render_page,
                    page,
                    cores,
                    live_text=live_text,
                    mono=mono,
                    fonts=book.fonts,
                    aria=aria,
                    embed=embed,
                ),
            )
        )
        if core:
            outputs.append((target.with_suffix(".core.json"), page.to_json))
        if debug:
            outputs.append(
                (
                    target.with_name(f"{target.stem}.debug.svg"),
                    partial(render_page, page, cores, debug=True),
                )
            )
    if pdf is not None:
        outputs.append((base.with_suffix(".pdf"), partial(bytes, pdf)))
    return outputs
