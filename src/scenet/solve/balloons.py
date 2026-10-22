"""Placing everything in a panel that carries words: balloons, captions, and tails.

Placement is a scored search over candidate positions rather than a sweep of a cost
grid. Balloons belong in a small number of sensible places relative to their speaker
-- around the head, or tucked into a corner -- so generating those directly is both
cheaper than scanning cells and produces more natural results. This is the approach
used in the cartographic label-placement literature, which is the same problem.

The constraint that naive implementations miss is **reading order**. A box may never
sit above-and-left of the one before it in the script -- above-and-right, in a panel read
right to left -- because that makes the panel read in the wrong order. That is a
correctness bug in a comic, not a cosmetic one, so it is enforced as a hard filter rather
than scored.

**Read right to left, the lettering is the mirror image, and nothing else is** (#68). Every
rule and tiebreak reading decides -- the order itself, which candidate is tried first, where
an unplaced box would rather start -- is mirrored, so a mirrored panel read right to left is
lettered as the mirror of the original. The scene is not mirrored: the figures, their gaze,
sound effects and every tail stay as staged.

Captions go through this machinery rather than a parallel one. The placement
principles the lettering references give for floating text -- keep off the important
figures, preserve the space of the art, keep the reading order flowing -- are the ones
already implemented here. What differs is where a caption *wants* to be: a balloon
mildly dislikes hugging the panel edge, and a caption is looking for exactly that.

So the two are placed in **one pass in script order**, sharing the list of boxes
already down. Placing every caption first would be simpler and wrong: a caption
written after the dialogue would then impose reading order on balloons that precede
it.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from shapely import get_coordinates
from shapely.geometry import LineString, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from scenet.errors import BalloonPlacementError
from scenet.geom import BBox, Circle, Point, segment_intersects_circle
from scenet.ir import (
    BalloonKind,
    CaptionEvent,
    CaptionKind,
    CaptionTone,
    Direction,
    Face,
    PlacementZone,
    Plane,
    SayEvent,
    ScriptEvent,
    SfxEvent,
    Side,
    TimeOfDay,
    TypeSize,
)
from scenet.solve.backdrop import LADDER, ResolvedBackdrop, contrast_ratio
from scenet.solve.sfx import PlacedEffect, place_effects
from scenet.solve.speakers import NOBODY, Bystanders, Speaker
from scenet.solve.text import (
    PADDING_FACTOR,
    FontMetrics,
    TextBlock,
    Typeface,
    balloon_size,
    layout_text,
    styled,
)

# Candidate ring around the speaker's head.
RING_DIRECTIONS = 16
RING_RADII = (1.15, 1.5, 2.0)

# Cost weights. Tuned together; changing one in isolation will not do what you expect.
W_OCCLUSION = 1.0  # per unit of actor silhouette covered, normalised by balloon area
W_MOUTH_DISTANCE = 0.9  # keeps a balloon near whoever is speaking
W_PREFERRED_ZONE = 1.4  # honours an explicit `prefer:` hint
W_GAZE_BLOCKING = 0.7  # do not stand in front of what a character is looking at
W_EDGE = 0.25  # mild dislike of hugging the panel edge

# A backdrop mass is *not* an exclusion. Balloons sit over backgrounds routinely; that
# is what a background is for. So covering one is a soft cost, and a mild one -- an
# order of magnitude below covering a face, which is forbidden outright.
W_MASS_OCCLUSION = 0.5

# What covering a mass costs, by how near it is. Empty sky is nearly free; a foreground
# silhouette is the one thing in a backdrop a balloon should genuinely stay off, because
# it reads as an object in the room rather than as scenery.
PLANE_OCCLUSION_WEIGHT: dict[Plane, float] = {
    Plane.FOREGROUND: 1.0,
    Plane.NEAR: 0.55,
    Plane.MID: 0.3,
    Plane.FAR: 0.12,
}

# Emanata -- plewds, grawlixes and the rest -- are drawn outside the head, where balloons
# go. Covering one is a soft cost rather than an exclusion, so a crowded panel still
# compiles; but it is weighted above covering a body. A balloon over a shoulder hides a
# shoulder, while one over a plewd deletes what the panel was saying about the
# character. There is no forgiveness for the speaker either: a balloon resting on its
# own speaker's sweat hides the sweat just the same.
W_EMANATA_OCCLUSION = 1.5

# Tolerance when comparing balloon positions for reading order, in panel units.
READING_EPSILON = 2.0

# Balloon text size as a fraction of panel height.
FONT_SIZE_FRACTION = 0.035

# How far along a gaze direction the character is considered to be looking.
GAZE_REACH_FACTOR = 3.0

# Caption lettering runs slightly smaller than dialogue: a caption is the panel's own
# voice rather than someone speaking, and setting it at dialogue size makes it compete
# with the balloons instead of framing them.
CAPTION_FONT_SIZE_FRACTION = 0.030

# A caption box holds its text more tightly than a balloon does. A balloon's padding is
# generous because the outline is a curve pulling away from the text at the corners; a
# rectangle does not, so the same padding would look slack.
CAPTION_PADDING_FACTOR = 0.42

#: Small lettering against the panel's dialogue size: a step down a letterer would make
#: by eye, as the caption size is one. The balloon keeps the padding the normal size
#: would have, which is what makes small type read as muttered rather than as a
#: smaller balloon.
SMALL_TYPE_FRACTION = 0.75

# How strongly a caption is drawn to the panel edge. The opposite sign to `W_EDGE`:
# tucking into a corner is where a caption belongs, not a compromise it settles for.
W_CAPTION_EDGE = 1.1

#: Where a box with no zone of its own would rather start: where reading starts. A locale
#: caption sits there by convention, and an off-panel voice with no side named is heard
#: from there. A zone the author writes is a place on the panel, and does not follow.
READING_STARTS: dict[Direction, PlacementZone] = {
    Direction.LTR: PlacementZone.TOP_LEFT,
    Direction.RTL: PlacementZone.TOP_RIGHT,
}

#: Each horizontal third of the panel and its mirror, for laying candidates out the other
#: way round.
_MIRRORED = {"left": "right", "center": "center", "right": "left"}

# Quotation marks for a `spoken` caption. Applied here rather than in the emitter --
# characters added after measurement would not fit the box drawn for them.
OPENING_QUOTE = "“"
CLOSING_QUOTE = "”"

# -- caption tones ------------------------------------------------------------------
#
# What each tone fills its box with. Two of the three are rungs of the backdrop's own
# value ladder, taken by index rather than restated as literals: one hardcoded ladder
# feeds both palettes, which is what stops lettering and backdrop drifting apart as
# either is tuned. `day` is the row they come from because it is the ladder at its
# widest, so three tones taken from it span the most ground.
#
# `paper` is not on the ladder and should not be: it is the paper the panel is printed
# on, the same white the panel ground and every balloon already use.
CAPTION_TONES: dict[CaptionTone, str] = {
    CaptionTone.PAPER: "#ffffff",
    CaptionTone.PALE: LADDER[TimeOfDay.DAY][3],
    CaptionTone.INK: LADDER[TimeOfDay.DAY][0],
}

#: What lettering is drawn in, and its opposite. `CAPTION_INK` is the emitter's stroke
#: colour, restated here because the choice between the two is made in the solver.
CAPTION_INK = "#111111"
CAPTION_PAPER = "#ffffff"

#: The floor a caption's own lettering must clear against its fill: WCAG AA for body
#: text. This is the contrast a reader actually gets, because the box is opaque and the
#: text sits on the fill whatever is behind it. `letter_tone` is what holds it, and
#: `tests/test_setting.py` is what proves every tone in the palette does.
LETTERING_FLOOR = 4.5

#: The floor at which a box separates from the plane behind it: WCAG AA for large text,
#: which is the right comparison for a filled rectangle rather than for type.
#:
#: **Not every tone clears this on every rung, and none is required to.** White on a
#: noon sky is 1.16:1, which is the whole reason `tone` exists. What the palette owes
#: the author is an escape from every background the compiler can produce -- at least
#: one tone above this floor for every rung of every row -- and that is what is tested.
SEPARATION_FLOOR = 3.0


@dataclass(frozen=True, slots=True)
class TailRoute:
    """The pointer from balloon to mouth.

    A straight tail is correct almost always. `control` is set only when the direct
    route was obstructed and the tail had to bend around something.
    """

    start: Point
    end: Point
    control: Point | None = None

    @property
    def is_curved(self) -> bool:
        """Whether this tail had to bend around a face.

        Reported in :attr:`CompileResult.notes <scenet.pipeline.CompileResult.notes>`, since
        a curved tail is a sign the panel is crowded enough to be worth a second look.
        """
        return self.control is not None


@dataclass(frozen=True, slots=True)
class PlacedBalloon:
    """One balloon after placement, before it is reduced to a Core document.

    Attributes:
        id: Stable identifier, `b0`, `b1`, ... in script order.
        speaker: Actor id of whoever is talking.
        order: Position in reading order, counting from zero.
        kind: Which sort of balloon to draw.
        box: Where it ended up.
        block: The text, already broken into lines and measured.
        tail: The route from balloon to mouth -- or, for a speaker off panel, to the
            frame on their side.
        off_panel: The side of the frame an off-panel speaker is on, as resolved, or
            `None` for one who is drawn.
    """

    id: str
    speaker: str
    order: int
    kind: BalloonKind
    box: BBox
    block: TextBlock
    tail: TailRoute
    off_panel: Side | None = None


@dataclass(frozen=True, slots=True)
class PlacedCaption:
    """One caption after placement, before it is reduced to a Core document.

    Attributes:
        id: Stable identifier, `c0`, `c1`, ... in the order the captions appear.
        order: Position in the panel's reading order, which captions share with
            balloons -- so a caption between two lines of dialogue takes the number
            between theirs.
        kind: What the box is doing, which decides how it is set.
        box: Where it ended up.
        block: The text, already quoted where the kind calls for it, broken into lines
            and measured against the face it will be drawn in.
        fill: The value the box is filled with, resolved from the declared tone.
        ink: The value its lettering is drawn in, chosen against `fill` so the text
            reads on the box it sits in.
        speaker: Who is talking, for a `spoken` caption. They are off panel, so this
            is not an actor id and resolves to nobody in the cast.

    There is no tail, which is the reason this is not a fifth `BalloonKind`.
    """

    id: str
    order: int
    kind: CaptionKind
    box: BBox
    block: TextBlock
    fill: str = CAPTION_TONES[CaptionTone.PAPER]
    ink: str = CAPTION_INK
    speaker: str | None = None


@dataclass(frozen=True, slots=True)
class ScriptLayout:
    """Everything in a panel that carries words, placed.

    Separate tuples rather than one merged sequence: they reduce to different Core
    types, and the thing that orders them -- `order` -- is on each.
    """

    captions: tuple[PlacedCaption, ...] = ()
    balloons: tuple[PlacedBalloon, ...] = ()
    effects: tuple[PlacedEffect, ...] = ()


def _hull_polygon(actor: Speaker) -> Polygon:
    return Polygon([(point.x, point.y) for point in actor.body])


def _candidate_positions(
    speaker: Speaker,
    size: tuple[float, float],
    panel: BBox,
    direction: Direction = Direction.LTR,
) -> list[BBox]:
    """Positions worth evaluating for a balloon of this size.

    A ring around the speaker's head, plus the four panel corners. The corners matter
    because a crowded panel often has room nowhere else, and a corner balloon with a
    long tail is a perfectly ordinary comics solution.

    The first candidate wins a tie, so their order is a tiebreak, and read right to left
    it is mirrored: candidate *i* is the mirror of candidate *i* read left to right.
    """
    width, height = size
    head = speaker.face
    reach = head.r + math.hypot(width, height) / 2
    rtl = direction is Direction.RTL
    candidates: list[BBox] = []

    for step in range(RING_DIRECTIONS):
        # Start at straight up and go clockwise -- anticlockwise, read right to left;
        # balloons above the speaker are the commonest and should be tried first so that
        # ties resolve upward.
        angle = -math.pi / 2 + 2 * math.pi * step / RING_DIRECTIONS
        for factor in RING_RADII:
            distance = reach * factor
            across = math.cos(angle) * distance
            centre_x = head.cx - across if rtl else head.cx + across
            centre_y = head.cy + math.sin(angle) * distance
            candidates.append(BBox(centre_x - width / 2, centre_y - height / 2, width, height))

    inset = min(panel.width, panel.height) * 0.02
    near, far = panel.x + inset, panel.right - inset - width
    first, second = (far, near) if rtl else (near, far)
    for corner_x, corner_y in (
        (first, panel.y + inset),
        (second, panel.y + inset),
        (first, panel.bottom - inset - height),
        (second, panel.bottom - inset - height),
    ):
        candidates.append(BBox(corner_x, corner_y, width, height))

    return candidates


def _caption_positions(
    size: tuple[float, float], panel: BBox, direction: Direction = Direction.LTR
) -> list[BBox]:
    """Positions worth evaluating for a caption of this size.

    One per :class:`PlacementZone <scenet.ir.PlacementZone>`, with the outer zones
    snapped flat against the panel edge rather than floated at the zone's centre.
    Derived from the enum rather than hand-listed, so a zone that becomes expressible
    in the language is a zone a caption can actually reach. Read right to left, each
    zone's place is tried in its mirror's turn, as the balloons' candidates are.
    """
    width, height = size
    inset = min(panel.width, panel.height) * 0.02
    across = {
        "left": panel.x + inset,
        "center": panel.x + (panel.width - width) / 2,
        "right": panel.right - inset - width,
    }
    down = {
        "top": panel.y + inset,
        "middle": panel.y + (panel.height - height) / 2,
        "bottom": panel.bottom - inset - height,
    }
    candidates: list[BBox] = []
    for zone in PlacementZone:
        vertical, horizontal = zone.value.split("_")
        if direction is Direction.RTL:
            horizontal = _MIRRORED[horizontal]
        candidates.append(BBox(across[horizontal], down[vertical], width, height))
    return candidates


def _blocks_gaze(candidate: BBox, actor: Speaker, reach: float) -> bool:
    """Whether a balloon stands in the line of sight.

    Kress and van Leeuwen's "vectors": a character's gaze is a real compositional line
    that carries the reader's eye. Covering it reads as an obstruction. A figure a
    picture draws declares no gaze, so it has none to block.
    """
    if actor.gaze.length == 0:
        return False
    origin = actor.eyes
    if origin is None:
        return False
    end = origin.translated(actor.gaze.dx * reach, actor.gaze.dy * reach)
    return _segment_hits_box(origin, end, candidate)


def _segment_hits_box(start: Point, end: Point, target: BBox) -> bool:
    """Sampled segment-box test.

    Sampling rather than exact clipping: this feeds a soft cost term, the segment is
    short, and an exact Liang-Barsky implementation would be more code than the
    approximation is worth.
    """
    samples = 12
    for step in range(samples + 1):
        t = step / samples
        x = start.x + (end.x - start.x) * t
        y = start.y + (end.y - start.y) * t
        if target.x <= x <= target.right and target.y <= y <= target.bottom:
            return True
    return False


def _reading_order_allows(
    placed: Sequence[BBox], candidate: BBox, direction: Direction = Direction.LTR
) -> bool:
    """Whether `candidate` may be read after everything in `placed`.

    Read left to right, top to bottom, a balloon may sit below an earlier one, or to its
    right, but never both above *and* left of it. Read right to left, as manga are, it is
    the mirror: below, or to its left, but never above and right.

    Checked against **every** predecessor rather than only the immediately preceding
    balloon. The relation is not transitive: with balloons 0, 1, 2, it is entirely
    possible for 2 to be legal after 1 while sitting above and left of 0, and a reader
    following the page would then take them in the wrong order.
    """
    if direction is Direction.RTL:
        return all(
            candidate.y >= previous.y - READING_EPSILON
            or candidate.right <= previous.x + READING_EPSILON
            for previous in placed
        )
    return all(
        candidate.y >= previous.y - READING_EPSILON
        or candidate.x >= previous.right - READING_EPSILON
        for previous in placed
    )


@dataclass(frozen=True, slots=True)
class _Limits:
    """Where lettering may not go, beyond the panel's margined rectangle.

    Attributes:
        blocked: Areas drawn over the panel, such as insets.
        inside: The shape a box must lie within, for a panel that is not a rectangle.
        direction: Which way the panel is read, which every box is placed in order for.
    """

    blocked: tuple[BBox, ...] = ()
    inside: Polygon | None = None
    direction: Direction = Direction.LTR

    def allow(self, candidate: BBox) -> bool:
        """Whether a box clears every blocked area and lies inside the shape."""
        if any(candidate.overlap_area(area) > 0 for area in self.blocked):
            return False
        return self.inside is None or self.inside.contains(
            box(candidate.x, candidate.y, candidate.right, candidate.bottom)
        )


_NO_LIMITS = _Limits()


def _is_legal(
    candidate: BBox,
    actors: Mapping[str, Speaker],
    panel: BBox,
    placed: list[BBox],
    limits: _Limits = _NO_LIMITS,
    *,
    bystanders: Bystanders = NOBODY,
) -> bool:
    """The hard rules, which apply to anything carrying words.

    A box over a face is never acceptable whatever else it has going for it -- a cast
    member's or a bystander's -- a box outside the panel is not a box, two overlapping
    boxes make both unreadable, and a box under something drawn over the panel -- an
    inset -- cannot be read at all, and nor can one cut off by a slanted edge.
    """
    if not panel.contains(candidate):
        return False
    if any(candidate.intersects_circle(actor.face) for actor in actors.values()):
        return False
    if any(candidate.intersects_circle(face) for face in bystanders.faces):
        return False
    if not limits.allow(candidate):
        return False
    return all(candidate.overlap_area(existing) == 0 for existing in placed)


def _occlusion_cost(
    candidate: BBox,
    hulls: Mapping[str, Polygon],
    forgive: str | None,
    bystanders: Sequence[Polygon] = (),
) -> float:
    """How much silhouette this box covers, normalised by its own area.

    `forgive` names an actor whose silhouette is half-weighted -- a balloon resting on
    its own speaker's shoulder reads naturally in a way that covering a bystander does
    not. A caption has no speaker, so it forgives nobody. `bystanders` are the bodies of
    figures a picture draws and nobody cast: nobody speaks from them, so covering them is
    never forgiven.
    """
    area = max(candidate.area, 1.0)
    shape = box(candidate.x, candidate.y, candidate.right, candidate.bottom)
    cost = 0.0
    for actor_id, hull in hulls.items():
        overlap = shape.intersection(hull).area
        if overlap:
            weight = 0.5 if actor_id == forgive else 1.0
            cost += W_OCCLUSION * weight * overlap / area
    for body in bystanders:
        overlap = shape.intersection(body).area
        if overlap:
            cost += W_OCCLUSION * overlap / area
    return cost


def _mass_polygons(backdrop: ResolvedBackdrop | None) -> list[tuple[Polygon, float]]:
    """The backdrop as weighted shapes, built once per panel rather than per candidate.

    Returns:
        Each mass as a `shapely` polygon paired with what covering it costs.
    """
    if backdrop is None:
        return []
    return [
        (Polygon([(point.x, point.y) for point in polygon]), PLANE_OCCLUSION_WEIGHT[plane])
        for polygon, plane in backdrop.occluders()
    ]


def _mass_cost(candidate: BBox, masses: Sequence[tuple[Polygon, float]]) -> float:
    """How much backdrop this box covers, weighted by how near that backdrop is.

    The counterpart of `_occlusion_cost` for scenery. It never makes a position
    illegal -- a balloon over a sky is not a fault, it is the ordinary case -- so this
    only ever nudges a choice between candidates that are all legal.
    """
    if not masses:
        return 0.0
    area = max(candidate.area, 1.0)
    shape = box(candidate.x, candidate.y, candidate.right, candidate.bottom)
    cost = 0.0
    for polygon, weight in masses:
        overlap = shape.intersection(polygon).area
        if overlap:
            cost += W_MASS_OCCLUSION * weight * overlap / area
    return cost


def _emanata_shapes(zones: Mapping[str, Sequence[Sequence[Point]]]) -> list[BaseGeometry]:
    """Each actor's emanata as one shape, built once per panel rather than per candidate.

    The zones of one actor are merged first, so a box over the place where an actor's
    plewds and squeans overlap pays for that ground once rather than twice. Sorted by
    actor id, because summing in a different order can change the last bit of a float.
    """
    shapes: list[BaseGeometry] = []
    for actor_id in sorted(zones):
        polygons = [Polygon([(point.x, point.y) for point in zone]) for zone in zones[actor_id]]
        if polygons:
            shapes.append(unary_union(polygons))
    return shapes


def _keep_out_shape(regions: Sequence[Sequence[Point]]) -> BaseGeometry:
    """A picture's keep-out regions as one shape, so ground two of them share is paid once.

    Built once per panel. Each region is a simple polygon -- the artwork contract refuses
    any other -- in panel units.
    """
    return unary_union([Polygon([(point.x, point.y) for point in region]) for region in regions])


def _emanata_cost(candidate: BBox, shapes: Sequence[BaseGeometry]) -> float:
    """How much of anyone's emanata this box covers, normalised by its own area.

    Normalised exactly as `_occlusion_cost` is, so the two weights mean the same kind
    of thing. With no marks in the panel there are no shapes and the cost is exactly
    zero, which is what keeps every panel without marks laid out as it was before they
    existed.
    """
    if not shapes:
        return 0.0
    area = max(candidate.area, 1.0)
    shape = box(candidate.x, candidate.y, candidate.right, candidate.bottom)
    cost = 0.0
    for zone in shapes:
        overlap = shape.intersection(zone).area
        if overlap:
            cost += W_EMANATA_OCCLUSION * overlap / area
    return cost


def _edge_slack(candidate: BBox, panel: BBox) -> float:
    """Distance from the box to the nearest panel edge."""
    return min(
        candidate.x - panel.x,
        candidate.y - panel.y,
        panel.right - candidate.right,
        panel.bottom - candidate.bottom,
    )


def _score(
    candidate: BBox,
    *,
    speaker: Speaker,
    speaker_id: str,
    actors: Mapping[str, Speaker],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    prefer: PlacementZone | None,
    placed: list[BBox],
    masses: Sequence[tuple[Polygon, float]],
    emanata: Sequence[BaseGeometry] = (),
    limits: _Limits = _NO_LIMITS,
    bystanders: Bystanders = NOBODY,
) -> float:
    """Cost of putting a balloon here. Lower is better; infinity means illegal.

    `speaker_id` is the actor id the cast and `hulls` are keyed by -- never the puppet's
    name, which is another namespace: `ALICE: {reference: alice}` is spoken by `ALICE`.
    """
    if not _is_legal(candidate, actors, panel, placed, limits, bystanders=bystanders):
        return math.inf

    cost = _occlusion_cost(candidate, hulls, speaker_id, bystanders.bodies) + _mass_cost(
        candidate, masses
    )
    cost += _emanata_cost(candidate, emanata)

    diagonal = math.hypot(panel.width, panel.height)
    cost += W_MOUTH_DISTANCE * (candidate.centre.distance_to(speaker.mouth) / diagonal)

    if prefer is not None:
        across, down = prefer.fractions
        target = Point(panel.x + panel.width * across, panel.y + panel.height * down)
        cost += W_PREFERRED_ZONE * (candidate.centre.distance_to(target) / diagonal)

    reach = speaker.face.r * GAZE_REACH_FACTOR
    for actor in actors.values():
        if _blocks_gaze(candidate, actor, reach):
            cost += W_GAZE_BLOCKING

    cost += W_EDGE * max(0.0, 1.0 - _edge_slack(candidate, panel) / (diagonal * 0.05))

    return cost


def _score_caption(
    candidate: BBox,
    *,
    actors: Mapping[str, Speaker],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    prefer: PlacementZone,
    placed: list[BBox],
    masses: Sequence[tuple[Polygon, float]],
    emanata: Sequence[BaseGeometry] = (),
    limits: _Limits = _NO_LIMITS,
    bystanders: Bystanders = NOBODY,
) -> float:
    """Cost of putting a caption here. Lower is better; infinity means illegal.

    The same hard rules as a balloon, and two differences in the soft ones. There is
    no mouth to stay near, because a caption has no speaker in the panel. And the edge
    term is reversed: a balloon floating against the frame looks stranded, while a
    caption tucked into the corner is doing what a caption is for.
    """
    if not _is_legal(candidate, actors, panel, placed, limits, bystanders=bystanders):
        return math.inf

    cost = _occlusion_cost(candidate, hulls, None, bystanders.bodies) + _mass_cost(
        candidate, masses
    )
    cost += _emanata_cost(candidate, emanata)

    diagonal = math.hypot(panel.width, panel.height)
    across, down = prefer.fractions
    target = Point(panel.x + panel.width * across, panel.y + panel.height * down)
    cost += W_PREFERRED_ZONE * (candidate.centre.distance_to(target) / diagonal)

    # Reach is taken from the largest face in the panel rather than a speaker's, since
    # a caption has none. It is the conservative choice: the longest sight line any
    # character in this panel has.
    reach = max((actor.face.r for actor in actors.values()), default=0.0) * GAZE_REACH_FACTOR
    for actor in actors.values():
        if _blocks_gaze(candidate, actor, reach):
            cost += W_GAZE_BLOCKING

    cost += W_CAPTION_EDGE * min(1.0, _edge_slack(candidate, panel) / (diagonal * 0.05))

    return cost


def _stop_at_face(start: Point, mouth: Point, face: Circle | None) -> Point:
    """Trim a tail so it stops on the face outline instead of inside the head.

    The mouth anchor sits well within the face circle, so a tail drawn all the way to
    it stabs through the middle of the head -- correct by the numbers and obviously
    wrong on the page. Letterers stop the tip at the outline, aimed at the mouth. This
    finds where the tail crosses that outline and ends there.
    """
    if face is None or not face.contains_point(mouth):
        return mouth

    dx, dy = mouth.x - start.x, mouth.y - start.y
    a = dx * dx + dy * dy
    if a == 0:
        return mouth
    fx, fy = start.x - face.cx, start.y - face.cy
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - face.r * face.r
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return mouth

    root = math.sqrt(discriminant)
    # The first crossing along the segment is where the tail meets the outline.
    for t in sorted(((-b - root) / (2 * a), (-b + root) / (2 * a))):
        if 0.0 <= t <= 1.0:
            return Point(start.x + dx * t, start.y + dy * t)
    return mouth


def route_tail(
    balloon: BBox, mouth: Point, obstacles: list[Circle], speaker_face: Circle | None = None
) -> TailRoute:
    """Route a tail from the balloon toward the speaker's mouth.

    Straight is right almost always, so it is tried first. Only when the direct line
    crosses another character's face does the tail bend, and then via a single control
    point chosen from a handful of lateral offsets.

    Grid pathfinding is deliberately not used here. A tail is a short tapered stroke,
    and A-star produces a jointed path that looks nothing like one drawn by hand.
    """
    start = _rim_point(balloon, mouth)
    tip = _stop_at_face(start, mouth, speaker_face)
    if not any(segment_intersects_circle(start, tip, circle) for circle in obstacles):
        return TailRoute(start=start, end=tip)
    mouth = tip

    midpoint = Point((start.x + mouth.x) / 2, (start.y + mouth.y) / 2)
    dx, dy = mouth.x - start.x, mouth.y - start.y
    length = math.hypot(dx, dy) or 1.0
    normal_x, normal_y = -dy / length, dx / length

    for magnitude in (0.35, 0.7, 1.1, 1.6):
        for sign in (1.0, -1.0):
            offset = length * magnitude * sign
            control = midpoint.translated(normal_x * offset, normal_y * offset)
            if not _curve_hits(start, control, mouth, obstacles):
                return TailRoute(start=start, end=mouth, control=control)

    # Nothing clears the obstacle. A straight tail that clips a face is still better
    # than no tail at all, since a balloon with no pointer has no attributed speaker.
    return TailRoute(start=start, end=mouth)


def _curve_hits(start: Point, control: Point, end: Point, obstacles: list[Circle]) -> bool:
    samples = 16
    previous = start
    for step in range(1, samples + 1):
        t = step / samples
        inverse = 1 - t
        x = inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x
        y = inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y
        current = Point(x, y)
        if any(segment_intersects_circle(previous, current, circle) for circle in obstacles):
            return True
        previous = current
    return False


def _rim_point(balloon: BBox, toward: Point) -> Point:
    """Where a tail leaves the balloon outline, heading toward a point."""
    centre = balloon.centre
    dx, dy = toward.x - centre.x, toward.y - centre.y
    if dx == 0 and dy == 0:
        return centre
    # Scale the direction until it meets the box edge.
    scale_x = (balloon.width / 2) / abs(dx) if dx else math.inf
    scale_y = (balloon.height / 2) / abs(dy) if dy else math.inf
    scale = min(scale_x, scale_y)
    return centre.translated(dx * scale, dy * scale)


def letter_tone(fill: str) -> str:
    """What a caption filled with this value is lettered in.

    Ink over a pale box, paper over a dark one, chosen by contrast rather than by a
    threshold on the tone -- the same rule and the same reason as falling rain in
    `solve/backdrop.py`, where a white streak is invisible against noon and a black one
    against midnight. Inkers flip the same way.

    Resolved here rather than in the emitter because which mark reads is a fact about
    the panel, not a rendering preference: the emitter must not be able to draw a box in
    a value the solver did not choose.

    Args:
        fill: The `#rrggbb` the box is filled with.

    Returns:
        The value the lettering is drawn in.

    Example:
        >>> from scenet.solve.balloons import letter_tone
        >>> letter_tone("#ffffff"), letter_tone("#090909")
        ('#111111', '#ffffff')
    """
    if contrast_ratio(CAPTION_INK, fill) >= contrast_ratio(CAPTION_PAPER, fill):
        return CAPTION_INK
    return CAPTION_PAPER


def caption_text(events: Sequence[ScriptEvent], index: int) -> str:
    """The text of a caption, with quotation marks where the kind calls for them.

    Blambot's rule for a run of one speaker's spoken captions: an opening quote on each, a
    closing quote **only on the last**. Consecutive boxes are one continuous line of
    off-panel speech, and closing each of them would read as four separate interruptions.

    Applied here, before measurement, and carried through Panel Core as part of the
    resolved lines. Adding the marks in the emitter would make the text wider than the
    box that was drawn for it.

    Args:
        events: The whole script, because whether this caption closes depends on what
            follows it.
        index: Which entry to render.

    Returns:
        The text to letter.

    Example:
        >>> from scenet.ir import CaptionEvent, CaptionKind
        >>> from scenet.solve.balloons import caption_text
        >>> run = (
        ...     CaptionEvent(text="Get down!", kind=CaptionKind.SPOKEN),
        ...     CaptionEvent(text="All of you!", kind=CaptionKind.SPOKEN),
        ... )
        >>> caption_text(run, 0).endswith("”")
        False
        >>> caption_text(run, 1).endswith("”")
        True
    """
    event = events[index]
    if not isinstance(event, CaptionEvent) or not event.kind.is_quoted:
        return events[index].text

    # A run is one speaker's speech. Blambot again: "end quotes should appear as each
    # speaker finishes/before the next one begins" -- so a change of speaker closes it,
    # and a box naming nobody is not the same voice as one naming somebody.
    following = events[index + 1] if index + 1 < len(events) else None
    continues = (
        isinstance(following, CaptionEvent)
        and following.kind.is_quoted
        and following.by == event.by
    )
    return OPENING_QUOTE + event.text + ("" if continues else CLOSING_QUOTE)


def place_script(
    events: Sequence[ScriptEvent],
    speakers: Mapping[str, Speaker],
    panel: BBox,
    *,
    bystanders: Sequence[Speaker] = (),
    keep_out: Sequence[Sequence[Point]] = (),
    metrics: FontMetrics | None = None,
    italic_metrics: FontMetrics | None = None,
    typeface: Typeface | None = None,
    font_size: float | None = None,
    type_size: float | None = None,
    lettering_height: float | None = None,
    backdrop: ResolvedBackdrop | None = None,
    emanata: Mapping[str, Sequence[Sequence[Point]]] | None = None,
    exclusions: Sequence[BBox] = (),
    inside: Sequence[tuple[float, float]] | None = None,
    bounds: BBox | None = None,
    outline: Sequence[tuple[float, float]] | None = None,
    direction: Direction = Direction.LTR,
) -> ScriptLayout:
    """Place every sound effect, then every balloon and caption in script order.

    Greedy rather than jointly optimised: each box is placed against those already
    down, which is exactly how reading order works -- a box constrains its successor,
    never its predecessor. That makes the greedy pass the natural formulation rather
    than a compromise.

    One pass over the whole script, not captions and then balloons. The two share the
    list of boxes already placed, so a caption written between two lines of dialogue
    is read between them.

    Args:
        events: The panel's script, in reading order.
        speakers: Everybody in the cast who is drawn, keyed by actor id, as lettering
            sees them: posed puppets, or figures a picture draws.
        panel: The rectangle to compose within, margins already applied.
        bystanders: Figures a picture draws that nobody cast. Their faces are as
            forbidden as a speaker's, and their bodies cost as much, never forgiven.
        keep_out: Regions of a picture lettering should stay off. A soft cost, at the
            weight of emanata, and never an exclusion.
        metrics: Font to measure roman lettering against, in place of the family's.
        italic_metrics: Font to measure italic captions against, in place of the
            family's.
        typeface: The lettering family, emphasis face included. Defaults to the shipped
            one; `metrics` and `italic_metrics` replace single faces of it.
        font_size: Override for every type size, dialogue and captions alike, in panel
            units. For tests that want one size throughout.
        type_size: The dialogue size the author set with `lettering.size`, in panel
            units. Captions keep their proportion to it. Takes the place of
            `lettering_height`, which only matters when no size was set.
        lettering_height: The height type sizes are a fraction of, in place of the
            frame's own. A page passes one value to every panel on it, so a short panel
            and a tall one letter alike.
        backdrop: The resolved setting, if the panel has one. Its masses are a soft
            cost, never an exclusion: a balloon over a sky is the ordinary case.
        emanata: Actor id to the zones of the marks drawn around them. Also a soft
            cost, and a heavier one than a body, but never an exclusion.
        exclusions: Areas that are drawn over, such as an inset: as hard as a face, since
            words under them could not be read. They take no part in reading order.
        inside: The shape every box must lie within, when the panel is not a rectangle,
            margins already applied -- as `panel` has them. A box must also lie within
            `panel`; candidates are still generated in it.
        bounds: The panel's own rectangle, margins not applied: the frame an off-panel
            speaker's tail ends on. Defaults to `panel`.
        outline: The panel's own outline when it is not a rectangle, margins not
            applied, which that tail ends on instead.
        direction: Which way the panel is read. It decides the reading order and every
            tiebreak reading decides, and nothing about the picture.

    Returns:
        Everything that carries words, placed.

    Raises:
        BalloonPlacementError: Some box had no legal position anywhere in the panel.
        SfxPlacementError: Some sound effect had no legal position anywhere in the panel.
    """
    if not events:
        return ScriptLayout()

    reference = lettering_height if lettering_height is not None else panel.height
    if font_size is not None:
        size = caption_size = font_size
    elif type_size is not None:
        size = type_size
        caption_size = type_size * CAPTION_FONT_SIZE_FRACTION / FONT_SIZE_FRACTION
    else:
        size = reference * FONT_SIZE_FRACTION
        caption_size = reference * CAPTION_FONT_SIZE_FRACTION
    family = typeface or Typeface()
    if metrics is not None:
        family = replace(family, regular=metrics)
    if italic_metrics is not None:
        family = replace(family, italic=italic_metrics)
    hulls = {
        actor_id: _hull_polygon(speaker) for actor_id, speaker in speakers.items() if speaker.body
    }
    others = Bystanders.of(bystanders)
    faces = [speaker.face for speaker in speakers.values()] + list(others.faces)
    masses = _mass_polygons(backdrop)
    marks = _emanata_shapes(emanata or {})
    # A keep-out is ground as emanata are, and paid for at their weight: a picture's
    # region a balloon may still cover when nothing else is free.
    if keep_out:
        marks.append(_keep_out_shape(keep_out))

    placed: list[BBox] = []
    limits = _Limits(
        blocked=tuple(exclusions),
        inside=Polygon(inside) if inside is not None else None,
        direction=direction,
    )
    captions: list[PlacedCaption] = []
    balloons: list[PlacedBalloon] = []

    # Sound effects first: they are part of the picture, which lettering is placed over.
    # They are exempt from the geometric reading-order rule -- a sound sits where the
    # sound is -- but keep their number in the one sequence. Once down, each one's
    # footprint is ground a balloon or caption pays to cover, as it pays for emanata, and
    # is never forbidden to; with no effects the list is exactly the emanata it was.
    effects = place_effects(
        [(order, event) for order, event in enumerate(events) if isinstance(event, SfxEvent)],
        actors=speakers,
        hulls=hulls,
        panel=panel,
        dialogue_size=size,
        typeface=family,
        marks=marks,
        blocked=exclusions,
        inside=limits.inside,
        bystanders=others,
    )
    marks = [*marks, *(effect.zone for effect in effects)]

    for order, event in enumerate(events):
        if isinstance(event, SfxEvent):
            continue
        if isinstance(event, CaptionEvent):
            captions.append(
                _place_caption(
                    event,
                    text=caption_text(events, order),
                    identifier=f"c{len(captions)}",
                    order=order,
                    actors=speakers,
                    hulls=hulls,
                    panel=panel,
                    placed=placed,
                    font_size=caption_size,
                    typeface=family,
                    masses=masses,
                    emanata=marks,
                    limits=limits,
                    bystanders=others,
                )
            )
            placed.append(captions[-1].box)
            continue

        lettering = _Lettering.of(event, size)
        frame = _Frame(bounds or panel, outline)
        if event.off_panel is not False:
            balloons.append(
                _place_off_panel(
                    event,
                    identifier=f"b{len(balloons)}",
                    order=order,
                    actors=speakers,
                    hulls=hulls,
                    faces=faces,
                    panel=panel,
                    frame=frame,
                    placed=placed,
                    lettering=lettering,
                    typeface=family,
                    masses=masses,
                    emanata=marks,
                    limits=limits,
                    bystanders=others,
                )
            )
            placed.append(balloons[-1].box)
            continue

        balloons.append(
            _place_balloon(
                event,
                identifier=f"b{len(balloons)}",
                order=order,
                actors=speakers,
                hulls=hulls,
                panel=panel,
                frame=frame,
                placed=placed,
                lettering=lettering,
                typeface=family,
                masses=masses,
                emanata=marks,
                limits=limits,
                bystanders=others,
            )
        )
        placed.append(balloons[-1].box)

    return ScriptLayout(captions=tuple(captions), balloons=tuple(balloons), effects=effects)


def _place_balloon(
    event: SayEvent,
    *,
    identifier: str,
    order: int,
    actors: Mapping[str, Speaker],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    frame: "_Frame",
    placed: list[BBox],
    lettering: "_Lettering",
    typeface: Typeface,
    masses: Sequence[tuple[Polygon, float]],
    emanata: Sequence[BaseGeometry],
    limits: _Limits = _NO_LIMITS,
    bystanders: Bystanders = NOBODY,
) -> PlacedBalloon:
    """Choose a position for one balloon and route its tail."""
    speaker = actors[event.by]
    block = layout_text(styled(event.text), font_size=lettering.font_size, typeface=typeface)
    balloon_box = balloon_size(block, lettering.padding_factor)

    best: BBox | None = None
    best_cost = math.inf
    for candidate in _candidate_positions(speaker, balloon_box, panel, limits.direction):
        if not _reading_order_allows(placed, candidate, limits.direction):
            continue
        cost = _score(
            candidate,
            speaker=speaker,
            speaker_id=event.by,
            actors=actors,
            hulls=hulls,
            panel=panel,
            prefer=event.prefer,
            placed=placed,
            masses=masses,
            emanata=emanata,
            limits=limits,
            bystanders=bystanders,
        )
        if cost < best_cost:
            best, best_cost = candidate, cost

    if best is None:
        raise BalloonPlacementError(
            f"no legal position for balloon {order} spoken by '{event.by}': every "
            "candidate either covered a face, left the panel, overlapped another "
            "balloon, lay under an inset, or broke reading order"
        )

    # A speaker's own face does not obstruct their own tail -- the tail is
    # supposed to arrive there.
    obstacles = [
        *(other.face for actor_id, other in actors.items() if actor_id != event.by),
        *bystanders.faces,
    ]
    return PlacedBalloon(
        id=identifier,
        speaker=event.by,
        order=order,
        kind=event.kind,
        box=best,
        block=block,
        tail=route_tail(
            best,
            _within_frame(best.centre, speaker.mouth, frame),
            obstacles,
            speaker_face=speaker.face,
        ),
    )


def _within_frame(origin: Point, target: Point, frame: "_Frame") -> Point:
    """Where a tail aimed from `origin` at `target` ends: there, or on the frame first.

    A figure a picture draws can have its mouth cropped out of the panel -- a `cover` fit
    overhangs -- and a tail drawn to it would leave the panel. It ends where it crosses the
    frame instead, as a tail to somebody off panel does, aimed the same way. Every other
    tail reaches its mouth, which lies inside.

    Example:
        >>> _within_frame(Point(50, 50), Point(150, 50), _Frame(BBox(0, 0, 100, 100)))
        Point(x=100.0, y=50.0)
    """
    bounds = frame.bounds
    shape = (
        Polygon(frame.outline)
        if frame.outline is not None
        else box(bounds.x, bounds.y, bounds.right, bounds.bottom)
    )
    # The balloon is inside the frame, and a frame is convex: the line to a mouth inside it
    # crosses nothing, and to one beyond it crosses the frame exactly once.
    crossing = LineString([(origin.x, origin.y), (target.x, target.y)]).intersection(shape.exterior)
    points = [Point(float(x), float(y)) for x, y in get_coordinates(crossing)]
    return min(points, key=origin.distance_to) if points else target


@dataclass(frozen=True, slots=True)
class _Lettering:
    """How one balloon is lettered: its type size, and the padding that goes around it."""

    font_size: float
    padding_factor: float = PADDING_FACTOR

    @classmethod
    def of(cls, event: SayEvent, size: float) -> "_Lettering":
        """A line's lettering, against the panel's dialogue size.

        Small type keeps the padding normal type would have -- the balloon keeps its
        room -- so its factor grows as its size shrinks.
        """
        if event.size is TypeSize.SMALL:
            return cls(size * SMALL_TYPE_FRACTION, PADDING_FACTOR / SMALL_TYPE_FRACTION)
        return cls(size)


@dataclass(frozen=True, slots=True)
class _Frame:
    """The edge an off-panel speaker's tail ends on: the panel's rectangle, or its outline."""

    bounds: BBox
    outline: Sequence[tuple[float, float]] | None = None


#: Where an off-panel balloon would rather sit, by the side its speaker is on: near that
#: side, high, since a balloon reads before the picture it is over.
_SIDE_ZONES = {
    Side.LEFT: PlacementZone.TOP_LEFT,
    Side.RIGHT: PlacementZone.TOP_RIGHT,
    Side.TOP: PlacementZone.TOP_CENTRE,
    Side.BOTTOM: PlacementZone.BOTTOM_CENTRE,
}


def _place_off_panel(
    event: SayEvent,
    *,
    identifier: str,
    order: int,
    actors: Mapping[str, Speaker],
    hulls: Mapping[str, Polygon],
    faces: list[Circle],
    panel: BBox,
    frame: _Frame,
    placed: list[BBox],
    lettering: "_Lettering",
    typeface: Typeface,
    masses: Sequence[tuple[Polygon, float]],
    emanata: Sequence[BaseGeometry],
    limits: _Limits = _NO_LIMITS,
    bystanders: Bystanders = NOBODY,
) -> PlacedBalloon:
    """Choose a position for a balloon whose speaker is not drawn, and route its tail.

    There is no mouth to stay near, so it is placed as a caption is -- the same zones, the
    same hard rules, reading order included -- drawn toward the side named, if one is, and
    otherwise toward where reading starts. With none named, the side is the nearer of left
    and right to where it went: a balloon sits high, so "nearest edge" would aim most tails
    at the top border, which reads as a speaker above. Its tail then ends on the frame on
    that side -- Blambot: "the tail of the balloon generally butts against the panel
    border".
    """
    named = event.off_panel if isinstance(event.off_panel, Side) else None
    block = layout_text(styled(event.text), font_size=lettering.font_size, typeface=typeface)
    balloon_box = balloon_size(block, lettering.padding_factor)
    start = READING_STARTS[limits.direction]
    prefer = event.prefer or (_SIDE_ZONES[named] if named is not None else start)

    best: BBox | None = None
    best_cost = math.inf
    for candidate in _caption_positions(balloon_box, panel, limits.direction):
        if not _reading_order_allows(placed, candidate, limits.direction):
            continue
        cost = _score_caption(
            candidate,
            actors=actors,
            hulls=hulls,
            panel=panel,
            prefer=prefer,
            placed=placed,
            masses=masses,
            emanata=emanata,
            limits=limits,
            bystanders=bystanders,
        )
        if cost < best_cost:
            best, best_cost = candidate, cost

    if best is None:
        raise BalloonPlacementError(
            f"no legal position for balloon {order} spoken from off panel by '{event.by}': "
            "every candidate either covered a face, left the panel, overlapped another "
            "balloon, lay under an inset, or broke reading order"
        )

    side = named if named is not None else _nearer_side(best, panel, limits.direction)
    return PlacedBalloon(
        id=identifier,
        speaker=event.by,
        order=order,
        kind=event.kind,
        box=best,
        block=block,
        tail=route_tail(best, _edge_point(best, side, frame), faces, speaker_face=None),
        off_panel=side,
    )


def _nearer_side(balloon: BBox, panel: BBox, direction: Direction = Direction.LTR) -> Side:
    """The nearer of the panel's left and right to a balloon's centre.

    On a tie, the side reading starts from: left, or right for a panel read right to left.

    Example:
        >>> _nearer_side(BBox(100, 50, 40, 20), BBox(0, 0, 300, 200))
        <Side.LEFT: 'left'>
        >>> _nearer_side(BBox(130, 50, 40, 20), BBox(0, 0, 300, 200), Direction.RTL)
        <Side.RIGHT: 'right'>
    """
    middle = panel.x + panel.width / 2
    if direction is Direction.RTL:
        return Side.RIGHT if balloon.centre.x >= middle else Side.LEFT
    return Side.LEFT if balloon.centre.x <= middle else Side.RIGHT


def _edge_point(balloon: BBox, side: Side, frame: _Frame) -> Point:
    """Where an off-panel tail meets the frame: straight out from the balloon to that side.

    On a slanted panel the side is the outline's, so the point is where a line straight
    out from the balloon's centre crosses it.

    Example:
        >>> _edge_point(BBox(100, 50, 40, 20), Side.LEFT, _Frame(BBox(0, 0, 300, 200)))
        Point(x=0, y=60.0)
    """
    centre = balloon.centre
    bounds = frame.bounds
    target = {
        Side.LEFT: Point(bounds.x, centre.y),
        Side.RIGHT: Point(bounds.right, centre.y),
        Side.TOP: Point(centre.x, bounds.y),
        Side.BOTTOM: Point(centre.x, bounds.bottom),
    }[side]
    if frame.outline is None:
        return target
    # Past the rectangle, so the line is sure to reach a slanted edge however it leans.
    beyond = Point(
        centre.x + 2 * (target.x - centre.x) or centre.x,
        centre.y + 2 * (target.y - centre.y) or centre.y,
    )
    crossing = LineString([(centre.x, centre.y), (beyond.x, beyond.y)]).intersection(
        Polygon(frame.outline).exterior
    )
    points = [
        Point(float(x), float(y))
        for geometry in getattr(crossing, "geoms", [crossing])
        for x, y in getattr(geometry, "coords", [])
    ]
    if not points:  # pragma: no cover -- the line runs from inside to beyond the frame
        return target
    return min(points, key=centre.distance_to)


def _place_caption(
    event: CaptionEvent,
    *,
    text: str,
    identifier: str,
    order: int,
    actors: Mapping[str, Speaker],
    hulls: Mapping[str, Polygon],
    panel: BBox,
    placed: list[BBox],
    font_size: float,
    typeface: Typeface,
    masses: Sequence[tuple[Polygon, float]],
    emanata: Sequence[BaseGeometry],
    limits: _Limits = _NO_LIMITS,
    bystanders: Bystanders = NOBODY,
) -> PlacedCaption:
    """Choose a position for one caption.

    The face it is measured against is the face it will be drawn in, which is the
    whole reason the italic kinds use a real italic file rather than a skew. The values
    are resolved on the same principle: the emitter is handed a fill and an ink, never
    a tone to interpret.
    """
    base = Face.ITALIC if event.kind.is_italic else Face.REGULAR
    block = layout_text(styled(text, base), font_size=font_size, typeface=typeface)
    caption_box = balloon_size(block, CAPTION_PADDING_FACTOR)

    best: BBox | None = None
    best_cost = math.inf
    for candidate in _caption_positions(caption_box, panel, limits.direction):
        if not _reading_order_allows(placed, candidate, limits.direction):
            continue
        cost = _score_caption(
            candidate,
            actors=actors,
            hulls=hulls,
            panel=panel,
            # Unwritten, where a locale caption conventionally sits: where reading starts.
            prefer=event.prefer or READING_STARTS[limits.direction],
            placed=placed,
            masses=masses,
            emanata=emanata,
            limits=limits,
            bystanders=bystanders,
        )
        if cost < best_cost:
            best, best_cost = candidate, cost

    if best is None:
        raise BalloonPlacementError(
            f"no legal position for caption {order}: every candidate either covered a "
            "face, left the panel, overlapped another box, lay under an inset, or broke "
            "reading order"
        )

    fill = CAPTION_TONES[event.tone]
    return PlacedCaption(
        id=identifier,
        order=order,
        kind=event.kind,
        box=best,
        block=block,
        fill=fill,
        ink=letter_tone(fill),
        speaker=event.by,
    )
