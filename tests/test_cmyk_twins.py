"""The tinted palette's CMYK twins, and black's ramp, for print (#280).

Every colour the compiler owns has a CMYK twin, converted by `scripts/make_palette.py` through
a printing condition's ICC profile -- CGATS21-2-CRPC6, GRACoL 2013 -- with littleCMS, relative
colorimetric with black point compensation, and committed as a table print reads. The tests
hold the table to the conversion, then check on paper what the twin rule asks on screen: each
twin, read back through the same profile, has its sRGB colour's lightness.
"""

import hashlib
import importlib.util
import sys
from itertools import pairwise
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image, ImageCms

from scenet.emit.cmyk import BLACK_RAMP, CMYK, CONDITION
from scenet.solve.backdrop import TINTED
from scenet.solve.balloons import CAPTION_COLOURS

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "scripts" / "profiles"

#: The profiles as published: a changed byte is an altered profile, which neither licence allows.
DIGESTS = {
    "sRGB2014.icc": "384b832de3412066743b52a75ee906b6fb9fb8d9e09e936fc2c43223815c6e0a",
    "GRACoL2013_CRPC6.icc": "4ebbfad6bc9cfc033fdafdd8ac5df8159208932cb16d9a6596d349ae7ab50443",
}

#: How far, in CIELAB L*, a twin may print from its colour: what whole percents allow, and the
#: pale day sky, which lies just outside the condition's gamut.
LIGHTNESS = 1.5


def _load_generator() -> ModuleType:
    path = ROOT / "scripts" / "make_palette.py"
    spec = importlib.util.spec_from_file_location("make_palette", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_palette"] = module
    spec.loader.exec_module(module)
    return module


make_palette = _load_generator()

COLOURS = sorted(
    {colour for colours in TINTED.values() for colour in colours} | set(CAPTION_COLOURS.values())
)


@pytest.mark.parametrize("name", sorted(DIGESTS))
def test_the_profiles_are_as_published(name: str):
    assert hashlib.sha256((PROFILES / name).read_bytes()).hexdigest() == DIGESTS[name]


def test_the_condition_is_the_registrys_name():
    assert CONDITION == "CGATS21-2-CRPC6"


def test_every_colour_the_compiler_owns_has_a_twin():
    assert sorted(CMYK) == COLOURS


def test_the_table_is_what_the_conversion_makes():
    assert make_palette.cmyk() == CMYK
    assert make_palette.black_ramp() == BLACK_RAMP


def test_the_generated_module_is_committed_as_the_script_writes_it():
    assert make_palette.cmyk_source() == (ROOT / "src" / "scenet" / "emit" / "cmyk.py").read_text(
        encoding="utf-8"
    )


def test_every_ink_is_a_whole_percent():
    for inks in CMYK.values():
        assert len(inks) == 4
        assert all(isinstance(value, int) and 0 <= value <= 100 for value in inks)


def test_no_twin_takes_more_ink_than_the_conditions_own_black():
    deepest = sum(make_palette.convert("#000000"))
    assert all(sum(inks) <= deepest for inks in CMYK.values())


def _printed_lightness(inks: tuple[int, int, int, int]) -> float:
    """CIELAB L* of a CMYK, read back through the condition's profile."""
    profile = ImageCms.getOpenProfile(str(PROFILES / "GRACoL2013_CRPC6.icc"))
    lab = ImageCms.createProfile("LAB", 5000)
    transform = ImageCms.buildTransform(
        profile, lab, "CMYK", "LAB", renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC
    )
    image = Image.new("CMYK", (1, 1), tuple(round(value * 255 / 100) for value in inks))
    return ImageCms.applyTransform(image, transform).getpixel((0, 0))[0] * 100 / 255


@pytest.mark.parametrize("colour", COLOURS)
def test_a_twin_prints_at_its_colours_lightness(colour: str):
    """The twin rule, on paper: what the colour shows on screen, the twin prints."""
    assert _printed_lightness(CMYK[colour]) == pytest.approx(
        make_palette.lightness_star(colour), abs=LIGHTNESS
    )


class TestBlacksRamp:
    def test_it_holds_the_lightness_of_every_whole_percent_of_black(self):
        assert len(BLACK_RAMP) == 101
        assert BLACK_RAMP[0] == 100.0

    def test_more_black_prints_darker(self):
        assert all(lighter > darker for lighter, darker in pairwise(BLACK_RAMP))

    @pytest.mark.parametrize("percent", [10, 50, 90, 100])
    def test_it_is_what_the_profile_prints(self, percent: int):
        assert BLACK_RAMP[percent] == pytest.approx(_printed_lightness((0, 0, 0, percent)), abs=0.5)
