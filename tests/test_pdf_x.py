"""Toward PDF/X-4, with no claim (#283).

No free tool validates PDF/X-4, so the print PDF claims nothing: it carries no
`GTS_PDFXVersion`, no XMP and no dates, and does not embed the 3.5 MB profile of its
printing condition. What it does carry is true of the file whatever a preflight would say:
it is not trapped; an output intent names the condition its CMYK was made for, by the ICC
registry's identifier; RGB pictures say they are sRGB, in the ICC's own sRGB profile; and
every page blends its transparency in CMYK.
"""

import hashlib
import io
import re
import zlib
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject

from scenet.emit.cmyk import CONDITION
from scenet.emit.pdf import SRGB_PROFILE, render_pdf
from scenet.pipeline import Book, compile_book_file
from tests.images import PNG_SIGNATURE, chunk
from tests.test_pdf_images import _jpeg

GALLERY = Path(__file__).parent.parent / "examples" / "gallery"
PROFILE = Path(__file__).parent.parent / "src" / "scenet" / "profiles" / "sRGB2014.icc"

#: The ICC's `sRGB2014.icc`, as color.org publishes it.
SRGB_SHA256 = "384b832de3412066743b52a75ee906b6fb9fb8d9e09e936fc2c43223815c6e0a"


def _pdf(book: Book) -> bytes:
    cores = {name: result.core for name, result in book.panels.items()}
    return render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)


def _gallery(name: str) -> bytes:
    return _pdf(compile_book_file(GALLERY / name))


def _with_picture(tmp_path: Path, name: str, data: bytes) -> bytes:
    """A one-panel page whose backdrop is the picture `data`, printed."""
    (tmp_path / name).write_bytes(data)
    source = tmp_path / "page.scene.yaml"
    source.write_text(
        "cast: {a: {reference: alice}}\n"
        "pages: [{tiers: [{panels: [shown]}]}]\n"
        f"panels: {{shown: {{setting: {{image: {name}}}}}}}\n",
        encoding="utf-8",
    )
    return _pdf(compile_book_file(source))


def _png(kind: int, pixels: bytes, *, palette: bytes = b"") -> bytes:
    """A 2 x 1 PNG, 8 bits, of colour type `kind`, with `pixels` as its one row's samples."""
    header = (2).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, kind, 0, 0, 0])
    parts = [chunk(b"IHDR", header)]
    if palette:
        parts.append(chunk(b"PLTE", palette))
    parts += [chunk(b"IDAT", zlib.compress(b"\x00" + pixels)), chunk(b"IEND", b"")]
    return PNG_SIGNATURE + b"".join(parts)


def _images(data: bytes) -> list[StreamObject]:
    reader = PdfReader(io.BytesIO(data))
    found: list[StreamObject] = []
    for page in reader.pages:
        resources = page["/Resources"]
        assert isinstance(resources, DictionaryObject)
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        assert isinstance(xobjects, DictionaryObject)
        for reference in xobjects.values():
            image = reference.get_object()
            assert isinstance(image, StreamObject)
            if image.get("/Subtype") == "/Image":
                found.append(image)
    return found


def _profiles(data: bytes) -> int:
    return len(re.findall(rb"/N 3 /Alternate /DeviceRGB", data))


class TestTheProfile:
    def test_it_is_the_iccs_srgb_unaltered(self):
        assert hashlib.sha256(PROFILE.read_bytes()).hexdigest() == SRGB_SHA256
        assert PROFILE.read_bytes() == SRGB_PROFILE

    def test_its_notice_ships_beside_it(self):
        notice = (PROFILE.parent / "README.md").read_text(encoding="utf-8")
        assert "without restriction" in notice


class TestTheDocument:
    @pytest.mark.parametrize(
        "name", ["70-a-page-for-print.scene.yaml", "01-two-characters.panel.yaml"]
    )
    def test_it_is_not_trapped(self, name: str):
        info = PdfReader(io.BytesIO(_gallery(name))).trailer["/Info"].get_object()
        assert isinstance(info, DictionaryObject)
        assert info["/Trapped"] == "/False"

    def test_its_output_intent_names_the_condition(self):
        catalog = (
            PdfReader(io.BytesIO(_gallery("70-a-page-for-print.scene.yaml")))
            .trailer["/Root"]
            .get_object()
        )
        assert isinstance(catalog, DictionaryObject)
        intents = catalog["/OutputIntents"]
        assert isinstance(intents, ArrayObject)
        (intent,) = intents
        intent = intent.get_object()
        assert isinstance(intent, DictionaryObject)
        assert intent["/Type"] == "/OutputIntent"
        assert intent["/S"] == "/GTS_PDFX"
        assert intent["/OutputConditionIdentifier"] == CONDITION == "CGATS21-2-CRPC6"
        assert intent["/RegistryName"] == "http://www.color.org"
        assert "GRACoL" in str(intent["/Info"])
        # Identifier only: the registered condition needs no profile in plain PDF.
        assert "/DestOutputProfile" not in intent

    def test_it_claims_no_pdf_x(self):
        """What a PDF/X-4 claim would need is left out on purpose: no preflight backs one."""
        data = _gallery("70-a-page-for-print.scene.yaml")
        for absent in (b"GTS_PDFXVersion", b"/Metadata", b"CreationDate", b"ModDate"):
            assert absent not in data

    @pytest.mark.parametrize(
        "name",
        ["70-a-page-for-print.scene.yaml", "21-atmosphere.scene.yaml", "24-page.scene.yaml"],
    )
    def test_every_page_blends_in_cmyk(self, name: str):
        reader = PdfReader(io.BytesIO(_gallery(name)))
        for page in reader.pages:
            group = page["/Group"]
            assert isinstance(group, DictionaryObject)
            assert (group["/S"], group["/CS"]) == ("/Transparency", "/DeviceCMYK")


class TestPictures:
    def test_an_rgb_picture_is_srgb(self):
        data = _gallery("70-a-page-for-print.scene.yaml")
        (image,) = _images(data)
        space = image["/ColorSpace"]
        assert isinstance(space, ArrayObject)
        assert space[0] == "/ICCBased"
        profile = space[1]
        assert isinstance(profile, IndirectObject)
        stream = profile.get_object()
        assert isinstance(stream, StreamObject)
        assert stream["/N"] == 3
        assert stream["/Alternate"] == "/DeviceRGB"
        assert stream.get_data() == SRGB_PROFILE
        assert b"/DeviceRGB /BitsPerComponent" not in data

    def test_the_profile_is_written_once(self):
        data = _gallery("38-tour.scene.yaml")
        assert len(_images(data)) > 1
        assert _profiles(data) == 1

    def test_a_palette_is_indexed_over_srgb(self, tmp_path: Path):
        palette = bytes([255, 0, 0, 0, 0, 255])
        data = _with_picture(tmp_path, "p.png", _png(3, bytes([0, 1]), palette=palette))
        (image,) = _images(data)
        space = image["/ColorSpace"]
        assert isinstance(space, ArrayObject)
        assert space[0] == "/Indexed"
        base = space[1]
        assert isinstance(base, ArrayObject)
        assert base[0] == "/ICCBased"

    def test_a_grey_picture_stays_device_grey(self, tmp_path: Path):
        """Grey prints on black alone, as every grey does: no profile to convert it by."""
        data = _with_picture(tmp_path, "g.png", _png(0, bytes([0, 255])))
        (image,) = _images(data)
        assert image["/ColorSpace"] == "/DeviceGray"
        assert _profiles(data) == 0

    def test_a_cmyk_jpeg_stays_device_cmyk(self, tmp_path: Path):
        """Tagging it would convert CMYK to CMYK, and black would no longer be K alone."""
        data = _with_picture(tmp_path, "c.jpg", _jpeg(components=4))
        (image,) = _images(data)
        assert image["/ColorSpace"] == "/DeviceCMYK"
        assert _profiles(data) == 0

    def test_a_document_without_rgb_pictures_carries_no_profile(self):
        assert _profiles(_gallery("70-a-page-for-print.scene.yaml")) == 1
        assert _profiles(_gallery("24-page.scene.yaml")) == 0

    def test_it_prints_the_same_twice(self):
        assert _gallery("38-tour.scene.yaml") == _gallery("38-tour.scene.yaml")
