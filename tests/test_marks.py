"""Marks: a panel as the things drawn in it, in order, for every emitter alike (#80).

The SVG emitter used to work out, while writing text, where a burst's spikes go, how wide
a tail is where it leaves its balloon and where each letter lands. A second emitter -- the
print PDF -- must draw exactly the same shapes, so those numbers now come from
`scenet.emit.geometry`, and the order things are painted in from `scenet.emit.marks`.

The tests hold both to what the SVG has always drawn: for every gallery panel, the marks
are the SVG's painted elements one for one, in the same order and for the same owner.
"""

import math
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

import pytest
import yaml

from scenet.core import Box, CoreBalloon, CoreRun, PanelCore, Tail
from scenet.emit import geometry
from scenet.emit.marks import (
    Circle,
    Ellipse,
    Glyph,
    Line,
    Mark,
    Picture,
    Pointer,
    Polygon,
    Rect,
    Role,
    Segment,
    Veil,
    marks,
)
from scenet.emit.svg import fmt, render, typeface_of
from scenet.ir import BalloonKind, Face
from scenet.pipeline import Book, compile_book_file
from scenet.solve.text import Typeface, load_metrics

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
ENTRIES = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))["examples"]
IDS = [entry["file"] for entry in ENTRIES]

SVG = "{http://www.w3.org/2000/svg}"

#: The ids that make an element some mark's owner. A face's marks and its emanata have ids
#: of their own and belong to the actor whose group holds them.
OWNERS = ("mass-", "actor-", "sfx-", "balloon-", "caption-")


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _balloon(kind: BalloonKind, *, control: tuple[float, float] | None = None) -> CoreBalloon:
    return CoreBalloon(
        id="b1",
        speaker="bob",
        order=0,
        kind=kind,
        box=Box(x=100.0, y=50.0, width=240.0, height=90.0),
        lines=("HELLO",),
        font_size=30.0,
        line_height=36.0,
        tail=Tail(start=(220.0, 140.0), end=(260.0, 300.0), control=control),
    )


def _owner(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    node: ET.Element | None = element
    while node is not None:
        identifier = node.get("id", "")
        if identifier in {"image", "weather"} or identifier.startswith(OWNERS):
            return identifier
        node = parents.get(node)
    return "panel"


#: What each painted element says about how it is painted, inherited from its groups as SVG
#: inherits it: fill, stroke, stroke width, line cap, opacity and dash pattern.
Painting = tuple[str, str, str, str, str, str, str, str]

#: SVG's initial values, for an attribute no element or group sets.
INITIAL = {
    "fill": "#000000",
    "stroke": "none",
    "stroke-width": "1",
    "stroke-linecap": "butt",
    "fill-opacity": "1",
    "stroke-opacity": "1",
    "stroke-dasharray": "",
}


def _inherited(element: ET.Element, parents: dict[ET.Element, ET.Element], name: str) -> str:
    node: ET.Element | None = element
    while node is not None:
        value = node.get(name)
        if value is not None:
            return value
        node = parents.get(node)
    return INITIAL[name]


def _painted(svg: str) -> list[Painting]:
    """Each painted element of an SVG, in document order: its owner, tag and paint."""
    root = ET.fromstring(svg)
    parents = {child: parent for parent in root.iter() for child in parent}
    painted: list[Painting] = []

    def walk(element: ET.Element) -> None:
        for child in element:
            tag = child.tag.removeprefix(SVG)
            if tag in {"clipPath", "filter", "title"}:
                continue
            if tag == "g":
                walk(child)
                continue
            if tag == "rect" and child.get("filter"):
                continue
            if tag == "image":
                painted.append((_owner(child, parents), tag, "", "", "", "", "", ""))
                continue
            stroke = _inherited(child, parents, "stroke")
            # A line is never filled, whatever its group says.
            fill = "none" if tag == "line" else _inherited(child, parents, "fill")
            stroked = stroke != "none"
            painted.append(
                (
                    _owner(child, parents),
                    tag,
                    fill,
                    stroke,
                    _inherited(child, parents, "stroke-width") if stroked else "",
                    _inherited(child, parents, "stroke-linecap") if stroked else "",
                    _inherited(child, parents, "stroke-opacity" if stroked else "fill-opacity"),
                    _inherited(child, parents, "stroke-dasharray") if stroked else "",
                )
            )

    walk(root)
    return painted


def _drawn(core: PanelCore, family: Typeface) -> list[Painting]:
    drawn: list[Painting] = []
    for mark in marks(core, family):
        if mark.is_veil:
            continue
        if isinstance(mark.shape, Picture):
            drawn.append((mark.owner, mark.shape.tag, "", "", "", "", "", ""))
            continue
        stroked = mark.stroke is not None
        paint = mark.stroke if mark.stroke is not None else mark.fill
        drawn.append(
            (
                mark.owner,
                mark.shape.tag,
                mark.fill.colour if mark.fill is not None else "none",
                mark.stroke.colour if mark.stroke is not None else "none",
                fmt(mark.width) if stroked else "",
                ("round" if mark.rounded else "butt") if stroked else "",
                fmt(paint.opacity) if paint is not None else "1",
                " ".join(fmt(length) for length in mark.dash) if stroked else "",
            )
        )
    return drawn


class TestGeometry:
    """The numbers both emitters draw from."""

    def test_a_burst_alternates_long_and_short_spikes(self):
        box = Box(x=0.0, y=0.0, width=260.0, height=130.0)
        points = geometry.burst(box)
        spikes = max(10, int((box.width + box.height) / 26) * 2)
        assert len(points) == spikes * 2
        reach = [math.hypot((x - 130.0) / 130.0, (y - 65.0) / 65.0) for x, y in points]
        assert reach[0] == pytest.approx(1.22)
        assert reach[1] == pytest.approx(0.94)

    def test_a_pointer_is_as_wide_on_both_sides_of_its_start(self):
        pointer = geometry.pointer(_balloon(BalloonKind.SPEECH))
        (lx, ly), (rx, ry) = pointer.left, pointer.right
        assert ((lx + rx) / 2, (ly + ry) / 2) == pytest.approx((220.0, 140.0))
        assert pointer.tip == (260.0, 300.0)
        assert math.hypot(lx - rx, ly - ry) == pytest.approx(max(90.0 * 0.18, 30.0 * 0.35))

    def test_a_curved_pointer_keeps_its_control(self):
        assert geometry.pointer(_balloon(BalloonKind.SPEECH, control=(1.0, 2.0))).control == (
            1.0,
            2.0,
        )

    def test_thought_bubbles_shrink_towards_the_mouth(self):
        bubbles = geometry.thought_bubbles(_balloon(BalloonKind.THOUGHT))
        assert [r for _, _, r in bubbles] == pytest.approx([30.0 * 0.34, 30.0 * 0.25, 30.0 * 0.16])

    def test_lines_are_centred_in_their_box(self):
        padding, baselines = geometry.baselines(
            Box(x=0.0, y=10.0, width=100.0, height=100.0), 2, 30.0, 20.0
        )
        assert padding == 20.0
        assert baselines == [10.0 + 20.0 + 20.0 * 0.74, 10.0 + 20.0 + 30.0 + 20.0 * 0.74]

    def test_glyphs_advance_by_what_was_measured(self):
        family = Typeface()
        runs = (CoreRun(text="AVA", face=Face.REGULAR),)
        (placed,) = geometry.glyph_walk(runs, 5.0, 40.0, family)
        metrics = load_metrics()
        steps = [metrics.step("A", "V"), metrics.step("V", "A"), metrics.step("A", None)]
        assert placed.origins[0] == 5.0
        assert placed.origins[1] == pytest.approx(5.0 + steps[0] * 40.0)
        assert placed.origins[2] == pytest.approx(5.0 + (steps[0] + steps[1]) * 40.0)
        assert placed.scale == 40.0 / metrics.units_per_em


class TestRoles:
    """What each mark is, for an emitter that prints inks rather than colours."""

    def _marks(self, name: str) -> list[Mark]:
        book = _book(name)
        return [
            mark
            for result in book.panels.values()
            for mark in marks(result.core, typeface_of(result.core, fonts=book.fonts))
        ]

    def test_balloon_lettering_and_borders_are_ink_over_paper(self):
        drawn = list(self._marks("01-two-characters.panel.yaml"))
        balloons = [mark for mark in drawn if mark.owner.startswith("balloon-")]
        assert balloons
        for mark in balloons:
            if isinstance(mark.shape, Glyph):
                assert mark.fill is not None
                assert mark.fill.role is Role.INK
                assert mark.stroke is None
            else:
                assert mark.fill is not None
                assert mark.fill.role is Role.PAPER
                assert mark.stroke is not None
                assert mark.stroke.role is Role.INK

    def test_a_reversed_caption_is_solid_ink_lettered_in_paper(self):
        captions = [
            mark
            for mark in self._marks("22-caption-tones.panel.yaml")
            if mark.owner.startswith("caption-")
        ]
        boxes = [mark for mark in captions if isinstance(mark.shape, Rect)]
        assert any(mark.fill is not None and mark.fill.role is Role.SOLID for mark in boxes)
        assert any(
            isinstance(mark.shape, Glyph) and mark.fill is not None and mark.fill.role is Role.PAPER
            for mark in captions
        )

    def test_a_tinted_mass_keeps_its_grey_for_print(self):
        masses = [
            mark
            for mark in self._marks("40-tinted-hours.scene.yaml")
            if mark.owner.startswith("mass-")
        ]
        assert masses
        assert any(mark.fill is not None and mark.fill.colour != mark.fill.grey for mark in masses)
        assert all(mark.fill is not None and mark.fill.role is Role.MASS for mark in masses)

    def test_the_veil_is_a_mark_of_its_own(self):
        assert any(mark.is_veil for mark in self._marks("21-atmosphere.scene.yaml"))

    def test_shapes_are_the_known_kinds(self):
        kinds = (Rect, Circle, Ellipse, Polygon, Line, Segment, Pointer, Glyph, Picture, Veil)
        for entry in ENTRIES:
            assert all(isinstance(mark.shape, kinds) for mark in self._marks(entry["file"]))


@pytest.mark.parametrize("name", IDS)
def test_the_marks_are_what_the_svg_paints_in_order(name: str):
    book = _book(name)
    for result in book.panels.values():
        family = typeface_of(result.core, fonts=book.fonts)
        svg = render(result.core, fonts=book.fonts, aria=False, embed=book.images)
        assert _drawn(result.core, family) == _painted(svg)


@pytest.mark.parametrize("name", IDS)
def test_a_tinted_mark_keeps_its_grey_as_the_core_does(name: str):
    """Every paint's grey is the Core's grey: what `--mono` draws, and what print inks."""
    book = _book(name)
    for result in book.panels.values():
        family = typeface_of(result.core, fonts=book.fonts)
        mono = result.core.as_mono()
        tinted = [mark.fill.grey for mark in marks(result.core, family) if mark.fill is not None]
        greys = [mark.fill.colour for mark in marks(mono, family) if mark.fill is not None]
        assert tinted == greys


def test_snow_is_the_paper_falling():
    flecks = [
        mark
        for result in _book("21-atmosphere.scene.yaml").panels.values()
        for mark in marks(result.core, typeface_of(result.core))
        if mark.owner == "weather" and isinstance(mark.shape, Circle)
    ]
    assert flecks
    assert all(mark.fill is not None and mark.fill.role is Role.PAPER for mark in flecks)


def test_a_paper_caption_is_the_paper():
    captions = [
        mark
        for result in _book("22-caption-tones.panel.yaml").panels.values()
        for mark in marks(result.core, typeface_of(result.core))
        if mark.owner.startswith("caption-") and isinstance(mark.shape, Rect)
    ]
    assert {mark.fill.role for mark in captions if mark.fill is not None} == {
        Role.PAPER,
        Role.TONE,
        Role.SOLID,
    }
