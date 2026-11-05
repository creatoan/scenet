"""Small files the print tests build from their parts: a face, and a page lettered in it.

A face is made with fontTools' `FontBuilder` -- a triangle for each of A and B, and a space --
in whatever outline format and with whatever licence bits a test needs, so no test depends on
a font it cannot see whole. A page is the least PDF that letters one line: the catalog, one
page, its content and the font's own objects, so a face's objects can be read back by pypdf
and drawn by Ghostscript before any writer uses them.
"""

from pathlib import Path
from typing import Literal

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scenet.emit.pdf_fonts import PdfFont

#: Each glyph of a test face, and how tall its triangle stands; the space has none.
GLYPHS = {".notdef": 700, "A": 700, "B": 500, "space": 0}

#: Each glyph's advance, in font units of a 1000-unit em.
ADVANCES = {".notdef": 600, "A": 600, "B": 650, "space": 250}


def face(
    path: Path,
    *,
    outlines: Literal["glyf", "CFF", "CFF2"] = "glyf",
    fs_type: int | None = 0,
    postscript_name: str = "Test-Regular",
    also: dict[int, str] | None = None,
) -> Path:
    """A three-glyph face, written to `path`.

    Args:
        path: Where to write it.
        outlines: TrueType, CFF or CFF2 outlines.
        fs_type: Its `OS/2` embedding bits, or `None` for a face with no `OS/2` table.
        postscript_name: What its `name` table calls it.
        also: More characters mapped onto its glyphs, by code point.
    """
    builder = FontBuilder(1000, isTTF=outlines == "glyf")
    builder.setupGlyphOrder(list(GLYPHS))
    builder.setupCharacterMap({ord("A"): "A", ord("B"): "B", ord(" "): "space", **(also or {})})
    if outlines == "glyf":
        glyphs = {}
        for name, top in GLYPHS.items():
            pen = TTGlyphPen(None)
            _triangle(pen, top)
            glyphs[name] = pen.glyph()
        builder.setupGlyf(glyphs)
    else:
        strings = {}
        for name, top in GLYPHS.items():
            # CFF2 keeps a glyph's advance in `hmtx` alone.
            width = None if outlines == "CFF2" else ADVANCES[name]
            pen = T2CharStringPen(width, None, CFF2=outlines == "CFF2")
            _triangle(pen, top)
            strings[name] = pen.getCharString()
        if outlines == "CFF2":
            builder.setupCFF2(strings)
        else:
            builder.setupCFF(postscript_name, {"FullName": "Test"}, strings, {})
    builder.setupHorizontalMetrics({name: (advance, 0) for name, advance in ADVANCES.items()})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {"familyName": "Test", "styleName": "Regular", "psName": postscript_name}
    )
    if fs_type is not None:
        builder.setupOS2(
            fsType=fs_type,
            usWeightClass=400,
            sTypoAscender=800,
            sTypoDescender=-200,
            sCapHeight=700,
        )
    builder.setupPost()
    builder.save(str(path))
    return path


def _triangle(pen: TTGlyphPen | T2CharStringPen, top: int) -> None:
    if top:
        pen.moveTo((50, 0))
        pen.lineTo((550, 0))
        pen.lineTo((300, top))
        pen.closePath()


def page(font: PdfFont | None, content: str, *, width: float = 300, height: float = 100) -> bytes:
    """A one-page PDF drawn by `content`, with `font` as its `/F1` if it has one."""
    first = 5
    resources = f"<< /Font << /F1 {first} 0 R >> >>" if font is not None else "<< >>"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources {resources} /Contents 4 0 R >>"
        ).encode(),
        _stream("", content.encode()),
    ]
    if font is not None:
        for entries, data in font.objects(first):
            objects.append(
                _stream(entries, data) if data is not None else f"<< {entries} >>".encode()
            )
    output = bytearray(b"%PDF-1.6\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def _stream(entries: str, data: bytes) -> bytes:
    head = f"<< {entries} /Length {len(data)} >>" if entries else f"<< /Length {len(data)} >>"
    return head.encode() + b"\nstream\n" + data + b"\nendstream"
