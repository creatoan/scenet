"""A panel as the marks drawn in it: what each is, where, and in which order.

The SVG emitter writes a panel as text as it goes. A print emitter (#80) needs the same
drawing as data: every shape, the order it is painted in, and what it *is* -- a line of
ink, the paper showing through, a grey -- because a printer is told inks, not colours.
`marks` lists exactly what the SVG paints, one mark per painted element, in the same
order, from the same numbers (`scenet.emit.geometry`); `tests/test_marks.py` holds the
two to each other for every gallery panel.

Each paint keeps the colour the SVG draws and the grey it is the twin of (#244): a tinted
mass draws its colour on screen and prints its grey.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from scenet.core import (
    CoreActor,
    CoreAtmosphere,
    CoreBalloon,
    CoreCaption,
    CoreImage,
    CoreMass,
    CoreRun,
    CoreSfx,
    CoreVeil,
    FaceDisc,
    FaceMark,
    PanelCore,
)
from scenet.emit import geometry
from scenet.emit.geometry import (
    BALLOON_STROKE_WIDTH,
    CAPTION_STROKE_WIDTH,
    FIGURE_STROKE_WIDTH,
    FILL_FIGURE,
    FRAME_STROKE_WIDTH,
    STROKE,
    WEATHER_OPACITY,
    WHISPER_DASH,
)
from scenet.emit.svg import in_painters_order
from scenet.ir import BalloonKind, Face
from scenet.solve.text import FontMetrics, Typeface

#: The paper, which every white in Scenet is: nothing is ever printed in white ink.
PAPER = "#ffffff"


class Role(StrEnum):
    """What a paint is, which is what decides the ink it prints in."""

    #: A line or letter of ink, drawn over whatever is beneath it.
    INK = "ink"
    #: A solid area of ink with something reversed out of it: a dark caption box.
    SOLID = "solid"
    #: The paper: a balloon, the panel's ground, letters reversed out of ink.
    PAPER = "paper"
    #: A grey: a figure's fill, a caption box, weather.
    TONE = "tone"
    #: A backdrop mass: a grey, which may be large and near black.
    MASS = "mass"


@dataclass(frozen=True, slots=True)
class Paint:
    """A fill or a stroke.

    Attributes:
        colour: What the SVG draws: a colour when the palette gave one, a grey otherwise.
        role: What it is.
        grey: The grey `colour` is the twin of, which is what print uses (#244).
        opacity: Below 1 only for falling weather.
    """

    colour: str
    role: Role
    grey: str
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class Rect:
    """A rectangle, its corners rounded by `radius`."""

    tag: ClassVar[str] = "rect"
    x: float
    y: float
    width: float
    height: float
    radius: float = 0.0


@dataclass(frozen=True, slots=True)
class Circle:
    """A circle."""

    tag: ClassVar[str] = "circle"
    cx: float
    cy: float
    r: float


@dataclass(frozen=True, slots=True)
class Ellipse:
    """An ellipse, its axes along the panel's."""

    tag: ClassVar[str] = "ellipse"
    cx: float
    cy: float
    rx: float
    ry: float


@dataclass(frozen=True, slots=True)
class Polygon:
    """Points joined in order, closed back to the first or left open."""

    points: tuple[tuple[float, float], ...]
    closed: bool = True

    @property
    def tag(self) -> str:
        """The SVG element: a polygon, or a polyline when open."""
        return "polygon" if self.closed else "polyline"


@dataclass(frozen=True, slots=True)
class Line:
    """A straight line: a streak of rain."""

    tag: ClassVar[str] = "line"
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass(frozen=True, slots=True)
class Segment:
    """A straight stroke, which SVG writes as a path: a figure's limb."""

    tag: ClassVar[str] = "path"
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass(frozen=True, slots=True)
class Pointer:
    """A balloon's tail."""

    tag: ClassVar[str] = "path"
    shape: geometry.Pointer


@dataclass(frozen=True, slots=True)
class Glyph:
    """One letter's outline, in its font's units, placed and scaled into the panel.

    Attributes:
        metrics: The face it is drawn from.
        char: The character.
        x: Where its origin lands.
        y: Its baseline.
        scale: Font units to panel units; the outline is flipped, since fonts are y-up.
        angle: How far it is turned, in degrees clockwise: 0 but for a sound effect.
    """

    tag: ClassVar[str] = "path"
    metrics: FontMetrics
    char: str
    x: float
    y: float
    scale: float
    angle: float = 0.0


@dataclass(frozen=True, slots=True)
class Text:
    """One line of lettering set as text, with `--live-text` (#284).

    The SVG writes it as one `<text>`; print sets each run in its embedded face. Its glyphs
    land where their outlines would, each run's origins worked out by
    :func:`geometry.glyph_walk <scenet.emit.geometry.glyph_walk>`.

    Attributes:
        runs: The line's runs, each in its face, with every character's origin.
        baseline: The line's baseline.
        font_size: The type size, in panel units.
    """

    tag: ClassVar[str] = "text"
    runs: tuple[geometry.PlacedRun, ...]
    baseline: float
    font_size: float


@dataclass(frozen=True, slots=True)
class Picture:
    """A supplied picture, in the box Panel Core placed it in."""

    tag: ClassVar[str] = "image"
    image: CoreImage


@dataclass(frozen=True, slots=True)
class Veil:
    """The fog or cloud over a backdrop: the atmosphere's noise, over the panel (#282)."""

    tag: ClassVar[str] = "rect"
    width: float
    height: float
    veil: CoreVeil


Shape = Rect | Circle | Ellipse | Polygon | Line | Segment | Pointer | Glyph | Text | Picture | Veil


@dataclass(frozen=True, slots=True)
class Mark:
    """One thing painted in a panel.

    Attributes:
        owner: What it belongs to, named as the SVG's ids name it: `panel`, `image`,
            `mass-<id>`, `actor-<id>`, `sfx-<id>`, `balloon-<id>`, `caption-<id>`,
            `weather` or `veil`.
        shape: Where it is.
        fill: Its fill, if it has one.
        stroke: Its outline, if it has one.
        width: The outline's width -- in font units for a glyph, which is scaled.
        rounded: Round caps and joins on its outline, as everything drawn over the backdrop
            has. Only an outline has caps and joins, so a mark with none leaves it `False`.
        dash: A dash pattern along the outline: a whisper's.
        stroke_first: The outline is painted under the fill, as a sound effect's halo is.
    """

    owner: str
    shape: Shape
    fill: Paint | None = None
    stroke: Paint | None = None
    width: float = 0.0
    rounded: bool = False
    dash: tuple[float, ...] = ()
    stroke_first: bool = False

    @property
    def is_veil(self) -> bool:
        """Whether this is the veil, which the SVG draws with a filter and print as a mask."""
        return isinstance(self.shape, Veil)


INK = Paint(STROKE, Role.INK, STROKE)
WHITE = Paint(PAPER, Role.PAPER, PAPER)
FIGURE = Paint(FILL_FIGURE, Role.TONE, FILL_FIGURE)


def _valued(value: str) -> Paint | None:
    """A paint Panel Core gives as a value -- a caption's ink, a sound effect's colours.

    Ink and paper are what the solver chooses between for lettering; anything else, which
    only a Core edited by hand could hold, is a grey.
    """
    if value == "none":
        return None
    if value == STROKE:
        return INK
    if value == PAPER:
        return WHITE
    return Paint(value, Role.TONE, value)


def marks(core: PanelCore, family: Typeface, *, live_text: bool = False) -> list[Mark]:
    """Everything a panel paints, in the order it is painted.

    Args:
        core: The compiled panel.
        family: The faces its lettering was measured in, from
            :func:`typeface_of <scenet.emit.svg.typeface_of>`.
        live_text: Each line of a balloon or a caption as one :class:`Text` mark, as the
            SVG's `--live-text` writes one `<text>`, rather than a mark for each letter's
            outline. Sound effects are outlines either way.

    Returns:
        One mark per element the SVG paints, in the same order, with the veil where the
        SVG draws it.
    """
    backdrop = core.backdrop
    air = backdrop.atmosphere if backdrop is not None else None
    drawn = [Mark("panel", Rect(0.0, 0.0, core.width, core.height), fill=WHITE)]
    if backdrop is not None and backdrop.image is not None:
        drawn.append(Mark("image", Picture(backdrop.image)))

    ordered = in_painters_order(core)
    for item in ordered:
        if item.depth < 0:
            drawn.extend(_item(item))
    if air is not None and air.veil is not None:
        # Painted in its grey's ink, as every paint prints its grey (#244).
        tone = Paint(air.veil.colour or air.veil.tone, Role.TONE, air.veil.tone)
        drawn.append(Mark("veil", Veil(core.width, core.height, air.veil), fill=tone))
    for item in ordered:
        if item.depth >= 0:
            drawn.extend(_item(item))

    if core.sfx:
        display = family.face(Face.DISPLAY)
        for effect in core.sfx:
            drawn.extend(_sfx(effect, display))

    for lettered in sorted([*core.balloons, *core.captions], key=lambda item: item.order):
        if isinstance(lettered, CoreCaption):
            drawn.extend(_caption(lettered, family, live_text=live_text))
        else:
            drawn.extend(_balloon(lettered, family, live_text=live_text))

    if air is not None:
        drawn.extend(_weather(air))

    frame: Shape = (
        Polygon(tuple(core.outline))
        if core.outline is not None
        else Rect(0.0, 0.0, core.width, core.height)
    )
    drawn.append(Mark("panel", frame, stroke=INK, width=FRAME_STROKE_WIDTH))
    return drawn


def _item(item: CoreActor | CoreMass) -> list[Mark]:
    if isinstance(item, CoreMass):
        fill = Paint(item.colour or item.tone, Role.MASS, item.tone)
        return [Mark(f"mass-{item.id}", Polygon(item.polygon), fill=fill)]
    return _actor(item)


def _actor(actor: CoreActor) -> list[Mark]:
    owner = f"actor-{actor.id}"
    drawn: list[Mark] = []
    for capsule in actor.capsules:
        limb = Segment(capsule.start, capsule.end)
        drawn.append(Mark(owner, limb, stroke=INK, width=capsule.width, rounded=True))
        drawn.append(
            Mark(
                owner,
                limb,
                stroke=FIGURE,
                width=geometry.inner_width(capsule.width),
                rounded=True,
            )
        )
    for blob in actor.blobs:
        cx, cy = blob.centre
        drawn.append(
            Mark(
                owner,
                Circle(cx, cy, blob.radius),
                fill=FIGURE,
                stroke=INK,
                width=FIGURE_STROKE_WIDTH,
                rounded=True,
            )
        )
    drawn.extend(_face_mark(owner, mark) for mark in (*actor.face_marks, *actor.emanata))
    return drawn


def _face_mark(owner: str, mark: FaceMark) -> Mark:
    if isinstance(mark, FaceDisc):
        cx, cy = mark.centre
        disc = Circle(cx, cy, mark.radius)
        if mark.filled:
            return Mark(owner, disc, fill=INK)
        return Mark(owner, disc, fill=WHITE, stroke=INK, width=mark.width, rounded=True)
    return Mark(
        owner,
        Polygon(mark.points, closed=mark.closed),
        stroke=INK,
        width=mark.width,
        rounded=True,
    )


def _sfx(effect: CoreSfx, metrics: FontMetrics) -> list[Mark]:
    owner = f"sfx-{effect.id}"
    scale = geometry.sfx_scale(effect, metrics)
    fill, stroke = _valued(effect.fill), _valued(effect.stroke)
    drawn: list[Mark] = []
    outlined: dict[str, bool] = {}
    for glyph in effect.glyphs:
        if glyph.char not in outlined:
            outlined[glyph.char] = bool(metrics.glyph_outlines(glyph.char)[0][0])
        if not outlined[glyph.char]:
            continue
        x, y = glyph.origin
        drawn.append(
            Mark(
                owner,
                Glyph(metrics, glyph.char, x, y, scale, glyph.angle),
                fill=fill,
                stroke=stroke,
                width=effect.stroke_width / scale,
                rounded=True,
                stroke_first=True,
            )
        )
    return drawn


def _lettering(
    owner: str,
    runs: Sequence[CoreRun],
    x: float,
    baseline: float,
    *,
    font_size: float,
    family: Typeface,
    ink: Paint | None,
    live_text: bool,
) -> list[Mark]:
    if live_text:
        placed_runs = tuple(geometry.glyph_walk(runs, x, font_size, family))
        return [Mark(owner, Text(placed_runs, baseline, font_size), fill=ink)]
    drawn: list[Mark] = []
    for placed in geometry.glyph_walk(runs, x, font_size, family):
        outlines = placed.metrics.glyph_outlines(placed.run.text)
        for (path, _), character, origin in zip(
            outlines, placed.run.text, placed.origins, strict=True
        ):
            if path:
                glyph = Glyph(placed.metrics, character, origin, baseline, placed.scale)
                drawn.append(Mark(owner, glyph, fill=ink))
    return drawn


def _runs(
    lines: tuple[str, ...], runs: tuple[tuple[CoreRun, ...], ...], index: int, base: Face
) -> tuple[CoreRun, ...]:
    return runs[index] if runs else (CoreRun(text=lines[index], face=base),)


def _balloon(balloon: CoreBalloon, family: Typeface, *, live_text: bool) -> list[Mark]:
    owner = f"balloon-{balloon.id}"
    box = balloon.box
    drawn: list[Mark] = []
    if balloon.kind is BalloonKind.THOUGHT:
        drawn.extend(
            _outlined(owner, Circle(x, y, r)) for x, y, r in geometry.thought_bubbles(balloon)
        )
    else:
        drawn.append(_outlined(owner, Pointer(geometry.pointer(balloon))))

    outline: Shape
    if balloon.kind is BalloonKind.SHOUT:
        outline = Polygon(tuple(geometry.burst(box)))
    elif balloon.kind is BalloonKind.THOUGHT:
        outline = Ellipse(*geometry.ellipse(box))
    else:
        outline = Rect(box.x, box.y, box.width, box.height, geometry.corner_radius(box))
    dash = WHISPER_DASH if balloon.kind is BalloonKind.WHISPER else ()
    drawn.append(_outlined(owner, outline, dash=dash))

    _, baselines = geometry.baselines(
        box, len(balloon.lines), balloon.line_height, balloon.font_size
    )
    for index, baseline in enumerate(baselines):
        runs = _runs(balloon.lines, balloon.runs, index, Face.REGULAR)
        start = geometry.centred(box, geometry.line_width(runs, balloon.font_size, family))
        drawn.extend(
            _lettering(
                owner,
                runs,
                start,
                baseline,
                font_size=balloon.font_size,
                family=family,
                ink=INK,
                live_text=live_text,
            )
        )
    return drawn


def _outlined(owner: str, shape: Shape, *, dash: tuple[float, ...] = ()) -> Mark:
    """A balloon's outline or tail: paper, edged in ink."""
    return Mark(
        owner,
        shape,
        fill=WHITE,
        stroke=INK,
        width=BALLOON_STROKE_WIDTH,
        rounded=True,
        dash=dash,
    )


def _caption(caption: CoreCaption, family: Typeface, *, live_text: bool) -> list[Mark]:
    owner = f"caption-{caption.id}"
    box = caption.box
    role = (
        Role.SOLID if caption.ink == PAPER else Role.PAPER if caption.fill == PAPER else Role.TONE
    )
    fill = Paint(caption.colour or caption.fill, role, caption.fill)
    drawn = [
        Mark(
            owner,
            Rect(box.x, box.y, box.width, box.height),
            fill=fill,
            stroke=INK,
            width=CAPTION_STROKE_WIDTH,
            rounded=True,
        )
    ]
    padding, baselines = geometry.baselines(
        box, len(caption.lines), caption.line_height, caption.font_size
    )
    base = Face.ITALIC if caption.italic else Face.REGULAR
    ink = _valued(caption.ink)
    for index, baseline in enumerate(baselines):
        runs = _runs(caption.lines, caption.runs, index, base)
        drawn.extend(
            _lettering(
                owner,
                runs,
                box.x + padding,
                baseline,
                font_size=caption.font_size,
                family=family,
                ink=ink,
                live_text=live_text,
            )
        )
    return drawn


def _weather(atmosphere: CoreAtmosphere) -> list[Mark]:
    if not atmosphere.streaks and not atmosphere.flecks:
        return []
    grey = atmosphere.fall_tone
    role = Role.PAPER if grey == PAPER else Role.TONE
    fall = Paint(atmosphere.fall_colour or grey, role, grey, WEATHER_OPACITY)
    drawn = [
        Mark(
            "weather",
            Line(streak.start, streak.end),
            stroke=fall,
            width=atmosphere.streak_width,
            rounded=True,
        )
        for streak in atmosphere.streaks
    ]
    drawn.extend(
        Mark("weather", Circle(fleck.cx, fleck.cy, fleck.r), fill=fall)
        for fleck in atmosphere.flecks
    )
    return drawn
