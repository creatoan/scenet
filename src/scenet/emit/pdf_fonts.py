"""A lettering face as a font in the print PDF, for live text.

With `--live-text`, print letters in the faces themselves rather than in their outlines, so
the words can be selected, searched and copied. The outlines' promise holds all the same:
each glyph lands where its outline would, at the step the solver measured -- that is
`scenet.emit.pdf`'s part; this module carries the face.

A face goes in as a **subset**: the glyphs drawn, the glyphs those are built from, and
`.notdef`, made by fontTools' subsetter with every glyph kept at its own id. The code the PDF
draws a glyph by is that id, so there is one kind of font for every face: Type0, Identity-H.
TrueType outlines go in as `FontFile2`; CFF outlines as their OpenType file,
`FontFile3 /OpenType` (PDF 1.6, ISO 32000-1 §9.7.4.2: a CFF without CID operators is read by
glyph id). Nothing a reader would lay text out with goes in -- no `GSUB`, no `GPOS`, no
hinting -- because every position is the PDF's.

The face's licence decides whether it goes in at all: the `OS/2` table's `fsType`, read as the
OpenType specification says (:func:`embedding`). A face that may not go in, or one PDF 1.6
cannot carry, keeps its lettering in outlines, and :func:`refusal` says why.

Deterministic, like the rest of the file: the subset's options are fixed, its date is never
rewritten (fontTools would otherwise stamp the time, or read `SOURCE_DATE_EPOCH`), its tag
comes from what it holds, and nothing is compressed.
"""

import functools
import hashlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fontTools import subset
from fontTools.ttLib import TTFont

from scenet.emit.svg import fmt
from scenet.solve.text import FontMetrics

#: `fsType`'s usage permissions, bits 0 to 3 (OpenType, `OS/2`): 0 is installable.
USAGE = 0x000F
#: A restricted licence: the face may not be embedded.
RESTRICTED = 0x0002
#: Preview and print: the face may be embedded in a document that is viewed or printed.
PREVIEW_AND_PRINT = 0x0004
#: Editable: the face may be embedded in a document that is edited.
EDITABLE = 0x0008
#: The face may not be subset before it is embedded.
NO_SUBSETTING = 0x0100
#: Only the face's bitmaps may be embedded, none of its outlines.
BITMAP_ONLY = 0x0200

#: Places for a width, in thousandths of an em.
WIDTH_PLACES = 6

#: Tables print never reads from a subset: positions are the PDF's, not the face's layout
#: tables', and the default instance of a variable face is the one that was measured.
UNREAD = (
    "GSUB",
    "GPOS",
    "GDEF",
    "BASE",
    "JSTF",
    "fvar",
    "gvar",
    "avar",
    "cvar",
    "HVAR",
    "VVAR",
    "MVAR",
    "STAT",
)

#: The most entries one `beginbfchar` block of a CMap may hold.
CMAP_BLOCK = 100

#: `FontDescriptor` flags (ISO 32000-1, table 123).
FIXED_PITCH = 1
SYMBOLIC = 4
ITALIC = 64

#: One object of the PDF: its dictionary's entries, and its stream's bytes when it is one.
Part = tuple[str, bytes | None]


class Embedding(StrEnum):
    """What of a face goes into the PDF."""

    #: The glyphs drawn, and the glyphs those are built from.
    SUBSET = "subset"
    #: The whole file, as it is: the face may not be subset.
    WHOLE = "whole"
    #: Nothing: its licence forbids it, or lets only its bitmaps go in.
    NONE = "none"


def embedding(fs_type: int | None) -> Embedding:
    """What a face's `fsType` lets print embed.

    The usage sub-field is 0 for an installable face, 2 for a restricted licence, 4 for
    preview and print, 8 for editable. A face that sets several takes the least restrictive,
    as the specification allows; one that sets only the reserved bit 0 is read as restricted.
    A face whose bitmaps alone may go in is not embedded: print has no use for its bitmaps.

    Args:
        fs_type: The `OS/2` table's `fsType`, or `None` for a face without that table, which
            nothing restricts.

    Returns:
        What goes in.

    Example:
        >>> from scenet.emit.pdf_fonts import embedding
        >>> [embedding(bits).value for bits in (0x0004, 0x0002, 0x0006, 0x0100)]
        ['subset', 'none', 'subset', 'whole']
    """
    if fs_type is None:
        return Embedding.SUBSET
    usage = fs_type & USAGE
    allowed = usage == 0 or bool(usage & (PREVIEW_AND_PRINT | EDITABLE))
    if not allowed or fs_type & BITMAP_ONLY:
        return Embedding.NONE
    return Embedding.WHOLE if fs_type & NO_SUBSETTING else Embedding.SUBSET


@functools.lru_cache(maxsize=32)
def refusal(metrics: FontMetrics) -> str | None:
    """Why a face cannot go into the print PDF, or `None` when it can.

    Worded to follow "is not embedded: ", in a print note.
    """
    font = TTFont(io.BytesIO(metrics.data), lazy=True)
    fs_type = _fs_type(font)
    if embedding(fs_type) is Embedding.NONE:
        bits = f"OS/2 fsType {fs_type:#06x}"
        if fs_type is not None and fs_type & BITMAP_ONLY:
            return f"its licence lets only its bitmaps be embedded ({bits})"
        return f"its licence does not allow it to be embedded ({bits})"
    if "CFF2" in font:
        return "its outlines are CFF2, which a PDF 1.6 file cannot carry"
    if "CFF " in font:
        table: Any = font["CFF "]
        if hasattr(table.cff.topDictIndex[0], "ROS"):
            return "its CFF outlines are CID-keyed, which print does not embed"
    elif "glyf" not in font:
        return "it has no outlines to embed"
    return None


@dataclass(frozen=True, slots=True)
class PdfFont:
    """A face as the print PDF carries it.

    Attributes:
        name: Its name in the PDF: a subset's tag, then its PostScript name --
            `ABCDEF+SourceSansPro-Regular`.
        program: The font file the PDF embeds.
        truetype: TrueType outlines, embedded as `FontFile2`; otherwise CFF, in its
            OpenType file.
        widths: Each code's advance, in thousandths of an em, in order of code.
        text: The character each code stands for, in order of code: its `ToUnicode` map.
        descriptor: The entries of its `FontDescriptor` that describe the face.
    """

    name: str
    program: bytes
    truetype: bool
    widths: tuple[tuple[int, float], ...]
    text: tuple[tuple[int, str], ...]
    descriptor: str

    def objects(self, first: int) -> list[Part]:
        """Its five objects, numbered from `first`.

        The font a page names, its CIDFont, its descriptor, the font file and its
        `ToUnicode` map, in that order.
        """
        cid_font, descriptor, program, to_unicode = range(first + 1, first + 5)
        if self.truetype:
            kind, key, entries = "/CIDFontType2", "/FontFile2", f"/Length1 {len(self.program)}"
            glyphs = " /CIDToGIDMap /Identity"
        else:
            kind, key, entries, glyphs = "/CIDFontType0", "/FontFile3", "/Subtype /OpenType", ""
        return [
            (
                f"/Type /Font /Subtype /Type0 /BaseFont /{self.name} /Encoding /Identity-H "
                f"/DescendantFonts [{cid_font} 0 R] /ToUnicode {to_unicode} 0 R",
                None,
            ),
            (
                f"/Type /Font /Subtype {kind} /BaseFont /{self.name} "
                "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
                f"/FontDescriptor {descriptor} 0 R /W [{self._widths()}]{glyphs}",
                None,
            ),
            (
                f"/Type /FontDescriptor /FontName /{self.name} {self.descriptor} "
                f"{key} {program} 0 R",
                None,
            ),
            (entries, self.program),
            ("", _character_map(self.text)),
        ]

    def _widths(self) -> str:
        """The `W` array's entries: each run of consecutive codes, then their widths."""
        runs: list[tuple[int, list[str]]] = []
        for code, width in self.widths:
            if runs and runs[-1][0] + len(runs[-1][1]) == code:
                runs[-1][1].append(fmt(width, WIDTH_PLACES))
            else:
                runs.append((code, [fmt(width, WIDTH_PLACES)]))
        return " ".join(f"{start} [{' '.join(widths)}]" for start, widths in runs)


def width(metrics: FontMetrics, character: str) -> float:
    """A character's advance as the font's `W` array gives it, in thousandths of an em.

    The writer sets each glyph by this same number, so a reader's arithmetic and the
    outlines' agree: see `scenet.emit.pdf`.
    """
    advance = round(metrics.advance(character) * metrics.units_per_em)
    return advance * 1000 / metrics.units_per_em


def pdf_font(metrics: FontMetrics, characters: Iterable[str]) -> PdfFont:
    """A face as a PDF font, holding the glyphs of `characters`.

    Args:
        metrics: The face, which :func:`refusal` found nothing against.
        characters: Every character lettered in it, in any order. One the face lacks is
            left out, as its outlines leave it out.

    Returns:
        The font -- the same for the same face and characters, whatever their order.
    """
    return _pdf_font(metrics, tuple(sorted(set(characters))))


@functools.lru_cache(maxsize=64)
def _pdf_font(metrics: FontMetrics, characters: tuple[str, ...]) -> PdfFont:
    # In order of code point, so a glyph two characters share stands for the lower one.
    text: dict[int, str] = {}
    for character in characters:
        code = metrics.glyph_id(character)
        if code is not None and code not in text:
            text[code] = character
    codes = sorted(text)
    source = TTFont(io.BytesIO(metrics.data), lazy=True)
    whole = embedding(_fs_type(source)) is Embedding.WHOLE
    postscript = _postscript_name(source)
    return PdfFont(
        name=postscript if whole else f"{_tag(metrics.sha256, codes)}+{postscript}",
        program=_sfnt(metrics.data) if whole else _subset(metrics.data, codes),
        truetype="glyf" in source,
        widths=tuple((code, width(metrics, text[code])) for code in codes),
        text=tuple((code, text[code]) for code in codes),
        descriptor=_descriptor(source, metrics.units_per_em),
    )


def _fs_type(font: TTFont) -> int | None:
    if "OS/2" not in font:
        return None
    table: Any = font["OS/2"]
    return int(table.fsType)


def _subset(data: bytes, codes: list[int]) -> bytes:
    """The face cut to the glyphs `codes` names, each kept at its id."""
    font = TTFont(io.BytesIO(data), recalcTimestamp=False, recalcBBoxes=False)
    options = subset.Options()
    options.retain_gids = True
    options.hinting = False
    options.layout_features = []
    options.drop_tables = [*options.drop_tables, *UNREAD]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(gids=codes)
    subsetter.subset(font)
    return _saved(font)


def _sfnt(data: bytes) -> bytes:
    """A whole face, as it is -- or, from a WOFF, as the font file it wraps."""
    font = TTFont(io.BytesIO(data), recalcTimestamp=False, recalcBBoxes=False, lazy=True)
    if font.flavor is None:
        return data
    return _saved(font)


def _saved(font: TTFont) -> bytes:
    # A web font goes in as the font file it wraps: no PDF reader unwraps one.
    font.flavor = None
    output = io.BytesIO()
    font.save(output)
    return output.getvalue()


def _tag(digest: str, codes: list[int]) -> str:
    """A subset's tag: six capitals, from the face and the glyphs it holds."""
    held = hashlib.sha256(f"{digest}:{','.join(map(str, codes))}".encode()).digest()
    return "".join(chr(ord("A") + byte % 26) for byte in held[:6])


def _postscript_name(font: TTFont) -> str:
    """The face's PostScript name, cut to characters a PDF name may hold.

    A font is untrusted input like a document, and a name it writes reaches the PDF: so only
    letters, digits, `-`, `_` and `.` are kept.
    """
    found = ""
    if "name" in font:
        table: Any = font["name"]
        found = table.getDebugName(6) or ""
        if not found:
            found = f"{table.getDebugName(1) or ''}-{table.getDebugName(2) or ''}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", found).strip("-") or "Lettering"


def _descriptor(font: TTFont, units_per_em: float) -> str:
    """What a `FontDescriptor` says of a face, in thousandths of an em."""
    scale = 1000 / units_per_em
    head: Any = font["head"]
    hhea: Any = font["hhea"]
    os2: Any = font.get("OS/2")
    post: Any = font.get("post")
    angle = float(post.italicAngle) if post is not None else 0.0
    italic = angle != 0 or (os2 is not None and bool(os2.fsSelection & 1))
    fixed = post is not None and bool(post.isFixedPitch)
    flags = SYMBOLIC | (FIXED_PITCH if fixed else 0) | (ITALIC if italic else 0)
    cap = (
        os2.sCapHeight
        if os2 is not None and os2.version >= 2 and os2.sCapHeight > 0
        else hhea.ascent
    )
    weight = int(os2.usWeightClass) if os2 is not None else 400
    box = " ".join(fmt(value * scale) for value in (head.xMin, head.yMin, head.xMax, head.yMax))
    # No face says how thick its vertical stems are; this estimate from its weight class is
    # ReportLab's, and is what every reader that asks for `StemV` gets.
    stem = 50 + weight * weight // (65 * 65)
    return (
        f"/Flags {flags} /FontBBox [{box}] /ItalicAngle {fmt(angle, 4)} "
        f"/Ascent {fmt(hhea.ascent * scale)} /Descent {fmt(hhea.descent * scale)} "
        f"/CapHeight {fmt(cap * scale)} /StemV {stem}"
    )


def _character_map(text: tuple[tuple[int, str], ...]) -> bytes:
    """A `ToUnicode` CMap: each code, and the character it stands for, in UTF-16."""
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    for start in range(0, len(text), CMAP_BLOCK):
        block = text[start : start + CMAP_BLOCK]
        lines.append(f"{len(block)} beginbfchar")
        lines += [
            f"<{code:04X}> <{character.encode('utf-16-be').hex().upper()}>"
            for code, character in block
        ]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return ("\n".join(lines) + "\n").encode("ascii")
