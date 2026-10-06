"""Pages into SVG: every panel at its frame.

Mechanical, like every emitter: the frames were resolved into Page Core and each panel into
its own Panel Core, so this only places one inside the other. Each panel is placed exactly
as the strip places one (:func:`placed_panel <scenet.emit.strip.placed_panel>`): rendered on
its own, clipped to its frame, its ids prefixed by its position so they stay unique in the
page.
"""

from collections.abc import Mapping, Sequence

from scenet.core import PageCore, PanelCore
from scenet.emit.strip import placed_panel
from scenet.emit.svg import fmt

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
) -> str:
    r"""Render one page as a standalone SVG document.

    Args:
        page: The page: its size and where each panel's frame is.
        panels: Every panel's compiled Core, by name. Each one named by a frame must be
            here, compiled at that frame's size.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place each panel's diagnostic overlay instead of the panel.

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
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(page.width)}" '
        f'height="{fmt(page.height)}" viewBox="0 0 {fmt(page.width)} {fmt(page.height)}">',
        f'  <rect x="0" y="0" width="{fmt(page.width)}" height="{fmt(page.height)}" '
        f'fill="{PAGE_FILL}"/>',
        *_frames(page, panels, 1, live_text=live_text, debug=debug),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def render_pages(
    pages: Sequence[PageCore],
    panels: Mapping[str, PanelCore],
    *,
    live_text: bool = False,
    debug: bool = False,
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

    Returns:
        Every page, left to right, as SVG.

    Raises:
        ValueError: There are no pages, or a frame names a panel `panels` does not hold.
    """
    if not pages:
        raise ValueError("there are no pages to render")
    spacing = max(page.width for page in pages) * PAGE_SPACING_FRACTION
    width = sum(page.width for page in pages) + spacing * (len(pages) - 1)
    height = max(page.height for page in pages)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" height="{fmt(height)}" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}">',
        f'  <rect x="0" y="0" width="{fmt(width)}" height="{fmt(height)}" fill="{BACKGROUND}"/>',
    ]
    cursor = 0.0
    position = 1
    for number, page in enumerate(pages, start=1):
        parts.append(f'  <g id="page-{number}" transform="translate({fmt(cursor)} 0)">')
        parts.append(
            f'  <rect x="0" y="0" width="{fmt(page.width)}" height="{fmt(page.height)}" '
            f'fill="{PAGE_FILL}" stroke="{PAGE_EDGE}" stroke-width="2"/>'
        )
        parts.extend(_frames(page, panels, position, live_text=live_text, debug=debug))
        parts.append("  </g>")
        position += len(page.frames)
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
) -> list[str]:
    """Every panel of one page, at its frame, positions counting from `first_position`.

    Positions follow reading order, but painting does not: every inset is painted after
    every other panel, so it is on top of its parent even when it is read first. Each one
    goes down on its clearance, painted white, so its parent's art stops a gutter short of
    it all round.
    """
    lines: list[str] = []
    numbered = list(enumerate(page.frames, start=first_position))
    painted = [entry for entry in numbered if entry[1].inset_of is None] + [
        entry for entry in numbered if entry[1].inset_of is not None
    ]
    for position, frame in painted:
        core = panels.get(frame.panel)
        if core is None:
            raise ValueError(f"the page places panel '{frame.panel}', which was not given")
        if frame.clearance is not None:
            ring = frame.clearance
            lines.append(
                f'  <rect x="{fmt(ring.x)}" y="{fmt(ring.y)}" width="{fmt(ring.width)}" '
                f'height="{fmt(ring.height)}" fill="{PAGE_FILL}"/>'
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
            )
        )
    return lines
