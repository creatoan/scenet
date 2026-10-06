"""What every compiled panel must satisfy, whatever the input.

A solver has an enormous space of outputs and no obvious "correct" coordinate to assert
against, so what can be checked is that certain things are *never* true. These are those
things, in one place: the hand-written panels in `test_pipeline.py` and the generated
ones in `properties/` call the same functions, so the two can never disagree about what
a correct panel is.

Each check raises `AssertionError` naming the box at fault.
"""

import math
import re
from collections import Counter
from collections.abc import Iterable
from functools import cache
from xml.etree import ElementTree

from scenet.core import PanelCore
from scenet.geom import BBox
from scenet.solve.balloons import READING_EPSILON
from scenet.solve.text import DEFAULT_FONT_PATH, ITALIC_FONT_PATH, load_metrics

__all__ = [
    "TOLERANCE",
    "assert_lettering_is_placed",
    "assert_svg_is_sound",
    "lettered_boxes",
]

#: How far a Core box may stray past a limit. Core coordinates are rounded to two places
#: and the solver checks the unrounded ones, so a box exactly on the margin can land a
#: hundredth either side of it.
TOLERANCE = 0.02

#: The tail of a balloon must end this close to its speaker's face, as a multiple of the
#: face's radius. A tail that stops short gives the line no voice.
TAIL_REACH = 1.35


def lettered_boxes(core: PanelCore) -> list[tuple[str, int, BBox]]:
    """Every balloon and caption as `(id, reading order, box)`, in reading order."""
    boxes = [(balloon.id, balloon.order, balloon.box.as_bbox()) for balloon in core.balloons]
    boxes += [(caption.id, caption.order, caption.box.as_bbox()) for caption in core.captions]
    return sorted(boxes, key=lambda entry: entry[1])


def _inside(outer: BBox, inner: BBox) -> bool:
    return (
        inner.x >= outer.x - TOLERANCE
        and inner.y >= outer.y - TOLERANCE
        and inner.right <= outer.right + TOLERANCE
        and inner.bottom <= outer.bottom + TOLERANCE
    )


def _overlap(first: BBox, second: BBox) -> float:
    """Shared area beyond rounding: two boxes that merely touch share none."""
    return first.expanded(-TOLERANCE).overlap_area(second.expanded(-TOLERANCE))


def assert_lettering_is_placed(core: PanelCore, *, margin: float = 0.0) -> None:
    """Every balloon and caption is where the language promises it will be.

    - inside the panel's margin, which `PanelCore` does not record, so it is passed in
      from the authored document;
    - over no face, and under no exclusion such as an inset's clearance;
    - overlapping no other balloon or caption;
    - in reading order against **every** box read before it, not only the previous one;
    - and, for a balloon, with a tail that starts on it and ends at its speaker.

    Args:
        core: The compiled panel.
        margin: The panel's margin, as authored.
    """
    inner = BBox(margin, margin, core.width - 2 * margin, core.height - 2 * margin)
    faces = [actor.face_exclusion.as_circle() for actor in core.actors]
    exclusions = [box.as_bbox() for box in core.exclusions]
    boxes = lettered_boxes(core)

    for identifier, _, box in boxes:
        assert _inside(inner, box), f"{identifier} leaves the margin: {box} not in {inner}"
        for face in faces:
            shrunk = box.expanded(-TOLERANCE)
            assert not shrunk.intersects_circle(face), f"{identifier} covers a face"
        for exclusion in exclusions:
            assert _overlap(box, exclusion) == 0, f"{identifier} is under an exclusion"

    for index, (identifier, _, box) in enumerate(boxes):
        for earlier_id, _, earlier in boxes[:index]:
            assert _overlap(box, earlier) == 0, f"{identifier} overlaps {earlier_id}"
            below = box.y >= earlier.y - READING_EPSILON - TOLERANCE
            right_of = box.x >= earlier.right - READING_EPSILON - TOLERANCE
            assert below or right_of, f"{identifier} reads before {earlier_id}"

    for balloon in core.balloons:
        start = balloon.tail.start
        around = balloon.box.as_bbox().expanded(1.5)
        assert around.x <= start[0] <= around.right, f"tail of {balloon.id} starts off it"
        assert around.y <= start[1] <= around.bottom, f"tail of {balloon.id} starts off it"
        face = core.actor(balloon.speaker).face_exclusion.as_circle()
        end = balloon.tail.end
        distance = math.hypot(end[0] - face.cx, end[1] - face.cy)
        assert distance <= face.r * TAIL_REACH, f"tail of {balloon.id} misses its speaker"


# `url(#id)` in a style or presentation attribute, and `href="#id"` on a <use>.
_URL_REFERENCE = re.compile(r"url\(#([^)]+)\)")
_HREF_REFERENCE = re.compile(r'href="#([^"]+)"')
# A glyph outline: flipped by `scale(s -s)`, which is how glyphs are told apart from any
# other transformed path.
_GLYPH_SCALE = re.compile(r"scale\(([0-9.]+) -([0-9.]+)\)")
_NON_FINITE = re.compile(r"\b(nan|inf|infinity)\b", re.IGNORECASE)


@cache
def _units_per_em() -> frozenset[float]:
    return frozenset(
        load_metrics(str(path)).units_per_em for path in (DEFAULT_FONT_PATH, ITALIC_FONT_PATH)
    )


def _ids(root: ElementTree.Element) -> list[str]:
    return [element.attrib["id"] for element in root.iter() if "id" in element.attrib]


def assert_svg_is_sound(
    svg: str, *, size: tuple[float, float], font_sizes: Iterable[float] = ()
) -> None:
    """An emitted SVG parses, holds together and draws what was measured.

    - it parses as XML;
    - every `id` is unique, and every `url(#…)` and `href="#…"` names one of them;
    - no number in it is `nan` or `inf`;
    - the root `viewBox` is the panel's size;
    - and every glyph is drawn at exactly the scale it was measured at, `font_size /
      unitsPerEm`, so lettering is the size its box was made for.

    Args:
        svg: The document.
        size: `(width, height)` the `viewBox` must match.
        font_sizes: The type sizes the panel's balloons and captions were measured at.
            Every glyph's scale must come from one of them.
    """
    root = ElementTree.fromstring(svg)

    ids = _ids(root)
    repeated = [name for name, count in Counter(ids).items() if count > 1]
    assert not repeated, f"ids are repeated: {repeated}"
    defined = set(ids)
    for pattern in (_URL_REFERENCE, _HREF_REFERENCE):
        for name in pattern.findall(svg):
            assert name in defined, f"#{name} is referenced but never defined"

    # Attributes only: the words of live text are free to say "inf".
    for element in root.iter():
        for name, value in element.attrib.items():
            assert not _NON_FINITE.search(value), f"{name}={value!r} is not finite"

    view_box = [float(part) for part in root.attrib["viewBox"].split()]
    assert view_box[2:] == [round(value, 2) for value in size], f"viewBox {view_box} is not {size}"

    scales = {round(font_size / units, 6) for font_size in font_sizes for units in _units_per_em()}
    for first, second in _GLYPH_SCALE.findall(svg):
        assert first == second, f"a glyph is scaled unevenly: {first} by {second}"
        assert any(abs(float(first) - scale) <= 1e-6 for scale in scales), (
            f"a glyph is drawn at scale {first}, but lettering was measured at {sorted(scales)}"
        )
