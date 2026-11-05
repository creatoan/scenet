"""Panels that bleed past the trim (#281): their frames, their staging and their lettering.

A bleeding panel's frame runs out to the bleed line on each side that reaches the page's
margin. Three boxes follow from that: the **bled frame**, which is the panel's size and what
its art covers; the **visible frame**, out to the trim, where its cast is staged and framed,
so the trim never cuts a shot; and its **lettering box**, the frame as it was before bleeding
and inset by the panel's margin, so the page margin stays the live area.

The authored key comes last, with the gallery example that writes it; until then these tests
reach the layout through `resolve_frames(bleeds=...)`, the argument the key will fill.
"""

import pytest

from scenet.core import Box
from scenet.errors import RuleViolationError
from scenet.frontends.yaml_front import parse_scene, parse_scene_document
from scenet.geom import BBox
from scenet.ir import Direction, PageFormat, PageSpec, PanelSpec, Side
from scenet.pipeline import _compile_document, compile_ir
from scenet.solve.page import Frame, resolve_frames
from tests.invariants import (
    assert_effects_are_placed,
    assert_frames_are_placed,
    assert_lettering_is_placed,
)

# Usable area 1080 x 1680: `wide` is the top-left corner panel, `tall` the top-right one,
# `last` fills the bottom tier. The bleed adds 30 past the trim.
FORMAT = PageFormat(size=(1200, 1800), margin=60, gutter=30, tier_gutter=40, bleed=30)
PAGE = PageSpec.model_validate(
    {
        "tiers": [
            {"height": 1, "panels": [{"use": "wide"}, {"use": "tall", "width": 2}]},
            {"height": 3, "panels": [{"use": "last"}]},
        ]
    }
)
SCENE = """\
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40, bleed: 30}
setting: {place: street, time: day}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - {height: 1, panels: [wide, {use: tall, width: 2}]}
      - {height: 3, panels: [last]}
panels:
  wide: {camera: {shot: full_shot}, script: [{say: {by: alice, text: "Hello."}}]}
  tall: {over: wide, camera: {shot: medium_shot}}
  last:
    over: wide
    camera: {shot: full_shot}
    script:
      - say: {by: bob, text: "Hi."}
      - sfx: {text: BANG, prefer: bottom_left}
"""


def _frames(
    bleeds: dict[str, bool | tuple[Side, ...]],
    page: PageSpec = PAGE,
    *,
    direction: Direction = Direction.LTR,
) -> dict[str, Frame]:
    laid = resolve_frames(FORMAT, page, bleeds=bleeds, direction=direction)
    return {frame.panel: frame for frame in laid}


class TestTheFrames:
    def test_true_bleeds_on_every_side_that_reaches_the_margin(self):
        wide = _frames({"wide": True})["wide"]
        assert (wide.x, wide.y, wide.width, wide.height) == (-30.0, -30.0, 440.0, 500.0)
        assert wide.bleed == (Side.LEFT, Side.TOP)
        assert wide.visible == BBox(0.0, 0.0, 410.0, 470.0)
        assert wide.live == BBox(60.0, 60.0, 350.0, 410.0)

    def test_a_listed_side_bleeds_and_no_other(self):
        last = _frames({"last": (Side.BOTTOM,)})["last"]
        assert (last.x, last.y, last.width, last.height) == (60.0, 510.0, 1080.0, 1320.0)
        assert last.bleed == (Side.BOTTOM,)
        assert last.visible == BBox(60.0, 510.0, 1080.0, 1290.0)

    def test_a_panel_that_does_not_bleed_is_as_it_was(self):
        plain = resolve_frames(FORMAT, PAGE)
        bled = _frames({"wide": True})
        assert bled["tall"] == next(frame for frame in plain if frame.panel == "tall")
        assert bled["tall"].bleed == ()
        assert bled["tall"].visible is None
        assert bled["tall"].live is None

    def test_a_side_that_does_not_reach_the_margin_is_refused(self):
        with pytest.raises(RuleViolationError, match="left") as caught:
            _frames({"tall": (Side.LEFT,)})
        assert caught.value.rule == "page-layout"

    def test_a_panel_that_reaches_no_edge_cannot_bleed(self):
        page = PageSpec.model_validate(
            {
                "tiers": [
                    {"panels": [{"use": "a"}, {"use": "b"}, {"use": "c"}]},
                    {"panels": [{"use": "d"}, {"use": "e"}, {"use": "f"}]},
                    {"panels": [{"use": "g"}, {"use": "h"}, {"use": "i"}]},
                ]
            }
        )
        with pytest.raises(RuleViolationError, match="'e'") as caught:
            _frames({"e": True}, page)
        assert caught.value.rule == "page-layout"

    def test_an_inset_of_a_bleeding_panel_stays_where_it_was(self):
        page = PageSpec.model_validate(
            {
                "tiers": [
                    {
                        "panels": [
                            {
                                "use": "big",
                                "insets": [{"use": "small", "at": "top_left", "size": 0.3}],
                            }
                        ]
                    }
                ]
            }
        )
        plain = {frame.panel: frame for frame in resolve_frames(FORMAT, page)}
        bled = _frames({"big": True}, page)
        assert bled["small"] == plain["small"]
        assert bled["big"].width == plain["big"].width + 2 * 90

    def test_a_slanted_tiers_outline_runs_out_too(self):
        page = PageSpec.model_validate(
            {"tiers": [{"slant": 10, "panels": [{"use": "a"}, {"use": "b"}]}]}
        )
        plain = {frame.panel: frame for frame in resolve_frames(FORMAT, page)}
        a = _frames({"a": (Side.LEFT, Side.TOP)}, page)["a"]
        assert a.outline is not None
        assert plain["a"].outline is not None
        assert a.outline[0] == (-30.0, -30.0)
        assert a.outline[3][0] == -30.0
        assert a.outline[1] == (plain["a"].outline[1][0], -30.0)
        assert a.x == -30.0

    def test_sides_are_the_pages_whichever_way_it_is_read(self):
        """Right to left, the first panel of a tier is at the right: its left side is a
        gutter, so it cannot bleed there."""
        with pytest.raises(RuleViolationError, match="left"):
            _frames({"wide": (Side.LEFT,)}, direction=Direction.RTL)
        assert _frames({"wide": (Side.RIGHT,)}, direction=Direction.RTL)["wide"].bleed == (
            Side.RIGHT,
        )


@pytest.fixture(scope="module")
def book():
    return _compile_document(
        parse_scene_document(SCENE), None, None, None, bleeds={"wide": True, "last": True}
    )


class TestTheCompiledPanel:
    def test_it_is_compiled_at_its_bled_frame(self, book):
        assert (book.panels["wide"].core.width, book.panels["wide"].core.height) == (440.0, 500.0)

    def test_it_records_its_open_sides_and_its_lettering_box(self, book):
        core = book.panels["wide"].core
        assert core.open == (Side.LEFT, Side.TOP)
        assert core.lettering == Box(x=90.0, y=90.0, width=350.0, height=410.0)
        (page,) = book.pages
        assert {frame.panel: frame.bleed for frame in page.frames}["wide"] == (Side.LEFT, Side.TOP)

    def test_its_cast_is_staged_in_its_visible_frame(self, book):
        """As the panel alone at the size the reader sees, moved by the bleed.

        `last` reaches the left, right and bottom margins: its visible frame runs to the trim
        on all three, 1200 by 1290, and starts 30 in from its bled frame's left edge.
        """
        (page,) = book.pages
        alone = compile_ir(
            parse_scene(SCENE)["last"].model_copy(
                update={"panel": PanelSpec(size=(1200.0, 1290.0))}
            ),
            lettering_height=page.lettering_height,
        )
        bled = book.panels["last"].core
        assert bled.open == (Side.LEFT, Side.RIGHT, Side.BOTTOM)
        moved = [
            (actor.transform.x - 30.0, actor.transform.y, actor.transform.scale)
            for actor in bled.actors
        ]
        assert moved == [
            pytest.approx((actor.transform.x, actor.transform.y, actor.transform.scale))
            for actor in alone.core.actors
        ]
        assert bled.camera == alone.core.camera

    def test_its_art_covers_the_bleed(self, book):
        core = book.panels["wide"].core
        assert core.backdrop is not None
        right = max(x for mass in core.backdrop.masses for x, _ in mass.polygon)
        bottom = max(y for mass in core.backdrop.masses for _, y in mass.polygon)
        assert (right, bottom) == (core.width, core.height)

    def test_its_lettering_keeps_inside_its_lettering_box(self, book):
        for result in book.panels.values():
            assert_lettering_is_placed(result.core)
            assert_effects_are_placed(result.core)

    def test_the_page_holds_its_frames(self, book):
        (page,) = book.pages
        assert_frames_are_placed(page, margin=60)

    def test_a_panel_that_does_not_bleed_compiles_as_it_did(self, book):
        plain = _compile_document(parse_scene_document(SCENE), None, None, None)
        assert book.panels["tall"].core.to_json() == plain.panels["tall"].core.to_json()
        assert "open" not in plain.panels["wide"].core.to_json()
        assert "lettering" not in plain.panels["wide"].core.to_json()
        assert '"bleed": [' not in plain.pages[0].to_json()
