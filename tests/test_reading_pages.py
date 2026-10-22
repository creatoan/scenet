"""Pages and strips read right to left (#68).

A tier's panels are written in reading order, as ever, and read right to left the first is
at the right. The same arithmetic lays the tier out, over its panels in the other order, so
every frame is the one a left-to-right page gives that panel with the tier reversed -- and a
slanted gutter leans the way it was written, since the page is not mirrored. An inset's
corner is a corner of the page. Every document is written in reading order, which is the
order a screen reader follows.
"""

import math
from xml.etree import ElementTree

import pytest

from scenet import Direction
from scenet.core import PageCore, PanelCore
from scenet.emit.page import render_page, render_pages
from scenet.emit.strip import reading_direction, render_strip
from scenet.pipeline import Book, compile_book

SVG = "{http://www.w3.org/2000/svg}"

CAST = """\
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
"""

# Usable area 1080 x 1680, as in tests/test_page.py: the first tier is 410 tall and its
# 1050 is split 1 : 2.
PAGE = (
    "page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}\n"
    + CAST
    + """pages:
  - tiers:
      - {height: 1, panels: [wide, {use: tall, width: 2}]}
      - {height: 3, panels: [last]}
panels:
  wide: {camera: {shot: full_shot}, script: [{say: {by: alice, text: "Hello."}}]}
  tall: {over: wide, camera: {shot: medium_shot}}
  last: {over: wide, camera: {shot: close_up}, script: [{say: {by: bob, text: "Hi."}}]}
"""
)


def _rtl(text: str) -> str:
    return "direction: rtl\n" + text


def _frames(page: PageCore) -> dict[str, tuple[float, float, float, float]]:
    return {frame.panel: (frame.x, frame.y, frame.width, frame.height) for frame in page.frames}


def _first(text: str) -> PageCore:
    return compile_book(text).pages[0]


class TestATierOfPanels:
    def test_the_first_panel_is_at_the_right(self):
        frames = _frames(_first(_rtl(PAGE)))
        assert frames["wide"] == (790.0, 60.0, 350.0, 410.0)
        assert frames["tall"] == (60.0, 60.0, 700.0, 410.0)

    def test_the_frames_are_still_listed_in_reading_order(self):
        assert [frame.panel for frame in _first(_rtl(PAGE)).frames] == ["wide", "tall", "last"]

    def test_each_frame_is_the_mirror_of_its_left_to_right_frame(self):
        ltr, rtl = _frames(_first(PAGE)), _frames(_first(_rtl(PAGE)))
        for name, (x, y, width, height) in ltr.items():
            assert rtl[name] == pytest.approx((1200 - x - width, y, width, height), abs=0.01)

    def test_every_panel_is_compiled_at_the_size_it_had(self):
        """The page decides where a frame is; its size, and so the art in it, is the same."""
        ltr, rtl = compile_book(PAGE), compile_book(_rtl(PAGE))
        for name, result in ltr.panels.items():
            mine = rtl.panels[name].core
            assert (mine.width, mine.height) == (result.core.width, result.core.height)
            assert mine.actors == result.core.actors


COLUMNS = (
    "page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}\n"
    + CAST
    + """pages:
  - tiers:
      - columns:
          - {panels: [above, below]}
          - {panels: [falling]}
panels:
  above: {}
  below: {}
  falling: {}
"""
)


class TestAColumnBesideAStack:
    def test_the_first_column_is_at_the_right_and_read_down(self):
        page = _first(_rtl(COLUMNS))
        assert [frame.panel for frame in page.frames] == ["above", "below", "falling"]
        frames = _frames(page)
        assert frames["above"][0] == frames["below"][0] > frames["falling"][0]
        assert frames["above"][1] < frames["below"][1]


INSETS = (
    "page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}\n"
    + CAST
    + """pages:
  - tiers:
      - panels:
          - use: street
            insets:
              - {use: clock, at: top_left, size: 0.2, read: before}
              - {use: face, at: bottom_right, size: 0.3}
          - door
panels: {street: {}, clock: {}, face: {}, door: {}}
"""
)


class TestAnInset:
    def test_its_corner_is_a_corner_of_the_page(self):
        page = _first(_rtl(INSETS))
        frames = _frames(page)
        street, clock, face = frames["street"], frames["clock"], frames["face"]
        assert clock[0] == pytest.approx(street[0] + 30)
        assert face[0] + face[2] == pytest.approx(street[0] + street[2] - 30)

    def test_it_is_read_as_it_says(self):
        page = _first(_rtl(INSETS))
        assert [frame.panel for frame in page.frames] == ["clock", "street", "face", "door"]
        assert _frames(page)["street"][0] > _frames(page)["door"][0]


SLANT = """\
page: {size: [1060, 660], margin: 30, gutter: 40, tier_gutter: 40}
cast: {x: {reference: alice}}
pages: [{tiers: [{slant: 10, panels: [punch, {use: impact, width: 2}]}]}]
panels: {punch: {}, impact: {}}
"""


def _outline(page: PageCore, name: str) -> tuple[tuple[float, float], ...]:
    frame = next(frame for frame in page.frames if frame.panel == name)
    assert frame.outline is not None
    return frame.outline


class TestASlantedTier:
    def test_it_leans_the_way_it_was_written(self):
        """Positive leans the top of each gutter right, read either way: never mirrored."""
        page = _first(_rtl(SLANT))
        (_, top_right, bottom_right, _) = _outline(page, "impact")
        assert top_right[0] > bottom_right[0]

    def test_its_frames_are_the_left_to_right_frames_of_the_tier_reversed(self):
        rtl = _first(_rtl(SLANT))
        reversed_tier = SLANT.replace(
            "[punch, {use: impact, width: 2}]", "[{use: impact, width: 2}, punch]"
        )
        ltr = _first(reversed_tier)
        assert {frame.panel: frame for frame in rtl.frames} == {
            frame.panel: frame for frame in ltr.frames
        }
        assert [frame.panel for frame in rtl.frames] == ["punch", "impact"]

    def test_the_first_panel_is_at_the_right(self):
        page = _first(_rtl(SLANT))
        assert _frames(page)["punch"][0] > _frames(page)["impact"][0]


def _root(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


def _panels(root: ElementTree.Element) -> list[tuple[str, float]]:
    """Each panel group's name and the x it is placed at, in document order."""
    placed: list[tuple[str, float]] = []
    for group in root.iter(f"{SVG}g"):
        identifier = group.get("id") or ""
        if identifier.startswith("panel-"):
            transform = group.get("transform") or ""
            x = float(transform.removeprefix("translate(").split()[0])
            placed.append((identifier.removeprefix("panel-"), x))
    return placed


def _cores(book: Book) -> dict[str, PanelCore]:
    return {name: result.core for name, result in book.panels.items()}


class TestTheDocuments:
    def test_a_page_writes_its_panels_in_reading_order_from_the_right(self):
        book = compile_book(_rtl(PAGE))
        placed = _panels(_root(render_page(book.pages[0], _cores(book))))
        assert [name for name, _ in placed] == ["wide", "tall", "last"]
        assert placed[0][1] > placed[1][1]

    def test_each_panel_s_title_reads_its_words_in_order(self):
        book = compile_book(_rtl(PAGE))
        root = _root(render_page(book.pages[0], _cores(book)))
        titles = [
            group.findtext(f"{SVG}title") or ""
            for group in root.iter(f"{SVG}g")
            if (group.get("id") or "").startswith("panel-")
        ]
        assert titles[0].endswith("Alice: Hello.")
        assert titles[2].endswith("Bob: Hi.")

    def test_a_strip_lays_its_panels_right_to_left(self):
        book = compile_book(_rtl(PAGE))
        placed = _panels(_root(render_strip(list(_cores(book).items()))))
        assert [name for name, _ in placed] == ["wide", "tall", "last"]
        xs = [x for _, x in placed]
        assert xs == sorted(xs, reverse=True)

    def test_a_left_to_right_strip_is_unchanged(self):
        book = compile_book(PAGE)
        xs = [x for _, x in _panels(_root(render_strip(list(_cores(book).items()))))]
        assert xs == sorted(xs)

    def test_pages_side_by_side_start_at_the_right(self):
        two = _rtl(PAGE).replace(
            "      - {height: 3, panels: [last]}\n",
            "  - tiers:\n      - {height: 3, panels: [last]}\n",
        )
        book = compile_book(two)
        root = _root(render_pages(book.pages, _cores(book)))
        pages = [
            group for group in root.iter(f"{SVG}g") if (group.get("id") or "").startswith("page-")
        ]
        assert [group.get("id") for group in pages] == ["page-1", "page-2"]
        first, second = (
            float((group.get("transform") or "").removeprefix("translate(").split()[0])
            for group in pages
        )
        assert first > second == 0.0

    def test_a_strip_reads_one_way(self):
        ltr = compile_book(PAGE).panels["wide"].core
        rtl = compile_book(_rtl(PAGE)).panels["wide"].core
        with pytest.raises(ValueError, match="one direction"):
            render_strip([("a", ltr), ("b", rtl)])

    def test_pages_read_one_way(self):
        ltr, rtl = compile_book(PAGE), compile_book(_rtl(PAGE))
        with pytest.raises(ValueError, match="one direction"):
            render_pages([ltr.pages[0], rtl.pages[0]], {**_cores(ltr)})

    def test_a_page_core_says_which_way_it_is_read(self):
        assert _first(_rtl(PAGE)).direction is Direction.RTL
        assert _first(PAGE).direction is Direction.LTR
        assert math.isclose(_first(_rtl(PAGE)).width, _first(PAGE).width)


class TestTwoDirectionsAreRefusedByName:
    """Laying out panels or pages read two ways has no answer, so the refusal says which
    two -- every word of it, since an author reads it to find the panel at fault."""

    def test_a_strip(self):
        ltr = compile_book(PAGE).panels["wide"].core
        rtl = compile_book(_rtl(PAGE)).panels["wide"].core
        with pytest.raises(ValueError, match="one direction") as raised:
            render_strip([("a", ltr), ("b", rtl)])
        assert str(raised.value) == (
            "a strip's panels are read in one direction, and these are read ltr and rtl"
        )

    def test_pages(self):
        ltr, rtl = compile_book(PAGE), compile_book(_rtl(PAGE))
        with pytest.raises(ValueError, match="one direction") as raised:
            render_pages([ltr.pages[0], rtl.pages[0]], _cores(ltr))
        assert (
            str(raised.value) == "pages are read in one direction, and these are read ltr and rtl"
        )

    def test_nothing_to_lay_out_reads_the_default_way(self):
        assert reading_direction([], "nothing") is Direction.LTR
