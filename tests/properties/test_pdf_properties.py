"""Properties of the print PDF (#80), over generated documents.

New properties over the existing strategies, as for the other emitters. Pictures are left
out: the strategies' pictures are headers with no pixels, which the SVG links and print
cannot embed.
"""

import io

from hypothesis import given
from pypdf import PdfReader

from scenet.core import PanelCore
from scenet.emit.marks import Role, marks
from scenet.emit.pdf import panel_content, render_pdf
from scenet.emit.svg import typeface_of
from scenet.pipeline import compile_book, compile_source
from tests.properties.test_panel_properties import EXPECTED_FAILURES
from tests.strategies import LIBRARY, Drawn, DrawnScene, panels, scenes


def _blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    depth = 0
    for line in lines:
        if line == "q":
            depth += 1
            if depth == 1:
                blocks.append([])
        if depth:
            blocks[-1].append(line)
        if line == "Q":
            depth -= 1
    return blocks


def _sound(core: PanelCore) -> None:
    drawn = marks(core, typeface_of(core))
    blocks = _blocks(panel_content(core))
    assert len(blocks) == len(drawn)
    for mark, block in zip(drawn, blocks, strict=True):
        assert all("nan" not in line and "inf" not in line for line in block)
        if mark.fill is not None and mark.fill.role is Role.INK:
            assert "0 0 0 1 k" in block


@given(panels(images=False))
def test_every_panel_prints_every_mark_once(drawn: Drawn):
    try:
        core = compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    except EXPECTED_FAILURES:
        return
    _sound(core)
    data = render_pdf((), {"panel": core})
    assert len(PdfReader(io.BytesIO(data)).pages) == 1
    assert render_pdf((), {"panel": core}, mono=True) == render_pdf((), {"panel": core.as_mono()})
    if core.as_mono() == core:
        assert data == render_pdf((), {"panel": core}, mono=True)


@given(scenes())
def test_every_page_prints(drawn: DrawnScene):
    try:
        book = compile_book(drawn.text, library=LIBRARY)
    except EXPECTED_FAILURES:
        return
    cores = {name: result.core for name, result in book.panels.items()}
    for core in cores.values():
        _sound(core)
    data = render_pdf(book.pages, cores)
    assert len(PdfReader(io.BytesIO(data)).pages) == (len(book.pages) or len(cores))
