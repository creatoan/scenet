"""The print PDF (#80): the SVG's drawing, in inks a printer separates.

Read back with pypdf, a dev-only oracle as HarfBuzz is for kerning: what the file says is
checked against what was meant -- lettering on the black plate, overprinting; the paper
knocking out; greys as black tints -- and the drawing against the marks it was made from.
"""

import io
import os
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import fonts.ttf
import pytest
import yaml
from pypdf import PdfReader
from pypdf.generic import BooleanObject, ContentStream, DictionaryObject

from scenet.core import Box, CoreImage, PanelCore
from scenet.emit.cmyk import CMYK
from scenet.emit.marks import Mark, Paint, Picture, Rect, Role, marks
from scenet.emit.pdf import (
    POINTS_PER_UNIT,
    RICH_BLACK,
    _rect,
    ink,
    lightness,
    overprints,
    panel_content,
    print_notes,
    render_pdf,
    resolution,
)
from scenet.emit.svg import typeface_of
from scenet.ir import Fit
from scenet.pipeline import Book, compile_book, compile_book_file

ROOT = Path(__file__).parent.parent
SEMIBOLD = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
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
    if isinstance(mark.shape, Picture):
        return ()
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

    def test_a_tinted_paint_prints_its_cmyk_twin(self):
        assert ink(Paint("#fef0a1", Role.TONE, "#eeeeee")) == tuple(
            value / 100 for value in CMYK["#fef0a1"]
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

    def test_right_to_left_is_said_of_panels_printed_one_a_page(self):
        """Without pages a PDF page is a panel, read in the panels' own direction."""
        panels = "cast: {a: {reference: alice}}\npanels: {one: {}, two: {}}\n"
        assert b"/Direction /R2L" in _pdf(compile_book(f"direction: rtl\n{panels}"))
        assert b"/Direction" not in _pdf(compile_book(panels))


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
        drawn = marks(core, typeface_of(core, fonts=book.fonts))
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
        drawn = marks(core, family)
        blocks = _blocks(panel_content(core, book.fonts))
        assert [_painting(block) for block in blocks] == [_expected(mark) for mark in drawn]


@pytest.mark.parametrize("name", IDS)
def test_every_example_prints_the_same_twice_and_in_mono_its_greys(name: str):
    book = _book(name)
    data = _pdf(book)
    assert data == _pdf(_book(name))
    mono = {key: core.as_mono() for key, core in _cores(book).items()}
    greys = render_pdf(book.pages, mono, fonts=book.fonts, images=book.images)
    assert greys == render_pdf(
        book.pages, _cores(book), fonts=book.fonts, images=book.images, mono=True
    )
    tinted = any(core.as_mono() != core for core in _cores(book).values())
    assert (data != greys) == tinted
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
    def test_the_veil_is_printed_and_so_not_said(self):
        notes = print_notes(_cores(_book("21-atmosphere.scene.yaml")))
        assert not any("fog" in note for note in notes)

    def test_a_tinted_panel_prints_in_colour_and_so_is_not_said(self):
        assert print_notes(_cores(_book("40-tinted-hours.scene.yaml"))) == []

    def test_a_plain_panel_has_nothing_to_say(self):
        assert print_notes(_cores(_book("01-two-characters.panel.yaml"))) == []


class TestWhatMutationTestingFound:
    """Behaviour the mutation run (#80) showed nothing checked."""

    def test_resolution_is_pixels_per_inch_at_a_tenth_of_a_millimetre(self):
        image = CoreImage(
            href="art/p.png",
            media_type="image/png",
            sha256="00",
            pixels=(720, 480),
            fit=Fit.COVER,
            preserve_aspect_ratio="xMidYMid slice",
            box=Box(x=0.0, y=0.0, width=1000.0, height=500.0),
        )
        # 720 px over 100 mm is 182.88 dpi; 480 px over 50 mm is 243.84: the lower, floored.
        assert resolution(image) == 182
        tall = image.model_copy(update={"box": Box(x=0.0, y=0.0, width=500.0, height=1000.0)})
        assert resolution(tall) == 121

    def test_a_picture_at_exactly_300_dpi_is_not_noted(self):
        book = compile_book_file(GALLERY / "52-a-jpeg.panel.yaml")
        core = next(iter(_cores(book).values()))
        assert core.backdrop is not None
        assert core.backdrop.image is not None
        image = core.backdrop.image
        width = image.pixels[0] * 254 / 300
        height = image.pixels[1] * 254 / 300
        exact = image.model_copy(update={"box": Box(x=0.0, y=0.0, width=width, height=height)})
        assert resolution(exact) == 300
        backdrop = core.backdrop.model_copy(update={"image": exact})
        assert not [
            note
            for note in print_notes({"p": core.model_copy(update={"backdrop": backdrop})})
            if "dpi" in note
        ]

    def test_a_page_lettered_in_a_declared_font_prints_in_it(self, tmp_path: Path):
        folder = tmp_path / "comic"
        (folder / "fonts").mkdir(parents=True)
        shutil.copy(SEMIBOLD, folder / "fonts" / "Lettering-Regular.ttf")
        source = folder / "page.scene.yaml"
        source.write_text(
            "lettering: {font: fonts/Lettering-Regular.ttf}\n"
            "cast: {a: {reference: alice}}\n"
            "pages: [{tiers: [{panels: [one]}]}]\n"
            "panels: {one: {script: [{say: {by: a, text: Printed.}}]}}\n",
            encoding="utf-8",
        )
        book = compile_book_file(source)
        assert book.fonts
        data = render_pdf(book.pages, _cores(book), fonts=book.fonts)
        assert data.startswith(b"%PDF")
        with pytest.raises(ValueError, match="not given to the renderer"):
            render_pdf(book.pages, _cores(book))

    def test_a_corner_rounder_than_its_box_is_clamped_to_half_of_it(self):
        assert _rect(Rect(0.0, 0.0, 10.0, 40.0, radius=30.0)).startswith("5 0 m 5 0 l")
        assert _rect(Rect(0.0, 0.0, 40.0, 10.0, radius=30.0)).startswith("5 0 m 35 0 l")

    def test_a_slightly_rounded_corner_is_still_a_curve(self):
        assert " c " in _rect(Rect(0.0, 0.0, 10.0, 10.0, radius=0.5))
        assert _rect(Rect(0.0, 0.0, 10.0, 10.0)) == "0 0 10 10 re"
