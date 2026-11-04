"""A page's printed size and its bleed (#80).

#66 laid pages out in abstract units; print gives them a size: a page unit prints as a tenth
of a millimetre. `bleed` is how far the printed sheet runs past the trim on every side, in
the same units, so that art reaching the edge can be cut cleanly. Nothing in the layout
moves: the bleed is paper around the page, and a page without one is what it always was.
"""

import io

import pytest
from pypdf import PdfReader

from scenet import compile_script
from scenet.core import PageCore
from scenet.emit.pdf import POINTS_PER_UNIT, render_pdf
from scenet.errors import PanelSyntaxError
from scenet.ir import PageFormat
from scenet.pipeline import compile_book

DOCUMENT = (
    "cast: {{a: {{reference: alice}}}}\n"
    "page: {{size: [1682.75, 2603.5]{bleed}}}\n"
    "pages: [{{tiers: [{{panels: [one]}}]}}]\n"
    "panels: {{one: {{}}}}\n"
)


def _book(bleed: str = ""):
    return compile_book(DOCUMENT.format(bleed=bleed))


class TestTheKey:
    def test_it_defaults_to_none(self):
        assert PageFormat().bleed == 0.0

    def test_it_reaches_page_core(self):
        (page,) = _book(", bleed: 31.75").pages
        assert page.bleed == 31.75

    def test_a_page_without_one_writes_what_it_always_did(self):
        (page,) = _book().pages
        assert "bleed" not in page.to_json()
        assert PageCore.from_json(page.to_json()) == page

    def test_one_with_it_reads_back(self):
        (page,) = _book(", bleed: 30").pages
        assert '"bleed": 30.0' in page.to_json()
        assert PageCore.from_json(page.to_json()) == page

    def test_it_is_not_negative(self):
        with pytest.raises(PanelSyntaxError):
            _book(", bleed: -1")

    def test_it_moves_nothing_on_the_page(self):
        plain, bled = _book().pages[0], _book(", bleed: 31.75").pages[0]
        assert plain.frames == bled.frames
        assert plain.width == bled.width

    def test_a_comic_script_takes_it_in_its_front_matter(self):
        book = compile_script(
            "---\npage: {size: [1280, 1820], bleed: 30}\n"
            "cast:\n  BOB: {reference: bob}\n---\n\nPAGE ONE\n\nPANEL 1\nA street.\n\nBOB\nHi.\n"
        )
        assert book.pages[0].bleed == 30.0


class TestThePdf:
    def _boxes(self, bleed: str):
        book = _book(bleed)
        cores = {name: result.core for name, result in book.panels.items()}
        page = PdfReader(io.BytesIO(render_pdf(book.pages, cores))).pages[0]
        return book.pages[0], page

    def test_the_trim_is_the_page_and_the_bleed_runs_past_it(self):
        core, page = self._boxes(", bleed: 31.75")
        k = POINTS_PER_UNIT
        b = 31.75
        assert [float(v) for v in page.trimbox] == pytest.approx(
            [b * k, b * k, (core.width + b) * k, (core.height + b) * k], abs=1e-3
        )
        assert [float(v) for v in page.bleedbox] == pytest.approx(
            [0, 0, (core.width + 2 * b) * k, (core.height + 2 * b) * k], abs=1e-3
        )
        assert [float(v) for v in page.mediabox] == [float(v) for v in page.bleedbox]

    def test_a_us_comic_page_is_its_trim_size(self):
        _core, page = self._boxes(", bleed: 31.75")
        trim = page.trimbox
        assert float(trim.width) == pytest.approx(6.625 * 72, abs=0.01)
        assert float(trim.height) == pytest.approx(10.25 * 72, abs=0.01)

    def test_with_no_bleed_the_three_boxes_are_one(self):
        _, page = self._boxes("")
        assert list(page.trimbox) == list(page.bleedbox) == list(page.mediabox)

    def test_the_drawing_is_shifted_into_the_trim(self):
        book = _book(", bleed: 30")
        cores = {name: result.core for name, result in book.panels.items()}
        data = render_pdf(book.pages, cores)
        k = POINTS_PER_UNIT
        assert f" 0 0 -{k:.6f} {30 * k:.4f} ".encode() in data.replace(b"\n", b" ")
