"""What the exports for image models share: the canvas, fractions of it, and the JSON (#72).

The exports hand a panel's staging to whatever a reader feeds it to -- ControlNet, GLIGEN, a
tool of their own. **No model runs in Scenet**: each export is another emitter, reading Panel
Core and nothing else, as deterministic and as explicable as the SVG.

Everything is said on the panel's own canvas: one pixel per panel unit, rounded up to whole
pixels. A box is said as fractions of the panel, which is what box-conditioned models take.
"""

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from shapely.geometry import MultiPoint, Point, Polygon, box

from scenet.core import CoreFigure, CoreMass, Disc, PanelCore
from scenet.emit.svg import attr, fmt, in_painters_order
from scenet.ir import MassKind

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


@dataclass(frozen=True, slots=True)
class Region:
    """One region a map export fills: what the panel's geometric contract names.

    An actor's hull -- where staging put it, not the mannequin Scenet draws it as, so a
    model is told where a character is and the pose how it stands -- a mass's polygon, or
    a figure's body and face as its picture's contract declares them.

    Attributes:
        id: The id the panel's SVG gives it: `actor-alice`, `mass-m0`, `figure-ana`.
        polygon: The outline. Empty for a figure whose contract declares no body.
        disc: A figure's face, which joins its body. None for anything else.
        depth: Painter's order, as Panel Core records it. None for a figure, which has
            none of its own.
        kind: What a mass is made of, which the depth map reads: the sky is at infinity,
            and a ground, floor, water or ceiling recedes. None for an actor or a figure.
        who: The character it is, for an actor or a figure: the actor's id, or the part a
            figure plays -- or, uncast, its own name. None for a mass.
    """

    id: str
    polygon: tuple[tuple[float, float], ...]
    disc: Disc | None = None
    depth: int | None = None
    kind: MassKind | None = None
    who: str | None = None

    @property
    def sky(self) -> bool:
        """Whether it is sky, which is at infinity whatever plane it was filed under."""
        return self.kind is MassKind.SKY


@dataclass(frozen=True, slots=True)
class Ramp:
    """A fill that runs straight down or up the panel, from one colour to another (#227).

    A linear gradient in the panel's own units with no slant, so everything at one height is
    one colour; past either end, the colour is that end's. Its paint names `start` as the
    fallback: a renderer that cannot resolve the gradient draws `start`, and so does a tool
    reading a region's colour from its `fill`.

    Attributes:
        start: The colour at `begins`.
        end: The colour at `ends`.
        begins: Where it begins, in panel units down from the top edge.
        ends: Where it ends: below `begins` for a ramp that runs down, above it for one that
            runs up.
    """

    start: str
    end: str
    begins: float
    ends: float


def regions(core: PanelCore) -> list[Region]:
    """Every region of the panel, in the order the panel draws them: back to front.

    Masses and actors in the panel's own painter's order, then the figures a picture draws,
    which are over the picture and under nothing, in the order their contract declares them.
    Marks and sound effects are none of them: they are drawn around a figure, not part of
    it.
    """
    drawn = [
        Region(
            id=f"mass-{item.id}",
            polygon=item.polygon,
            depth=item.depth,
            kind=item.kind,
        )
        if isinstance(item, CoreMass)
        else Region(id=f"actor-{item.id}", polygon=item.hull, depth=item.depth, who=item.id)
        for item in in_painters_order(core)
    ]
    drawn += [
        Region(
            id=f"figure-{figure.figure}",
            polygon=figure.body,
            disc=figure.face_exclusion,
            who=figure.actor or figure.figure,
        )
        for figure in core.figures
    ]
    return drawn


def _points(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


def _shape(region: Region, fill: str) -> str:
    if region.disc is None:
        return f'  <polygon id={attr(region.id)} points="{_points(region.polygon)}" fill="{fill}"/>'
    body = f'<polygon points="{_points(region.polygon)}"/>' if region.polygon else ""
    face = region.disc
    return (
        f'  <g id={attr(region.id)} fill="{fill}">{body}'
        f'<circle cx="{fmt(face.cx)}" cy="{fmt(face.cy)}" r="{fmt(face.r)}"/></g>'
    )


def _gradient(ramp_id: str, ramp: Ramp) -> str:
    return (
        f'  <linearGradient id="{ramp_id}" gradientUnits="userSpaceOnUse" '
        f'x1="0" y1="{fmt(ramp.begins)}" x2="0" y2="{fmt(ramp.ends)}">'
        f'<stop offset="0" stop-color="{ramp.start}"/>'
        f'<stop offset="1" stop-color="{ramp.end}"/></linearGradient>'
    )


def flat_map(core: PanelCore, fills: Sequence[tuple[Region, str | Ramp]]) -> str:
    """An SVG of flat fills and ramps on black, on the panel's canvas, clipped as the panel is.

    Black is nothing: the paper, the sky, a supplied picture whose content the compiler
    never saw. A panel in a slanted tier is clipped to its outline; an inset over it is not
    there, since the panel's art is drawn under it as usual.

    Edges are crisp, `shape-rendering="crispEdges"`: an antialiased edge would blend two
    regions into a colour, or a grey, that belongs to neither. A ramp's greys are all its own
    region's. The map is the pose's and the boxes' canvas -- the panel rounded up to whole
    pixels, one unit to a pixel -- so every export is on one pixel grid. Nothing is
    stretched: what lies past the panel's own edge, under a pixel wide, is black, which is
    nothing.

    Each ramp is a gradient defined before any shape and named by the position of its
    region in drawing order, `ramp-2`, never by the region's id: an id is whatever a Core
    said, and while attribute escaping keeps one inside its quotes, nothing would keep it
    inside `url(...)`.

    Args:
        core: The panel.
        fills: Each region and what it is filled with, in drawing order.

    Returns:
        The document.
    """
    width, height = canvas(core)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges">',
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#000000"/>',
    ]
    shapes: list[str] = []
    for index, (region, fill) in enumerate(fills):
        if isinstance(fill, Ramp):
            lines.append(_gradient(f"ramp-{index}", fill))
            shapes.append(_shape(region, f"url(#ramp-{index}) {fill.start}"))
        else:
            shapes.append(_shape(region, fill))
    if core.outline is not None:
        lines.append(
            f'  <clipPath id="outline"><polygon points="{_points(core.outline)}"/></clipPath>'
        )
        lines.append('  <g clip-path="url(#outline)">')
    lines.extend(shapes)
    if core.outline is not None:
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


__all__ = [
    "FRACTION_PLACES",
    "Ramp",
    "Region",
    "canvas",
    "drawn_at",
    "figure_extent",
    "flat_map",
    "fraction_box",
    "regions",
    "to_json",
]
