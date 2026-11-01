"""The tinted ladder: the value ladder in colour, with every value kept (#244).

The colour policy rests on one rule: a colour is a *twin* of a grey on the ladder, never a
replacement for it. It has the grey's OKLab lightness, so in monochrome it is the grey, the
ladder stays monotonic in depth, and every contrast floor already tested still holds. What
is testable about that is arithmetic, and it is all here. Whether the hues are the right
hues is a question about a picture, and `scripts/setting_sheet.py --palette tinted` is the
instrument for it.

The arithmetic is checked with the full OKLab and WCAG formulas from
`scripts/make_palette.py`, not with the runtime's, because the runtime's are shortcuts that
hold only for a neutral grey -- which is why they refuse a colour, and why a decision the
solver makes is always made on the grey.
"""

import importlib.util
import sys
from itertools import pairwise
from pathlib import Path
from types import ModuleType

import pytest

from scenet.ir import Plane, TimeOfDay
from scenet.solve.backdrop import LADDER, TINTED, contrast_ratio, lightness
from scenet.solve.balloons import CAPTION_TONES, SEPARATION_FLOOR

ROOT = Path(__file__).resolve().parents[1]

REGENERATE = "run `uv run python scripts/make_palette.py` and paste its table"

#: How far a colour's lightness may sit from its grey's: what rounding to `#rrggbb` allows.
TOLERANCE = 0.005


def _load_generator() -> ModuleType:
    """Import `scripts/make_palette.py`, which is a script rather than a package module."""
    path = ROOT / "scripts" / "make_palette.py"
    spec = importlib.util.spec_from_file_location("make_palette", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_palette"] = module
    spec.loader.exec_module(module)
    return module


make_palette = _load_generator()

RUNGS = [(time, rung) for time in TimeOfDay for rung in range(len(Plane) + 1)]
RUNG_IDS = [f"{time.value}-{rung}" for time, rung in RUNGS]


class TestTheRulerIsThePublishedOne:
    """The table is only as good as the formulas that check it, so they are pinned to
    values published elsewhere before they are trusted with anything."""

    def test_mid_grey_has_the_lightness_css_gives_it(self):
        """`#808080` is `oklch(59.99% 0 0)` in CSS Color 4."""
        lightness_, a, b = make_palette.oklab("#808080")
        assert lightness_ == pytest.approx(0.5999, abs=1e-4)
        assert (a, b) == pytest.approx((0.0, 0.0), abs=1e-6)

    def test_red_is_where_ottosson_puts_it(self):
        """sRGB red in OKLab, from the post that defines it."""
        assert make_palette.oklab("#ff0000") == pytest.approx(
            (0.627955, 0.224863, 0.125846), abs=1e-5
        )

    def test_red_weighs_its_coefficient_in_wcag(self):
        """Relative luminance weighs red at 0.2126, which the neutral shortcut never
        needs and a colour always does."""
        assert make_palette.luminance("#ff0000") == pytest.approx(0.2126, abs=1e-6)

    def test_red_on_white_is_just_under_four_to_one(self):
        assert make_palette.contrast("#ff0000", "#ffffff") == pytest.approx(3.998, abs=1e-3)

    @pytest.mark.parametrize("grey", [tone for rungs in LADDER.values() for tone in rungs])
    def test_on_a_grey_the_two_rulers_agree(self, grey: str):
        """The runtime's shortcuts and the full formulas are one ruler on a neutral -- to the
        last digits Ottosson's published matrices carry, whose rows sum to one within 1e-8."""
        assert make_palette.oklab(grey)[0] == pytest.approx(lightness(grey), abs=1e-7)
        assert make_palette.contrast(grey, "#ffffff") == pytest.approx(
            contrast_ratio(grey, "#ffffff"), abs=1e-9
        )


class TestEveryColourKeepsItsValue:
    """Rule 1 of the policy: same lightness as the grey it stands for."""

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_it_has_a_colour_for_every_rung(self, time: TimeOfDay):
        assert len(TINTED[time]) == len(LADDER[time])

    @pytest.mark.parametrize(("time", "rung"), RUNGS, ids=RUNG_IDS)
    def test_it_is_written_the_way_the_ladder_is(self, time: TimeOfDay, rung: int):
        colour = TINTED[time][rung]
        assert len(colour) == 7
        assert colour.startswith("#")
        assert colour == colour.lower()
        int(colour[1:], 16)

    @pytest.mark.parametrize(("time", "rung"), RUNGS, ids=RUNG_IDS)
    def test_it_has_the_lightness_of_its_grey(self, time: TimeOfDay, rung: int):
        grey, colour = LADDER[time][rung], TINTED[time][rung]
        assert make_palette.oklab(colour)[0] == pytest.approx(lightness(grey), abs=TOLERANCE)

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_it_is_monotonic_in_depth(self, time: TimeOfDay):
        values = [make_palette.oklab(colour)[0] for colour in TINTED[time]]
        assert values == sorted(values), f"{time.value} is not monotonic"

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_every_rung_is_distinguishable(self, time: TimeOfDay):
        """The same margin the grey ladder is held to."""
        values = [make_palette.oklab(colour)[0] for colour in TINTED[time]]
        assert min(b - a for a, b in pairwise(values)) > 0.02


class TestItIsColour:
    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_the_atmosphere_has_a_hue_at_every_hour(self, time: TimeOfDay):
        """A tinted ladder whose sky is grey would be a grey ladder with extra steps."""
        _, a, b = make_palette.oklab(TINTED[time][-1])
        assert (a * a + b * b) ** 0.5 > 0.01

    def test_the_table_is_what_the_rule_produces(self):
        """The hexes are an output, not a tuning. Each hour's two hues and two chromas
        are the inputs, in the generator, and the table must be exactly what they give."""
        assert make_palette.tinted() == TINTED, REGENERATE

    def test_its_chroma_and_hue_are_written_beside_it(self):
        """The comment above the table is generated with it, so it cannot go stale."""
        source = ROOT / "src" / "scenet" / "solve" / "backdrop.py"
        assert make_palette.table_source() in source.read_text(encoding="utf-8"), REGENERATE


class TestTheFloorsHoldInColour:
    """At equal OKLab lightness a colour weighs 1-10% less in WCAG luminance than its
    grey, so a floor that holds on the greys is checked again on the colours."""

    @pytest.mark.parametrize(("time", "rung"), RUNGS, ids=RUNG_IDS)
    def test_some_tone_separates_the_box_from_every_rung(self, time: TimeOfDay, rung: int):
        """The escape the caption palette owes the author, over the tinted ladder."""
        behind = TINTED[time][rung]
        best = max(make_palette.contrast(fill, behind) for fill in CAPTION_TONES.values())
        assert best >= SEPARATION_FLOOR, f"no caption tone separates from {behind}"


class TestTheRuntimeMeasuresRefuseAColour:
    """Rule 2 of the policy: every decision the solver makes from a value is made on the
    grey. The runtime's measures are exact only for a neutral, so they refuse anything
    else rather than answer it wrongly."""

    @pytest.mark.parametrize("colour", sorted({c for rungs in TINTED.values() for c in rungs}))
    def test_lightness_refuses_every_colour_of_the_table(self, colour: str):
        """So no value of the table is a grey in disguise, and none can reach a decision."""
        with pytest.raises(ValueError, match="not a neutral grey"):
            lightness(colour)

    def test_contrast_refuses_a_colour_on_either_side(self):
        with pytest.raises(ValueError, match="not a neutral grey"):
            contrast_ratio("#ffffff", "#fdefba")
        with pytest.raises(ValueError, match="not a neutral grey"):
            contrast_ratio("#fdefba", "#ffffff")

    @pytest.mark.parametrize("colour", ["#ff0000", "#00ff00", "#0000ff", "#fefeff", "#e8e6e1"])
    def test_a_single_channel_off_is_enough(self, colour: str):
        with pytest.raises(ValueError, match="not a neutral grey"):
            lightness(colour)

    def test_a_grey_in_capitals_is_still_a_grey(self):
        assert lightness("#ADADAD") == lightness("#adadad")
