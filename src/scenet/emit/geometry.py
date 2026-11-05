"""The numbers every emitter draws from, where Panel Core names a shape but not its points.

Panel Core says a balloon is a shout in this box with its tail from here to there; it does
not list a burst's spikes, the two corners where a tail leaves its balloon, or where each
letter of a line lands. Those follow from the Core by arithmetic alone, and two emitters
-- the SVG and the print PDF (#80) -- must draw exactly the same ones. So they are worked
out here, once, and each emitter only writes them down in its own format.

Nothing here decides anything: every position was the solver's, and these are its shapes
spelt out. Each expression keeps the order of operations it had inside the SVG emitter,
so the floats -- and the SVG written from them -- are what they always were.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from scenet.core import Box, CoreBalloon, CoreRun, CoreSfx, PanelCore
from scenet.ir import Side
from scenet.solve.text import FontMetrics, Styled, Typeface

#: Ink: every line drawn and every letter lettered, unless Core says otherwise.
STROKE = "#111111"
#: The pale fill of a figure, inside its outline.
FILL_FIGURE = "#e8e6e1"
#: A balloon's fill, which is the paper's.
FILL_BALLOON = "#ffffff"
#: The panel's ground: the paper it is printed on.
FILL_PANEL = "#ffffff"

FIGURE_STROKE_WIDTH = 3.0
BALLOON_STROKE_WIDTH = 3.0

#: Corner rounding of a speech balloon, as a fraction of its smaller side.
BALLOON_CORNER = 0.42

#: Half-width of a tail where it meets the balloon, as a fraction of balloon height.
TAIL_BASE_FRACTION = 0.18

CAPTION_STROKE_WIDTH = 2.5

#: The frame around a panel, centred on its edge.
FRAME_STROKE_WIDTH = 6.0

#: A whisper's dashes, along its outline.
WHISPER_DASH = (12.0, 9.0)

#: Falling weather is drawn at less than full opacity so it reads as passing through the
#: panel rather than as marks on top of it. *Which* tone it uses was chosen by the solver
#: and travels in `CoreAtmosphere.fall_tone`.
WEATHER_OPACITY = 0.85

#: Where a thought balloon's three bubbles sit along its tail, from balloon to mouth.
THOUGHT_BUBBLES = (0.35, 0.62, 0.85)

#: How far below the top of a line its baseline sits, as a fraction of the type size.
ASCENT = 0.74


@dataclass(frozen=True, slots=True)
class Pointer:
    """A tail's triangle: wide where it leaves the balloon, a point at the mouth.

    Attributes:
        left: One corner of its base.
        tip: The point, at the mouth.
        right: The other corner of its base.
        control: Where a curved tail bends, through both of its sides; `None` when straight.
    """

    left: tuple[float, float]
    tip: tuple[float, float]
    right: tuple[float, float]
    control: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class PlacedRun:
    """Where each letter of one run lands along its line.

    Attributes:
        run: The run.
        metrics: The face it is lettered in.
        scale: Font units to panel units: the type size over the face's units per em.
        origins: The left edge of each character of `run.text`, in panel units, whether
            or not the character has an outline to draw.
    """

    run: CoreRun
    metrics: FontMetrics
    scale: float
    origins: tuple[float, ...]


def burst(box: Box) -> list[tuple[float, float]]:
    """A shout's spiky outline.

    Spike count follows the balloon's perimeter so a long balloon does not end up with a
    handful of enormous points.
    """
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    rx, ry = box.width / 2, box.height / 2
    spikes = max(10, int((box.width + box.height) / 26) * 2)
    points: list[tuple[float, float]] = []
    for index in range(spikes * 2):
        angle = math.pi * index / spikes
        reach = 1.22 if index % 2 == 0 else 0.94
        points.append((cx + math.cos(angle) * rx * reach, cy + math.sin(angle) * ry * reach))
    return points


def corner_radius(box: Box) -> float:
    """How round a speech balloon's corners are."""
    return min(box.width, box.height) * BALLOON_CORNER


def ellipse(box: Box) -> tuple[float, float, float, float]:
    """A thought balloon: the ellipse inscribed in its box, as `(cx, cy, rx, ry)`."""
    return box.x + box.width / 2, box.y + box.height / 2, box.width / 2, box.height / 2


def thought_bubbles(balloon: CoreBalloon) -> list[tuple[float, float, float]]:
    """A thought balloon's tail: shrinking circles towards the mouth, as `(x, y, r)`.

    The established convention, which reads instantly.
    """
    (sx, sy), (ex, ey) = balloon.tail.start, balloon.tail.end
    bubbles: list[tuple[float, float, float]] = []
    for index, t in enumerate(THOUGHT_BUBBLES):
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t
        bubbles.append((x, y, balloon.font_size * (0.34 - index * 0.09)))
    return bubbles


def pointer(balloon: CoreBalloon) -> Pointer:
    """Every other balloon's tail: a tapered triangle from its start to the mouth."""
    tail = balloon.tail
    (sx, sy), (ex, ey) = tail.start, tail.end
    base = max(balloon.box.height * TAIL_BASE_FRACTION, balloon.font_size * 0.35)
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * base / 2, dx / length * base / 2
    return Pointer(
        left=(sx + nx, sy + ny), tip=(ex, ey), right=(sx - nx, sy - ny), control=tail.control
    )


def inner_width(width: float) -> float:
    """The pale stroke inside a limb's ink one, which leaves a figure's outline showing."""
    return max(width - 2 * FIGURE_STROKE_WIDTH, 1.0)


def baselines(
    box: Box, count: int, line_height: float, font_size: float
) -> tuple[float, list[float]]:
    """Where a box's lines of lettering sit: its padding, and each line's baseline.

    Text is laid out from the top of the box: padding, then one line height per line,
    landing each baseline where the solver's measurement assumed it. The padding is derived
    from the box rather than restated as a constant, so it cannot drift from the solver's.
    """
    padding = (box.height - count * line_height) / 2
    ascent = font_size * ASCENT
    return padding, [box.y + padding + index * line_height + ascent for index in range(count)]


def line_width(runs: Sequence[CoreRun], font_size: float, family: Typeface) -> float:
    """A line's width, measured exactly as the solver measured it."""
    line = Styled("", ())
    for run in runs:
        line += Styled.of(run.text, run.face)
    return family.measure(line, font_size)


def centred(box: Box, width: float) -> float:
    """Where a line of this width starts, centred in a balloon's box."""
    return box.x + (box.width - width) / 2


def glyph_walk(
    runs: Sequence[CoreRun], x: float, font_size: float, family: Typeface
) -> list[PlacedRun]:
    """Where every letter of a line lands, from its left edge.

    Each run is drawn from its own face, and the cursor advances by each character's step
    -- its advance plus the kerning to the next -- which is exactly what was measured.
    """
    cursor = x
    placed: list[PlacedRun] = []
    for run in runs:
        metrics = family.face(run.face)
        scale = font_size / metrics.units_per_em
        origins: list[float] = []
        last = len(run.text) - 1
        for index, character in enumerate(run.text):
            origins.append(cursor)
            step = metrics.step(character, run.text[index + 1] if index < last else None)
            cursor += step * font_size
        placed.append(PlacedRun(run=run, metrics=metrics, scale=scale, origins=tuple(origins)))
    return placed


def border(core: PanelCore) -> list[tuple[tuple[float, float], ...]] | None:
    """The border of a panel that bleeds (#281): the sides that keep one, as open lines.

    Each run of neighbouring sides that keep a border is one line, from corner to corner
    clockwise, so a border that turns a corner is drawn as one stroke round it.

    Returns:
        The lines, none at all for a panel open on every side; or `None` for a panel that
        does not bleed, whose border is its whole frame, closed.
    """
    if not core.open:
        return None
    corners = core.outline or (
        (0.0, 0.0),
        (core.width, 0.0),
        (core.width, core.height),
        (0.0, core.height),
    )
    sides = (Side.TOP, Side.RIGHT, Side.BOTTOM, Side.LEFT)
    kept = [side not in core.open for side in sides]
    if not any(kept):
        return []
    # Start just after an open side, so no run is split where the list wraps round.
    start = next(index for index in range(4) if kept[index] and not kept[index - 1])
    runs: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for step in range(4):
        index = (start + step) % 4
        if kept[index]:
            current = current or [corners[index]]
            current.append(corners[(index + 1) % 4])
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return runs


def sfx_scale(effect: CoreSfx, metrics: FontMetrics) -> float:
    """Font units to panel units for a sound effect's letters."""
    return effect.font_size / metrics.units_per_em
