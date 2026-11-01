"""Pages into SVG: every panel at its frame.

Mechanical, like every emitter: the frames were resolved into Page Core and each panel into
its own Panel Core, so this only places one inside the other. Each panel is placed exactly
as the strip places one (:func:`placed_panel <scenet.emit.strip.placed_panel>`): rendered on
its own, clipped to its frame, its ids prefixed by its position so they stay unique in the
page.

For a screen reader, a page is a named group and each panel in it one image, in reading
order; the page's own shapes -- its sheet, an inset's ring -- are hidden.
"""

from collections.abc import Mapping, Sequence

from scenet.core import PageCore, PanelCore
from scenet.emit.strip import GROUP, HIDDEN, counted, placed_panel, reading_direction
from scenet.emit.svg import fmt
from scenet.ir import Direction
from scenet.solve.text import FontMetrics

__all__ = ["render_page", "render_pages"]

#: Space between pages laid side by side, as a fraction of the widest page.
PAGE_SPACING_FRACTION = 0.05

PAGE_FILL = "#ffffff"
PAGE_EDGE = "#c9c9c9"
BACKGROUND = "#eeeeee"


def render_page(
    page: PageCore,
    panels: Mapping[str, PanelCore],
    *,
    live_text: bool = False,
    debug: bool = False,
    fonts: Mapping[str, FontMetrics] | None = None,
    aria: bool = True,
    embed: Mapping[str, bytes] | None = None,
    mono: bool = False,
) -> str:
    r"""Render one page as a standalone SVG document.

    Args:
        page: The page: its size and where each panel's frame is.
        panels: Every panel's compiled Core, by name. Each one named by a frame must be
            here, compiled at that frame's size.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place each panel's diagnostic overlay instead of the panel.
        fonts: The declared fonts the panels were lettered in, by digest -- what
            :attr:`Book.fonts <scenet.pipeline.Book.fonts>` holds.
        aria: Make the page a named group of panels a screen reader reads in order.
            `False` writes none of it. An overlay never has it.
        embed: The supplied pictures' bytes, by digest -- what
            :attr:`Book.images <scenet.pipeline.Book.images>` holds -- to write into the
            SVG. Left out, each picture is linked by the path its document wrote.
        mono: Draw every value as its grey and ignore its colour, as for a black-and-white
            edition (#244). Every decision was made on the grey, so this draws exactly what
            `palette: mono` would; see :meth:`PanelCore.as_mono <scenet.core.PanelCore.as_mono>`.

    Returns:
        The page, as SVG.

    Raises:
        ValueError: A frame names a panel that `panels` does not hold.

    Example:
        >>> from scenet import compile_book, render_page
        >>> book = compile_book(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "pages: [{tiers: [{panels: [one]}]}]\npanels: {one: {}}"
        ... )
        >>> cores = {name: result.core for name, result in book.panels.items()}
        >>> 'viewBox="0 0 2000 3000"' in render_page(book.pages[0], cores)
        True
    """
    if mono:
        panels = {name: core.as_mono() for name, core in panels.items()}
    access = aria and not debug
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(page.width)}" '
        f'height="{fmt(page.height)}" viewBox="0 0 {fmt(page.width)} {fmt(page.height)}"'
        f"{GROUP if access else ''}>",
        *([f"  <title>A page of {counted(len(page.frames), 'panel')}.</title>"] if access else []),
        f'  <rect x="0" y="0" width="{fmt(page.width)}" height="{fmt(page.height)}" '
        f'fill="{PAGE_FILL}"{HIDDEN if access else ""}/>',
        *_frames(
            page,
            panels,
            1,
            live_text=live_text,
            debug=debug,
            fonts=fonts,
            aria=aria,
            embed=embed,
        ),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def render_pages(
    pages: Sequence[PageCore],
    panels: Mapping[str, PanelCore],
    *,
    live_text: bool = False,
    debug: bool = False,
    fonts: Mapping[str, FontMetrics] | None = None,
    aria: bool = True,
    embed: Mapping[str, bytes] | None = None,
    mono: bool = False,
) -> str:
    """Render every page side by side, as one SVG document.

    What a single view shows -- the playground's, for one. Each page sits in a group
    `page-<n>`, and panel positions count on across pages, so every id in the document
    stays unique.

    Args:
        pages: The pages, in order.
        panels: Every panel's compiled Core, by name.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place each panel's diagnostic overlay instead of the panel.
        fonts: The declared fonts the panels were lettered in, by digest -- what
            :attr:`Book.fonts <scenet.pipeline.Book.fonts>` holds.
        aria: Make the document a named group of pages, each a named group of panels a
            screen reader reads in order. `False` writes none of it.
        embed: The supplied pictures' bytes, by digest -- what
            :attr:`Book.images <scenet.pipeline.Book.images>` holds -- to write into the
            SVG. Left out, each picture is linked by the path its document wrote.
        mono: Draw every value as its grey and ignore its colour, as for a black-and-white
            edition (#244). Every decision was made on the grey, so this draws exactly what
            `palette: mono` would; see :meth:`PanelCore.as_mono <scenet.core.PanelCore.as_mono>`.

    Returns:
        Every page, side by side, as SVG: left to right, or for pages read right to left
        (#68), from the right, as a manga's spread opens. They are written in reading order.

    Raises:
        ValueError: There are no pages, a frame names a panel `panels` does not hold, or
            the pages are not all read the same way.
    """
    if not pages:
        raise ValueError("there are no pages to render")
    if mono:
        panels = {name: core.as_mono() for name, core in panels.items()}
    rtl = reading_direction([page.direction for page in pages], "pages") is Direction.RTL
    spacing = max(page.width for page in pages) * PAGE_SPACING_FRACTION
    width = sum(page.width for page in pages) + spacing * (len(pages) - 1)
    height = max(page.height for page in pages)
    access = aria and not debug
    hidden = HIDDEN if access else ""

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" height="{fmt(height)}" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}"{GROUP if access else ""}>',
        *([f"  <title>{counted(len(pages), 'page')}.</title>"] if access else []),
        f'  <rect x="0" y="0" width="{fmt(width)}" height="{fmt(height)}" '
        f'fill="{BACKGROUND}"{hidden}/>',
    ]
    cursor = width - pages[0].width if rtl else 0.0
    position = 1
    for number, page in enumerate(pages, start=1):
        parts.append(
            f'  <g id="page-{number}" transform="translate({fmt(cursor)} 0)"'
            f"{GROUP if access else ''}>"
        )
        if access:
            parts.append(
                f"  <title>Page {number} of {len(pages)}, "
                f"{counted(len(page.frames), 'panel')}.</title>"
            )
        parts.append(
            f'  <rect x="0" y="0" width="{fmt(page.width)}" height="{fmt(page.height)}" '
            f'fill="{PAGE_FILL}" stroke="{PAGE_EDGE}" stroke-width="2"{hidden}/>'
        )
        parts.extend(
            _frames(
                page,
                panels,
                position,
                live_text=live_text,
                debug=debug,
                fonts=fonts,
                aria=aria,
                embed=embed,
            )
        )
        parts.append("  </g>")
        position += len(page.frames)
        if rtl and number < len(pages):
            cursor -= spacing + pages[number].width
        else:
            cursor += page.width + spacing
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _frames(
    page: PageCore,
    panels: Mapping[str, PanelCore],
    first_position: int,
    *,
    live_text: bool,
    debug: bool,
    fonts: Mapping[str, FontMetrics] | None,
    aria: bool,
    embed: Mapping[str, bytes] | None,
) -> list[str]:
    """Every panel of one page, at its frame, in reading order from `first_position`.

    Document order is reading order -- it is the order a screen reader follows -- so an
    inset read before its parent is written before it. It stays on top all the same: its
    parent is cut around the inset's clearance, which is in the parent's own units as its
    `exclusions`, so the parent's art stops a gutter short of the inset all round whatever
    is painted first. The clearance is still painted white, just before its inset.
    """
    hidden = HIDDEN if aria and not debug else ""
    lines: list[str] = []
    for position, frame in enumerate(page.frames, start=first_position):
        core = panels.get(frame.panel)
        if core is None:
            raise ValueError(f"the page places panel '{frame.panel}', which was not given")
        if frame.clearance is not None:
            ring = frame.clearance
            lines.append(
                f'  <rect x="{fmt(ring.x)}" y="{fmt(ring.y)}" width="{fmt(ring.width)}" '
                f'height="{fmt(ring.height)}" fill="{PAGE_FILL}"{hidden}/>'
            )
        lines.extend(
            placed_panel(
                frame.panel,
                core,
                position,
                frame.x,
                frame.y,
                live_text=live_text,
                debug=debug,
                fonts=fonts,
                holes=core.exclusions,
                aria=aria,
                embed=embed,
            )
        )
    return lines
