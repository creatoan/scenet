"""The numbers every emitter draws from, where Panel Core names a shape but not its points.

Panel Core says a balloon is a shout in this box with its tail from here to there; it does
not list a burst's spikes or the two corners where a tail leaves its balloon. Those follow
from the Core by arithmetic alone. Where each letter of a line lands is not here: Panel Core
says it, and an emitter only looks the outline up. Two emitters
-- the SVG and the print PDF -- must draw exactly the same ones. So they are worked
out here, once, and each emitter only writes them down in its own format.

Nothing here decides anything: every position was the solver's, and these are its shapes
spelt out. Each expression keeps the order of operations it had inside the SVG emitter,
so the floats -- and the SVG written from them -- are what they always were.
"""

import math
from dataclasses import dataclass

from scenet.core import Box, CoreBalloon, PanelCore
from scenet.ir import Side

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


def border(core: PanelCore) -> list[tuple[tuple[float, float], ...]] | None:
    """The border of a panel that bleeds: the sides that keep one, as open lines.

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
