"""Properties of pages, strips and comic scripts, checked against generated ones.

A page is where most recent layout bugs lived: panels read out of order, a strip that
repeated its ids, panel numbers that started again on each page of a script and quietly
replaced the panels before them. Each was an input nobody had written. These properties
write them by the hundred.
"""

from hypothesis import event, given

from scenet.core import PageCore, PanelCore
from scenet.emit.page import render_page, render_pages
from scenet.emit.strip import render_strip
from scenet.errors import BalloonPlacementError
from scenet.frontends.script_front import parse_script
from scenet.pipeline import Book, compile_book
from tests.invariants import assert_frames_are_placed, assert_svg_is_sound
from tests.strategies import LIBRARY, DrawnScene, DrawnScript, scenes, scripts


def _compile(drawn: DrawnScene) -> Book | None:
    """The compiled book, or `None` when a panel has no room for its lettering."""
    try:
        book = compile_book(drawn.text, library=LIBRARY)
    except BalloonPlacementError:
        event("failed: BalloonPlacementError")
        return None
    event(f"pages: {len(book.pages)}, panels: {len(book.panels)}")
    return book


def _cores(book: Book) -> dict[str, PanelCore]:
    return {name: result.core for name, result in book.panels.items()}


def _font_sizes(cores: dict[str, PanelCore]) -> list[float]:
    return [box.font_size for core in cores.values() for box in (*core.balloons, *core.captions)]


@given(scenes())
def test_frames_are_read_in_the_order_the_page_was_written(drawn: DrawnScene):
    """Tier by tier, left to right, down each column, insets before or after their
    parent as `read` says. The order is worked out from the document, not the solver."""
    book = _compile(drawn)
    if book is None:
        return
    assert tuple(tuple(frame.panel for frame in page.frames) for page in book.pages) == (
        drawn.order
    )


@given(scenes())
def test_frames_keep_inside_the_page_and_clear_of_each_other(drawn: DrawnScene):
    book = _compile(drawn)
    if book is None:
        return
    for page in book.pages:
        assert_frames_are_placed(page, margin=drawn.page_margin)


@given(scenes())
def test_each_panel_is_compiled_at_its_frame_size(drawn: DrawnScene):
    book = _compile(drawn)
    if book is None:
        return
    for page in book.pages:
        for frame in page.frames:
            core = book.panels[frame.panel].core
            assert (core.width, core.height) == (frame.width, frame.height), frame.panel


@given(scenes())
def test_page_core_survives_a_round_trip(drawn: DrawnScene):
    book = _compile(drawn)
    if book is None:
        return
    for page in book.pages:
        text = page.to_json()
        restored = PageCore.from_json(text)
        assert restored == page
        assert restored.to_json() == text


@given(scenes())
def test_pages_and_strips_render_sound_svg(drawn: DrawnScene):
    """Every way of drawing a book parses, keeps its ids unique -- across pages too --
    and resolves every reference, and compiling it twice gives the same bytes."""
    book = _compile(drawn)
    if book is None:
        return
    cores = _cores(book)
    sizes = _font_sizes(cores)
    for page in book.pages:
        for live_text in (False, True):
            svg = render_page(page, cores, live_text=live_text)
            assert_svg_is_sound(svg, size=(page.width, page.height), font_sizes=sizes)
    assert_svg_is_sound(render_pages(book.pages, cores), font_sizes=sizes)
    assert_svg_is_sound(render_pages(book.pages, cores, debug=True), font_sizes=sizes)
    assert_svg_is_sound(render_strip(list(cores.items())), font_sizes=sizes)

    again = compile_book(drawn.text, library=LIBRARY)
    assert [page.to_json() for page in again.pages] == [page.to_json() for page in book.pages]
    assert render_pages(again.pages, _cores(again)) == render_pages(book.pages, cores)


@given(scripts())
def test_a_comic_script_loses_nothing(drawn: DrawnScript):
    """As many panels as were written, each holding as many balloons and captions as it
    had lines -- whether panel numbers run on or start again on each page (#63)."""
    panels = parse_script(drawn.text)
    assert tuple(len(panel.script) for panel in panels.values()) == drawn.lines
