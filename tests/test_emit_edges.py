"""The emitters at the edges the gallery never reaches.

Mutation testing found these unchecked (#95). The golden outputs pin every byte the gallery
produces, so what survived is what the gallery never produces: several pages side by side,
a curved tail, a gaze that is not level, a limb thinner than its outline. A Core is a
format people hand-edit, and the emitters must draw whatever it says, so several tests
below edit a compiled one.
"""

import math
import re
from xml.etree import ElementTree

import pytest

from scenet import compile_book, compile_source
from scenet.core import PanelCore
from scenet.emit.debug_svg import GAZE, render_debug
from scenet.emit.page import PAGE_SPACING_FRACTION, render_page, render_pages
from scenet.emit.strip import render_strip
from scenet.emit.svg import FIGURE_STROKE_WIDTH, FILL_FIGURE, fmt, render
from scenet.pipeline import Book

SPEECH = "cast: {a: {reference: alice}}\nscript:\n  - say: {by: a, text: Over here.}\n"

#: Three pages of one format, 1000 wide: two panels on the first, one on each of the rest.
THREE_PAGES = """
cast: {a: {reference: alice}}
script:
  - say: {by: a, text: Over here.}
page: {size: [1000, 1500]}
pages:
  - tiers: [{panels: [one, two]}]
  - tiers: [{panels: [three]}]
  - tiers: [{panels: [four]}]
panels: {one: {}, two: {}, three: {}, four: {}}
"""


@pytest.fixture(scope="module")
def book() -> Book:
    return compile_book(THREE_PAGES)


def _cores(book: Book) -> dict[str, PanelCore]:
    return {name: result.core for name, result in book.panels.items()}


def _assert_no_stray_text(svg: str) -> None:
    """Character data only inside `<text>`: anything else between elements is litter."""
    for element in ElementTree.fromstring(svg).iter():
        if not element.tag.endswith("text"):
            assert not (element.text or "").strip(), element.text
        assert not (element.tail or "").strip(), element.tail


class TestPagesSideBySide:
    def test_the_document_is_every_page_and_the_spaces_between(self, book: Book):
        spacing = 1000 * PAGE_SPACING_FRACTION
        root = ElementTree.fromstring(render_pages(book.pages, _cores(book)))
        assert root.get("width") == fmt(3 * 1000 + 2 * spacing)

    def test_each_page_starts_where_the_last_one_and_its_space_end(self, book: Book):
        svg = render_pages(book.pages, _cores(book))
        placed = re.findall(r'<g id="(page-\d+)" transform="translate\(([\d.-]+) 0\)">', svg)
        assert placed == [("page-1", "0"), ("page-2", "1050"), ("page-3", "2100")]

    def test_panel_positions_count_on_across_pages(self, book: Book):
        svg = render_pages(book.pages, _cores(book))
        assert re.findall(r'<clipPath id="(p\d+)-frame">', svg) == ["p1", "p2", "p3", "p4"]

    def test_it_starts_as_every_document_does(self, book: Book):
        svg = render_pages(book.pages, _cores(book))
        assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')

    def test_it_holds_no_stray_text(self, book: Book):
        _assert_no_stray_text(render_pages(book.pages, _cores(book)))

    def test_by_default_lettering_is_outlined_and_no_overlay_is_drawn(self, book: Book):
        together = render_pages(book.pages, _cores(book))
        alone = render_page(book.pages[0], _cores(book))
        assert "<text" not in together
        assert "<text" not in alone
        assert "debug-a" not in together

    def test_live_text_and_overlays_reach_every_page(self, book: Book):
        assert "<text" in render_pages(book.pages, _cores(book), live_text=True)
        assert 'id="p4-debug-a"' in render_pages(book.pages, _cores(book), debug=True)


class TestAStrip:
    def test_by_default_lettering_is_outlined(self):
        core = compile_source(SPEECH).core
        assert "<text" not in render_strip([("one", core), ("two", core)])


@pytest.fixture(scope="module")
def edited() -> PanelCore:
    """A compiled panel, edited as a person might edit its Core: a curved tail on a
    diagonal chord, a gaze tilted down, and a first limb four units thick."""
    core = compile_source(SPEECH).core
    balloon = core.balloons[0]
    tail = balloon.tail.model_copy(
        update={"start": (100.0, 140.0), "end": (200.0, 260.0), "control": (180.0, 120.0)}
    )
    actor = core.actors[0]
    capsule = actor.capsules[0].model_copy(update={"width": 4.0})
    actor = actor.model_copy(
        update={"gaze": (0.6, 0.8), "capsules": (capsule, *actor.capsules[1:])}
    )
    return core.model_copy(
        update={
            "balloons": (balloon.model_copy(update={"tail": tail}), *core.balloons[1:]),
            "actors": (actor, *core.actors[1:]),
        }
    )


class TestTheOverlayDrawsWhatTheCoreSays:
    def test_a_curved_tail_is_drawn_through_its_control_point(self, edited: PanelCore):
        assert 'd="M100 140 Q180 120 200 260"' in render_debug(edited)

    def test_a_curved_tail_is_labelled_curved(self, edited: PanelCore):
        balloon = edited.balloons[0]
        label = f"{balloon.id} #{balloon.order} -&gt; {balloon.speaker} curved</text>"
        assert label in render_debug(edited)

    def test_a_tilted_gaze_is_drawn_tilted(self, edited: PanelCore):
        actor = edited.actors[0]
        eyes = actor.anchors["eyes"]
        reach = actor.face_exclusion.r * 3.0
        x2, y2 = fmt(eyes[0] + 0.6 * reach), fmt(eyes[1] + 0.8 * reach)
        assert f'x2="{x2}" y2="{y2}" stroke="{GAZE}"' in render_debug(edited)


class TestThePanelDrawsWhatTheCoreSays:
    def test_a_curved_tail_straddles_its_start_square_to_its_chord(self, edited: PanelCore):
        """The tail's root is a base laid across the chord at its start: its two ends are
        either side of the start, and the line between them is square to the chord."""
        number = r"([\d.-]+)"
        shape = re.search(
            rf'd="M{number} {number} Q[\d.-]+ [\d.-]+ [\d.-]+ [\d.-]+ '
            rf'Q[\d.-]+ [\d.-]+ {number} {number} Z"',
            render(edited),
        )
        assert shape is not None
        x1, y1, x2, y2 = (float(value) for value in shape.groups())
        assert ((x1 + x2) / 2, (y1 + y2) / 2) == pytest.approx((100.0, 140.0), abs=0.02)
        across = math.hypot(x1 - x2, y1 - y2)
        assert across > 1.0
        cosine = ((x1 - x2) * 100.0 + (y1 - y2) * 120.0) / (across * math.hypot(100.0, 120.0))
        assert cosine == pytest.approx(0.0, abs=1e-3)

    def test_a_limb_thinner_than_its_outline_keeps_a_unit_of_fill(self, edited: PanelCore):
        """Four units thick with a three-unit outline each side leaves nothing inside, so
        the fill is drawn one unit wide rather than vanishing."""
        capsule = edited.actors[0].capsules[0]
        assert 4.0 - 2 * FIGURE_STROKE_WIDTH < 1.0
        (x1, y1), (x2, y2) = capsule.start, capsule.end
        fill = (
            f'<path d="M{fmt(x1)} {fmt(y1)} L{fmt(x2)} {fmt(y2)}" '
            f'fill="none" stroke="{FILL_FIGURE}" stroke-width="1"/>'
        )
        assert fill in render(edited)


class TestPaintersOrder:
    def test_a_figure_in_front_is_drawn_after_whatever_its_name(self):
        svg = render(
            compile_source(
                "cast:\n  a: {reference: alice}\n  z: {reference: bob}\n"
                "staging:\n  - a in_front_of z\n"
            ).core
        )
        assert svg.index('id="actor-z"') < svg.index('id="actor-a"')

    def test_figures_at_one_depth_are_drawn_in_order_of_their_ids(self):
        """`a` before `a!`, as strings sort -- though the rendered group for `a!` would
        sort first, since `!` comes before the closing quote."""
        svg = render(
            compile_source('cast:\n  a: {reference: alice}\n  "a!": {reference: bob}\n').core
        )
        assert svg.index('id="actor-a"') < svg.index('id="actor-a!"')
