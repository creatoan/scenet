"""The print PDF's plates, as a printer separates them (#80).

Ghostscript's `tiffsep` device renders a PDF the way a press sees it: one plate per ink, with
overprint honoured. These tests read its output and check what the black-plate rule means in
ink, not in PDF syntax: lettering lands on K alone; an overprinting line leaves the colour
under it; the paper and a reversed caption knock out; the night foreground is rich black.
`qpdf --check` reads every gallery PDF's structure.

Both tools are external and not Python packages, so the tests skip where they are absent --
except where `SCENET_REQUIRE_PRINT_TOOLS` is set, as in CI, where a missing tool fails. They
assert where ink is and is not, never exact values: Ghostscript's conversion of an RGB
picture to CMYK changes from one version to the next. The determinism contract is on the
PDF's bytes; these plates are checked, never kept as goldens.

At 254 dpi a page unit, a tenth of a millimetre, is exactly one pixel. With
`SCENET_PLATES_DIR` set, the plates are written there, for a person to look at.
"""

import os
import shutil
import struct
import subprocess
from functools import cache
from pathlib import Path

import pytest
import yaml
from shapely.geometry import Polygon

from scenet.core import PanelCore
from scenet.emit.pdf import render_pdf
from scenet.pipeline import Book, compile_book, compile_book_file

GALLERY = Path(__file__).parent.parent / "examples" / "gallery"
ENTRIES = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))["examples"]

GHOSTSCRIPT = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
QPDF = shutil.which("qpdf")
REQUIRED = bool(os.environ.get("SCENET_REQUIRE_PRINT_TOOLS"))

if REQUIRED:
    assert GHOSTSCRIPT, "SCENET_REQUIRE_PRINT_TOOLS is set and Ghostscript is not installed"
    assert QPDF, "SCENET_REQUIRE_PRINT_TOOLS is set and qpdf is not installed"

needs_ghostscript = pytest.mark.skipif(GHOSTSCRIPT is None, reason="Ghostscript is not installed")
needs_qpdf = pytest.mark.skipif(QPDF is None, reason="qpdf is not installed")

#: A pixel: cyan, magenta, yellow and black, 0 for no ink and 255 for full.
Pixel = tuple[int, int, int, int]


class Plates:
    """A rendered page: four inks per pixel, as Ghostscript separated them."""

    def __init__(self, width: int, height: int, data: bytes) -> None:
        self.width, self.height, self.data = width, height, data

    def at(self, x: float, y: float) -> Pixel:
        """The inks at a point in page units, which at 254 dpi are pixels."""
        offset = (int(y) * self.width + int(x)) * 4
        c, m, y_, k = self.data[offset : offset + 4]
        return c, m, y_, k

    def pixels(self) -> list[Pixel]:
        """Every pixel."""
        data = self.data
        return [(data[i], data[i + 1], data[i + 2], data[i + 3]) for i in range(0, len(data), 4)]

    def within(self, left: float, top: float, right: float, bottom: float) -> list[Pixel]:
        """The pixels of a rectangle, in page units."""
        return [
            self.at(x, y)
            for y in range(max(0, int(top)), min(self.height, int(bottom)))
            for x in range(max(0, int(left)), min(self.width, int(right)))
        ]


def _tiff(path: Path) -> Plates:
    """An uncompressed CMYK TIFF, as `tiffsep` writes its composite."""
    data = path.read_bytes()
    order = "<" if data[:2] == b"II" else ">"
    (offset,) = struct.unpack(order + "I", data[4:8])
    (count,) = struct.unpack(order + "H", data[offset : offset + 2])
    tags: dict[int, list[int]] = {}
    for index in range(count):
        entry = data[offset + 2 + index * 12 : offset + 14 + index * 12]
        tag, kind, number = struct.unpack(order + "HHI", entry[:8])
        size = {3: 2, 4: 4}.get(kind, 1)
        if number * size <= 4:
            raw = entry[8 : 8 + number * size]
        else:
            (pointer,) = struct.unpack(order + "I", entry[8:12])
            raw = data[pointer : pointer + number * size]
        code = {2: "H", 4: "I"}.get(size, "B")
        tags[tag] = list(struct.unpack(order + code * number, raw))
    assert tags[259] == [1], "the plates must be uncompressed"
    assert tags[262] == [5], "the composite must be separated CMYK"
    assert tags[277] == [4]
    width, height = tags[256][0], tags[257][0]
    strips = b"".join(
        data[start : start + size] for start, size in zip(tags[273], tags[279], strict=True)
    )
    return Plates(width, height, strips)


def _separate(pdf: bytes, folder: Path, *, overprint: bool = True) -> Plates:
    """Render one page to its plates."""
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "page.pdf"
    source.write_bytes(pdf)
    assert GHOSTSCRIPT is not None
    command = [
        GHOSTSCRIPT,
        "-q",
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-sDEVICE=tiffsep",
        "-sCompression=none",
        "-r254",
        "-dFirstPage=1",
        "-dLastPage=1",
        *([] if overprint else ["-dOverprint=/disable"]),
        f"-sOutputFile={folder / 'plate.tif'}",
        str(source),
    ]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603 -- a fixed command
    return _tiff(folder / "plate.tif")


def _folder(tmp_path: Path, name: str) -> Path:
    kept = os.environ.get("SCENET_PLATES_DIR")
    return Path(kept) / name if kept else tmp_path / name


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _alone(book: Book, panel: str) -> tuple[PanelCore, bytes]:
    """One panel printed on a page of its own size, so a pixel is one of its units."""
    core = book.panels[panel].core
    return core, render_pdf((), {panel: core}, fonts=book.fonts, images=book.images)


@needs_ghostscript
class TestThePlates:
    def test_a_balloon_over_a_picture_is_paper_lettered_in_black(self, tmp_path: Path):
        core, pdf = _alone(_book("38-tour.scene.yaml"), "worry")
        plates = _separate(pdf, _folder(tmp_path, "38-tour-worry"))
        assert core.balloons
        for balloon in core.balloons:
            # The middle half of its box is inside a balloon of any shape.
            box = balloon.box
            cx, cy = box.x + box.width / 2, box.y + box.height / 2
            inside = plates.within(
                cx - box.width / 4, cy - box.height / 4, cx + box.width / 4, cy + box.height / 4
            )
            assert inside
            assert all(c == m == y == 0 for c, m, y, _ in inside)
            assert {k for *_, k in inside} <= {0, 255}
            assert 255 in {k for *_, k in inside}

    def test_ink_overprints_the_colour_under_it(self, tmp_path: Path):
        _, pdf = _alone(_book("38-tour.scene.yaml"), "worry")
        printed = _separate(pdf, _folder(tmp_path, "38-tour-worry"))
        knocked = _separate(pdf, tmp_path / "knockout", overprint=False)
        differing = [
            (over, out)
            for over, out in zip(printed.pixels(), knocked.pixels(), strict=True)
            if over[:3] != out[:3]
        ]
        assert differing, "nothing overprints: the art under the ink was knocked out"
        assert all(over[3] == 255 for over, _ in differing)

    def test_a_reversed_caption_knocks_out_of_solid_black(self, tmp_path: Path):
        book = _book("22-caption-tones.panel.yaml")
        name = next(iter(book.panels))
        core, pdf = _alone(book, name)
        plates = _separate(pdf, _folder(tmp_path, "22-caption-tones"))
        reversed_ = [caption for caption in core.captions if caption.ink == "#ffffff"]
        assert reversed_
        for caption in reversed_:
            box = caption.box
            inside = plates.within(box.x + 3, box.y + 3, box.right - 3, box.bottom - 3)
            assert all(c == m == y == 0 for c, m, y, _ in inside)
            assert {0, 255} <= {k for *_, k in inside}

    def test_a_page_with_no_picture_prints_on_black_alone(self, tmp_path: Path):
        book = _book("24-page.scene.yaml")
        cores = {name: result.core for name, result in book.panels.items()}
        plates = _separate(
            render_pdf(book.pages, cores, fonts=book.fonts), _folder(tmp_path, "24-page")
        )
        assert all(c == m == y == 0 for c, m, y, _ in plates.pixels())

    def test_the_night_foreground_is_rich_black(self, tmp_path: Path):
        book = compile_book(
            "cast: {a: {reference: alice}}\npanels: {one: {setting: {place: alley, time: night}}}\n"
        )
        core, pdf = _alone(book, "one")
        assert core.backdrop is not None
        darkest = [mass for mass in core.backdrop.masses if mass.tone == "#020202"]
        assert darkest
        plates = _separate(pdf, _folder(tmp_path, "night-foreground"))
        for mass in darkest:
            shape = Polygon(mass.polygon).buffer(-6)
            if shape.is_empty:
                continue
            point = shape.representative_point()
            c, m, y, k = plates.at(point.x, point.y)
            assert 98 <= c <= 106
            assert m == y == 0
            assert k == 255


@needs_qpdf
@pytest.mark.parametrize("entry", ENTRIES, ids=[entry["file"] for entry in ENTRIES])
def test_every_gallery_pdf_is_sound(entry: dict[str, str], tmp_path: Path):
    book = _book(entry["file"])
    cores = {name: result.core for name, result in book.panels.items()}
    path = tmp_path / "document.pdf"
    path.write_bytes(render_pdf(book.pages, cores, fonts=book.fonts, images=book.images))
    assert QPDF is not None
    result = subprocess.run(  # noqa: S603 -- a fixed command
        [QPDF, "--check", str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
