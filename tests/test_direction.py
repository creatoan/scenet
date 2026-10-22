"""Which way a comic is read (#68): `direction: ltr | rtl`, the whole document's.

Progression direction, not text direction: a manga translated into English still reads
right to left, while the words in each balloon read left to right. It is written once for
the whole document -- a single panel, a scene beside its `panels:`, a comic script in its
front matter -- and a panel may not have one of its own, because a page read right to left
holding a panel read left to right has no reading a reader could follow.
"""

import json
import math
from pathlib import Path

import pytest

from scenet import (
    Direction,
    PageCore,
    PanelCore,
    compile_book,
    compile_source,
    parse_panel,
    parse_scene,
)
from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import accessible_name
from scenet.errors import PanelSyntaxError
from scenet.frontends.script_front import ScriptSyntaxError, parse_script_document
from scenet.frontends.yaml_front import parse_scene_document
from scenet.geom import BBox, Circle, Point
from scenet.ir import CaptionEvent, Side
from scenet.solve.balloons import (
    READING_EPSILON,
    _candidate_positions,
    _caption_positions,
    _nearer_side,
    _reading_order_allows,
)
from scenet.solve.describe import describe
from scenet.solve.speakers import Speaker
from tests.images import contract, png
from tests.invariants import assert_lettering_is_placed

CAST = "cast: {alice: {reference: alice, at: left_third}, bob: {reference: bob, at: right_third}}\n"

SCENE = (
    "direction: rtl\n"
    + CAST
    + "pages: [{tiers: [{panels: [one, two]}]}]\n"
    + "panels:\n"
    + "  one: {script: [{say: {by: alice, text: Hello.}}]}\n"
    + "  two: {over: one}\n"
)

SCRIPT = """---
direction: rtl
cast:
  ALICE: {reference: alice, at: left_third}
---

PAGE ONE

PANEL 1

ALICE
Hello.

PANEL 2

ALICE
Again.
"""


class TestTheKey:
    def test_left_to_right_is_the_default(self):
        assert parse_panel(CAST).direction is Direction.LTR

    @pytest.mark.parametrize("written", ["ltr", "rtl"])
    def test_a_single_panel_writes_it_at_the_top(self, written: str):
        assert parse_panel(f"direction: {written}\n{CAST}").direction is Direction(written)

    def test_a_value_it_does_not_know_is_invalid_at_the_key(self):
        (found,) = diagnose_source(f"direction: sideways\n{CAST}")
        assert (found.rule, found.path) == ("invalid-field", ("direction",))

    def test_every_panel_of_a_scene_inherits_it(self):
        panels = parse_scene(SCENE)
        assert {name: panel.direction for name, panel in panels.items()} == {
            "one": Direction.RTL,
            "two": Direction.RTL,
        }

    def test_a_scene_document_reads_in_its_panels_direction(self):
        assert parse_scene_document(SCENE).direction is Direction.RTL
        assert parse_scene_document(CAST).direction is Direction.LTR

    def test_a_bad_value_beside_panels_is_one_finding_at_it(self):
        found = diagnose_source(SCENE.replace("direction: rtl", "direction: up"))
        assert [(item.rule, item.path) for item in found] == [("invalid-field", ("direction",))]


class TestAPanelHasNoDirectionOfItsOwn:
    @pytest.mark.parametrize("value", ["rtl", "ltr", "null"])
    def test_a_scene_panel_writing_it_is_refused(self, value: str):
        text = SCENE.replace("two: {over: one}", f"two: {{over: one, direction: {value}}}")
        with pytest.raises(PanelSyntaxError) as raised:
            parse_scene(text)
        assert raised.value.rule == "panel-direction"
        assert raised.value.loc == ("panels", "two", "direction")

    def test_check_reports_it_once_where_it_is_written(self):
        text = SCENE.replace("two: {over: one}", "two: {over: one, direction: ltr}")
        (found,) = diagnose_source(text, source=Path("x.scene.yaml"))
        assert (found.rule, found.path) == ("panel-direction", ("panels", "two", "direction"))
        assert found.region is not None
        assert found.region.start.line == 6

    def test_check_still_finds_a_fault_in_another_panel(self):
        text = SCENE.replace(
            "two: {over: one}", "two: {direction: ltr, script: [{say: {by: carol, text: Hi.}}]}"
        )
        rules = sorted(item.rule for item in diagnose_source(text))
        assert rules == ["panel-direction", "unknown-actor"]

    def test_a_script_directive_is_refused_at_its_line(self):
        text = SCRIPT.replace("PANEL 2\n", "PANEL 2\n@direction: ltr\n")
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text)
        assert (raised.value.rule, raised.value.line) == ("panel-direction", 15)
        (found,) = diagnose_script(text)
        assert found.rule == "panel-direction"
        assert found.region is not None
        assert found.region.start.line == 15


class TestAComicScript:
    def test_the_front_matter_sets_it_for_every_panel(self):
        document = parse_script_document(SCRIPT)
        assert {panel.direction for panel in document.panels.values()} == {Direction.RTL}
        assert document.direction is Direction.RTL

    def test_without_it_a_script_reads_left_to_right(self):
        document = parse_script_document(SCRIPT.replace("direction: rtl\n", ""))
        assert document.direction is Direction.LTR

    def test_a_bad_value_is_found_at_its_own_line(self):
        text = SCRIPT.replace("direction: rtl", "direction: backwards")
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text)
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 2)
        (found,) = diagnose_script(text)
        assert found.region is not None
        assert (found.rule, found.region.start.line) == ("invalid-field", 2)


class TestCore:
    def test_a_left_to_right_core_does_not_say_so(self):
        core = compile_source(CAST).core
        assert core.direction is Direction.LTR
        assert "direction" not in json.loads(core.to_json())

    def test_a_right_to_left_core_records_it(self):
        core = compile_source(f"direction: rtl\n{CAST}").core
        assert json.loads(core.to_json())["direction"] == "rtl"
        restored = PanelCore.from_json(core.to_json())
        assert restored == core
        assert restored.to_json() == core.to_json()

    def test_a_page_core_records_it_too(self):
        book = compile_book(SCENE)
        (page,) = book.pages
        assert json.loads(page.to_json())["direction"] == "rtl"
        assert PageCore.from_json(page.to_json()) == page
        assert {result.core.direction for result in book.panels.values()} == {Direction.RTL}
        (ltr,) = compile_book(SCENE.replace("direction: rtl\n", "")).pages
        assert "direction" not in json.loads(ltr.to_json())

    def test_a_core_written_before_it_reads_as_left_to_right(self):
        text = compile_source(CAST).core.to_json()
        assert PanelCore.from_json(text).direction is Direction.LTR


# ---------------------------------------------------------------- the lettering

RTL = Direction.RTL
FIRST = BBox(100, 100, 80, 40)


class TestReadingOrderRightToLeft:
    """Read from the top right, a box may never sit above *and* right of one before it."""

    def test_below_is_allowed(self):
        assert _reading_order_allows([FIRST], BBox(300, 200, 80, 40), RTL)

    def test_left_of_is_allowed(self):
        assert _reading_order_allows([FIRST], BBox(0, 0, 80, 40), RTL)

    def test_above_and_right_is_refused(self):
        assert not _reading_order_allows([FIRST], BBox(200, 0, 80, 40), RTL)

    def test_directly_above_is_refused(self):
        assert not _reading_order_allows([FIRST], BBox(100, 0, 80, 40), RTL)

    def test_left_to_right_is_the_mirror(self):
        """The same two boxes, read the other way: what one allows the other refuses."""
        assert not _reading_order_allows([FIRST], BBox(0, 0, 80, 40))
        assert _reading_order_allows([FIRST], BBox(200, 0, 80, 40))

    def test_checked_against_every_predecessor_not_just_the_last(self):
        """The mirror of the left-to-right case: legal after the last box alone, and yet
        above and right of the first."""
        first = BBox(400, 300, 100, 60)
        second = BBox(0, 100, 100, 60)
        candidate = BBox(400, 200, 100, 60)
        assert _reading_order_allows([first], second, RTL)
        assert _reading_order_allows([second], candidate, RTL)
        assert not _reading_order_allows([first, second], candidate, RTL)

    @pytest.mark.parametrize("reach", [READING_EPSILON, READING_EPSILON / 2])
    def test_touching_within_the_tolerance_counts_as_left_of(self, reach: float):
        assert _reading_order_allows([FIRST], BBox(FIRST.x + reach - 40, 0, 40, 40), RTL)

    def test_beyond_the_tolerance_it_is_refused(self):
        reach = READING_EPSILON + 0.5
        assert not _reading_order_allows([FIRST], BBox(FIRST.x + reach - 40, 0, 40, 40), RTL)


PANEL = BBox(20.0, 20.0, 960.0, 560.0)


def _mirrored(box: BBox, panel: BBox = PANEL) -> BBox:
    return BBox(panel.x + panel.right - box.right, box.y, box.width, box.height)


def _speaker(cx: float) -> Speaker:
    return Speaker(face=Circle(cx, 260.0, 40.0), mouth=Point(cx + 6.0, 280.0))


class TestTheTiebreaksAreMirrored:
    """The first candidate wins an exact tie, so the order candidates are tried in is a
    tiebreak. Read right to left, candidate *i* is the mirror of candidate *i* read left to
    right -- which is what makes a right-to-left panel the mirror of a left-to-right one
    rather than a mirrored-but-different layout. Tested on the order, never on a tie."""

    def test_the_ring_and_the_corners(self):
        ltr = _candidate_positions(_speaker(300.0), (180.0, 60.0), PANEL)
        rtl = _candidate_positions(
            _speaker(PANEL.x + PANEL.right - 300.0), (180.0, 60.0), PANEL, RTL
        )
        assert len(ltr) == len(rtl)
        for left, right in zip(ltr, rtl, strict=True):
            mirrored = _mirrored(right)
            assert (mirrored.x, mirrored.y) == pytest.approx((left.x, left.y), abs=1e-9)

    def test_the_first_ring_step_after_straight_up_leans_toward_where_reading_starts(self):
        speaker = _speaker(500.0)
        straight, *_ = _candidate_positions(speaker, (100.0, 40.0), PANEL)
        ltr = _candidate_positions(speaker, (100.0, 40.0), PANEL)[3]
        rtl = _candidate_positions(speaker, (100.0, 40.0), PANEL, RTL)[3]
        assert rtl.centre.x < straight.centre.x < ltr.centre.x

    def test_the_corners_start_at_the_top_right(self):
        rtl = _candidate_positions(_speaker(500.0), (100.0, 40.0), PANEL, RTL)
        top_right, top_left = rtl[-4], rtl[-3]
        assert top_right.right > top_left.right
        assert top_right.y == top_left.y

    def test_the_caption_zones(self):
        ltr = _caption_positions((200.0, 50.0), PANEL)
        rtl = _caption_positions((200.0, 50.0), PANEL, RTL)
        for left, right in zip(ltr, rtl, strict=True):
            assert (_mirrored(right).x, right.y) == pytest.approx((left.x, left.y), abs=1e-9)

    @pytest.mark.parametrize("direction", list(Direction))
    def test_a_balloon_dead_centre_goes_to_the_side_reading_starts_from(self, direction: Direction):
        centred = BBox(PANEL.x + PANEL.width / 2 - 50, 100, 100, 40)
        expected = Side.LEFT if direction is Direction.LTR else Side.RIGHT
        assert _nearer_side(centred, PANEL, direction) is expected

    @pytest.mark.parametrize("direction", list(Direction))
    def test_off_centre_the_nearer_side_is_the_nearer_side(self, direction: Direction):
        assert _nearer_side(BBox(PANEL.x + 10, 100, 100, 40), PANEL, direction) is Side.LEFT
        assert _nearer_side(BBox(PANEL.right - 110, 100, 100, 40), PANEL, direction) is Side.RIGHT


SOLO = "panel: {size: [1000, 600]}\ncast: {bob: {reference: bob, at: center}}\nscript:\n"


def _rtl(script: str) -> PanelCore:
    return compile_source("direction: rtl\n" + SOLO + script).core


class TestWhereReadingStarts:
    """An unwritten zone is where reading starts; a written one is a place on the panel."""

    def test_an_unwritten_caption_zone_is_none_until_the_solver_reads_the_direction(self):
        assert CaptionEvent(text="Midnight.").prefer is None

    def test_a_caption_with_no_zone_sits_top_right(self):
        (caption,) = _rtl("  - caption: {text: Midnight. The docks.}\n").captions
        assert caption.box.x + caption.box.width / 2 > 500

    def test_left_to_right_it_still_sits_top_left(self):
        core = compile_source(SOLO + "  - caption: {text: Midnight. The docks.}\n").core
        (caption,) = core.captions
        assert caption.box.x + caption.box.width / 2 < 500

    def test_a_written_zone_is_a_place_on_the_panel(self):
        (caption,) = _rtl("  - caption: {text: Midnight., prefer: top_left}\n").captions
        assert caption.box.x + caption.box.width / 2 < 500

    def test_an_off_panel_voice_with_no_side_is_heard_from_where_reading_starts(self):
        (balloon,) = _rtl("  - say: {by: carol, text: Over here!, off_panel: true}\n").balloons
        assert balloon.off_panel is Side.RIGHT
        assert balloon.tail.end[0] == pytest.approx(1000.0)

    def test_a_named_side_is_a_side_of_the_panel(self):
        (balloon,) = _rtl("  - say: {by: carol, text: Over here!, off_panel: left}\n").balloons
        assert balloon.off_panel is Side.LEFT
        assert balloon.tail.end[0] == pytest.approx(0.0)


def _boxes(core: PanelCore) -> list[tuple[str, BBox]]:
    items = sorted([*core.balloons, *core.captions], key=lambda item: item.order)
    return [(item.id, item.box.as_bbox()) for item in items]


#: A picture whose people are given exactly, in its own pixels, and the same picture
#: mirrored: x becomes 1200 - x, which is exact in binary for these numbers.
FIGURES: dict[str, dict[str, object]] = {
    "ana": {
        "face": {"center": [880, 200], "radius": 55},
        "mouth": [870, 232],
        "body": [[800, 160], [960, 160], [990, 600], [780, 600]],
    },
    "ben": {
        "face": {"center": [330, 230], "radius": 50},
        "mouth": [342, 262],
        "body": [[250, 190], [410, 190], [430, 600], [230, 600]],
    },
}


def _mirror_figures(figures: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    def flip(point: object) -> list[float]:
        assert isinstance(point, list)
        return [1200 - point[0], point[1]]

    mirrored: dict[str, dict[str, object]] = {}
    for name, figure in figures.items():
        face = figure["face"]
        assert isinstance(face, dict)
        body = figure["body"]
        assert isinstance(body, list)
        mirrored[name] = {
            "face": {"center": flip(face["center"]), "radius": face["radius"]},
            "mouth": flip(figure["mouth"]),
            "body": [flip(point) for point in body],
        }
    return mirrored


MANGA = """panel: {size: [1200, 600]}
cast:
  ANA: {figure: ana}
  BEN: {figure: ben}
setting: {image: art/p.png}
script:
  - caption: {text: "Shinjuku. Ten past midnight."}
  - say: {by: ANA, text: "You came."}
  - say: {by: BEN, text: "You called. I always come when you call."}
  - say: {by: ANA, text: "Then listen."}
  - say: {by: MOTHER, text: "Ana? Where are you?", off_panel: true}
"""


def _figure_panel(direction: str, figures: dict[str, dict[str, object]]) -> PanelCore:
    files = {"art/p.png": png(1200, 600), "art/p.art.yaml": contract((1200, 600), figures)}
    return compile_source(f"direction: {direction}\n{MANGA}", base=files).core


class TestTheMirror:
    """The test that defines `rtl`: compile the mirror image of a panel right to left, and
    every balloon and caption lands at the mirror of where left to right puts it in the
    original. A figure panel, because its people are given exactly, so the two pictures are
    exact mirrors; the margins between the costs of its candidates are wide, so no near-tie
    decides it on any platform."""

    def test_every_box_lands_at_the_mirror(self):
        ltr = _figure_panel("ltr", FIGURES)
        rtl = _figure_panel("rtl", _mirror_figures(FIGURES))
        frame = BBox(0.0, 0.0, 1200.0, 600.0)
        for (left_id, left), (right_id, right) in zip(_boxes(ltr), _boxes(rtl), strict=True):
            assert left_id == right_id
            mirrored = _mirrored(right, frame)
            assert (mirrored.x, mirrored.y, mirrored.width, mirrored.height) == pytest.approx(
                (left.x, left.y, left.width, left.height), abs=0.05
            ), left_id

    def test_off_panel_sides_are_mirrored_too(self):
        ltr = _figure_panel("ltr", FIGURES)
        rtl = _figure_panel("rtl", _mirror_figures(FIGURES))
        flip = {Side.LEFT: Side.RIGHT, Side.RIGHT: Side.LEFT, None: None}
        assert [flip[b.off_panel] for b in ltr.balloons] == [b.off_panel for b in rtl.balloons]

    def test_both_read_in_their_own_order(self):
        for core in (_figure_panel("ltr", FIGURES), _figure_panel("rtl", _mirror_figures(FIGURES))):
            assert_lettering_is_placed(core)


#: Two puppets, a look, a mark, a sound and a setting: everything the picture decides.
STAGED = """panel: {size: [1100, 700]}
setting: {place: street, time: night, weather: rain}
camera: {shot: full_shot}
cast:
  alice: {reference: alice, pose: pointing, at: right_third, facing: left, marks: [plewds]}
  bob: {reference: bob, pose: arms_crossed, at: left_third}
staging:
  - bob left_of alice
  - alice looking_at bob
script:
  - caption: {text: "Midnight."}
  - say: {by: alice, text: "You forgot your umbrella!"}
  - sfx: {text: CRASH, from: bob, size: medium}
  - say: {by: bob, text: "I know.", kind: whisper}
  - say: {by: carol, text: "Keep it down!", off_panel: true}
"""


def _both(source: str = STAGED) -> tuple[PanelCore, PanelCore]:
    return compile_source(source).core, compile_source("direction: rtl\n" + source).core


class TestTheSceneIsNotMirrored:
    """Only what reading decides follows the direction: the picture stays as staged."""

    def test_figures_gaze_and_the_backdrop_are_byte_identical(self):
        ltr, rtl = _both()
        assert [actor.model_dump_json() for actor in ltr.actors] == [
            actor.model_dump_json() for actor in rtl.actors
        ]
        assert ltr.backdrop == rtl.backdrop
        assert ltr.actor("alice").gaze == rtl.actor("alice").gaze

    def test_sound_effects_are_picture_and_byte_identical(self):
        ltr, rtl = _both()
        assert [effect.model_dump_json() for effect in ltr.sfx] == [
            effect.model_dump_json() for effect in rtl.sfx
        ]

    def test_a_sound_effect_keeps_its_number_in_the_one_order(self):
        _, rtl = _both()
        assert [effect.order for effect in rtl.sfx] == [2]
        assert sorted(item.order for item in (*rtl.balloons, *rtl.captions)) == [0, 1, 3, 4]

    def test_figures_a_picture_draws_are_byte_identical(self):
        ltr, rtl = _figure_panel("ltr", FIGURES), _figure_panel("rtl", FIGURES)
        assert ltr.figures == rtl.figures
        assert ltr.backdrop == rtl.backdrop

    def test_every_tail_still_ends_at_its_own_speaker(self):
        _, rtl = _both()
        for balloon in rtl.balloons:
            if balloon.off_panel is not None:
                continue
            disc, _ = rtl.speaker(balloon.speaker)
            end = balloon.tail.end
            assert math.hypot(end[0] - disc.cx, end[1] - disc.cy) <= disc.r * 1.35

    def test_a_balloon_on_the_same_box_has_the_same_tail(self):
        ltr, rtl = _both()
        same = [
            (left, right)
            for left, right in zip(ltr.balloons, rtl.balloons, strict=True)
            if left.box == right.box
        ]
        for left, right in same:
            assert left.tail == right.tail

    def test_a_panel_reading_order_does_not_bind_is_identical_but_for_its_direction(self):
        """One line, from a speaker well off centre: nothing for the order to decide."""
        source = SOLO.replace("at: center", "at: left_third") + "  - say: {by: bob, text: Hi.}\n"
        ltr, rtl = _both(source)
        assert rtl.model_copy(update={"direction": Direction.LTR}).to_json() == ltr.to_json()


class TestReadFromTheTopRight:
    def test_the_lettering_keeps_the_right_to_left_rule(self):
        _, rtl = _both()
        assert_lettering_is_placed(rtl)

    def test_the_panel_s_name_reads_its_words_in_order(self):
        _, rtl = _both()
        _, (title,) = accessible_name(rtl)
        said = ["Midnight.", "You forgot your umbrella!", "CRASH.", "I know.", "Keep it down!"]
        positions = [title.index(words) for words in said]
        assert positions == sorted(positions)

    def test_the_overlay_says_which_way_the_panel_is_read(self):
        ltr, rtl = _both()
        assert "read right to left" in render_debug(rtl)
        assert "read right to left" not in render_debug(ltr)


class TestTheDescription:
    """The cast is said in reading order; where each stands is said as it is on the panel."""

    TWO = (
        "cast:\n  alice: {reference: alice}\n  bob: {reference: bob}\n"
        "staging: [alice left_of bob]\n"
    )

    def test_right_to_left_the_cast_is_said_from_the_right(self):
        said = describe(
            parse_panel("direction: rtl\n" + self.TWO), {"alice": 250.0, "bob": 750.0}, 1000.0
        )
        assert said.index("Bob, right") < said.index("Alice, left")

    def test_left_to_right_it_is_said_from_the_left(self):
        said = describe(parse_panel(self.TWO), {"alice": 250.0, "bob": 750.0}, 1000.0)
        assert said.index("Alice, left") < said.index("Bob, right")

    def test_a_tie_is_still_broken_by_id(self):
        said = describe(
            parse_panel("direction: rtl\n" + self.TWO), {"alice": 500.0, "bob": 500.0}, 1000.0
        )
        assert said.index("Alice, centre") < said.index("Bob, centre")
