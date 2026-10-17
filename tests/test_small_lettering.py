"""Small lettering: a line said under the breath.

Dark Horse lists "(small), (burst), and (weak)" among the "common indications for
modified lettering". Blambot, *Small Dialogue / Big Balloon*: "A reduced font size is used
when a character mutters something, says something to him/herself, or speaks
sheepishly" -- the type is smaller, and the balloon keeps the room it would have had.
Blambot's *Script Basics* reads `(WEAK)` as "dialogue should be diminished", so a weak
line is lettered small too.
"""

import pytest

from scenet import compile_book, compile_source, parse_panel
from scenet.core import CoreBalloon
from scenet.frontends.script_front import parse_script
from scenet.ir import SayEvent, TypeSize
from scenet.solve.balloons import SMALL_TYPE_FRACTION

CAST = "panel: {size: [900, 600]}\ncast:\n  bob: {reference: bob}\n"


def balloons(source: str) -> tuple[CoreBalloon, ...]:
    return compile_source(source).core.balloons


def padding(balloon: CoreBalloon) -> float:
    """The room between the lines and the balloon's edge, top and bottom."""
    return (balloon.box.height - len(balloon.lines) * balloon.line_height) / 2


class TestTheLanguage:
    def test_a_line_is_normal_size_unless_it_says_so(self):
        ir = parse_panel(CAST + "script:\n  - say: {by: bob, text: Hi.}\n")
        (line,) = ir.script
        assert isinstance(line, SayEvent)
        assert line.size is TypeSize.NORMAL

    def test_small_is_a_size(self):
        ir = parse_panel(CAST + "script:\n  - say: {by: bob, text: Hi., size: small}\n")
        (line,) = ir.script
        assert isinstance(line, SayEvent)
        assert line.size is TypeSize.SMALL


class TestTheLettering:
    SOURCE = (
        CAST + "script:\n"
        "  - say: {by: bob, text: 'Well, I suppose so.'}\n"
        "  - say: {by: bob, text: 'Well, I suppose so.', size: small}\n"
    )

    def test_the_type_is_smaller(self):
        normal, small = balloons(self.SOURCE)
        assert small.font_size == pytest.approx(normal.font_size * SMALL_TYPE_FRACTION, abs=0.01)

    def test_the_balloon_keeps_the_room_it_had(self):
        normal, small = balloons(self.SOURCE)
        assert padding(small) == pytest.approx(padding(normal), abs=0.05)

    def test_against_a_size_the_author_set(self):
        source = self.SOURCE.replace(
            "panel: {size: [900, 600]}", "panel: {size: [900, 600]}\nlettering: {size: 30}"
        )
        normal, small = balloons(source)
        assert (normal.font_size, small.font_size) == pytest.approx(
            (30.0, 30.0 * SMALL_TYPE_FRACTION)
        )

    def test_on_a_page(self):
        source = (
            "pages: [{tiers: [{panels: [a]}]}]\n"
            "panels:\n  a:\n    cast: {bob: {reference: bob}}\n    script:\n"
            "      - say: {by: bob, text: Hm.}\n"
            "      - say: {by: bob, text: Hm., size: small}\n"
        )
        normal, small = compile_book(source).panels["a"].core.balloons
        assert small.font_size == pytest.approx(normal.font_size * SMALL_TYPE_FRACTION, abs=0.01)

    def test_off_panel_too(self):
        source = CAST + "script:\n  - say: {by: voice, text: Psst., size: small, off_panel: left}\n"
        (balloon,) = balloons(source)
        normal = balloons(CAST + "script:\n  - say: {by: voice, text: Psst., off_panel: left}\n")
        assert balloon.font_size == pytest.approx(
            normal[0].font_size * SMALL_TYPE_FRACTION, abs=0.01
        )


class TestComicScripts:
    FRONT = "---\ncast: {BOB: {reference: bob}}\n---\nPANEL 1\n"

    @pytest.mark.parametrize("cue", ["BOB (small)", "BOB (weak)", "BOB (whisper, small)"])
    def test_small_and_weak_are_small(self, cue: str):
        (line,) = parse_script(f"{self.FRONT}{cue}\nWell.\n")["1"].script
        assert isinstance(line, SayEvent)
        assert line.size is TypeSize.SMALL

    def test_with_a_kind_both_hold(self):
        (line,) = parse_script(f"{self.FRONT}BOB (whisper, small)\nWell.\n")["1"].script
        assert isinstance(line, SayEvent)
        assert line.kind.value == "whisper"
