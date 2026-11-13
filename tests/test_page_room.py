"""Whether a page has room for its tiers, its panels and its stacks, to the unit (#345).

`PageLayout` refuses a layout whose gutters and margins leave a tier, a panel or a stacked
panel no room, and says which. The mutation run found every margin of those sums unheld:
a margin counted three times, a gutter too many, a stack's height divided the wrong way,
`<=` relaxed -- each passed the suite. Each layout here sits exactly on one boundary, in
numbers floating point holds exactly, so the sum is tested at the unit where it turns.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from scenet.errors import RuleViolationError
from scenet.ir import PageFormat, PageLayout


def _layout(page: dict[str, Any], *pages: list[dict[str, Any]]) -> PageLayout:
    return PageLayout.model_validate({"page": page, "pages": [{"tiers": tiers} for tiers in pages]})


def _refusal(page: dict[str, Any], *pages: list[dict[str, Any]]) -> RuleViolationError:
    with pytest.raises(ValidationError) as caught:
        _layout(page, *pages)
    (error,) = caught.value.errors()
    found = (error.get("ctx") or {}).get("error")
    assert isinstance(found, RuleViolationError)
    assert found.rule == "page-layout"
    return found


def _uses(*names: str) -> list[dict[str, str]]:
    return [{"use": name} for name in names]


def _panels(count: int) -> dict[str, Any]:
    return {"panels": _uses(*(f"p{index}" for index in range(count)))}


class TestTheTiersOfAPage:
    """Height 80 between margins of 10: tier gutters of 40 leave 0 for three tiers."""

    PAGE: dict[str, Any] = {"size": [100, 100], "margin": 10, "gutter": 0, "tier_gutter": 40}

    def test_no_room_is_refused_and_says_which_page(self):
        refusal = _refusal(self.PAGE, [_panels(1)], [_panels(1)] * 3)
        assert str(refusal) == (
            "page 2 has no room for 3 tiers between its margins and tier gutters"
        )
        assert refusal.loc == ("pages", 1)

    def test_a_unit_of_room_is_room(self):
        # 80 - 2 * 39.5 = 1: counted with the margin twice and one gutter fewer than tiers.
        page = {**self.PAGE, "tier_gutter": 39.5}
        assert _layout(page, [_panels(1)] * 3).pages


class TestThePanelsOfATier:
    """Width 80 between margins of 10: gutters of 40 leave 0 for three panels."""

    PAGE: dict[str, Any] = {"size": [100, 400], "margin": 10, "gutter": 40, "tier_gutter": 0}

    def test_no_room_is_refused_and_says_which_tier(self):
        refusal = _refusal(self.PAGE, [_panels(1)], [_panels(1), _panels(3)])
        assert str(refusal) == (
            "tier 2 of page 2 has no room for 3 panels between its margins and gutters"
        )
        assert refusal.loc == ("pages", 1, "tiers", 1)

    def test_columns_are_counted_as_columns(self):
        columns = {"columns": [{"panels": _uses(name)} for name in "abc"]}
        refusal = _refusal(self.PAGE, [columns])
        assert str(refusal) == (
            "tier 1 of page 1 has no room for 3 columns between its margins and gutters"
        )

    def test_a_unit_of_room_is_room(self):
        # 80 - 2 * 39.5 = 1.
        page = {**self.PAGE, "gutter": 39.5}
        assert _layout(page, [_panels(3)]).pages


class TestTheStackOfAColumn:
    """No margins, tier gutters of 8, two tiers weighted 1 and 3 on a page 76 high: the
    tiers share 68, so the first is 17 high and the second 51."""

    PAGE: dict[str, Any] = {"size": [400, 76], "margin": 0, "gutter": 0, "tier_gutter": 8}

    @staticmethod
    def _stack(count: int, height: float) -> dict[str, Any]:
        return {
            "height": height,
            "columns": [
                {"panels": _uses("solo")},
                {"panels": _uses(*(f"s{index}" for index in range(count)))},
            ],
        }

    def test_a_unit_of_room_is_room(self):
        # 17 - 8 * (3 - 1) = 1.
        assert _layout(self.PAGE, [self._stack(3, 1), {"height": 3, **_panels(1)}])

    def test_no_room_is_refused_and_says_which_column(self):
        # 17 - 8 * 3 < 0 for four panels.
        refusal = _refusal(self.PAGE, [self._stack(4, 1), {"height": 3, **_panels(1)}])
        assert str(refusal) == (
            "column 2 of tier 1 of page 1 has no room for 4 panels between its tier gutters"
        )
        assert refusal.loc == ("pages", 0, "tiers", 0, "columns", 1)

    def test_a_tier_s_share_is_its_weight_over_the_total(self):
        # The second tier is 68 * 3 / 4 = 51 high, so six stacked panels leave 51 - 40 = 11.
        assert _layout(self.PAGE, [{"height": 1, **_panels(1)}, self._stack(6, 3)])


class TestTwoStacksSideBySide:
    def test_they_are_refused_and_named(self):
        tier = {
            "columns": [
                {"panels": _uses("a")},
                {"panels": _uses("b", "c")},
                {"panels": _uses("d", "e")},
            ]
        }
        refusal = _refusal({"size": [2000, 3000]}, [_panels(1)], [_panels(1), tier])
        assert str(refusal).startswith(
            "columns 2 and 3 of tier 2 of page 2 are both stacks; with no panel "
        )
        assert refusal.loc == ("pages", 1, "tiers", 1, "columns", 2)


class TestAPageFormat:
    """A page needs a width, a height, and an inside between its margins."""

    @staticmethod
    def _format_refusal(**fields: Any) -> RuleViolationError:
        with pytest.raises(ValidationError) as caught:
            PageFormat.model_validate(fields)
        (error,) = caught.value.errors()
        found = (error.get("ctx") or {}).get("error")
        assert isinstance(found, RuleViolationError)
        return found

    @pytest.mark.parametrize("size", [(0, 100), (100, 0), (-1, 100), (100, -1)])
    def test_a_side_of_nothing_is_refused(self, size: tuple[float, float]):
        refusal = self._format_refusal(size=size, margin=0)
        assert (str(refusal), refusal.rule, refusal.loc) == (
            "page size must be positive",
            "page-layout",
            ("page",),
        )

    def test_a_side_of_one_unit_is_a_page(self):
        assert PageFormat(size=(1, 1), margin=0).width == 1

    def test_margins_that_meet_leave_no_inside(self):
        refusal = self._format_refusal(size=(100, 200), margin=50)
        assert (str(refusal), refusal.rule, refusal.loc) == (
            "the page margin leaves no room for panels",
            "page-layout",
            ("page",),
        )

    def test_margins_a_unit_apart_leave_one(self):
        assert PageFormat(size=(100, 200), margin=49.5).margin == 49.5
