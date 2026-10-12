"""Sound effects: letters set as part of the picture, and placed like it.

A sound effect is lettering treated as art. It is set in the display face rather than
the balloon face, on one line, and bent and turned the way letterers bend and turn them --
an arc, a rotation -- as transforms of the glyph outlines Scenet already draws, so no
renderer and no installed font has a say. Then it is placed the way everything else is
placed: by generating candidate positions and scoring them, never at a coordinate.

**What it may not do** is the hard rule every box obeys: cover a face, leave the frame,
lie under an inset. And two effects never overlap. **What it prefers** is to sit near the
actor it comes from, or in the zone it names, and off any figure but its source's.

**What it does to everything else** is cost them. Effects are placed before any balloon or
caption -- they are part of the picture, which lettering is placed over -- and each one's
footprint then joins the emanata as ground a balloon pays to cover and is never forbidden
to. Covering a sound effect deletes what the panel was saying, which is the argument for
emanata too (`docs/explanation/design_decisions.md`).

**They move nobody.** An effect is placed after staging and the camera, from the figures
those produced, and reaches neither.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import MultiPoint, Polygon, box
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.base import BaseGeometry

from scenet.assets.kinematics import ResolvedPuppet
from scenet.errors import SfxPlacementError
from scenet.geom import BBox, Point
from scenet.ir import Face, PlacementZone, SfxEvent, SfxSize
from scenet.solve.text import FontMetrics, Typeface

__all__ = [
    "INK",
    "PAPER",
    "SIZE_FACTORS",
    "EffectShape",
    "PlacedEffect",
    "PlacedGlyph",
    "layout_effect",
    "place_effects",
]

#: How big each size is, as a multiple of the dialogue type size. Of the type, not of the
#: figure, so an effect reads at a long shot as well as at a close-up.
SIZE_FACTORS: dict[SfxSize, float] = {
    SfxSize.SMALL: 1.6,
    SfxSize.MEDIUM: 2.6,
    SfxSize.LARGE: 4.0,
}

#: The outline drawn around every letter, as a fraction of the effect's type size. A solid
#: effect is ink with a paper halo, which reads over light art and dark alike; a hollow
#: one is that outline in ink with nothing inside it.
STROKE_FRACTION = 0.08

#: The two values an effect is drawn in: the stroke colour every balloon uses, and the
#: paper the panel is printed on.
INK = "#111111"
PAPER = "#ffffff"

# Candidates: rings around the source's figure, in multiples of half its diagonal --
# including the figure's own middle, since a BLAM over the gun is ordinary -- and rings
# around the preferred point, in fractions of the panel diagonal.
DIRECTIONS = 16
SOURCE_RINGS = (0.55, 0.9, 1.25)
TARGET_RINGS = (0.08, 0.16)

# Cost weights. A source pulls as hard as a preferred zone pulls a balloon; covering a
# figure that is not the source is mildly disliked -- an effect over a bystander is
# common, but it is not where the sound is -- and covering emanata is disliked as much as
# a balloon dislikes it.
W_SOURCE = 1.4
W_PREFERRED = 1.4
W_COVER = 0.4
W_MARKS = 1.5


@dataclass(frozen=True, slots=True)
class PlacedGlyph:
    """One letter of an effect, where it is drawn.

    Attributes:
        character: The letter.
        origin: Where its baseline starts, in panel units once the effect is placed.
        angle: Its rotation in degrees, clockwise, about `origin`.
    """

    character: str
    origin: Point
    angle: float


@dataclass(frozen=True, slots=True)
class EffectShape:
    """An effect laid out around its own centre, before it is placed.

    Attributes:
        glyphs: Every letter, the origin at the effect's centre.
        footprint: What the letters cover, outline included: a convex polygon.
        font_size: The type size, in panel units.
        stroke_width: The outline's width, in panel units.
        metrics: The face it is set in.
    """

    glyphs: tuple[PlacedGlyph, ...]
    footprint: Polygon
    font_size: float
    stroke_width: float
    metrics: FontMetrics


@dataclass(frozen=True, slots=True)
class PlacedEffect:
    """One effect after placement, before it is reduced to a Core document.

    Attributes:
        id: `s0`, `s1`, ... in script order.
        order: Its number in the panel's one reading order.
        text: The sound, as written.
        source: The actor it comes from, if any.
        font_size: The type size.
        glyphs: Every letter, in panel units.
        zone: The footprint, placed: what balloons paid to avoid.
        fill: What the letters are filled with, or `none`.
        stroke: What they are outlined in.
        stroke_width: The outline's width.
        hollow: Whether it is an open effect, all outline.
    """

    id: str
    order: int
    text: str
    source: str | None
    font_size: float
    glyphs: tuple[PlacedGlyph, ...]
    zone: Polygon
    fill: str
    stroke: str
    stroke_width: float
    hollow: bool


def _rotated(x: float, y: float, degrees: float) -> tuple[float, float]:
    """A point turned clockwise about the origin, in a y-down frame -- as SVG turns it."""
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    return x * cos - y * sin, x * sin + y * cos


def layout_effect(event: SfxEvent, *, dialogue_size: float, typeface: Typeface) -> EffectShape:
    """Set an effect's letters, bend and turn them, and find what they cover.

    The letters are kerned and advanced exactly as any lettering is. An arc puts their
    baselines on a circle whose length is the line's own, so the letters keep their
    spacing as it bends; each is turned to the tangent there. The whole is then centred
    on its own middle and turned by `rotate`.

    Args:
        event: The effect.
        dialogue_size: The panel's dialogue type size, which the effect's is a multiple of.
        typeface: The family whose display face the effect is set in.

    Returns:
        The effect, centred on the origin.

    Example:
        >>> from scenet.ir import SfxEvent
        >>> from scenet.solve.sfx import layout_effect
        >>> from scenet.solve.text import Typeface
        >>> shape = layout_effect(SfxEvent(text="BLAM"), dialogue_size=30, typeface=Typeface())
        >>> [glyph.character for glyph in shape.glyphs]
        ['B', 'L', 'A', 'M']
    """
    metrics = typeface.face(Face.DISPLAY)
    size = dialogue_size * SIZE_FACTORS[event.size]
    text = " ".join(event.text.split())
    last = len(text) - 1
    steps = [
        metrics.step(character, text[index + 1] if index < last else None) * size
        for index, character in enumerate(text)
    ]
    width = sum(steps)
    above, below = metrics.extent
    top, bottom = -above * size, below * size

    radius = width / math.radians(abs(event.arc)) if event.arc else math.inf
    bow = 1.0 if event.arc > 0 else -1.0

    glyphs: list[tuple[str, float, float, float, float]] = []
    corners: list[tuple[float, float]] = []
    cursor = -width / 2
    for character, step in zip(text, steps, strict=True):
        along = cursor + step / 2
        if math.isinf(radius):
            centre_x, centre_y, angle = along, 0.0, 0.0
        else:
            theta = along / radius
            centre_x = radius * math.sin(theta)
            centre_y = bow * radius * (1 - math.cos(theta))
            angle = bow * math.degrees(theta)
        back_x, back_y = _rotated(step / 2, 0.0, angle)
        origin_x, origin_y = centre_x - back_x, centre_y - back_y
        glyphs.append((character, origin_x, origin_y, angle, step))
        for corner_x, corner_y in ((0.0, top), (step, top), (step, bottom), (0.0, bottom)):
            dx, dy = _rotated(corner_x, corner_y, angle)
            corners.append((origin_x + dx, origin_y + dy))
        cursor += step

    stroke = size * STROKE_FRACTION
    hull = MultiPoint(corners).convex_hull
    min_x, min_y, max_x, max_y = hull.bounds
    shift_x, shift_y = -(min_x + max_x) / 2, -(min_y + max_y) / 2

    placed: list[PlacedGlyph] = []
    for character, origin_x, origin_y, angle, _step in glyphs:
        x, y = _rotated(origin_x + shift_x, origin_y + shift_y, event.rotate)
        placed.append(PlacedGlyph(character, Point(x, y), angle + event.rotate))
    footprint = affinity.rotate(
        affinity.translate(hull, shift_x, shift_y), event.rotate, origin=(0, 0)
    ).buffer(stroke / 2, join_style="mitre")
    return EffectShape(
        glyphs=tuple(placed),
        footprint=footprint,
        font_size=size,
        stroke_width=stroke,
        metrics=metrics,
    )


def _source_point(actor: ResolvedPuppet) -> tuple[Point, float]:
    """Where a sound from this actor comes from, and how far around it to look."""
    xs = [point.x for point in actor.hull]
    ys = [point.y for point in actor.hull]
    centre = Point((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    return centre, math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / 2


def _zone_point(zone: PlacementZone, panel: BBox) -> Point:
    across, down = zone.fractions
    return Point(panel.x + panel.width * across, panel.y + panel.height * down)


def _candidates(event: SfxEvent, actors: Mapping[str, ResolvedPuppet], panel: BBox) -> list[Point]:
    """Where an effect's centre is worth trying, in a fixed order.

    Around the source first, then around the point it prefers -- or the panel's middle --
    and finally the middle of every zone, so a crowded panel still has somewhere to look.
    """
    points: list[Point] = []
    diagonal = math.hypot(panel.width, panel.height)
    if event.source is not None:
        centre, reach = _source_point(actors[event.source])
        points.append(centre)
        points.extend(_ring(centre, [reach * factor for factor in SOURCE_RINGS]))
    target = (
        _zone_point(event.prefer, panel)
        if event.prefer is not None
        else _zone_point(PlacementZone.MIDDLE_CENTRE, panel)
    )
    points.append(target)
    points.extend(_ring(target, [diagonal * factor for factor in TARGET_RINGS]))
    points.extend(_zone_point(zone, panel) for zone in PlacementZone)
    return points


def _ring(centre: Point, radii: Sequence[float]) -> list[Point]:
    return [
        Point(
            centre.x + math.cos(-math.pi / 2 + 2 * math.pi * step / DIRECTIONS) * radius,
            centre.y + math.sin(-math.pi / 2 + 2 * math.pi * step / DIRECTIONS) * radius,
        )
        for radius in radii
        for step in range(DIRECTIONS)
    ]


def _cost(
    zone: Polygon,
    event: SfxEvent,
    *,
    actors: Mapping[str, ResolvedPuppet],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    marks: Sequence[BaseGeometry],
) -> float:
    """How poor a position is. Lower is better; legality is decided elsewhere."""
    diagonal = math.hypot(panel.width, panel.height)
    centre = zone.centroid
    cost = 0.0
    if event.source is not None:
        source, _ = _source_point(actors[event.source])
        cost += W_SOURCE * centre.distance(ShapelyPoint(source.x, source.y)) / diagonal
    if event.prefer is not None or event.source is None:
        zone_name = event.prefer or PlacementZone.MIDDLE_CENTRE
        target = _zone_point(zone_name, panel)
        cost += W_PREFERRED * centre.distance(ShapelyPoint(target.x, target.y)) / diagonal
    area = max(zone.area, 1.0)
    for actor_id in sorted(hulls):
        if actor_id != event.source:
            cost += W_COVER * zone.intersection(hulls[actor_id]).area / area
    for shape in marks:
        cost += W_MARKS * zone.intersection(shape).area / area
    return cost


def place_effects(
    events: Sequence[tuple[int, SfxEvent]],
    *,
    actors: Mapping[str, ResolvedPuppet],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    dialogue_size: float,
    typeface: Typeface,
    marks: Sequence[BaseGeometry] = (),
    blocked: Sequence[BBox] = (),
    inside: Polygon | None = None,
) -> tuple[PlacedEffect, ...]:
    """Place every sound effect, in script order, before any balloon is placed.

    Args:
        events: Each effect with its index in the script, which is its reading order.
        actors: Resolved figures, by actor id.
        hulls: Their silhouettes, by actor id.
        panel: The rectangle effects stay inside, margins applied.
        dialogue_size: The dialogue type size, which effect sizes are multiples of.
        typeface: The family whose display face effects are set in.
        marks: Emanata, which effects prefer not to cover.
        blocked: Areas drawn over the panel, such as insets.
        inside: The shape every effect must lie within, for a panel that is not a
            rectangle.

    Returns:
        The effects, placed.

    Raises:
        SfxPlacementError: An effect had no legal position anywhere in the panel.
    """
    frame = box(panel.x, panel.y, panel.right, panel.bottom)
    faces = [
        (ShapelyPoint(actor.face.cx, actor.face.cy), actor.face.r) for actor in actors.values()
    ]
    covers = [box(area.x, area.y, area.right, area.bottom) for area in blocked]

    placed: list[PlacedEffect] = []
    for order, event in events:
        shape = layout_effect(event, dialogue_size=dialogue_size, typeface=typeface)

        def legal(zone: Polygon) -> bool:
            if not frame.contains(zone) or (inside is not None and not inside.contains(zone)):
                return False
            if any(zone.distance(centre) < radius for centre, radius in faces):
                return False
            if any(zone.intersection(area).area > 0 for area in covers):
                return False
            return all(zone.intersection(other.zone).area == 0 for other in placed)

        best: tuple[float, Point, Polygon] | None = None
        for point in _candidates(event, actors, panel):
            zone = affinity.translate(shape.footprint, point.x, point.y)
            if not legal(zone):
                continue
            cost = _cost(zone, event, actors=actors, hulls=hulls, panel=panel, marks=marks)
            if best is None or cost < best[0]:
                best = (cost, point, zone)
        if best is None:
            raise SfxPlacementError(
                f"no legal position for sound effect {order} ({event.text!r}): every "
                "candidate either covered a face, left the panel, lay under an inset or "
                "overlapped another sound effect; make it smaller or shorter"
            )

        _, point, zone = best
        placed.append(
            PlacedEffect(
                id=f"s{len(placed)}",
                order=order,
                text=event.text,
                source=event.source,
                font_size=shape.font_size,
                glyphs=tuple(
                    PlacedGlyph(
                        glyph.character,
                        Point(glyph.origin.x + point.x, glyph.origin.y + point.y),
                        glyph.angle,
                    )
                    for glyph in shape.glyphs
                ),
                zone=zone,
                fill="none" if event.hollow else INK,
                stroke=INK if event.hollow else PAPER,
                stroke_width=shape.stroke_width,
                hollow=event.hollow,
            )
        )
    return tuple(placed)
