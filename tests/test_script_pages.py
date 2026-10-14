"""A comic script's PAGE headings lay its panels out on pages.

Pages exist in YAML scenes since #66; a script's `PAGE ONE` only kept panel numbers apart.
Dark Horse leaves "exact panel layout" to the artist, and Scenet is the artist here, so a
page's panels are laid out in tiers by a fixed rule -- three tiers at most, as a lettering
height assumes -- unless the writer says otherwise with `@tiers:`.
"""

from pathlib import Path

import pytest

from scenet import compile_script
from scenet.cli import main
from scenet.diagnostics import diagnose_script
from scenet.errors import ScriptSyntaxError
from scenet.frontends.script_front import default_tiers, parse_script_document

FRONT = "---\ncast: {ALICE: {reference: alice}}\n---\n"


def panels(count: int, *, start: int = 1) -> str:
    return "".join(
        f"PANEL {number}\nALICE\nLine {number}.\n\n" for number in range(start, start + count)
    )


def tiers(script: str) -> list[list[list[str]]]:
    """Each page's panels, tier by tier, as the frames lay them out."""
    book = compile_script(FRONT + script)
    laid_out = []
    for page in book.pages:
        rows: dict[float, list[str]] = {}
        for frame in page.frames:
            rows.setdefault(frame.y, []).append(frame.panel)
        laid_out.append([rows[y] for y in sorted(rows)])
    return laid_out


class TestTheDefaultTiers:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (1, [1]),
            (2, [1, 1]),
            (3, [1, 1, 1]),
            (4, [2, 2]),
            (5, [2, 1, 2]),
            (6, [2, 2, 2]),
            (7, [2, 3, 2]),
            (8, [3, 2, 3]),
            (9, [3, 3, 3]),
            (10, [3, 3, 2, 2]),
            (11, [3, 3, 3, 2]),
            (12, [3, 3, 3, 3]),
        ],
    )
    def test_a_fixed_rule_by_count(self, count: int, expected: list[int]):
        assert default_tiers(count) == expected
        assert sum(expected) == count


class TestPages:
    def test_each_page_heading_is_a_page(self):
        laid_out = tiers("PAGE ONE\n" + panels(2) + "PAGE TWO\n" + panels(3))
        assert laid_out == [[["1-1"], ["1-2"]], [["2-1"], ["2-2"], ["2-3"]]]

    def test_a_page_of_five_is_two_one_two(self):
        assert tiers("PAGE ONE (five panels)\n" + panels(5)) == [[["1", "2"], ["3"], ["4", "5"]]]

    def test_tiers_may_be_written(self):
        script = "PAGE ONE\n@tiers: 1 2\n" + panels(3)
        assert tiers(script) == [[["1"], ["2", "3"]]]

    def test_tiers_that_do_not_add_up_are_a_page_layout_fault(self):
        with pytest.raises(ScriptSyntaxError) as raised:
            compile_script(FRONT + "PAGE ONE\n@tiers: 2 2\n" + panels(3))
        assert (raised.value.rule, raised.value.line) == ("page-layout", 5)

    def test_tiers_belong_right_after_the_page_heading(self):
        with pytest.raises(ScriptSyntaxError, match="PAGE heading") as raised:
            compile_script(FRONT + "PAGE ONE\nPANEL 1\n@tiers: 1\n")
        assert raised.value.line == 6

    def test_panels_before_the_first_page_are_on_none(self):
        book = compile_script(FRONT + panels(1) + "PAGE ONE\n" + panels(1, start=2))
        assert list(book.panels) == ["1", "2"]
        (page,) = book.pages
        assert [frame.panel for frame in page.frames] == ["2"]

    def test_a_script_without_page_headings_has_no_pages(self):
        assert compile_script(FRONT + panels(2)).pages == ()

    def test_the_front_matter_sets_the_page_format(self):
        script = "---\ncast: {ALICE: {reference: alice}}\npage: {size: [1200, 1800]}\n---\n"
        book = compile_script(script + "PAGE ONE\n" + panels(1))
        assert (book.pages[0].width, book.pages[0].height) == (1200, 1800)

    def test_but_not_the_pages(self):
        script = "---\ncast: {ALICE: {reference: alice}}\npages: []\n---\n"
        with pytest.raises(ScriptSyntaxError, match="PAGE headings") as raised:
            parse_script_document(script + "PAGE ONE\n" + panels(1))
        assert raised.value.rule == "page-layout"

    def test_check_and_build_agree_on_a_paged_script(self):
        script = FRONT + "PAGE ONE\n" + panels(4)
        assert diagnose_script(script, deep=True) == []
        assert len(compile_script(script).pages) == 1


def test_scenet_build_writes_the_pages(tmp_path: Path):
    path = tmp_path / "x.script"
    path.write_text(FRONT + "PAGE ONE\n" + panels(2), encoding="utf-8")
    assert main(["build", str(path), "--core", "--debug"]) == 0
    for name in ("x.page-1.svg", "x.page-1.core.json", "x.page-1.debug.svg", "x.1.svg"):
        assert (tmp_path / name).exists(), name
