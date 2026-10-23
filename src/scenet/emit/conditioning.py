"""What the exports for image models share: the canvas, fractions of it, and the JSON (#72).

The exports hand a panel's staging to whatever a reader feeds it to -- ControlNet, GLIGEN, a
tool of their own. **No model runs in Scenet**: each export is another emitter, reading Panel
Core and nothing else, as deterministic and as explicable as the SVG.

Everything is said on the panel's own canvas: one pixel per panel unit, rounded up to whole
pixels. A box is said as fractions of the panel, which is what box-conditioned models take.
"""

import json
import math
from collections.abc import Iterable, Mapping

from shapely.geometry import MultiPoint, Point, Polygon, box

from scenet.core import CoreFigure, PanelCore

#: Decimal places of a fraction of the panel: a tenth of a unit on a panel 1000 wide.
FRACTION_PLACES = 4


def canvas(core: PanelCore) -> tuple[int, int]:
    """The panel as an image: one pixel per panel unit, rounded up to whole pixels.

    Example:
        >>> from scenet import compile_source
        >>> canvas(
        ...     compile_source("{panel: {size: [600.5, 400]}, cast: {a: {reference: alice}}}").core
        ... )
        (601, 400)
    """
    return math.ceil(core.width), math.ceil(core.height)


def to_json(payload: Mapping[str, object]) -> str:
    """Write a document exactly as Panel Core is written: sorted keys, two spaces, LF."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def fraction_box(core: PanelCore, points: Iterable[tuple[float, float]]) -> list[float] | None:
    """The bounds of what the panel draws of a shape, as `[xmin, ymin, xmax, ymax]` fractions.

    The shape is the convex hull of the points -- a hull, a body, a box -- cut to what the
    panel draws: its frame, or a slanted tier's outline. What lies outside is not in the
    picture, so a body wider below the frame is bounded where the frame cuts it.

    Args:
        core: The panel the fractions are of.
        points: What to bound.

    Returns:
        The box, or None when nothing of it with any area is inside the panel.
    """
    drawn = (
        Polygon(core.outline)
        if core.outline is not None
        else box(0.0, 0.0, core.width, core.height)
    )
    inside = MultiPoint(list(points)).convex_hull.intersection(drawn)
    if inside.area <= 0.0:
        return None
    xmin, ymin, xmax, ymax = inside.bounds
    return [
        _fraction(xmin, core.width),
        _fraction(ymin, core.height),
        _fraction(xmax, core.width),
        _fraction(ymax, core.height),
    ]


def _fraction(value: float, extent: float) -> float:
    return round(value / extent, FRACTION_PLACES) + 0.0


def figure_extent(figure: CoreFigure) -> tuple[tuple[float, float], ...]:
    """What a figure a picture draws covers: its body, and its face.

    A contract may declare a body without the head, or no body at all, and the face is
    always there: its bounding square joins whatever body there is.
    """
    face = figure.face_exclusion
    return (*figure.body, *corners(face.cx - face.r, face.cy - face.r, 2 * face.r, 2 * face.r))


def corners(x: float, y: float, width: float, height: float) -> tuple[tuple[float, float], ...]:
    """A rectangle's four corners, clockwise from the top left.

    A shape to clip, where two corners would be a line.
    """
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def drawn_at(core: PanelCore, point: tuple[float, float]) -> bool:
    """Whether a point is inside what the panel draws: the frame, edge included.

    A panel in a slanted tier is drawn clipped to its `outline`, so outside the outline is
    outside the panel. An inset over it is not: the panel's art is drawn under it as usual.
    """
    x, y = point
    if not (0.0 <= x <= core.width and 0.0 <= y <= core.height):
        return False
    return core.outline is None or Polygon(core.outline).covers(Point(x, y))


__all__ = ["FRACTION_PLACES", "canvas", "drawn_at", "figure_extent", "fraction_box", "to_json"]
