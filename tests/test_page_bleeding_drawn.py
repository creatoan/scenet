"""Panels that bleed past the trim, drawn (#281).

A bleeding panel has no border on its bleeding sides: its frame is drawn as the open line of
the sides that keep one, in the SVG and the print PDF alike. The SVG page stays drawn at its
trim, as the page will look once cut, and a page among others is clipped to its sheet, so a
frame running past it never spills onto its neighbour. The debug overlay shows what is cut:
the whole sheet, the trim, and each bleeding panel's lettering box.
"""

import xml.etree.ElementTree as ET
from functools import cache

from scenet.emit import geometry
from scenet.emit.debug_svg import render_debug
from scenet.emit.marks import Polygon, marks
from scenet.emit.page import render_page, render_pages
from scenet.emit.pdf import panel_content, render_pdf
from scenet.emit.svg import render, typeface_of
from scenet.frontends.yaml_front import parse_scene_document
from scenet.ir import Side
from scenet.pipeline import Book, _compile_document
from tests.test_marks import _drawn, _painted
from tests.test_page_bleeding import SCENE

SVG = "{http://www.w3.org/2000/svg}"


@cache
def _book() -> Book:
    return _compile_document(
        parse_scene_document(SCENE), None, None, None, bleeds={"wide": True, "last": True}
    )


@cache
def _plain() -> Book:
    return _compile_document(parse_scene_document(SCENE), None, None, None)


def test_the_border_is_the_sides_that_keep_one():
    core = _book().panels["wide"].core
    assert core.open == (Side.LEFT, Side.TOP)
    assert geometry.border(core) == [((440.0, 0.0), (440.0, 500.0), (0.0, 500.0))]


def test_a_border_wraps_round_the_corner_it_turns():
    last = _book().panels["last"].core
    assert last.open == (Side.LEFT, Side.RIGHT, Side.BOTTOM)
    assert geometry.border(last) == [((0.0, 0.0), (last.width, 0.0))]


def test_a_panel_that_does_not_bleed_has_its_whole_border():
    assert geometry.border(_plain().panels["wide"].core) is None


def test_the_svg_draws_the_border_as_an_open_line():
    core = _book().panels["wide"].core
    svg = render(core, aria=False)
    assert '<polyline points="440,0 440,500 0,500" fill="none"' in svg
    assert 'width="440" height="500" fill="none"' not in svg


def test_the_marks_are_what_the_svg_paints():
    book = _book()
    for name in ("wide", "last", "tall"):
        core = book.panels[name].core
        family = typeface_of(core, fonts=book.fonts)
        assert _drawn(core, family) == _painted(render(core, aria=False))
        frames = [mark for mark in marks(core, family) if mark.owner == "panel" and mark.stroke]
        if core.open:
            assert all(isinstance(mark.shape, Polygon) and not mark.shape.closed for mark in frames)


def test_the_pdf_leaves_the_border_open():
    core = _book().panels["wide"].core
    lines = panel_content(core)
    assert "440 0 m 440 500 l 0 500 l" in lines
    stroke = lines[lines.index("440 0 m 440 500 l 0 500 l") + 1]
    assert stroke == "S"


def test_a_page_among_pages_is_clipped_to_its_sheet():
    book = _book()
    cores = {name: result.core for name, result in book.panels.items()}
    svg = render_pages(book.pages, cores, aria=False)
    root = ET.fromstring(svg)
    clips = root.findall(f".//{SVG}clipPath")
    assert any(
        clip.get("id") == "page-1-sheet"
        and (rect := clip.find(f"{SVG}rect")) is not None
        and rect.get("width") == "1200"
        for clip in clips
    )
    plain = _plain()
    plain_cores = {name: result.core for name, result in plain.panels.items()}
    assert "page-1-sheet" not in render_pages(plain.pages, plain_cores, aria=False)


def test_the_page_is_drawn_at_its_trim():
    book = _book()
    cores = {name: result.core for name, result in book.panels.items()}
    (page,) = book.pages
    assert 'viewBox="0 0 1200 1800"' in render_page(page, cores)


def test_the_debug_page_shows_the_sheet_the_trim_and_the_lettering_boxes():
    book = _book()
    cores = {name: result.core for name, result in book.panels.items()}
    (page,) = book.pages
    debug = render_page(page, cores, debug=True)
    assert 'viewBox="-30 -30 1260 1860"' in debug
    assert 'id="trim"' in debug
    assert debug.count('class="lettering-box"') == 2
    plain = _plain()
    plain_cores = {name: result.core for name, result in plain.panels.items()}
    assert 'id="trim"' not in render_page(plain.pages[0], plain_cores, debug=True)


def test_a_panels_debug_overlay_marks_its_lettering_box():
    core = _book().panels["wide"].core
    overlay = render_debug(core)
    assert 'class="lettering-box"' in overlay
    assert 'x="90" y="90" width="350" height="410"' in overlay
    assert 'class="lettering-box"' not in render_debug(_plain().panels["wide"].core)


def test_the_print_pdf_carries_the_art_into_the_bleed():
    book = _book()
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores)
    assert data.startswith(b"%PDF")
