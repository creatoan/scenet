"""Greys print on black alone, at the lightness they show on screen (#280).

A grey used to print as K = 1 - L, its OKLab lightness, with no press curve: measured through
the printing condition the colours print under, that is far too light -- `#707070` at K 45%
prints L* 67.5, where the screen shows 47. So a grey now prints at the K whose ink, alone,
prints its lightness under that condition (`scenet.emit.cmyk.BLACK_RAMP`), once black point
compensation has put the screen's black on the press's, as it does for every colour's twin. A
grey darker than black alone can print takes it all.
"""

import pytest

from scenet.emit.cmyk import BLACK_POINT, BLACK_RAMP
from scenet.emit.marks import Paint, Role
from scenet.emit.pdf import RICH_BLACK, black_for, ink, lightness_star
from scenet.solve.backdrop import LADDER

GREYS = sorted({grey for greys in LADDER.values() for grey in greys} | {"#e8e6e1", "#ffffff"})


def _luminance(lightness: float) -> float:
    return ((lightness + 16) / 116) ** 3 if lightness > 8 else lightness / 903.3


def _lightness(luminance: float) -> float:
    return 116 * luminance ** (1 / 3) - 16 if luminance > 0.008856 else luminance * 903.3


def _ramp(black: float) -> float:
    """The L* black alone prints at, between whole percents, as the table is read."""
    percent = black * 100
    low = min(int(percent), 99)
    return BLACK_RAMP[low] + (BLACK_RAMP[low + 1] - BLACK_RAMP[low]) * (percent - low)


def test_lightness_star_is_cielabs():
    assert lightness_star("#ffffff") == pytest.approx(100.0)
    assert lightness_star("#000000") == 0.0
    assert lightness_star("#777777") == pytest.approx(50.03, abs=0.01)


@pytest.mark.parametrize("grey", GREYS)
def test_a_grey_prints_at_its_lightness_after_black_point_compensation(grey: str):
    black = _luminance(BLACK_POINT)
    wanted = _lightness(black + _luminance(lightness_star(grey)) * (1 - black))
    found = black_for(grey)
    assert 0.0 <= found <= 1.0
    if wanted >= BLACK_RAMP[-1]:
        assert _ramp(found) == pytest.approx(wanted, abs=0.01)
    else:
        assert found == 1.0


def test_the_paper_takes_no_black_and_a_darker_grey_takes_more():
    assert black_for("#ffffff") == 0.0
    blacks = [black_for(grey) for grey in sorted(GREYS, key=lightness_star, reverse=True)]
    assert blacks == sorted(blacks)


def test_the_mid_grey_prints_as_dark_as_it_shows():
    """The measurement that forced the ramp: #707070 needs about 68%, not 1 - L's 45%."""
    assert black_for("#707070") == pytest.approx(0.68, abs=0.02)


def test_a_grey_paint_prints_its_black_and_nothing_else():
    paint = Paint("#707070", Role.TONE, "#707070")
    assert ink(paint) == (0.0, 0.0, 0.0, pytest.approx(black_for("#707070")))


def test_the_night_foreground_still_prints_rich_black():
    assert ink(Paint("#020202", Role.MASS, "#020202")) == RICH_BLACK
