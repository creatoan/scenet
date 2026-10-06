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

from scenet.core import PanelCore
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import attr, fmt, render

# Space between panels, as a fraction of the tallest panel.
GUTTER_FRACTION = 0.04

MARGIN_FRACTION = 0.03


def render_strip(
    panels: list[tuple[str, PanelCore]], *, live_text: bool = False, debug: bool = False
) -> str:
    """Lay panels left to right in reading order.

    Each panel is rendered independently and then placed, rather than being
    re-solved: a panel's composition must not depend on what sits beside it, or the
    same source would compile differently in isolation.

    Args:
        panels: Panel name and compiled core, in reading order.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        debug: Place each panel's diagnostic overlay instead of the panel itself, in
            exactly the same positions, so a sequence can be debugged as a sequence.
            `live_text` does not apply: the overlay labels in plain text already.

    Returns:
        One SVG document holding every panel.
    """
    if not panels:
        raise ValueError("a strip needs at least one panel")

    tallest = max(core.height for _name, core in panels)
    gutter = tallest * GUTTER_FRACTION
    margin = tallest * MARGIN_FRACTION

    total_width = sum(core.width for _name, core in panels) + gutter * (len(panels) - 1)
    width = total_width + 2 * margin
    height = tallest + 2 * margin

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" height="{fmt(height)}" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}">',
        f'  <rect x="0" y="0" width="{fmt(width)}" height="{fmt(height)}" fill="#ffffff"/>',
    ]

    cursor = margin
    for position, (name, core) in enumerate(panels, start=1):
        prefix = f"p{position}-"
        frame = f"{prefix}frame"
        # Panels of differing height sit on a common top edge, which is how a tier of
        # unequal panels is conventionally aligned.
        inner = (
            render_debug(core, id_prefix=prefix)
            if debug
            else render(core, live_text=live_text, id_prefix=prefix)
        )
        body = inner.split("\n", 2)[2].rsplit("</svg>", 1)[0]
        parts.append(
            f'  <g id={attr("panel-" + name)} transform="translate({fmt(cursor)} {fmt(margin)})">'
        )
        parts.append(
            f'  <clipPath id="{frame}"><rect x="0" y="0" width="{fmt(core.width)}" '
            f'height="{fmt(core.height)}"/></clipPath>'
        )
        parts.append(f'  <g clip-path="url(#{frame})">')
        parts.append(body.rstrip())
        parts.append("  </g>")
        parts.append("  </g>")
        cursor += core.width + gutter

    parts.append("</svg>")
    return "\n".join(parts) + "\n"
