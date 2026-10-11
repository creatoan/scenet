"""Emphasis: the words a writer underlines, lettered in bold italic.

Blambot: "There's almost no plain bold in comics dialogue. Typically, bold italic is used
when emphasis is placed on a word." Dark Horse's script format asks writers to underline
the words they want stressed. Plain text has no underline, so a Scenet author writes the
word between underscores -- `I _told_ you` -- and the compiler sets it in the bold italic
face of the lettering family.

What these tests pin down is the part that is easy to get wrong: the spans reach
*measurement*, not just rendering. A bold italic word is wider than the same word in
roman, and a balloon measured in one face and drawn in another is exactly the
disagreement lettering as outlines exists to prevent. And a panel with no emphasis must
compile byte for byte as it did before emphasis existed -- `tests/test_golden.py` holds
every gallery panel to that; the tests here hold the mechanism.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from scenet.core import Box, CoreBalloon, CoreRun, PanelCore, Tail
from scenet.diagnostics import diagnose_source
from scenet.emit.svg import render
from scenet.emphasis import EmphasisError, Span, parse, plain
from scenet.errors import PanelSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_panel
from scenet.ir import BalloonKind, Face
from scenet.pipeline import compile_source
from scenet.solve.balloons import CLOSING_QUOTE, OPENING_QUOTE
from scenet.solve.text import (
    BOLD_ITALIC_FONT_PATH,
    DEFAULT_FONT_PATH,
    ITALIC_FONT_PATH,
    Styled,
    Typeface,
    layout_text,
    load_metrics,
    styled,
    wrap_styled,
)
from tests.invariants import assert_svg_is_sound

CAST = "cast: {alice: {reference: alice}}\n"


def _panel(script: str) -> PanelCore:
    return compile_source(f"{CAST}script:\n{script}").core


def _say(text: str) -> str:
    return f"  - say: {{by: alice, text: {text!r}}}\n"


class TestTheMarker:
    def test_a_word_between_underscores_is_emphasised(self):
        assert parse("I _told_ you") == (
            Span("I ", emphasised=False),
            Span("told", emphasised=True),
            Span(" you", emphasised=False),
        )

    def test_a_span_may_run_across_words(self):
        assert parse("_told you_ so") == (
            Span("told you", emphasised=True),
            Span(" so", emphasised=False),
        )

    def test_text_without_a_marker_is_one_plain_span(self):
        assert parse("You forgot your umbrella!") == (
            Span("You forgot your umbrella!", emphasised=False),
        )

    def test_an_underscore_inside_a_word_is_just_an_underscore(self):
        """`snake_case` is not emphasis, as in Markdown: intraword underscores stay."""
        text = "save it as file_name_v2 please"
        assert parse(text) == (Span(text, emphasised=False),)

    def test_an_underscore_standing_alone_is_just_an_underscore(self):
        assert parse("fill in the _ here") == (Span("fill in the _ here", emphasised=False),)

    def test_a_backslash_writes_an_underscore_anywhere(self):
        assert plain(r"\_told\_ you") == "_told_ you"
        assert parse(r"\_told\_") == (Span("_told_", emphasised=False),)

    def test_a_backslash_before_anything_else_is_kept(self):
        assert plain(r"C:\path") == r"C:\path"

    def test_punctuation_may_sit_either_side(self):
        assert parse("(_yes_), really") == (
            Span("(", emphasised=False),
            Span("yes", emphasised=True),
            Span("), really", emphasised=False),
        )

    def test_an_emphasised_word_may_end_the_line(self):
        assert parse("Never _again_") == (
            Span("Never ", emphasised=False),
            Span("again", emphasised=True),
        )

    def test_a_span_never_left_open(self):
        with pytest.raises(EmphasisError) as raised:
            parse("I _told you")
        assert raised.value.position == 2

    def test_a_closing_marker_glued_to_a_word_does_not_close(self):
        """`_told_s` has no closer: the second underscore is inside a word."""
        with pytest.raises(EmphasisError):
            parse("_told_s")

    def test_an_underscore_beside_another_is_just_an_underscore(self):
        assert parse("call __init__ first") == (Span("call __init__ first", emphasised=False),)

    def test_plain_drops_the_markers(self):
        assert plain("I _told_ you, _twice_.") == "I told you, twice."


class TestTheLanguage:
    def test_dialogue_takes_emphasis(self):
        panel = parse_panel(f"{CAST}script:\n{_say('I _told_ you.')}")
        assert panel.script[0].text == "I _told_ you."

    def test_an_unclosed_span_is_rejected(self):
        with pytest.raises(PanelSyntaxError, match="never closed"):
            parse_panel(f"{CAST}script:\n{_say('I _told you.')}")

    def test_an_unclosed_span_is_a_located_finding(self):
        source = f"{CAST}script:\n{_say('I _told you.')}"
        (found,) = diagnose_source(source, source=Path("emphasis.panel.yaml"))
        assert found.rule == "unbalanced-emphasis"
        assert found.path == ("script", 0, "say", "text")
        assert found.region is not None
        assert found.region.start.line == 3

    def test_captions_take_emphasis_too(self):
        with pytest.raises(PanelSyntaxError, match="never closed"):
            parse_panel(f"{CAST}script:\n  - caption: {{text: '_Midnight.'}}\n")

    def test_the_comic_script_frontend_reads_it(self):
        panels = parse_script(
            "---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1\n\nALICE\nI _told_ you.\n"
        )
        assert panels["1"].script[0].text == "I _told_ you."

    @pytest.mark.parametrize(
        "document",
        [
            f"{CAST}script:\n  - say: {{by: alice, text: *told* you}}\n",
            f"{CAST}script:\n  - say:\n      by: alice\n      text: *told you\n",
        ],
    )
    def test_a_value_starting_with_an_asterisk_says_to_quote_it(self, document: str):
        """In YAML a plain value that starts with `*` is an alias, and the parser's own
        message is about anchors -- nothing an author writing dialogue would recognise."""
        with pytest.raises(PanelSyntaxError, match="quote") as raised:
            parse_panel(document)
        assert "_told_" in str(raised.value)

    def test_check_gives_the_same_hint(self):
        source = f"{CAST}script:\n  - say: {{by: alice, text: *told* you}}\n"
        (found,) = diagnose_source(source)
        assert found.rule == "syntax"
        assert "quote" in found.message


class TestTypeface:
    def test_each_face_is_its_own_file(self):
        family = Typeface()
        assert family.face(Face.REGULAR).path == DEFAULT_FONT_PATH
        assert family.face(Face.ITALIC).path == ITALIC_FONT_PATH
        assert family.face(Face.BOLD_ITALIC).path == BOLD_ITALIC_FONT_PATH

    def test_bold_italic_is_wider_than_roman(self):
        family = Typeface()
        word = Styled("told", (Face.BOLD_ITALIC,) * 4)
        assert family.measure(word, 40) > family.measure(Styled.of("told"), 40)

    def test_a_face_can_be_replaced(self):
        italic = load_metrics(str(ITALIC_FONT_PATH))
        assert Typeface(regular=italic).face(Face.REGULAR) is italic


class TestMeasurement:
    def test_emphasis_widens_the_line(self):
        roman = layout_text("I told you.", font_size=40)
        stressed = layout_text(styled("I _told_ you."), font_size=40)
        assert stressed.lines == roman.lines == ("I told you.",)
        assert stressed.width > roman.width

    def test_the_width_is_each_run_in_its_own_face(self):
        block = layout_text(styled("I _told_ you"), font_size=40)
        regular = load_metrics(str(DEFAULT_FONT_PATH))
        bold = load_metrics(str(BOLD_ITALIC_FONT_PATH))
        expected = (
            regular.measure("I ", 40) + bold.measure("told", 40) + regular.measure(" you", 40)
        )
        assert block.width == pytest.approx(expected)

    def test_emphasis_changes_where_lines_break(self):
        """At the plain line's own width the roman text fits on one line, and the same
        text with a stressed word does not -- so the wrapping read the bold italic face."""
        family = Typeface()
        roman = Styled.of("I told you so")
        width = family.measure(roman, 40)
        assert len(wrap_styled(roman, family, 40, width)) == 1
        assert len(wrap_styled(styled("I _told_ you so"), family, 40, width)) == 2

    def test_plain_text_measures_exactly_as_it_always_did(self):
        """Not approximately: the same sum in the same order, or every golden moves."""
        text = "It has been raining since six this morning and you knew that."
        metrics = load_metrics()
        block = layout_text(styled(text), font_size=37.5)
        assert block.line_widths == tuple(metrics.measure(line, 37.5) for line in block.lines)
        assert block == layout_text(text, font_size=37.5, metrics=metrics)

    def test_a_line_knows_its_runs(self):
        block = layout_text(styled("I _told_ you"), font_size=40)
        assert block.runs == (
            (
                ("I ", Face.REGULAR),
                ("told", Face.BOLD_ITALIC),
                (" you", Face.REGULAR),
            ),
        )

    def test_the_space_inside_a_span_is_emphasised_with_it(self):
        block = layout_text(styled("_told you_"), font_size=40)
        assert block.runs == ((("told you", Face.BOLD_ITALIC),),)

    def test_an_italic_line_emphasises_in_bold_italic(self):
        block = layout_text(styled("_Midnight._ The docks.", base=Face.ITALIC), font_size=30)
        runs = [run for line in block.runs for run in line]
        assert runs[0] == ("Midnight.", Face.BOLD_ITALIC)
        assert runs[-1][1] is Face.ITALIC


class TestPanelCore:
    def test_a_stressed_line_carries_its_runs(self):
        (balloon,) = _panel(_say("I _told_ you.")).balloons
        assert balloon.lines == ("I told you.",)
        assert balloon.runs == (
            (
                CoreRun(text="I ", face=Face.REGULAR),
                CoreRun(text="told", face=Face.BOLD_ITALIC),
                CoreRun(text=" you.", face=Face.REGULAR),
            ),
        )

    def test_a_balloon_is_measured_wider_for_its_emphasis(self):
        (roman,) = _panel(_say("I told you.")).balloons
        (stressed,) = _panel(_say("I _told_ you.")).balloons
        assert stressed.box.width > roman.box.width

    def test_a_panel_without_emphasis_writes_no_runs(self):
        core = _panel(_say("I told you.") + "  - caption: {text: Midnight.}\n")
        assert '"runs"' not in core.to_json()
        assert all(balloon.runs == () for balloon in core.balloons)

    def test_runs_survive_a_round_trip(self):
        core = _panel(_say("I _told_ you.") + "  - caption: {text: '_Never_ again.'}\n")
        assert PanelCore.from_json(core.to_json()) == core

    def test_runs_must_spell_the_line(self):
        with pytest.raises(ValidationError, match="spell"):
            CoreBalloon(
                id="b0",
                speaker="alice",
                order=0,
                kind=BalloonKind.SPEECH,
                box=Box(x=0, y=0, width=100, height=50),
                lines=("I told you.",),
                font_size=35.0,
                line_height=43.75,
                tail=Tail(start=(0, 0), end=(1, 1)),
                runs=((CoreRun(text="I said", face=Face.REGULAR),),),
            )

    def test_runs_must_be_given_for_every_line(self):
        with pytest.raises(ValidationError, match="every line"):
            CoreBalloon(
                id="b0",
                speaker="alice",
                order=0,
                kind=BalloonKind.SPEECH,
                box=Box(x=0, y=0, width=100, height=50),
                lines=("I told", "you."),
                font_size=35.0,
                line_height=43.75,
                tail=Tail(start=(0, 0), end=(1, 1)),
                runs=((CoreRun(text="I told", face=Face.REGULAR),),),
            )

    def test_an_italic_caption_stresses_in_bold_italic(self):
        (caption,) = _panel("  - caption: {text: '_Later._ The docks.', kind: locale}\n").captions
        faces = [run.face for line in caption.runs for run in line]
        assert Face.BOLD_ITALIC in faces
        assert Face.REGULAR not in faces

    def test_a_spoken_caption_quotes_outside_the_emphasis(self):
        (caption,) = _panel("  - caption: {text: '_Down!_', kind: spoken}\n").captions
        assert caption.lines == (f"{OPENING_QUOTE}Down!{CLOSING_QUOTE}",)
        assert caption.runs == (
            (
                CoreRun(text=OPENING_QUOTE, face=Face.REGULAR),
                CoreRun(text="Down!", face=Face.BOLD_ITALIC),
                CoreRun(text=CLOSING_QUOTE, face=Face.REGULAR),
            ),
        )

    def test_it_is_deterministic(self):
        script = _say("I _told_ you, _twice_.")
        assert _panel(script).to_json() == _panel(script).to_json()


class TestEmitters:
    def test_the_stressed_word_is_drawn_in_the_bold_italic_face(self):
        svg = render(_panel(_say("I _told_ you.")))
        bold = load_metrics(str(BOLD_ITALIC_FONT_PATH))
        roman = load_metrics(str(DEFAULT_FONT_PATH))
        assert bold.glyph_outlines("d")[0][0] in svg
        assert roman.glyph_outlines("d")[0][0] not in svg

    def test_the_drawing_is_the_measurement(self):
        core = _panel(_say("I _told_ you, _twice_."))
        svg = render(core)
        assert_svg_is_sound(svg, size=(core.width, core.height), font_sizes=[35.0])

    def test_live_text_marks_the_stress_with_a_tspan(self):
        svg = render(_panel(_say("I _told_ you.")), live_text=True)
        assert '>I <tspan font-weight="bold" font-style="italic">told</tspan> you.</text>' in svg

    def test_live_text_without_emphasis_has_no_tspan(self):
        svg = render(_panel(_say("I told you.")), live_text=True)
        assert "<tspan" not in svg

    def test_a_stressed_line_is_still_centred(self):
        """The centring width is the run measurement, so the line sits in the middle of
        its balloon exactly as wide as it was measured."""
        core = _panel(_say("I _told_ you."))
        (balloon,) = core.balloons
        svg = render(core, live_text=True)
        found = re.search(r'<text x="([0-9.]+)"', svg)
        assert found is not None
        start = float(found.group(1))
        width = Typeface().measure(styled("I _told_ you."), balloon.font_size)
        assert start == pytest.approx(balloon.box.x + (balloon.box.width - width) / 2, abs=0.01)
