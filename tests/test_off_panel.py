"""Off-panel speech: a speaker who is not drawn, and a tail that ends on the frame.

Blambot, *Off-Panel Dialogue*: "When a character speaks from 'off-camera', the tail of
the balloon generally butts against the panel border." The speaker is not in the cast,
because nothing of them is drawn; the tail ends on the frame on their side -- named, or
the nearer of left and right to where the balloon was put.
"""

import json
from pathlib import Path

import pytest
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from scenet import compile_book, compile_source, parse_panel, render
from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.ir import SayEvent, Side
from tests.invariants import assert_lettering_is_placed

CAST = "panel: {size: [900, 600]}\ncast:\n  bob: {reference: bob, at: center}\n"


def panel(*lines: str) -> str:
    return CAST + "script:\n" + "".join(f"  - say: {line}\n" for line in lines)


def compiled(source: str) -> PanelCore:
    return compile_source(source).core


class TestTheLanguage:
    @pytest.mark.parametrize(("written", "value"), [("true", True), ("left", Side.LEFT)])
    def test_off_panel_is_true_or_a_side(self, written: str, value: object):
        ir = parse_panel(panel(f"{{by: carol, text: Hi, off_panel: {written}}}"))
        (event,) = ir.script
        assert isinstance(event, SayEvent)
        assert event.off_panel == value

    def test_a_side_it_does_not_know_is_invalid(self):
        (found,) = diagnose_source(panel("{by: carol, text: Hi, off_panel: sideways}"))
        assert found.rule == "invalid-field"
        assert found.path == ("script", 0, "say", "off_panel")

    def test_an_off_panel_speaker_is_not_in_the_cast(self):
        assert diagnose_source(panel("{by: carol, text: Hi, off_panel: true}")) == []

    def test_one_who_is_drawn_cannot_speak_from_off_panel(self):
        (found,) = diagnose_source(
            panel("{by: bob, text: Hi, off_panel: true}"), source=Path("x.panel.yaml")
        )
        assert (found.rule, found.path) == ("off-panel-speaker", ("script", 0, "say", "by"))
        assert found.region is not None
        assert found.region.start.line == 5

    def test_a_speaker_outside_the_cast_still_has_to_be_off_panel(self):
        (found,) = diagnose_source(panel("{by: carol, text: Hi}"))
        assert found.rule == "unknown-actor"
        assert "off_panel" in found.message


class TestTheTail:
    @pytest.mark.parametrize(
        ("side", "axis", "edge"),
        [("left", 0, 0.0), ("right", 0, 900.0), ("top", 1, 0.0), ("bottom", 1, 600.0)],
    )
    def test_a_named_side_is_where_it_ends(self, side: str, axis: int, edge: float):
        core = compiled(panel(f"{{by: carol, text: Over here!, off_panel: {side}}}"))
        (balloon,) = core.balloons
        assert balloon.off_panel == Side(side)
        assert balloon.tail.end[axis] == pytest.approx(edge)

    def test_with_no_side_named_it_ends_on_the_nearer_of_left_and_right(self):
        core = compiled(panel("{by: carol, text: Over here!, off_panel: true}"))
        (balloon,) = core.balloons
        box = balloon.box.as_bbox()
        nearer = Side.LEFT if box.centre.x <= core.width / 2 else Side.RIGHT
        assert balloon.off_panel == nearer
        assert balloon.tail.end[0] == pytest.approx(0.0 if nearer is Side.LEFT else 900.0)

    def test_the_tail_starts_on_the_balloon(self):
        core = compiled(panel("{by: carol, text: Over here!, off_panel: left}"))
        (balloon,) = core.balloons
        start = balloon.tail.start
        around = balloon.box.as_bbox().expanded(1.5)
        assert around.x <= start[0] <= around.right
        assert around.y <= start[1] <= around.bottom

    def test_reading_order_and_every_other_rule_still_hold(self):
        core = compiled(
            panel(
                "{by: bob, text: 'Who is there?'}",
                "{by: carol, text: Only me., off_panel: right}",
                "{by: bob, text: 'Come in, then.'}",
            )
        )
        assert [balloon.speaker for balloon in core.balloons] == ["bob", "carol", "bob"]
        assert_lettering_is_placed(core, margin=parse_panel(CAST).panel.margin)

    def test_a_panel_where_only_somebody_unseen_speaks(self):
        """Bob is drawn and says nothing; the only line is from off panel."""
        (balloon,) = compiled(panel("{by: voice, text: 'Hello?', off_panel: top}")).balloons
        assert balloon.tail.end[1] == pytest.approx(0.0)

    def test_on_a_slanted_panel_it_ends_on_the_slanted_frame(self):
        source = (
            "page: {size: [1500, 1000], margin: 60, gutter: 30, tier_gutter: 40}\n"
            "pages:\n  - tiers:\n      - {slant: 14, panels: [a, b]}\n"
            "panels:\n"
            "  a:\n    cast: {bob: {reference: bob}}\n"
            "    script:\n      - say: {by: bob, text: 'Who?'}\n"
            "  b:\n    cast: {bob: {reference: bob}}\n"
            "    script:\n      - say: {by: carol, text: Me., off_panel: left}\n"
        )
        core = compile_book(source).panels["b"].core
        assert core.outline is not None
        (balloon,) = core.balloons
        boundary = Polygon(core.outline).exterior
        # Within the rounding Panel Core applies to every coordinate.
        assert boundary.distance(ShapelyPoint(balloon.tail.end)) < 0.01

    @pytest.mark.parametrize("side", ["left", "top"])
    def test_on_a_slanted_panel_it_ends_on_the_side_named(self, side: str):
        """Straight out from the balloon to that side -- not across to the opposite one.

        The balloon is asked to sit mid-panel, far enough from every edge that a line
        aimed the wrong way would reach the opposite one.
        """
        source = (
            "page: {size: [1500, 1000], margin: 60, gutter: 30, tier_gutter: 40}\n"
            "pages:\n  - tiers:\n      - {slant: 14, panels: [a, b]}\n"
            "panels:\n"
            "  a:\n    cast: {bob: {reference: bob}}\n"
            "    script:\n      - say: {by: bob, text: 'Who?'}\n"
            "  b:\n    cast: {bob: {reference: bob}}\n"
            "    script:\n"
            f"      - say: {{by: carol, text: Me., off_panel: {side}, prefer: middle_center}}\n"
        )
        (balloon,) = compile_book(source).panels["b"].core.balloons
        box = balloon.box.as_bbox()
        end = balloon.tail.end
        if side == "left":
            assert end[0] < box.x
            assert end[1] == pytest.approx(box.centre.y, abs=0.01)
        else:
            assert end[1] < box.y
            assert end[0] == pytest.approx(box.centre.x, abs=0.01)

    def test_it_ends_on_the_frame_not_the_margin(self):
        """Lettering keeps inside the margin; a pointer to somebody outside the panel does not."""
        source = "panel: {size: [900, 600], margin: 40}\n" + panel(
            "{by: carol, text: Over here!, off_panel: left}"
        ).removeprefix("panel: {size: [900, 600]}\n")
        (balloon,) = compiled(source).balloons
        assert balloon.box.as_bbox().x >= 40.0
        assert balloon.tail.end[0] == pytest.approx(0.0)

    def test_it_is_the_same_every_time(self):
        source = panel("{by: carol, text: Over here!, off_panel: true}")
        assert compiled(source).to_json() == compiled(source).to_json()


class TestPanelCore:
    def test_the_side_is_recorded_only_for_an_off_panel_balloon(self):
        core = compiled(panel("{by: bob, text: Hi.}", "{by: carol, text: Hey!, off_panel: left}"))
        written = json.loads(core.to_json())["balloons"]
        assert "off_panel" not in written[0]
        assert written[1]["off_panel"] == "left"
        assert written[1]["speaker"] == "carol"

    def test_a_core_written_before_it_reads_as_before(self):
        core = compiled(panel("{by: bob, text: Hi.}"))
        again = PanelCore.model_validate_json(core.to_json())
        assert again == core
        assert again.balloons[0].off_panel is None


class TestTheEmitters:
    SOURCE = panel("{by: carol, text: Over here!, off_panel: left}")

    def test_the_balloon_and_its_tail_are_drawn(self):
        svg = render(compiled(self.SOURCE))
        assert "Over here!" not in svg  # outlines, not text
        assert svg.count("<path") >= 2

    def test_the_debug_overlay_says_where_the_speaker_is(self):
        assert "-&gt; carol (off panel, left)" in render_debug(compiled(self.SOURCE))
