"""The page solver at its edges: where an inset just fits, where a lean just closes a
panel, and where a mistake is reported.

These pin the boundaries mutation testing found unchecked (#95). The page tests build
whole documents; these call the solver's pieces directly, because the edge each one
holds is a single number -- a gutter, a height -- that a document only reaches by
coincidence.
"""

import math

import pytest

from scenet.errors import RuleViolationError
from scenet.geom import BBox
from scenet.ir import Corner, Inset, PageFormat, PageSpec, PanelPlacement
from scenet.solve.page import _slanted, _with_insets, resolve_frames


def _inset(use: str, at: Corner, size: float = 0.25) -> Inset:
    return Inset(use=use, at=at, size=size)


def _panel(*insets: Inset) -> PanelPlacement:
    return PanelPlacement(use="p", insets=insets)


class TestAnInsetThatDoesNotFit:
    def test_it_is_described_as_a_person_would_say_it(self):
        """Lengths without trailing zeros, the size as a whole percentage."""
        with pytest.raises(RuleViolationError) as caught:
            _with_insets(_panel(_inset("i", Corner.TOP_LEFT)), BBox(0, 0, 100, 50), 90, ("here",))
        assert "a 100 by 50 frame" in str(caught.value)
        assert "an inset 25% of its size" in str(caught.value)
        assert caught.value.loc == ("here", "insets", 0)

    def test_one_that_meets_the_far_edge_exactly_still_fits(self):
        """Half the height, a gutter in from the top: 50 + 50 is the whole 100."""
        frames = _with_insets(
            _panel(_inset("i", Corner.TOP_LEFT, 0.5)), BBox(0, 0, 200, 100), 50, ()
        )
        assert [frame.panel for frame in frames] == ["p", "i"]


class TestTwoInsetsInOnePanel:
    """Each inset keeps a gutter of white around it. Two in one panel may meet at the
    edge of that ring, but not cross it. With a gutter of 40 and insets a quarter of the
    panel, a 240-unit side leaves the two exactly a gutter apart, and 230 leaves them 30.
    """

    @pytest.mark.parametrize(
        ("area", "second"),
        [(BBox(0, 0, 240, 200), Corner.TOP_RIGHT), (BBox(0, 0, 200, 240), Corner.BOTTOM_LEFT)],
        ids=["across", "down"],
    )
    def test_a_gutter_apart_both_fit(self, area: BBox, second: Corner):
        placement = _panel(_inset("one", Corner.TOP_LEFT), _inset("two", second))
        frames = _with_insets(placement, area, 40, ())
        assert sorted(frame.panel for frame in frames) == ["one", "p", "two"]

    @pytest.mark.parametrize(
        ("area", "second"),
        [(BBox(0, 0, 230, 200), Corner.TOP_RIGHT), (BBox(0, 0, 200, 230), Corner.BOTTOM_LEFT)],
        ids=["across", "down"],
    )
    def test_closer_than_a_gutter_they_are_refused(self, area: BBox, second: Corner):
        placement = _panel(_inset("one", Corner.TOP_LEFT), _inset("two", second))
        with pytest.raises(RuleViolationError, match="'one' and 'two'"):
            _with_insets(placement, area, 40, ())


def _tier(*weights: float) -> list[PanelPlacement]:
    return [
        PanelPlacement(use=use, width=weight) for use, weight in zip("abc", weights, strict=False)
    ]


#: A slant of 30 degrees across a 1000-unit row with gutters of 40.
SLANT, WIDTH, GUTTER = 30.0, 1000.0, 40.0
LEAN = math.tan(math.radians(SLANT))
HALF = GUTTER / (2 * math.cos(math.radians(SLANT)))


class TestASteepSlant:
    """Leaning the gutters right narrows the first panel at its bottom and the last at its
    top; a panel between two gutters keeps its width all the way down. 1000 units tall,
    a quarter-width panel closes at whichever end its gutter leans across."""

    def test_a_narrow_last_panel_closing_at_its_top_is_refused(self):
        with pytest.raises(RuleViolationError, match="panel 'b'") as caught:
            _slanted(_tier(3, 1), SLANT, BBox(0, 0, WIDTH, 1000), GUTTER, ("tier",))
        assert caught.value.loc == ("tier", "slant")

    def test_a_narrow_first_panel_closing_at_its_bottom_is_refused(self):
        """In from the page's edge, as every real tier is: at x = 0 the first panel's
        upright left edge is 0, and a width measured from it cannot tell `-` from `+`."""
        with pytest.raises(RuleViolationError, match="panel 'a'"):
            _slanted(_tier(1, 3), SLANT, BBox(100, 0, WIDTH, 1000), GUTTER, ())

    def test_a_narrow_panel_between_two_wide_ones_takes_the_lean(self):
        """Its two gutters lean together, so it is as wide at the top as at the bottom,
        however far its top-left corner is from its bottom-right."""
        frames = _slanted(_tier(4, 1, 4), SLANT, BBox(0, 0, WIDTH, 600), GUTTER, ())
        assert [frame.panel for frame in frames] == ["a", "b", "c"]

    def test_half_a_unit_left_at_an_end_is_still_a_panel(self):
        """Tall enough that the last panel's top and the first panel's bottom are half a
        unit wide: narrow, but not closed."""
        centre = WIDTH / 2
        height = 2 * (WIDTH - centre - HALF - 0.5) / LEAN
        first, last = _slanted(_tier(1, 1), SLANT, BBox(0, 0, WIDTH, height), GUTTER, ())
        assert first.outline is not None
        assert last.outline is not None
        top_left, top_right = last.outline[0], last.outline[1]
        assert top_right[0] - top_left[0] == pytest.approx(0.5, abs=0.02)
        bottom_right, bottom_left = first.outline[2], first.outline[3]
        assert bottom_right[0] - bottom_left[0] == pytest.approx(0.5, abs=0.02)


class TestWhereAPageMistakeIsReported:
    def test_an_inset_in_a_stacked_panel_is_located_down_its_column(self):
        """A gutter of 900 leaves each column 450 wide, and half of that plus a gutter
        does not fit -- reported at the inset, through its column and its place in the
        stack, on the first page when no page is named."""
        page = PageSpec.model_validate(
            {
                "tiers": [
                    {
                        "columns": [
                            {"panels": [{"use": "tall"}]},
                            {
                                "panels": [
                                    {"use": "x"},
                                    {
                                        "use": "y",
                                        "insets": [{"use": "i", "at": "top_left", "size": 0.5}],
                                    },
                                ]
                            },
                        ]
                    }
                ]
            }
        )
        with pytest.raises(RuleViolationError) as caught:
            resolve_frames(PageFormat(gutter=900), page)
        assert caught.value.loc == (
            "pages", 0, "tiers", 0, "columns", 1, "panels", 1, "insets", 0,
        )  # fmt: skip
