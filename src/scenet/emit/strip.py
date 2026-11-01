"""Several panels laid out as a strip.

Deliberately minimal. Real page composition -- tiers, panels of varying size, the
page-level reading path, bleeds -- is a substantial design problem in its own right
and is explicitly out of scope. This is the smallest thing that lets a sequence be
read as a sequence: panels in a row, separated by a gutter, in declaration order.

The gutter is not decoration. It is where the reader performs what Scott McCloud calls
closure -- inferring what happened between two panels -- and it is the one formal
element that distinguishes comics from a series of illustrations.

**A panel in a strip looks exactly as it does alone.** Two things make that true, and
both used to be missing:

- **Each panel is clipped to its frame.** A shot crops the body at the frame, so most of
  a figure usually lies outside it. A panel on its own hides that behind its `viewBox`;
  here the same rectangle is a `clipPath`, or the rest of the figure would draw into the
  gutter -- and, once panels stack, into the tier below. The clip sits on an inner group
  with no transform of its own, because `userSpaceOnUse` is defined against the
  referencing element's user space, which is ambiguous on an element that also carries a
  `transform`. The overlay is clipped too: alone, its `viewBox` clips it just the same.
- **Every id is unique.** Each panel's ids, and the references to them, are prefixed by
  the panel's *position* -- `p1-`, `p2-` -- rather than its name. A name is whatever the
  document said, and while attribute escaping keeps one inside its quotes, nothing would
  keep it inside `url(#...)`. Position is unique, safe and the same on every run. The
  panel's group keeps its name, as `panel-<name>`.
"""

from collections.abc import Mapping, Sequence

from scenet.core import Box, PanelCore
from scenet.emit.debug_svg import debug_body
from scenet.emit.svg import accessible_name, attr, fmt, panel_body, typeface_of
from scenet.ir import Direction
from scenet.solve.text import FontMetrics

#: A document of panels, for a screen reader: a group, each panel in it an image. `group`
#: is the role every engine computes and screen readers announce; `graphics-document` is
#: the specification's, but Firefox reduces it to a plain document and no screen-reader
#: test of it is published (ACT rule 7d6734 calls its support inconsistent).
GROUP = ' role="group"'

#: On a shape of the document's own -- a background, a page, an inset's ring -- so that
#: WebKit, which exposes an unnamed shape under a named ancestor as an unnamed image, does
#: not announce it.
HIDDEN = ' aria-hidden="true"'

# Space between panels, as a fraction of the tallest panel.
GUTTER_FRACTION = 0.04


def reading_direction(directions: Sequence[Direction], what: str) -> Direction:
    """The one way a set of panels or pages is read, which laying them out side by side needs.

    Raises:
        ValueError: They are not all read the same way. Every panel and page of one
            document is, so this is panels gathered from documents read differently.
    """
    distinct = sorted(set(directions))
    if len(distinct) > 1:
        raise ValueError(
            f"{what} are read in one direction, and these are read {' and '.join(distinct)}"
        )
    return distinct[0] if distinct else Direction.LTR


def counted(number: int, noun: str) -> str:
    """`1 panel`, `2 panels`: a count as it is said.

    Example:
        >>> counted(1, "panel"), counted(3, "page")
        ('1 panel', '3 pages')
    """
    return f"{number} {noun}{'' if number == 1 else 's'}"


MARGIN_FRACTION = 0.03


def render_strip(
    panels: list[tuple[str, PanelCore]],
    *,
    live_text: bool = False,
    debug: bool = False,
    fonts: Mapping[str, FontMetrics] | None = None,
    aria: bool = True,
    embed: Mapping[str, bytes] | None = None,
    mono: bool = False,
) -> str:
    """Lay panels side by side in reading order: left to right, or right to left.

    Each panel is rendered independently and then placed, rather than being
    re-solved: a panel's composition must not depend on what sits beside it, or the
    same source would compile differently in isolation. Panels read right to left (#68)
    are laid from the right; they are still written in reading order, which is the order
    a screen reader follows.

    Args:
        panels: Panel name and compiled core, in reading order.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place each panel's diagnostic overlay instead of the panel itself, in
            exactly the same positions, so a sequence can be debugged as a sequence.
            `live_text` does not apply: the overlay labels in plain text already.
        fonts: The declared fonts the panels were lettered in, by digest -- what
            :attr:`Book.fonts <scenet.pipeline.Book.fonts>` holds.
        aria: Make the strip a named group of panels, each one image a screen reader
            reads whole, in reading order; its background hidden. `False` writes none of
            it. An overlay is a diagnostic, and never has it.
        embed: The supplied pictures' bytes, by digest -- what
            :attr:`Book.images <scenet.pipeline.Book.images>` holds -- to write into
            the SVG. Left out, each picture is linked by the path its document wrote.
        mono: Draw every value as its grey and ignore its colour, as for a black-and-white
            edition (#244). Every decision was made on the grey, so this draws exactly what
            `palette: mono` would; see :meth:`PanelCore.as_mono <scenet.core.PanelCore.as_mono>`.

    Returns:
        One SVG document holding every panel.

    Raises:
        ValueError: There are no panels, or they are not all read the same way.
    """
    if not panels:
        raise ValueError("a strip needs at least one panel")
    if mono:
        panels = [(name, core.as_mono()) for name, core in panels]
    rtl = reading_direction([core.direction for _, core in panels], "a strip's panels") is (
        Direction.RTL
    )

    tallest = max(core.height for _name, core in panels)
    gutter = tallest * GUTTER_FRACTION
    margin = tallest * MARGIN_FRACTION

    total_width = sum(core.width for _name, core in panels) + gutter * (len(panels) - 1)
    width = total_width + 2 * margin
    height = tallest + 2 * margin

    access = aria and not debug
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" height="{fmt(height)}" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}"{GROUP if access else ""}>',
        *([f"  <title>A strip of {counted(len(panels), 'panel')}.</title>"] if access else []),
        f'  <rect x="0" y="0" width="{fmt(width)}" height="{fmt(height)}" fill="#ffffff"'
        f"{HIDDEN if access else ''}/>",
    ]

    # Read right to left, the first panel's left edge is a panel's width short of the end.
    cursor = width - margin - panels[0][1].width if rtl else margin
    for position, (name, core) in enumerate(panels, start=1):
        # Panels of differing height sit on a common top edge, which is how a tier of
        # unequal panels is conventionally aligned.
        parts.extend(
            placed_panel(
                name,
                core,
                position,
                cursor,
                margin,
                live_text=live_text,
                debug=debug,
                fonts=fonts,
                embed=embed,
                aria=aria,
            )
        )
        if rtl and position < len(panels):
            cursor -= gutter + panels[position][1].width
        else:
            cursor += core.width + gutter

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def placed_panel(
    name: str,
    core: PanelCore,
    position: int,
    x: float,
    y: float,
    *,
    live_text: bool = False,
    debug: bool = False,
    fonts: Mapping[str, FontMetrics] | None = None,
    holes: Sequence[Box] = (),
    aria: bool = True,
    embed: Mapping[str, bytes] | None = None,
) -> list[str]:
    """One panel, rendered on its own and put at `(x, y)` in a larger document.

    Shared by the strip and the page, so both place a panel the same way: clipped to its
    frame, and with every id prefixed by the panel's position in the document -- see the
    module docstring for why position and not name.

    Args:
        name: The panel's name, kept as the group's id.
        core: The compiled panel.
        position: Its one-based position in the document, unique within it.
        x: Where its left edge goes.
        y: Where its top edge goes.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place the panel's diagnostic overlay instead of the panel.
        fonts: The declared fonts the panel was lettered in, by digest.
        holes: Areas cut out of it, in its own units: on a page, the rings of the insets
            set into it, which are drawn over it. Each is a clip of its own, nested inside
            the frame's, so the clips intersect and two rings that touch need no geometry.
        aria: Make the panel's group the image a screen reader reads, named as
            :func:`accessible_name <scenet.emit.svg.accessible_name>` names a panel.
            Never on an overlay.
        embed: The supplied pictures' bytes, by digest, to write into the SVG.

    Returns:
        The lines of SVG, indented for the document's top level.
    """
    prefix = f"p{position}-"
    frame = f"{prefix}frame"
    body = (
        debug_body(core, id_prefix=prefix)
        if debug
        else panel_body(
            core,
            typeface_of(core, fonts=fonts),
            live_text=live_text,
            id_prefix=prefix,
            embed=embed,
        )
    )
    # Clipped to the panel's outline when it has one: a slanted panel's bounding box
    # overlaps its neighbour's, and only the outline is its own.
    shape = (
        f'<polygon points="{" ".join(f"{fmt(px)},{fmt(py)}" for px, py in core.outline)}"/>'
        if core.outline is not None
        else f'<rect x="0" y="0" width="{fmt(core.width)}" height="{fmt(core.height)}"/>'
    )
    whole = f"M0 0 H{fmt(core.width)} V{fmt(core.height)} H0 Z"
    cut = [
        (
            f"{prefix}hole-{number}",
            f"{whole} M{fmt(hole.x)} {fmt(hole.y)} H{fmt(hole.right)} V{fmt(hole.bottom)} "
            f"H{fmt(hole.x)} Z",
        )
        for number, hole in enumerate(holes, start=1)
    ]
    # The panel's group is the image a screen reader reads, named as the panel alone is.
    named, names = accessible_name(core) if aria and not debug else ("", [])
    return [
        f'  <g id={attr("panel-" + name)} transform="translate({fmt(x)} {fmt(y)})"{named}>',
        *names,
        f'  <clipPath id="{frame}">{shape}</clipPath>',
        *(
            f'  <clipPath id="{hole}"><path d="{d}" clip-rule="evenodd"/></clipPath>'
            for hole, d in cut
        ),
        f'  <g clip-path="url(#{frame})">',
        *(f'  <g clip-path="url(#{hole})">' for hole, _ in cut),
        "\n".join(body),
        *("  </g>" for _ in cut),
        "  </g>",
        "  </g>",
    ]
