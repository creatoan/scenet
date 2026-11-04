"""The print PDF (#80): the SVG's drawing, in inks a printer separates.

Read back with pypdf, a dev-only oracle as HarfBuzz is for kerning: what the file says is
checked against what was meant -- lettering on the black plate, overprinting; the paper
knocking out; greys as black tints -- and the drawing against the marks it was made from.
"""

import io
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader
from pypdf.generic import BooleanObject, ContentStream, DictionaryObject

from scenet.core import PanelCore
from scenet.emit.marks import Mark, Paint, Role, marks
from scenet.emit.pdf import (
    POINTS_PER_UNIT,
    RICH_BLACK,
    ink,
    lightness,
    overprints,
    panel_content,
    print_notes,
    render_pdf,
)
from scenet.emit.svg import typeface_of
from scenet.pipeline import Book, compile_book, compile_book_file

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
ENTRIES = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))["examples"]
IDS = [entry["file"] for entry in ENTRIES]

#: What each mark's painting ends with, by whether it has a fill, a stroke, both, or both
#: with the stroke under the fill.
PAINTING = {"f": ("f",), "S": ("S",), "B": ("B",), "Sf": ("S", "f")}


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _cores(book: Book) -> dict[str, PanelCore]:
    return {name: result.core for name, result in book.panels.items()}


def _pdf(book: Book) -> bytes:
    return render_pdf(book.pages, _cores(book), fonts=book.fonts, images=book.images)


def _blocks(lines: list[str]) -> list[list[str]]:
    """Each top-level `q ... Q` block, as its lines."""
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


def _expected(mark: Mark) -> tuple[str, ...]:
    if mark.fill is not None and mark.stroke is not None:
        return PAINTING["Sf" if mark.stroke_first else "B"]
    return PAINTING["f" if mark.fill is not None else "S"]


def _painting(block: list[str]) -> tuple[str, ...]:
    return tuple(line for line in block if line in {"f", "S", "B"})


class TestInks:
    def test_ink_is_all_black_and_overprints(self):
        paint = Paint("#111111", Role.INK, "#111111")
        assert ink(paint) == (0.0, 0.0, 0.0, 1.0)
        assert overprints(paint)

    def test_the_paper_is_no_ink_and_knocks_out(self):
        paint = Paint("#ffffff", Role.PAPER, "#ffffff")
        assert ink(paint) == (0.0, 0.0, 0.0, 0.0)
        assert not overprints(paint)

    def test_a_grey_is_a_black_tint_of_its_darkness(self):
        paint = Paint("#707070", Role.TONE, "#707070")
        assert ink(paint) == pytest.approx((0.0, 0.0, 0.0, 1.0 - lightness("#707070")))
        assert not overprints(paint)

    def test_a_tinted_paint_prints_its_grey(self):
        assert ink(Paint("#fef0a1", Role.TONE, "#eeeeee")) == ink(
            Paint("#eeeeee", Role.TONE, "#eeeeee")
        )

    def test_a_near_black_mass_prints_rich_black(self):
        assert ink(Paint("#020202", Role.MASS, "#020202")) == RICH_BLACK
        assert ink(Paint("#060606", Role.MASS, "#060606"))[0] == 0.0

    def test_a_dark_caption_box_is_solid_black_and_knocks_out(self):
        paint = Paint("#090909", Role.SOLID, "#090909")
        assert ink(paint) == (0.0, 0.0, 0.0, 1.0)
        assert not overprints(paint)

    def test_lightness_is_oklab(self):
        assert lightness("#ffffff") == pytest.approx(1.0, abs=1e-6)
        assert lightness("#000000") == 0.0
        assert lightness("#e8e6e1") == pytest.approx(0.9254, abs=1e-3)


class TestFile:
    def test_it_is_a_pdf_a_reader_opens(self):
        book = _book("01-two-characters.panel.yaml")
        reader = PdfReader(io.BytesIO(_pdf(book)))
        assert len(reader.pages) == 1

    def test_a_page_unit_prints_as_a_tenth_of_a_millimetre(self):
        book = _book("24-page.scene.yaml")
        reader = PdfReader(io.BytesIO(_pdf(book)))
        page = book.pages[0]
        box = reader.pages[0].trimbox
        assert float(box.width) == pytest.approx(page.width * POINTS_PER_UNIT, abs=1e-3)
        assert float(box.height) == pytest.approx(page.height * POINTS_PER_UNIT, abs=1e-3)
        assert pytest.approx(72 / 25.4) == POINTS_PER_UNIT * 10

    def test_one_pdf_page_per_page_or_per_panel(self):
        paged = _book("24-page.scene.yaml")
        assert len(PdfReader(io.BytesIO(_pdf(paged))).pages) == len(paged.pages)
        loose = compile_book("cast: {a: {reference: alice}}\npanels: {one: {}, two: {}}\n")
        assert len(PdfReader(io.BytesIO(_pdf(loose))).pages) == 2

    def test_it_carries_no_date_and_no_version(self):
        data = _pdf(_book("01-two-characters.panel.yaml"))
        assert b"CreationDate" not in data
        assert b"ModDate" not in data
        assert b"/Producer (Scenet)" in data

    def test_right_to_left_is_said(self):
        assert b"/Direction /R2L" in _pdf(_book("36-right-to-left.scene.yaml"))
        assert b"/Direction" not in _pdf(_book("24-page.scene.yaml"))


class TestTheBlackPlate:
    def _states(self, data: bytes) -> dict[str, dict[str, object]]:
        reader = PdfReader(io.BytesIO(data))
        states: dict[str, dict[str, object]] = {}
        for page in reader.pages:
            resources = page["/Resources"]
            assert isinstance(resources, DictionaryObject)
            graphics = resources["/ExtGState"]
            assert isinstance(graphics, DictionaryObject)
            for name, state in graphics.items():
                assert isinstance(state, DictionaryObject)
                states[name] = {
                    key: value.value if isinstance(value, BooleanObject) else value
                    for key, value in state.items()
                }
        return states

    def test_lettering_overprints_in_black_alone(self):
        book = _book("01-two-characters.panel.yaml")
        core = next(iter(_cores(book).values()))
        drawn = [
            mark for mark in marks(core, typeface_of(core, fonts=book.fonts)) if not mark.is_veil
        ]
        blocks = _blocks(panel_content(core, book.fonts))
        assert len(blocks) == len(drawn)
        states = self._states(_pdf(book))
        for mark, block in zip(drawn, blocks, strict=True):
            if mark.owner.startswith("balloon-") and mark.stroke is None:
                assert "0 0 0 1 k" in block
                name = next(line.split()[0] for line in block if line.endswith(" gs"))
                assert states[name]["/op"] is True
                assert states[name]["/OPM"] == 1

    def test_a_balloon_knocks_out_its_fill_and_overprints_its_border(self):
        book = _book("01-two-characters.panel.yaml")
        core = next(iter(_cores(book).values()))
        lines = panel_content(core, book.fonts)
        states = self._states(_pdf(book))
        filled_and_stroked = [line.split()[0] for line in lines if line.endswith(" gs")]
        assert "/GS01100" in filled_and_stroked
        assert states["/GS01100"]["/op"] is False
        assert states["/GS01100"]["/OP"] is True


@pytest.mark.parametrize("name", IDS)
def test_every_mark_is_one_block_painted_as_it_should_be(name: str):
    book = _book(name)
    for core in _cores(book).values():
        family = typeface_of(core, fonts=book.fonts)
        drawn = [mark for mark in marks(core, family) if not mark.is_veil]
        blocks = _blocks(panel_content(core, book.fonts))
        assert [_painting(block) for block in blocks] == [_expected(mark) for mark in drawn]


@pytest.mark.parametrize("name", IDS)
def test_every_example_prints_the_same_twice_and_in_its_greys(name: str):
    book = _book(name)
    data = _pdf(book)
    assert data == _pdf(_book(name))
    mono = {key: core.as_mono() for key, core in _cores(book).items()}
    assert data == render_pdf(book.pages, mono, fonts=book.fonts, images=book.images)
    reader = PdfReader(io.BytesIO(data))
    for page in reader.pages:
        assert ContentStream(page.get_contents(), reader).operations


def test_the_same_bytes_whatever_the_hash_seed():
    script = (
        "import hashlib\n"
        "from pathlib import Path\n"
        "from scenet.pipeline import compile_book_file\n"
        "from scenet.emit.pdf import render_pdf\n"
        f"book = compile_book_file(Path({str(GALLERY / '24-page.scene.yaml')!r}))\n"
        "cores = {n: r.core for n, r in book.panels.items()}\n"
        "print(hashlib.sha256(render_pdf(book.pages, cores, fonts=book.fonts)).hexdigest())\n"
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
    assert len(digests) == 1


class TestNotes:
    def test_the_veil_is_said_to_be_left_out(self):
        notes = print_notes(_cores(_book("21-atmosphere.scene.yaml")))
        assert any("fog and cloud" in note for note in notes)

    def test_a_tinted_panel_is_said_to_print_in_greys(self):
        notes = print_notes(_cores(_book("40-tinted-hours.scene.yaml")))
        assert any("greys" in note for note in notes)

    def test_a_plain_panel_has_nothing_to_say(self):
        assert print_notes(_cores(_book("01-two-characters.panel.yaml"))) == []
