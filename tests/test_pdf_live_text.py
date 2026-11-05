"""Live text in the print PDF (#284): lettering set in its faces, where its outlines would be.

With `live_text`, a balloon's or a caption's lettering is text in an embedded subset of its
face (`scenet.emit.pdf_fonts`), so it can be selected, searched and copied. Nothing moves for
it: each glyph's origin, rebuilt here from the content stream as a reader would -- the text
matrix, the `TJ` adjustments, the widths the font's `W` array gives -- is the origin the
outlines are drawn at. Sound effects stay outlines, as in the SVG.
"""

import hashlib
import io
import os
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, TextStringObject

from scenet.core import PanelCore
from scenet.emit.marks import Glyph, Text, marks
from scenet.emit.pdf import panel_content, print_notes, render_pdf
from scenet.emit.svg import typeface_of
from scenet.pipeline import Book, compile_book_file
from tests.pdf_files import face

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
ENTRIES = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))["examples"]
IDS = [entry["file"] for entry in ENTRIES]


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _alone(book: Book, core: PanelCore, name: str) -> bytes:
    return render_pdf((), {name: core}, fonts=book.fonts, images=book.images, live_text=True)


def _widths(font: DictionaryObject) -> dict[int, float]:
    """A Type0 font's widths by code, from its CIDFont's `W` array."""
    descendant = font["/DescendantFonts"][0].get_object()
    entries = descendant["/W"]
    widths: dict[int, float] = {}
    index = 0
    while index < len(entries):
        start, run = int(entries[index]), entries[index + 1]
        assert isinstance(run, ArrayObject)
        for offset, width in enumerate(run):
            widths[start + offset] = float(width)
        index += 2
    return widths


def _origins(data: bytes) -> list[float]:
    """Where each glyph set as text lands along its line, as a reader works it out."""
    reader = PdfReader(io.BytesIO(data))
    origins: list[float] = []
    for page in reader.pages:
        resources = page["/Resources"]
        assert isinstance(resources, DictionaryObject)
        fonts = resources.get("/Font", DictionaryObject())
        widths = {name: _widths(font.get_object()) for name, font in fonts.items()}
        current: dict[int, float] = {}
        x = size = 0.0
        for operands, operator in ContentStream(page.get_contents(), reader).operations:
            if operator == b"Tf":
                current = widths[operands[0]]
            elif operator == b"Tm":
                size, x = float(operands[0]), float(operands[4])
            elif operator == b"TJ":
                for part in operands[0]:
                    if isinstance(part, (int, float)):
                        x -= float(part) / 1000 * size
                        continue
                    raw = part.original_bytes if isinstance(part, TextStringObject) else bytes(part)
                    for at in range(0, len(raw), 2):
                        origins.append(x)
                        x += current[int.from_bytes(raw[at : at + 2], "big")] / 1000 * size
    return origins


def _expected(book: Book, core: PanelCore) -> list[float]:
    """The origin of every glyph lettered as text, in the order the marks paint them."""
    origins: list[float] = []
    for mark in marks(core, typeface_of(core, fonts=book.fonts), live_text=True):
        if isinstance(mark.shape, Text):
            for placed in mark.shape.runs:
                for character, origin in zip(placed.run.text, placed.origins, strict=True):
                    if placed.metrics.glyph_id(character) is not None:
                        origins.append(origin)
    return origins


@pytest.mark.parametrize("name", IDS)
def test_every_glyph_lands_where_its_outline_would(name: str):
    book = _book(name)
    for panel, result in book.panels.items():
        expected = _expected(book, result.core)
        found = _origins(_alone(book, result.core, panel))
        assert found == pytest.approx(expected, abs=1e-6)


def test_balloons_and_captions_are_text_and_sound_effects_outlines():
    book = _book("38-tour.scene.yaml")
    core = book.panels["street"].core
    drawn = marks(core, typeface_of(core, fonts=book.fonts), live_text=True)
    lettered = [mark for mark in drawn if mark.owner.startswith(("balloon-", "caption-"))]
    assert any(isinstance(mark.shape, Text) for mark in lettered)
    assert not any(isinstance(mark.shape, Glyph) for mark in lettered)
    assert any(isinstance(mark.shape, Glyph) for mark in drawn if mark.owner.startswith("sfx-"))


def test_one_text_block_a_line_still_on_the_black_plate():
    book = _book("01-two-characters.panel.yaml")
    core = next(iter(book.panels.values())).core
    lines = panel_content(core, book.fonts, live_text=True)
    texts = [
        mark
        for mark in marks(core, typeface_of(core, fonts=book.fonts), live_text=True)
        if isinstance(mark.shape, Text)
    ]
    assert texts
    assert lines.count("BT") == lines.count("ET") == len(texts)
    for index, line in enumerate(lines):
        if line == "BT":
            assert lines[index - 1] == "0 0 0 1 k"
            assert lines[index - 2] == "/GS10100 gs"


def test_the_words_can_be_read_back():
    book = _book("01-two-characters.panel.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    words = [
        word
        for core in cores.values()
        for balloon in core.balloons
        for line in balloon.lines
        for word in line.split()
    ]
    assert words
    for word in words:
        assert word in text


def test_outlines_are_still_the_default():
    book = _book("01-two-characters.panel.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    assert b"/FontFile" not in render_pdf(book.pages, cores, fonts=book.fonts)
    assert b"/FontFile2" in render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)


def test_a_face_is_carried_once_however_many_panels_letter_in_it():
    book = _book("24-page.scene.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)
    assert data.count(b"/Subtype /Type0") == len(
        {
            placed.metrics.sha256
            for core in cores.values()
            for mark in marks(core, typeface_of(core, fonts=book.fonts), live_text=True)
            if isinstance(mark.shape, Text)
            for placed in mark.shape.runs
        }
    )


def test_the_same_bytes_twice_and_whatever_the_hash_seed():
    script = (
        "import hashlib\n"
        "from pathlib import Path\n"
        "from scenet.pipeline import compile_book_file\n"
        "from scenet.emit.pdf import render_pdf\n"
        f"book = compile_book_file(Path({str(GALLERY / '24-page.scene.yaml')!r}))\n"
        "cores = {n: r.core for n, r in book.panels.items()}\n"
        "data = render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)\n"
        "print(hashlib.sha256(data).hexdigest())\n"
    )
    digests = {
        subprocess.run(  # noqa: S603 -- our own interpreter, running our own script
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("0", "12345")
    }
    book = _book("24-page.scene.yaml")
    cores = {name: result.core for name, result in book.panels.items()}
    data = render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)
    assert digests == {hashlib.sha256(data).hexdigest() + "\n"}


class TestAFacePrintMayNotCarry:
    @pytest.fixture
    def book(self, tmp_path: Path) -> Book:
        folder = tmp_path / "comic"
        (folder / "fonts").mkdir(parents=True)
        shutil.copy(face(tmp_path / "restricted.ttf", fs_type=0x0002), folder / "fonts" / "R.ttf")
        source = folder / "panel.panel.yaml"
        source.write_text(
            "lettering: {font: fonts/R.ttf}\n"
            "cast: {a: {reference: alice}}\n"
            "script: [{say: {by: a, text: AB BA}}]\n",
            encoding="utf-8",
        )
        return compile_book_file(source)

    def test_its_lettering_stays_in_outlines(self, book: Book):
        cores = {name: result.core for name, result in book.panels.items()}
        data = render_pdf(book.pages, cores, fonts=book.fonts, live_text=True)
        assert b"/FontFile" not in data
        assert b" Tf" not in data
        core = next(iter(cores.values()))
        lines = panel_content(core, book.fonts, live_text=True)
        assert "f" in lines

    def test_print_says_so(self, book: Book):
        cores = {name: result.core for name, result in book.panels.items()}
        notes = print_notes(cores, live_text=True, fonts=book.fonts)
        assert any("not embedded" in note and "fsType 0x0002" in note for note in notes)
        assert not print_notes(cores, fonts=book.fonts)
