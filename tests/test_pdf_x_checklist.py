"""The PDF/X-4 requirements the print PDF can meet, never a claim that it conforms (#283).

No free tool validates PDF/X-4, so Scenet claims nothing: there is no `GTS_PDFXVersion`, no
XMP, no date and no embedded output profile, and this test checks that they stay absent. What
it checks besides is what ISO 15930-7 asks of a file that the writer can meet by
construction, on every gallery example, outlined and in live text:

- the boxes: a TrimBox on every page, inside its BleedBox, inside its MediaBox;
- every font embedded;
- nothing PDF/X forbids: no encryption, no LZW, JBIG2 or JPEG 2000, no transfer function, no
  interpolated image, no PostScript, no external content, no JavaScript;
- a PDF version PDF/X-4 is built on, 1.6 at most;
- `/Trapped` said, and an output intent naming the condition.

Passing it says the file breaks none of these. It does not say the file is PDF/X-4: only a
preflight can, and none was run.
"""

import io
import re
from functools import cache

import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject

from scenet.emit.pdf import render_pdf
from tests.test_pdf import IDS, _book, _cores

#: Filters, actions and keys ISO 15930-7 rules out, or that would reach outside the file.
FORBIDDEN = (
    b"/Encrypt",
    b"/LZWDecode",
    b"/JBIG2Decode",
    b"/JPXDecode",
    b"/TR ",
    b"/TR2",
    b"/Interpolate true",
    b"/Subtype /PS",
    b"/OPI",
    b"/JavaScript",
    b"/Launch",
    b"/Type /Filespec",
)

#: What a PDF/X-4 claim would need and the file leaves out on purpose.
UNCLAIMED = (b"GTS_PDFXVersion", b"/Metadata", b"/CreationDate", b"/ModDate", b"/DestOutputProfile")


@cache
def _pdf(name: str, *, live_text: bool) -> bytes:
    book = _book(name)
    return render_pdf(
        book.pages, _cores(book), fonts=book.fonts, images=book.images, live_text=live_text
    )


def _numbers(box: object) -> tuple[float, float, float, float]:
    assert isinstance(box, ArrayObject)
    left, bottom, right, top = (float(value) for value in box)
    return left, bottom, right, top


def _inside(inner: object, outer: object) -> bool:
    a, b = _numbers(inner), _numbers(outer)
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


@pytest.mark.parametrize("live_text", [False, True], ids=["outlines", "live-text"])
@pytest.mark.parametrize("name", IDS)
def test_x4_requirements_are_not_broken(name: str, live_text: bool):
    data = _pdf(name, live_text=live_text)
    assert re.match(rb"%PDF-1\.[0-6]\n", data)
    # The objects alone: a font's or a picture's bytes may spell anything.
    objects = re.sub(rb"\nstream\n.*?\nendstream", b"", data, flags=re.DOTALL)
    for forbidden in FORBIDDEN:
        assert forbidden not in objects, forbidden
    for unclaimed in UNCLAIMED:
        assert unclaimed not in objects, unclaimed

    reader = PdfReader(io.BytesIO(data))
    info = reader.trailer["/Info"].get_object()
    assert isinstance(info, DictionaryObject)
    assert info["/Trapped"] == "/False"
    catalog = reader.trailer["/Root"].get_object()
    assert isinstance(catalog, DictionaryObject)
    assert "/OutputIntents" in catalog

    for page in reader.pages:
        assert _inside(page["/TrimBox"], page["/BleedBox"])
        assert _inside(page["/BleedBox"], page["/MediaBox"])
        resources = page["/Resources"]
        assert isinstance(resources, DictionaryObject)
        fonts = resources.get("/Font")
        if fonts is None:
            continue
        assert isinstance(fonts, DictionaryObject)
        for reference in fonts.values():
            font = reference.get_object()
            assert isinstance(font, DictionaryObject)
            descendants = font["/DescendantFonts"]
            assert isinstance(descendants, ArrayObject)
            (descendant,) = descendants
            descriptor = descendant.get_object()["/FontDescriptor"].get_object()
            assert isinstance(descriptor, DictionaryObject)
            assert "/FontFile2" in descriptor or "/FontFile3" in descriptor


def test_live_text_embeds_a_font_somewhere():
    """The font check above is not vacuous: the gallery's live-text PDFs carry fonts."""
    assert any(b"/FontFile2" in _pdf(name, live_text=True) for name in IDS)
