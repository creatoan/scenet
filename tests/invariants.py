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

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon
from shapely.geometry import box as rectangle

from scenet.core import CoreFrame, PageCore, PanelCore
from scenet.geom import BBox
from scenet.solve.balloons import READING_EPSILON
from scenet.solve.text import SHIPPED_FACES, load_metrics

__all__ = [
    "TOLERANCE",
    "assert_effects_are_placed",
    "assert_frames_are_placed",
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
        end = balloon.tail.end
        if balloon.off_panel is not None:
            # Nobody drawn to point at: the tail ends on the frame, on the speaker's side.
            assert _on_the_frame(core, end), f"tail of {balloon.id} stops short of the frame"
            continue
        face = core.actor(balloon.speaker).face_exclusion.as_circle()
        distance = math.hypot(end[0] - face.cx, end[1] - face.cy)
        assert distance <= face.r * TAIL_REACH, f"tail of {balloon.id} misses its speaker"


def assert_words_are_carried(core: PanelCore, *, description: str | None = None) -> None:
    """The panel carries the words it is read in, and each item its own.

    - a description, which is the author's when one was written;
    - a label on every balloon, caption and sound effect, holding what it letters --
      a spoken caption's quotation marks aside, since they are lettering, not speech;
    - and every label is a sentence, so two in a row are heard as two.
    """
    assert core.description, "a compiled panel has a description"
    if description is not None:
        assert core.description == " ".join(description.split())
    items = [*core.balloons, *core.captions]
    for item in items:
        assert item.label, f"{item.id} has no label"
        lettered = " ".join(item.lines).strip("“”")
        assert lettered.rstrip(".") in item.label, f"{item.id}: {item.label!r} lacks {lettered!r}"
    for effect in core.sfx:
        assert effect.label, f"{effect.id} has no label"
        assert effect.text in effect.label
    for item in (*items, *core.sfx):
        assert item.label is not None
        closed = item.label.rstrip("\"'”\u2019»)]")
        assert closed[-1:] in tuple(".!?…—\u2013-"), item.label


def _on_the_frame(core: PanelCore, point: tuple[float, float]) -> bool:
    """Whether a point lies on the panel's edge: its outline when it has one, else its
    rectangle."""
    corners = core.outline or (
        (0.0, 0.0),
        (core.width, 0.0),
        (core.width, core.height),
        (0.0, core.height),
    )
    return Polygon(corners).exterior.distance(ShapelyPoint(point)) <= TOLERANCE


def assert_effects_are_placed(core: PanelCore, *, margin: float = 0.0) -> None:
    """Every sound effect is where the language promises it will be.

    - inside the panel's margin, and inside its outline when it has one;
    - over no face, and under no exclusion such as an inset;
    - overlapping no other sound effect;
    - and with one letter for every character of its text, once runs of spaces are one.

    Args:
        core: The compiled panel.
        margin: The panel's margin, as authored.
    """
    inner = rectangle(margin, margin, core.width - margin, core.height - margin).buffer(TOLERANCE)
    outline = Polygon(core.outline).buffer(TOLERANCE) if core.outline is not None else None
    zones = [(effect.id, Polygon(effect.zone)) for effect in core.sfx]
    for effect, (identifier, zone) in zip(core.sfx, zones, strict=True):
        assert inner.contains(zone), f"{identifier} leaves the margin"
        assert outline is None or outline.contains(zone), f"{identifier} leaves the outline"
        for actor in core.actors:
            face = actor.face_exclusion
            reach = zone.distance(ShapelyPoint(face.cx, face.cy))
            assert reach >= face.r - TOLERANCE, f"{identifier} covers {actor.id}'s face"
        for area in core.exclusions:
            covered = zone.intersection(rectangle(area.x, area.y, area.right, area.bottom)).area
            assert covered <= TOLERANCE, f"{identifier} is under an exclusion"
        assert "".join(glyph.char for glyph in effect.glyphs) == " ".join(effect.text.split())
    for index, (identifier, zone) in enumerate(zones):
        for other_id, other in zones[:index]:
            shared = zone.intersection(other).area
            assert shared <= TOLERANCE * 100, f"{identifier} overlaps {other_id} by {shared}"


# `url(#id)` in a style or presentation attribute; `href="#id"` on a <use> is read as an
# attribute.
_URL_REFERENCE = re.compile(r"url\(#([^)]+)\)")
# A glyph outline: flipped by `scale(s -s)`, which is how glyphs are told apart from any
# other transformed path.
_GLYPH_SCALE = re.compile(r"scale\(([0-9.]+) -([0-9.]+)\)")
_NON_FINITE = re.compile(r"\b(nan|inf|infinity)\b", re.IGNORECASE)


@cache
def _units_per_em() -> frozenset[float]:
    return frozenset(load_metrics(str(path)).units_per_em for path in SHIPPED_FACES.values())


def _ids(root: ElementTree.Element) -> list[str]:
    return [element.attrib["id"] for element in root.iter() if "id" in element.attrib]


def assert_svg_is_sound(
    svg: str, *, size: tuple[float, float] | None = None, font_sizes: Iterable[float] = ()
) -> None:
    """An emitted SVG parses, holds together and draws what was measured.

    - it parses as XML;
    - every `id` is unique, and every `url(#…)`, `href="#…"` and `aria-labelledby` names
      one of them -- read from attributes, so words in a `<desc>` cannot pass for one;
    - no number in it is `nan` or `inf`;
    - the root `viewBox` is the panel's size;
    - and every glyph is drawn at exactly the scale it was measured at, `font_size /
      unitsPerEm`, so lettering is the size its box was made for.

    Args:
        svg: The document.
        size: `(width, height)` the `viewBox` must match, or `None` for a document --
            a strip, several pages -- whose size is the sum of its parts.
        font_sizes: The type sizes the panel's balloons and captions were measured at.
            Every glyph's scale must come from one of them.
    """
    root = ElementTree.fromstring(svg)

    ids = _ids(root)
    repeated = [name for name, count in Counter(ids).items() if count > 1]
    assert not repeated, f"ids are repeated: {repeated}"
    defined = set(ids)
    # Attributes only, here and below: the words of live text, a title and a desc are
    # free to say "inf", or "url(#x)", or "scale(2 -2)".
    for element in root.iter():
        for attribute, value in element.attrib.items():
            named = _URL_REFERENCE.findall(value)
            if attribute.endswith("href") and value.startswith("#"):
                named.append(value[1:])
            for name in named:
                assert name in defined, f"#{name} is referenced but never defined"
        for name in element.get("aria-labelledby", "").split():
            assert name in defined, f"aria-labelledby names #{name}, which is never defined"

    for element in root.iter():
        for name, value in element.attrib.items():
            # A link is not a number, and base64 can spell `inf` as readily as anything.
            if name.endswith("href"):
                continue
            assert not _NON_FINITE.search(value), f"{name}={value!r} is not finite"

    if size is not None:
        view_box = [float(part) for part in root.attrib["viewBox"].split()]
        expected = [round(value, 2) for value in size]
        assert view_box[2:] == expected, f"viewBox {view_box} is not {size}"

    scales = {round(font_size / units, 6) for font_size in font_sizes for units in _units_per_em()}
    transforms = " ".join(element.get("transform", "") for element in root.iter())
    for first, second in _GLYPH_SCALE.findall(transforms):
        assert first == second, f"a glyph is scaled unevenly: {first} by {second}"
        assert any(abs(float(first) - scale) <= 1e-6 for scale in scales), (
            f"a glyph is drawn at scale {first}, but lettering was measured at {sorted(scales)}"
        )


_SVG = "{http://www.w3.org/2000/svg}"


def accessible_name(element: ElementTree.Element, root: ElementTree.Element | None = None) -> str:
    """The name accname 1.2 gives an SVG element, as far as Scenet's output needs it.

    `aria-labelledby` first (step 2B): the text of each element it names, in its order,
    joined by spaces -- looked up in `root`, the whole document, when given. Otherwise the
    element's own `<title>` child, as SVG-AAM names an SVG element.
    """
    document = root if root is not None else element
    named = element.get("aria-labelledby", "").split()
    if named:
        found = {e.get("id"): e for e in document.iter() if e.get("id") is not None}
        return " ".join("".join(found[name].itertext()) for name in named)
    title = element.find(f"{_SVG}title")
    return "".join(title.itertext()) if title is not None else ""


def without_access(svg: str) -> str:
    """An SVG with everything accessible output adds taken out again, as text.

    `role`, `aria-labelledby` and `aria-hidden` attributes, and each `<title>` and `<desc>`
    line. What is left must be exactly what `aria=False` writes.
    """
    svg = re.sub(r' role="[^"]*"| aria-labelledby="[^"]*"| aria-hidden="true"', "", svg)
    return re.sub(r"\n *<(title|desc)\b[^>]*>[^<]*</\1>", "", svg)


def assert_accessible(svg: str, core: PanelCore) -> None:
    """A panel is one image, named with what it shows and then its words, in reading order.

    - the root is `role="img"`, named by its one `<title>`, its first child;
    - the name is the description, then every balloon, caption and sound effect's label in
      `order` -- sound effects too, though they are painted under every balloon;
    - and nothing gives it a description to be read as well: no `<desc>`, no
      `aria-labelledby` or `aria-describedby`, which NVDA read a second time.
    """
    root = ElementTree.fromstring(svg)
    assert root.get("role") == "img", "a panel is an image"
    items = sorted([*core.balloons, *core.captions, *core.sfx], key=lambda item: item.order)
    words = [item.label for item in items if item.label]
    expected = " ".join([*([core.description] if core.description else []), *words])
    assert expected, "a panel with no words has nothing to be named by"
    assert next(iter(root)).tag == f"{_SVG}title"
    assert accessible_name(root) == expected
    assert root.find(f".//{_SVG}desc") is None
    for attribute in ("aria-labelledby", "aria-describedby"):
        assert root.get(attribute) is None, attribute


def _shape(frame: CoreFrame) -> Polygon:
    """A frame's drawn shape: its outline in a slanted tier, its rectangle otherwise."""
    if frame.outline is not None:
        return Polygon(frame.outline)
    return rectangle(frame.x, frame.y, frame.x + frame.width, frame.y + frame.height)


def assert_frames_are_placed(page: PageCore, *, margin: float) -> None:
    """Every frame on a page is inside its margins and clear of every other frame.

    The one exception is an inset, which lies wholly inside the panel it is set into.
    Frames are compared as the shapes they are drawn as, so the neighbours in a slanted
    tier, whose bounding boxes overlap, are held to their shared cut.

    Args:
        page: The compiled page.
        margin: The page's margin, as authored.
    """
    inner = rectangle(margin, margin, page.width - margin, page.height - margin).buffer(TOLERANCE)
    shapes = {frame.panel: _shape(frame) for frame in page.frames}
    parents = {frame.panel: frame.inset_of for frame in page.frames}
    for name, shape in shapes.items():
        assert inner.contains(shape), f"frame {name} leaves the page margins"
        parent = parents[name]
        if parent is not None:
            assert shapes[parent].buffer(TOLERANCE).contains(shape), f"inset {name} leaves {parent}"
    names = list(shapes)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            if first in (parents[second],) or second in (parents[first],):
                continue
            shared = shapes[first].intersection(shapes[second]).area
            assert shared <= TOLERANCE, f"frames {first} and {second} overlap by {shared}"
