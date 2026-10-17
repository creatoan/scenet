"""Kerning: pair adjustments read from the font, in measurement and outlines alike.

Kerning used to be ignored on purpose, because SVG renderers do not agree on whether to
apply it to `<text>`, and a measurement the renderer will not reproduce is worse than a
slightly generous one. That reasoning is right for `--live-text` and wrong for the
default: outlines are positioned by Scenet itself (`cursor += advance`), so no renderer
has a say, and a pair adjustment is reproduced exactly.

So the pairs are read from the font -- the GPOS `kern` feature, or a legacy `kern` table
for a font that has only that -- with fontTools, which the playground has. HarfBuzz would
do it for us, but Pyodide does not ship it; here it is the **oracle**: every advance
Scenet computes, for every pair of characters the tests letter, must be the advance a
real shaper produces. That is what proves the subtle rules -- the first subtable that
covers a pair wins, a class pair applies even when its value is zero -- rather than any
one hand-picked pair.
"""

import importlib
import string
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

from scenet.emit.svg import render
from scenet.ir import Face
from scenet.pipeline import compile_source
from scenet.solve.text import (
    ITALIC_FONT_PATH,
    SHIPPED_FACES,
    FontMetrics,
    Styled,
    Typeface,
    _ClassPairs,
    _gpos_kerning,
    _pair_table,
    _x_advance,
    load_metrics,
)

#: Every character the property tests letter, and the punctuation dialogue is made of.
ALPHABET = string.ascii_letters + string.digits + ".,!?'-:;\"()" + "éèàçüöñÉ "

#: HarfBuzz with every substitution that could change the glyphs turned off, so what is
#: left to compare is positioning -- and of positioning, only kerning applies to text with
#: no marks in it.
FEATURES = {"kern": True, "liga": False, "clig": False, "calt": False, "dlig": False}

#: HarfBuzz's Python binding is a compiled extension with no stubs, so neither type checker
#: can see its members; it is used through `Any` rather than an ignore on every line.
hb: Any = importlib.import_module("uharfbuzz")


@cache  # one HarfBuzz font per file: an `hb.Font`, which has no stub
def _shaper(path: str) -> Any:
    return hb.Font(hb.Face(hb.Blob.from_file_path(path)))


def _harfbuzz_advances(path: Path, text: str) -> list[int]:
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(_shaper(str(path)), buffer, FEATURES)
    return [position.x_advance for position in buffer.glyph_positions]


def _scenet_advances(metrics: FontMetrics, text: str) -> list[int]:
    return [round(advance * metrics.units_per_em) for _, advance in metrics.glyph_outlines(text)]


class TestAgainstHarfBuzz:
    @pytest.mark.parametrize("face", list(Face))
    @pytest.mark.parametrize("first", sorted(set(ALPHABET)))
    def test_every_pair_kerns_as_a_shaper_kerns_it(self, face: Face, first: str):
        """`first` beside every character, on both sides of it: every ordered pair of the
        alphabet, in all three faces, against HarfBuzz."""
        path = SHIPPED_FACES[face]
        text = first + "".join(other + first for other in ALPHABET)
        assert _scenet_advances(load_metrics(str(path)), text) == _harfbuzz_advances(path, text)

    @pytest.mark.parametrize(
        "text",
        [
            "You forgot your umbrella!",
            "AVATAR WAVY Tokyo, LT. P.J. Yes? Va-va-voom!",
            "It has been raining since six this morning and you knew that.",
        ],
    )
    def test_whole_lines_kern_as_a_shaper_kerns_them(self, text: str):
        path = SHIPPED_FACES[Face.REGULAR]
        assert _scenet_advances(load_metrics(str(path)), text) == _harfbuzz_advances(path, text)


class TestThePairs:
    def test_a_famous_pair_is_tightened(self):
        metrics = load_metrics()
        assert metrics.kerning("A", "V") < 0
        assert metrics.kerning("T", "o") < 0

    def test_a_character_the_font_lacks_is_not_kerned(self):
        assert load_metrics().kerning("A", "\u200b") == 0.0

    def test_kerning_is_in_em_units(self):
        metrics = load_metrics()
        raw = _harfbuzz_advances(SHIPPED_FACES[Face.REGULAR], "AV")[0]
        assert metrics.advance("A") + metrics.kerning("A", "V") == pytest.approx(raw / 1000)


class TestMeasurement:
    def test_a_kerned_pair_measures_narrower(self):
        metrics = load_metrics()
        unkerned = (metrics.advance("A") + metrics.advance("V")) * 40
        assert metrics.measure("AV", 40) < unkerned

    def test_measurement_is_the_sum_of_the_drawn_advances(self):
        """What is measured is what is drawn: the outlines advance by the same steps."""
        metrics = load_metrics()
        text = "AVATAR Tokyo, Wa we yo"
        drawn = sum(advance for _, advance in metrics.glyph_outlines(text)) * 37.5
        assert drawn == metrics.measure(text, 37.5)

    def test_styled_text_in_one_face_kerns_as_the_plain_string(self):
        assert Typeface().measure(Styled.of("AVATAR"), 40) == load_metrics().measure("AVATAR", 40)

    def test_no_pair_is_kerned_across_a_change_of_face(self):
        """Two faces are two fonts, and kerning is a property of one font's pairs."""
        family = Typeface()
        regular, bold = family.face(Face.REGULAR), family.face(Face.BOLD_ITALIC)
        mixed = Styled("AV", (Face.REGULAR, Face.BOLD_ITALIC))
        assert family.measure(mixed, 40) == (regular.advance("A") + bold.advance("V")) * 40

    def test_the_last_character_is_not_kerned_against_nothing(self):
        metrics = load_metrics()
        assert metrics.measure("A", 40) == metrics.advance("A") * 40


def _font(path: Path, *, features: str | None = None, kern_coverage: int | None = None) -> Path:
    """A two-letter font, `A` and `V`, kerned however the test needs.

    Args:
        path: Where to write it.
        features: OpenType feature code to compile into GPOS, if any.
        kern_coverage: Give it a legacy `kern` table kerning `AV` by -80, with this
            coverage, if any.
    """
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A", "V"])
    builder.setupCharacterMap({ord("A"): "A", ord("V"): "V"})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in (".notdef", "A", "V")})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (600, 0), "V": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    if features is not None:
        builder.addOpenTypeFeatures(features)
    if kern_coverage is not None:
        table = KernTable_format_0()
        table.coverage = kern_coverage
        table.kernTable = {("A", "V"): -80}
        # fontTools builds table classes at runtime, so their attributes are invisible
        # to `ty`.
        kern: Any = newTable("kern")
        kern.version = 0
        kern.kernTables = [table]
        builder.font["kern"] = kern
    builder.save(str(path))
    return path


class TestALegacyKernTable:
    def test_it_is_read_when_there_is_no_gpos(self, tmp_path: Path):
        metrics = FontMetrics(_font(tmp_path / "legacy.ttf", kern_coverage=1))
        assert metrics.kerning("A", "V") == pytest.approx(-0.08)
        assert metrics.kerning("V", "A") == 0.0
        assert metrics.measure("AV", 100) == pytest.approx(112.0)

    @pytest.mark.parametrize(
        "coverage",
        [0b0011, 0b0101, 0],
        ids=["minimum values", "cross-stream", "vertical"],
    )
    def test_a_subtable_that_is_not_pair_kerning_is_skipped(self, tmp_path: Path, coverage: int):
        metrics = FontMetrics(_font(tmp_path / "legacy.ttf", kern_coverage=coverage))
        assert metrics.kerning("A", "V") == 0.0


class TestOtherFonts:
    def test_a_font_with_no_kerning_measures_by_advances(self, tmp_path: Path):
        metrics = FontMetrics(_font(tmp_path / "plain.ttf"))
        assert metrics.kerning("A", "V") == 0.0
        assert metrics.measure("AV", 100) == 120.0

    def test_an_extension_lookup_is_unwrapped(self, tmp_path: Path):
        """Large fonts move their kerning behind extension lookups when a table outgrows
        16-bit offsets; the pairs inside are the same pairs."""
        fea = "lookup KERN useExtension { pos A V -80; } KERN;\nfeature kern { lookup KERN; } kern;"
        metrics = FontMetrics(_font(tmp_path / "extension.ttf", features=fea))
        assert metrics.kerning("A", "V") == pytest.approx(-0.08)

    def test_kerning_for_another_script_is_not_applied_to_latin(self, tmp_path: Path):
        fea = "languagesystem cyrl dflt;\nfeature kern { pos A V -80; } kern;"
        metrics = FontMetrics(_font(tmp_path / "cyrillic.ttf", features=fea))
        assert metrics.kerning("A", "V") == 0.0

    def test_gpos_kerning_wins_over_a_legacy_table(self, tmp_path: Path):
        """As in a shaper: a font with both is kerned by its GPOS."""
        fea = "feature kern { pos A V -30; } kern;"
        metrics = FontMetrics(_font(tmp_path / "both.ttf", features=fea, kern_coverage=1))
        assert metrics.kerning("A", "V") == pytest.approx(-0.03)

    def test_styled_text_must_have_a_face_for_every_character(self):
        with pytest.raises(ValueError, match="2 characters but 1 faces"):
            Styled("AV", (Face.REGULAR,))


class TestOutput:
    def test_kerned_lettering_is_byte_identical_across_runs(self):
        source = "{cast: {a: {reference: alice}}, script: [{say: {by: a, text: AVATAR WAVY.}}]}"
        first = compile_source(source).core
        second = compile_source(source).core
        assert first.to_json() == second.to_json()
        assert render(first) == render(second)


def _legacy(path: Path, *subtables: Any, version: float = 0) -> Path:
    """The two-letter font, with a legacy `kern` table holding these subtables."""
    _font(path)
    font = TTFont(str(path))
    kern: Any = newTable("kern")
    kern.version = version
    kern.kernTables = list(subtables)
    font["kern"] = kern
    font.save(str(path))
    return path


def _subtable(coverage: int, *, apple: bool = False) -> Any:
    table: Any = KernTable_format_0(apple=apple)
    table.coverage = coverage
    table.tupleIndex = 0
    table.kernTable = {("A", "V"): -80}
    return table


class TestTheLegacyTableInFull:
    def test_an_apple_table_reads_its_own_flags(self, tmp_path: Path):
        """Apple's `kern` (version 1.0) flags vertical and cross-stream in the high bits,
        so a coverage of 0 is horizontal there -- and would be skipped read as OpenType's."""
        path = _legacy(tmp_path / "apple.ttf", _subtable(0, apple=True), version=1.0)
        assert FontMetrics(path).kerning("A", "V") == pytest.approx(-0.08)

    def test_a_skipped_subtable_does_not_end_the_table(self, tmp_path: Path):
        path = _legacy(tmp_path / "two.ttf", _subtable(0), _subtable(1))
        assert FontMetrics(path).kerning("A", "V") == pytest.approx(-0.08)


class TestTheGposTableInFull:
    def test_latin_is_read_before_the_default_script(self, tmp_path: Path):
        fea = (
            "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
            "feature kern { script latn; pos A V -80; } kern;"
        )
        assert FontMetrics(_font(tmp_path / "latn.ttf", features=fea)).kerning(
            "A", "V"
        ) == pytest.approx(-0.08)

    def test_every_lookup_adds_its_adjustment(self, tmp_path: Path):
        """As a shaper applies each lookup in turn: two that kern a pair kern it twice."""
        fea = (
            "lookup ONE { pos A V -30; } ONE;\nlookup TWO { pos A V -50; } TWO;\n"
            "feature kern { lookup ONE; lookup TWO; } kern;"
        )
        assert FontMetrics(_font(tmp_path / "two.ttf", features=fea)).kerning(
            "A", "V"
        ) == pytest.approx(-0.08)

    @pytest.mark.parametrize("missing", ["ScriptList", "FeatureList", "LookupList"])
    def test_a_gpos_table_missing_a_list_kerns_nothing(self, missing: str):
        lists = {"ScriptList": object(), "FeatureList": object(), "LookupList": object()}
        lists[missing] = None
        font: Any = {"GPOS": SimpleNamespace(table=SimpleNamespace(**lists))}
        assert _gpos_kerning(font) == []


class TestClassPairs:
    PAIRS = _ClassPairs(
        coverage=frozenset({"A", "B"}),
        first={"A": 1},
        second={"V": 1, "W": 2},
        values=((0, -10), (0, -80)),
    )

    def test_a_covered_glyph_no_class_lists_is_in_class_zero(self):
        assert self.PAIRS.adjust("B", "V") == -10
        assert self.PAIRS.adjust("A", "V") == -80

    def test_a_second_class_past_the_row_is_not_an_answer(self):
        assert self.PAIRS.adjust("A", "W") is None

    def test_a_subtable_with_no_class_definitions_puts_every_glyph_in_class_zero(self):
        cell = SimpleNamespace(Value1=SimpleNamespace(XAdvance=-40))
        subtable = SimpleNamespace(
            Format=2,
            Coverage=SimpleNamespace(glyphs=["A"]),
            ClassDef1=None,
            ClassDef2=None,
            Class1Record=[SimpleNamespace(Class2Record=[cell])],
        )
        table = _pair_table(subtable)
        assert table is not None
        assert table.adjust("A", "V") == -40

    def test_a_value_record_that_does_not_move_the_advance_is_zero(self):
        assert _x_advance(SimpleNamespace(YAdvance=12)) == 0
        assert _x_advance(None) == 0


class TestAPairWithACharacterTheFontLacks:
    """Never kerned -- even against a font whose class 0 kerns everything it meets."""

    def metrics(self, tmp_path: Path) -> FontMetrics:
        metrics = FontMetrics(_font(tmp_path / "class.ttf"))
        everything = _ClassPairs(coverage=frozenset({"A"}), first={}, second={}, values=((-50,),))
        metrics._kerning = [(everything,)]
        return metrics

    def test_kerning(self, tmp_path: Path):
        metrics = self.metrics(tmp_path)
        assert metrics.kerning("A", "\u200b") == 0.0
        assert metrics.kerning("A", "V") == pytest.approx(-0.05)

    def test_step(self, tmp_path: Path):
        metrics = self.metrics(tmp_path)
        assert metrics.step("A", "\u200b") == metrics.advance("A")


class TestNames:
    def test_a_font_with_no_name_table_is_named_by_its_file(self, tmp_path: Path):
        metrics = FontMetrics(_font(tmp_path / "plain.ttf"))
        assert (metrics.family, metrics.style) == ("plain", "Regular")

    def test_a_name_table_without_a_style_is_regular(self, tmp_path: Path):
        path = _font(tmp_path / "named.ttf")
        font = TTFont(str(path))
        builder = FontBuilder(font=font)
        builder.setupNameTable({"familyName": "Tested"})
        name: Any = font["name"]
        name.removeNames(nameID=2)
        font.save(str(path))
        metrics = FontMetrics(path)
        assert (metrics.family, metrics.style) == ("Tested", "Regular")

    def test_the_style_is_read_from_the_font(self):
        # Built here, not through the cache: a cached face never runs the constructor.
        assert FontMetrics(ITALIC_FONT_PATH).style == "Italic"
