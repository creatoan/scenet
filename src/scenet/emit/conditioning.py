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

from shapely.geometry import Point, Polygon

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
    """The bounds of some points as `[xmin, ymin, xmax, ymax]` fractions of the panel.

    Clipped to the panel, since what lies outside it is not in the picture.

    Args:
        core: The panel the fractions are of.
        points: What to bound.

    Returns:
        The box, or None when nothing of it is inside the panel.
    """
    xs = [min(max(x, 0.0), core.width) for x, _ in points]
    ys = [min(max(y, 0.0), core.height) for _, y in points]
    if not xs or max(xs) <= min(xs) or max(ys) <= min(ys):
        return None
    return [
        _fraction(min(xs), core.width),
        _fraction(min(ys), core.height),
        _fraction(max(xs), core.width),
        _fraction(max(ys), core.height),
    ]


def _fraction(value: float, extent: float) -> float:
    return round(value / extent, FRACTION_PLACES) + 0.0


def figure_extent(figure: CoreFigure) -> tuple[tuple[float, float], ...]:
    """What a figure a picture draws covers: its body, and its face.

    A contract may declare a body without the head, or no body at all, and the face is
    always there: its bounding square joins whatever body there is.
    """
    face = figure.face_exclusion
    return (
        *figure.body,
        (face.cx - face.r, face.cy - face.r),
        (face.cx + face.r, face.cy + face.r),
    )


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
