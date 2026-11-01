"""The `warm` caption tone (#244): the yellow `locale` caption #28 left out.

#28 shipped caption tones as greys and kept the classic yellow out because the language had
no colour policy. With one, `warm` follows the same rule as the tinted ladder. Its value is a
rung of the ladder, the `day` row's atmosphere, `#eeeeee`, taken by index as `pale` and `ink`
are. Its colour is that grey's twin, a pale yellow of the same lightness, drawn only in a
palette that has colour. In `mono` it is the grey, which is what a black-and-white reprint
does to a yellow caption.

Its lettering is chosen on the grey, as every decision is, and the 4.5:1 floor is checked on
the colour too, with the full WCAG luminance, since a colour weighs less than its grey.
"""

import json
import math
import re

import pytest

from scenet import CaptionTone, Palette, PanelCore, compile_source, render
from scenet.ir import TimeOfDay
from scenet.solve.backdrop import LADDER
from scenet.solve.balloons import (
    CAPTION_COLOURS,
    CAPTION_INK,
    CAPTION_TONES,
    LETTERING_FLOOR,
    caption_colour,
    letter_tone,
)
from tests.test_palette import without_colour
from tests.test_tinted_ladder import TOLERANCE, make_palette

WARM = CAPTION_COLOURS[CaptionTone.WARM]

PANEL = """\
panel: {size: [1400, 900]}
camera: {shot: long_shot}
setting: {place: field, horizon: low, time: day}
cast:
  alice: {reference: alice, pose: standing_neutral, at: center}
script:
  - caption: {text: "Noon. Nothing for miles.", kind: locale, tone: warm, prefer: top_left}
  - caption: {text: "She had walked since dawn.", kind: monologue, tone: pale, prefer: top_right}
  - caption: {text: "Continued next issue.", kind: editorial, tone: ink, prefer: bottom_right}
"""


def tinted(text: str = PANEL) -> str:
    return f"palette: tinted\n{text}"


class TestTheTone:
    def test_it_is_written_like_any_tone(self):
        source = "cast: {a: {reference: alice}}\nscript: [{caption: {text: Then., tone: warm}}]"
        assert compile_source(source).core.captions[0].fill == CAPTION_TONES[CaptionTone.WARM]

    def test_paper_is_still_the_default(self):
        """So no caption written before `warm` existed changes."""
        assert CAPTION_TONES[CaptionTone.PAPER] == "#ffffff"

    def test_its_value_is_a_rung_of_the_ladder(self):
        """The `day` row's atmosphere, by index, as `pale` and `ink` are rungs of that row."""
        assert CAPTION_TONES[CaptionTone.WARM] == LADDER[TimeOfDay.DAY][-1]

    def test_it_is_lettered_in_ink(self):
        assert letter_tone(CAPTION_TONES[CaptionTone.WARM]) == CAPTION_INK


class TestItsColour:
    def test_it_has_the_lightness_of_its_grey(self):
        grey = CAPTION_TONES[CaptionTone.WARM]
        assert make_palette.oklab(WARM)[0] == pytest.approx(
            make_palette.oklab(grey)[0], abs=TOLERANCE
        )

    def test_it_is_a_yellow(self):
        _, a, b = make_palette.oklab(WARM)
        hue = math.degrees(math.atan2(b, a)) % 360
        assert 85 <= hue <= 115
        assert (a * a + b * b) ** 0.5 > 0.05

    def test_its_lettering_clears_the_floor_on_the_colour_too(self):
        """Chosen on the grey; checked on what the reader actually sees."""
        ink = letter_tone(CAPTION_TONES[CaptionTone.WARM])
        assert make_palette.contrast(ink, WARM) >= LETTERING_FLOOR

    def test_it_is_what_the_rule_produces(self):
        assert make_palette.warm() == WARM, "run `uv run python scripts/make_palette.py`"

    def test_only_warm_has_a_colour(self):
        """`paper`, `pale` and `ink` stay neutral in every palette: a tone is fixed (#28)."""
        assert set(CAPTION_COLOURS) == {CaptionTone.WARM}
        for tone in CaptionTone:
            assert caption_colour(tone, Palette.MONO) == ""
        assert caption_colour(CaptionTone.WARM, Palette.TINTED) == WARM
        for tone in (CaptionTone.PAPER, CaptionTone.PALE, CaptionTone.INK):
            assert caption_colour(tone, Palette.TINTED) == ""


class TestCore:
    def test_in_mono_it_is_its_grey(self):
        text = compile_source(PANEL).core.to_json()
        (warm, *_) = json.loads(text)["captions"]
        assert warm["fill"] == CAPTION_TONES[CaptionTone.WARM]
        assert "colour" not in warm

    def test_tinted_it_carries_its_colour_beside_its_grey(self):
        warm, pale, ink = compile_source(tinted()).core.captions
        assert (warm.fill, warm.colour) == (CAPTION_TONES[CaptionTone.WARM], WARM)
        assert (pale.colour, ink.colour) == ("", "")
        assert warm.ink == CAPTION_INK

    def test_taking_the_colour_out_gives_the_mono_core(self):
        """Rule 2: the yellow moves no caption and changes no lettering."""
        assert without_colour(compile_source(tinted()).core) == compile_source(PANEL).core.to_json()

    def test_in_mono_the_object_is_the_mono_one(self):
        assert compile_source(tinted()).core.as_mono() == compile_source(PANEL).core

    def test_a_tinted_core_reads_back(self):
        core = compile_source(tinted()).core
        assert PanelCore.from_json(core.to_json()) == core


class TestDrawn:
    def test_tinted_the_box_is_yellow(self):
        svg = render(compile_source(tinted()).core)
        assert re.search(rf'<rect [^>]*fill="{WARM}"', svg)

    def test_in_mono_the_box_is_its_grey(self):
        grey = CAPTION_TONES[CaptionTone.WARM]
        svg = render(compile_source(PANEL).core)
        assert re.search(rf'<rect [^>]*fill="{grey}"', svg)
        assert WARM not in svg

    def test_drawn_in_mono_a_tinted_panel_is_the_mono_one(self):
        assert render(compile_source(tinted()).core, mono=True) == render(
            compile_source(PANEL).core
        )
