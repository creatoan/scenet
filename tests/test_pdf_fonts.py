"""A lettering face as a font in the print PDF (#284).

`--live-text` letters the print PDF in its faces rather than in their outlines. A face goes in
as a subset, each glyph at its own id, so the code a PDF draws a glyph by is its id; its
licence -- the `OS/2` table's `fsType` -- decides whether it may go in at all. Each subset is
read back with fontTools, and its objects with pypdf from a one-page file built around them
(`tests/pdf_files.py`), so a test trusts neither the subsetter's word nor a writer's.
"""

import hashlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fontTools.ttLib import TTFont
from pypdf import PdfReader

from scenet.emit.pdf_fonts import Embedding, embedding, pdf_font, refusal
from scenet.ir import Face
from scenet.solve.text import FontMetrics, Typeface
from tests.pdf_files import face, page

#: Lettering with an accent, curly quotes and an ellipsis: glyphs built from other glyphs.
SAMPLE = "H" + chr(0xE9) + "llo, " + chr(0x201C) + "quoted" + chr(0x201D) + " AV" + chr(0x2026)


@pytest.mark.parametrize(
    ("fs_type", "expected"),
    [
        (None, Embedding.SUBSET),
        (0x0000, Embedding.SUBSET),
        (0x0002, Embedding.NONE),
        (0x0004, Embedding.SUBSET),
        (0x0008, Embedding.SUBSET),
        (0x0001, Embedding.NONE),
        (0x0003, Embedding.NONE),
        (0x0006, Embedding.SUBSET),
        (0x000A, Embedding.SUBSET),
        (0x0100, Embedding.WHOLE),
        (0x0104, Embedding.WHOLE),
        (0x0102, Embedding.NONE),
        (0x0200, Embedding.NONE),
        (0x0208, Embedding.NONE),
    ],
    ids=[
        "no OS/2 table",
        "installable",
        "restricted",
        "preview and print",
        "editable",
        "the reserved bit alone",
        "reserved and restricted",
        "restricted, and preview and print: the least restrictive",
        "restricted, and editable: the least restrictive",
        "no subsetting",
        "no subsetting, preview and print",
        "no subsetting, restricted",
        "bitmaps only",
        "bitmaps only, editable",
    ],
)
def test_the_licence_bits_decide_what_goes_in(fs_type: int | None, expected: Embedding):
    assert embedding(fs_type) is expected


def _source(metrics: FontMetrics) -> TTFont:
    return TTFont(io.BytesIO(metrics.data))


def _subset(metrics: FontMetrics, text: str = SAMPLE) -> TTFont:
    return TTFont(io.BytesIO(pdf_font(metrics, text).program))


def _cmap(font: TTFont) -> dict[int, str]:
    cmap = font.getBestCmap()
    assert cmap is not None
    return cmap


def _table(font: TTFont, tag: str) -> Any:
    """A table, as fontTools builds it at runtime: its attributes are invisible to checkers."""
    return font[tag]


class TestAShippedFace:
    @pytest.fixture(params=list(Face), ids=lambda face: face.value)
    def metrics(self, request: pytest.FixtureRequest) -> FontMetrics:
        return Typeface().face(request.param)

    def test_it_may_be_embedded(self, metrics: FontMetrics):
        assert refusal(metrics) is None

    def test_the_glyphs_drawn_keep_their_ids_and_their_advances(self, metrics: FontMetrics):
        source, subset = _source(metrics), _subset(metrics)
        cmap = _cmap(source)
        drawn = [character for character in SAMPLE if ord(character) in cmap]
        assert drawn
        # A subset keeps no glyph names, so glyphs are compared by id, as the PDF draws them.
        kept = subset.getGlyphOrder()
        for character in drawn:
            name = cmap[ord(character)]
            code = source.getGlyphID(name)
            assert metrics.glyph_id(character) == code
            assert subset["hmtx"][kept[code]][0] == source["hmtx"][name][0]

    def test_it_holds_the_glyphs_drawn_and_the_glyphs_they_are_made_of(self, metrics: FontMetrics):
        source, subset = _source(metrics), _subset(metrics)
        cmap = _cmap(source)
        wanted = {".notdef"} | {
            cmap[ord(character)] for character in SAMPLE if ord(character) in cmap
        }
        glyphs = source["glyf"]
        pending = list(wanted)
        while pending:
            glyph = glyphs[pending.pop()]
            if glyph.isComposite():
                for component in glyph.components:
                    if component.glyphName not in wanted:
                        wanted.add(component.glyphName)
                        pending.append(component.glyphName)
        drawn = {
            code
            for code, name in enumerate(subset.getGlyphOrder())
            if subset["glyf"][name].numberOfContours != 0
        }
        assert drawn == {
            source.getGlyphID(name) for name in wanted if glyphs[name].numberOfContours != 0
        }

    def test_its_licence_and_its_date_are_kept(self, metrics: FontMetrics):
        source, subset = _source(metrics), _subset(metrics)
        assert _table(subset, "OS/2").fsType == _table(source, "OS/2").fsType
        assert subset["head"].modified == source["head"].modified

    def test_what_print_never_reads_is_left_out(self, metrics: FontMetrics):
        tables = set(_subset(metrics).keys())
        assert not {"GSUB", "GPOS", "GDEF", "BASE", "fpgm", "prep", "cvt "} & tables

    def test_its_widths_are_its_advances_in_thousandths_of_an_em(self, metrics: FontMetrics):
        font = pdf_font(metrics, SAMPLE)
        source = _source(metrics)
        names = source.getGlyphOrder()
        assert font.widths
        for code, width in font.widths:
            assert width == source["hmtx"][names[code]][0] * 1000 / metrics.units_per_em

    def test_each_code_stands_for_the_character_drawn_with_it(self, metrics: FontMetrics):
        font = pdf_font(metrics, SAMPLE)
        expected = {
            code: character
            for character in SAMPLE
            if (code := metrics.glyph_id(character)) is not None
        }
        assert dict(font.text) == expected
        assert [code for code, _ in font.widths] == sorted(expected)

    def test_its_name_is_a_subset_tag_and_its_postscript_name(self, metrics: FontMetrics):
        postscript = _table(_source(metrics), "name").getDebugName(6)
        assert postscript
        assert re.fullmatch(r"[A-Z]{6}\+" + re.escape(postscript), pdf_font(metrics, SAMPLE).name)

    def test_it_goes_in_as_truetype(self, metrics: FontMetrics):
        font = pdf_font(metrics, SAMPLE)
        assert font.truetype
        entries = [part for part, _ in font.objects(5)]
        assert "/Subtype /CIDFontType2 " in entries[1]
        assert "/CIDToGIDMap /Identity" in entries[1]
        assert "/FontFile2 8 0 R" in entries[2]
        assert entries[3] == f"/Length1 {len(font.program)}"


def test_a_subset_tag_follows_the_glyphs_it_holds():
    metrics = Typeface().face(Face.REGULAR)
    first, again, other = pdf_font(metrics, "AB"), pdf_font(metrics, "BA"), pdf_font(metrics, "ABC")
    assert first == again
    assert first.name[:6] != other.name[:6]


def test_the_same_face_is_the_same_bytes_whatever_the_hash_seed():
    script = (
        "import hashlib\n"
        "from scenet.emit.pdf_fonts import pdf_font\n"
        "from scenet.ir import Face\n"
        "from scenet.solve.text import Typeface\n"
        f"font = pdf_font(Typeface().face(Face.REGULAR), {SAMPLE!a})\n"
        "print(hashlib.sha256(font.program + repr(font.objects(5)).encode()).hexdigest())\n"
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
    font = pdf_font(Typeface().face(Face.REGULAR), SAMPLE)
    local = hashlib.sha256(font.program + repr(font.objects(5)).encode()).hexdigest()
    assert digests == {local + "\n"}


class TestAFaceOfAnyKind:
    def test_a_restricted_face_is_not_embedded(self, tmp_path: Path):
        reason = refusal(FontMetrics(face(tmp_path / "restricted.ttf", fs_type=0x0002)))
        assert reason is not None
        assert "0x0002" in reason

    def test_a_face_whose_bitmaps_alone_may_go_in_is_not_embedded(self, tmp_path: Path):
        reason = refusal(FontMetrics(face(tmp_path / "bitmaps.ttf", fs_type=0x0200)))
        assert reason is not None
        assert "bitmap" in reason

    def test_a_cff2_face_is_not_embedded(self, tmp_path: Path):
        reason = refusal(FontMetrics(face(tmp_path / "variable.otf", outlines="CFF2")))
        assert reason is not None
        assert "CFF2" in reason

    def test_a_face_with_no_os2_table_is_embedded(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "bare.ttf", fs_type=None))
        assert refusal(metrics) is None
        assert pdf_font(metrics, "AB").program

    def test_a_face_that_may_not_be_subset_goes_in_whole(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "whole.ttf", fs_type=0x0100))
        assert refusal(metrics) is None
        assert pdf_font(metrics, "A").program == metrics.data

    def test_a_cff_face_goes_in_as_an_opentype_file(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "cff.otf", outlines="CFF"))
        assert refusal(metrics) is None
        font = pdf_font(metrics, "AB")
        assert not font.truetype
        assert "CFF " in TTFont(io.BytesIO(font.program))
        entries = [part for part, _ in font.objects(5)]
        assert "/Subtype /CIDFontType0 " in entries[1]
        assert "/CIDToGIDMap" not in entries[1]
        assert "/FontFile3 8 0 R" in entries[2]
        assert entries[3] == "/Subtype /OpenType"

    def test_two_characters_drawn_with_one_glyph_read_back_as_the_first(self, tmp_path: Path):
        # U+0391, GREEK CAPITAL LETTER ALPHA, drawn with the Latin A.
        metrics = FontMetrics(face(tmp_path / "alpha.ttf", also={0x0391: "A"}))
        font = pdf_font(metrics, chr(0x0391) + "A")
        assert dict(font.text) == {metrics.glyph_id("A"): "A"}

    def test_a_character_the_face_lacks_is_left_out(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "small.ttf"))
        assert metrics.glyph_id("Z") is None
        assert dict(pdf_font(metrics, "AZ").text) == {metrics.glyph_id("A"): "A"}

    def test_a_name_from_the_font_is_cut_to_what_a_pdf_name_holds(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "evil.ttf", postscript_name="Evil (Name)/<x>%"))
        assert re.fullmatch(r"[A-Z]{6}\+[A-Za-z0-9_.-]+", pdf_font(metrics, "A").name)


class TestTheMetrics:
    def test_they_keep_the_bytes_they_were_read_from(self, tmp_path: Path):
        path = face(tmp_path / "kept.ttf")
        assert FontMetrics(path).data == path.read_bytes()

    def test_a_glyph_id_is_the_one_the_font_maps_the_character_to(self):
        metrics = Typeface().face(Face.REGULAR)
        source = _source(metrics)
        assert metrics.glyph_id("A") == source.getGlyphID(_cmap(source)[ord("A")])
        assert metrics.glyph_id(chr(0x200B)) is None


class TestALineReadsBack:
    def test_in_a_shipped_face(self):
        metrics = Typeface().face(Face.REGULAR)
        codes = "".join(
            f"{code:04X}"
            for character in SAMPLE
            if (code := metrics.glyph_id(character)) is not None
        )
        data = page(pdf_font(metrics, SAMPLE), f"BT /F1 20 Tf 1 0 0 1 10 40 Tm <{codes}> Tj ET")
        assert PdfReader(io.BytesIO(data)).pages[0].extract_text() == SAMPLE

    def test_in_a_cff_face(self, tmp_path: Path):
        metrics = FontMetrics(face(tmp_path / "cff.otf", outlines="CFF"))
        text = "AB BA"
        codes = "".join(f"{metrics.glyph_id(character):04X}" for character in text)
        data = page(pdf_font(metrics, text), f"BT /F1 20 Tf 1 0 0 1 10 40 Tm <{codes}> Tj ET")
        assert PdfReader(io.BytesIO(data)).pages[0].extract_text() == text

    def test_its_character_map_is_one_a_reader_takes(self):
        font = pdf_font(Typeface().face(Face.REGULAR), SAMPLE)
        entries, cmap = font.objects(5)[4]
        assert entries == ""
        assert cmap is not None
        text = cmap.decode("ascii")
        assert "<0000> <FFFF>" in text
        blocks = [int(count) for count in re.findall(r"(\d+) beginbfchar", text)]
        assert sum(blocks) == len(font.text)
        assert all(0 < count <= 100 for count in blocks)
