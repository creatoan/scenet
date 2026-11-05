"""The fog and cloud veil in the print PDF (#282).

The SVG's veil is noise only a filter draws; print draws the same noise as an image
(`scenet.emit.turbulence`): a rectangle in the veil's ink, seen through a luminosity soft mask
that holds the noise, where the SVG paints it -- above the masses behind the cast, below the
ones in front. It knocks out, as the SVG's veil fades whatever is under it.
"""

import io
import math
from functools import cache
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    ContentStream,
    DictionaryObject,
    NameObject,
    PdfObject,
    StreamObject,
)

from scenet.core import PanelCore
from scenet.emit.marks import Paint, Role, Veil, marks
from scenet.emit.pdf import _cmyk, ink, panel_content, print_notes, render_pdf
from scenet.emit.svg import typeface_of
from scenet.emit.turbulence import VEIL_STEP, veil_alpha
from scenet.pipeline import Book, compile_book, compile_book_file

GALLERY = Path(__file__).parent.parent / "examples" / "gallery"


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _morning() -> tuple[Book, PanelCore]:
    book = _book("21-atmosphere.scene.yaml")
    return book, book.panels["morning"].core


def _dictionary(value: PdfObject | None) -> DictionaryObject:
    """A dictionary, followed through its reference."""
    assert value is not None
    found = value.get_object()
    assert isinstance(found, DictionaryObject)
    return found


def _veil_state(data: bytes) -> DictionaryObject:
    page = PdfReader(io.BytesIO(data)).pages[0]
    resources = page["/Resources"]
    assert isinstance(resources, DictionaryObject)
    states = resources["/ExtGState"]
    assert isinstance(states, DictionaryObject)
    (veiled,) = [state.get_object() for state in states.values() if "/SMask" in state.get_object()]
    assert isinstance(veiled, DictionaryObject)
    return veiled


def test_the_veil_is_a_mark_painted_in_its_greys_ink():
    book, core = _morning()
    (veil,) = [mark for mark in marks(core, typeface_of(core, fonts=book.fonts)) if mark.is_veil]
    assert isinstance(veil.shape, Veil)
    air = core.backdrop.atmosphere if core.backdrop is not None else None
    assert air is not None
    assert air.veil is not None
    paint = Paint(air.veil.colour or air.veil.tone, Role.TONE, air.veil.tone)
    assert veil.fill == paint
    lines = panel_content(core, book.fonts)
    assert f"{_cmyk(ink(paint))} k" in lines


def test_it_is_seen_through_a_luminosity_soft_mask_and_knocks_out():
    book, core = _morning()
    state = _veil_state(render_pdf((), {"morning": core}, fonts=book.fonts))
    knocks_out = state["/op"]
    assert isinstance(knocks_out, BooleanObject)
    assert not knocks_out.value
    mask = _dictionary(state["/SMask"])
    assert mask["/S"] == NameObject("/Luminosity")
    group = _dictionary(mask["/G"])
    assert _dictionary(group["/Group"])["/CS"] == NameObject("/DeviceGray")
    box = group["/BBox"]
    assert isinstance(box, ArrayObject)
    assert [float(value) for value in box] == [0.0, 0.0, core.width, core.height]


def test_its_image_is_the_veils_alpha_one_sample_per_two_units():
    book, core = _morning()
    state = _veil_state(render_pdf((), {"morning": core}, fonts=book.fonts))
    group = _dictionary(_dictionary(state["/SMask"])["/G"])
    assert isinstance(group, StreamObject)
    images = _dictionary(_dictionary(group["/Resources"])["/XObject"])
    (image,) = [value.get_object() for value in images.values()]
    assert isinstance(image, StreamObject)
    assert image["/ColorSpace"] == NameObject("/DeviceGray")
    assert image["/BitsPerComponent"] == 8
    across, down = int(str(image["/Width"])), int(str(image["/Height"]))
    assert across == math.ceil(core.width / VEIL_STEP)
    assert down == math.ceil(core.height / VEIL_STEP)
    air = core.backdrop.atmosphere if core.backdrop is not None else None
    assert air is not None
    assert air.veil is not None
    assert image.get_data() == veil_alpha(air.veil, core.width, core.height).data
    operations = ContentStream(group, None).operations
    (matrix,) = [operands for operands, operator in operations if operator == b"cm"]
    assert [float(value) for value in matrix] == [
        across * VEIL_STEP,
        0.0,
        0.0,
        -down * VEIL_STEP,
        0.0,
        down * VEIL_STEP,
    ]


def test_one_veil_drawn_twice_is_carried_once():
    book = compile_book(
        "cast: {a: {reference: alice}}\n"
        "setting: {place: street, weather: fog}\n"
        "panels: {one: {}, two: {}}\n"
    )
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores)
    # Each page lists the state that masks it; the noise and its group are written once.
    assert data.count(b"/Subtype /Form") == 1
    assert data.count(b"/ColorSpace /DeviceGray /BitsPerComponent 8") == 1


def test_a_panel_without_a_veil_has_no_mask():
    book = _book("01-two-characters.panel.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    assert b"/SMask" not in render_pdf(book.pages, cores, fonts=book.fonts)


def test_print_no_longer_says_it_leaves_the_veil_out():
    assert not [
        note for note in print_notes({"morning": _morning()[1]}) if "fog" in note or "cloud" in note
    ]


def test_every_page_of_a_rainy_page_carries_its_veils():
    book = _book("24-page.scene.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores, fonts=book.fonts)
    reader = PdfReader(io.BytesIO(data))
    for page in reader.pages:
        resources = page["/Resources"]
        assert isinstance(resources, DictionaryObject)
        states = resources["/ExtGState"]
        assert isinstance(states, DictionaryObject)
        assert any("/SMask" in state.get_object() for state in states.values())
    assert isinstance(reader.pages[0]["/MediaBox"], ArrayObject)
