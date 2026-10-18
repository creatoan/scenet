"""Text measurement and line breaking.

Nothing downstream can proceed without this. A balloon's size is a function of its
text, wrapped at some measure, in a specific font -- and placement, occlusion and
reading order all depend on that size. So wrapping is decided here, during
compilation, and the result is carried through Panel Core as explicit lines. The
emitter never re-measures and therefore can never disagree with the solver.

Determinism demands the font be fixed. It arrives as a declared dependency rather
than a system lookup precisely because "whatever font this machine happens to have"
is the opposite of reproducible.
"""

import functools
import hashlib
import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol

# The `fonts` packages publish each face through entry_points at install time, so
# the attribute exists at runtime but cannot be seen statically.
from fonts.ttf import (
    SourceSansPro,  # ty: ignore[unresolved-import]  # pyright: ignore[reportAttributeAccessIssue]
    SourceSansProBoldIt,  # ty: ignore[unresolved-import]  # pyright: ignore[reportAttributeAccessIssue]
    SourceSansProIt,  # ty: ignore[unresolved-import]  # pyright: ignore[reportAttributeAccessIssue]
)
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from scenet.emphasis import parse
from scenet.ir import Face

# Comic balloons are markedly wider than they are tall. Wrapping searches for the
# measure whose block lands nearest this ratio.
#
# 2.0 rather than something squarer: a lower target makes short dialogue break into
# too many lines, which is how "You forgot your umbrella!" ends up as
# "You forgot / your / umbrella!" with a word stranded alone. Letterers do not do
# that.
TARGET_ASPECT = 2.0

# Multiplied by font size to give the baseline-to-baseline distance.
LINE_HEIGHT_FACTOR = 1.25

# Space between the text block and the balloon outline, as a multiple of font size.
PADDING_FACTOR = 0.55

# Added to a block's shape score for each line beyond the first. Small, but enough
# that a marginally better aspect ratio cannot justify breaking a short phrase.
LINE_PENALTY = 0.08

# Weight on line-length imbalance. Comic lettering balances lines; a short line
# stranded beneath a long one reads as an accident even when the block as a whole is
# well proportioned.
RAGGEDNESS_WEIGHT = 0.3

DEFAULT_FONT_PATH = Path(SourceSansPro)

#: The italic face of the same family, for the caption kinds letterers set in italic.
#: A real font file rather than a skew transform: a synthetic oblique measures as the
#: roman face and draws as neither, which is exactly the disagreement between
#: measurement and rendering this module exists to prevent. It costs nothing to use --
#: it ships in the same declared dependency.
ITALIC_FONT_PATH = Path(SourceSansProIt)

#: The bold italic face of the same family, for emphasis. Blambot: "There's almost no
#: plain bold in comics dialogue. Typically, bold italic is used when emphasis is placed
#: on a word." A real file for the same reason the italic is one.
BOLD_ITALIC_FONT_PATH = Path(SourceSansProBoldIt)

#: The display face sound effects are lettered in: Bangers, by Vernon Adams, drawn in the
#: manner of mid-century comic cover lettering. Not of the same family, and not meant to
#: be -- a sound effect is letters treated as picture, not as text. No package carries it,
#: so it is vendored under `scenet/fonts/` with its licence, the SIL OFL 1.1, beside it.
#: A file of the package rather than a system font, for the same reason as every face.
DISPLAY_FONT_PATH = Path(str(files("scenet").joinpath("fonts", "Bangers-Regular.ttf")))

#: The shipped family, face by face.
SHIPPED_FACES: dict[Face, Path] = {
    Face.REGULAR: DEFAULT_FONT_PATH,
    Face.ITALIC: ITALIC_FONT_PATH,
    Face.BOLD_ITALIC: BOLD_ITALIC_FONT_PATH,
    Face.DISPLAY: DISPLAY_FONT_PATH,
}

#: A run of text in one face: what a line of lettering is made of.
Run = tuple[str, Face]

#: GPOS lookup types, from the OpenType specification: pair adjustment, and the
#: extension that wraps a lookup of another type when a table outgrows 16-bit offsets.
PAIR_LOOKUP = 2
EXTENSION_LOOKUP = 9


@dataclass(frozen=True, slots=True)
class Styled:
    """Text with the face every character is set in.

    What lettering is measured and drawn as once emphasis is read: `I _told_ you` is the
    plain text `I told you` with `told` in bold italic. A string of one face is the same
    thing with every character in that face, and measures exactly as the string always
    did.

    Attributes:
        text: The characters, markers already removed.
        faces: One face per character.
    """

    text: str
    faces: tuple[Face, ...]

    def __post_init__(self) -> None:
        """Refuse a face list that does not match the text, which would misalign every run."""
        if len(self.faces) != len(self.text):
            raise ValueError(f"{len(self.text)} characters but {len(self.faces)} faces")

    @classmethod
    def of(cls, text: str, face: Face = Face.REGULAR) -> "Styled":
        """Text all in one face."""
        return cls(text, (face,) * len(text))

    def __add__(self, other: "Styled") -> "Styled":
        """The two, one after the other."""
        return Styled(self.text + other.text, self.faces + other.faces)

    def slice(self, start: int, end: int) -> "Styled":
        """The characters from `start` up to `end`, with their faces."""
        return Styled(self.text[start:end], self.faces[start:end])

    @property
    def runs(self) -> tuple[Run, ...]:
        """The text cut wherever the face changes, as `(text, face)` pairs."""
        runs: list[Run] = []
        start = 0
        for index in range(1, len(self.text) + 1):
            if index == len(self.text) or self.faces[index] != self.faces[start]:
                runs.append((self.text[start:index], self.faces[start]))
                start = index
        return tuple(runs)


def styled(text: str, base: Face = Face.REGULAR) -> Styled:
    """Read a line as written into the faces it is lettered in.

    Args:
        text: Dialogue or a caption, emphasis markers and all.
        base: The face the line is set in -- italic for most captions. Emphasis is bold
            italic whatever the base, which is the letterers' convention for a stressed
            word in an italic caption as much as in a roman balloon.

    Returns:
        The text without its markers, each character in its face.

    Raises:
        EmphasisError: A span was opened and never closed. The IR refuses such text, so
            this only happens to a caller building lettering by hand.

    Example:
        >>> from scenet.solve.text import styled
        >>> [(text, face.value) for text, face in styled("I _told_ you").runs]
        [('I ', 'regular'), ('told', 'bold_italic'), (' you', 'regular')]
    """
    result = Styled("", ())
    for span in parse(text):
        result += Styled.of(span.text, Face.BOLD_ITALIC if span.emphasised else base)
    return result


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Wrapped text, measured."""

    lines: tuple[str, ...]
    width: float
    height: float
    font_size: float
    line_height: float

    line_widths: tuple[float, ...] = ()
    #: Each line cut into runs of one face. A line with no emphasis is one run.
    runs: tuple[tuple[Run, ...], ...] = ()

    @property
    def aspect(self) -> float:
        """Width divided by height, or `0.0` for an empty block.

        The quantity the line breaker optimises. Lettering convention wants a balloon
        wider than it is tall -- see `TARGET_ASPECT`.
        """
        return self.width / self.height if self.height else 0.0

    @property
    def raggedness(self) -> float:
        """How unbalanced the lines are, from 0 (equal) to nearly 1 (one line tiny)."""
        if len(self.line_widths) < 2 or self.width <= 0:
            return 0.0
        return 1.0 - min(self.line_widths) / max(self.line_widths)


class _PairTable(Protocol):
    """One subtable of kerning pairs."""

    def adjust(self, left: str, right: str) -> int | None:
        """The adjustment for a pair of glyphs, in font units.

        `None` means the subtable does not cover the pair, and the next one in its lookup
        is asked. Zero is an answer: a covered pair with no adjustment stops the search.
        """
        ...


@dataclass(frozen=True, slots=True)
class _GlyphPairs:
    """Pairs listed one by one: GPOS PairPos format 1, or a legacy `kern` table.

    Attributes:
        pairs: First glyph to second glyph to adjustment.
    """

    pairs: dict[str, dict[str, int]]

    def adjust(self, left: str, right: str) -> int | None:
        """The listed adjustment, or `None` for a pair not listed."""
        return self.pairs.get(left, {}).get(right)


@dataclass(frozen=True, slots=True)
class _ClassPairs:
    """Pairs by class: GPOS PairPos format 2.

    A glyph a class definition does not list is in class 0, and that is a real class: a
    first glyph the subtable covers always gets an answer from it, zero or not, and no
    later subtable is asked. Getting that wrong is invisible on a famous pair and wrong on
    thousands of others, which is why `tests/test_kerning.py` checks every pair against
    HarfBuzz.

    Attributes:
        coverage: The first glyphs this subtable answers for.
        first: First glyph to its class.
        second: Second glyph to its class.
        values: Adjustment by first class, then second class.
    """

    coverage: frozenset[str]
    first: dict[str, int]
    second: dict[str, int]
    values: tuple[tuple[int, ...], ...]

    def adjust(self, left: str, right: str) -> int | None:
        """The adjustment for the pair's classes, or `None` for an uncovered first glyph."""
        if left not in self.coverage:
            return None
        row = self.values[self.first.get(left, 0)]
        column = self.second.get(right, 0)
        return row[column] if column < len(row) else None


def _x_advance(value: object) -> int:
    """What a value record does to the advance: all a kern pair changes in a line of text."""
    return int(getattr(value, "XAdvance", 0) or 0)


def _pair_table(subtable: Any) -> _PairTable | None:  # noqa: ANN401 -- fontTools builds these dynamically
    """One PairPos subtable, indexed for lookup by glyph name."""
    if subtable.Format == 1:
        pairs: dict[str, dict[str, int]] = {}
        for first, pair_set in zip(subtable.Coverage.glyphs, subtable.PairSet, strict=True):
            seconds = pairs.setdefault(first, {})
            for record in pair_set.PairValueRecord:
                seconds.setdefault(record.SecondGlyph, _x_advance(record.Value1))
        return _GlyphPairs(pairs)
    if subtable.Format == 2:
        return _ClassPairs(
            coverage=frozenset(subtable.Coverage.glyphs),
            first=dict(subtable.ClassDef1.classDefs) if subtable.ClassDef1 else {},
            second=dict(subtable.ClassDef2.classDefs) if subtable.ClassDef2 else {},
            values=tuple(
                tuple(_x_advance(cell.Value1) for cell in row.Class2Record)
                for row in subtable.Class1Record
            ),
        )
    return None  # pragma: no cover -- OpenType defines PairPos formats 1 and 2 only


def _gpos_kerning(font: TTFont) -> list[tuple[_PairTable, ...]]:
    """The `kern` feature's lookups, each as its subtables in order.

    Read from the `latn` script's default language system, or `DFLT` when there is none:
    the lookups a shaper applies to Latin text, which is what lettering is.
    """
    if "GPOS" not in font:
        return []
    table: Any = font["GPOS"].table
    if table.ScriptList is None or table.FeatureList is None or table.LookupList is None:
        return []
    scripts = {record.ScriptTag: record.Script for record in table.ScriptList.ScriptRecord}
    script = scripts.get("latn", scripts.get("DFLT"))
    if script is None or script.DefaultLangSys is None:
        return []
    features = table.FeatureList.FeatureRecord
    indices = sorted(
        {
            index
            for feature in script.DefaultLangSys.FeatureIndex
            if features[feature].FeatureTag == "kern"
            for index in features[feature].Feature.LookupListIndex
        }
    )
    lookups: list[tuple[_PairTable, ...]] = []
    for index in indices:
        lookup = table.LookupList.Lookup[index]
        subtables: list[_PairTable] = []
        for subtable in lookup.SubTable:
            kind, body = lookup.LookupType, subtable
            if kind == EXTENSION_LOOKUP:
                kind, body = subtable.ExtensionLookupType, subtable.ExtSubTable
            if kind == PAIR_LOOKUP and (pairs := _pair_table(body)) is not None:
                subtables.append(pairs)
        if subtables:
            lookups.append(tuple(subtables))
    return lookups


def _legacy_kerning(font: TTFont) -> list[tuple[_PairTable, ...]]:
    """A legacy `kern` table's horizontal pair lists, each its own lookup.

    Only for a font with no GPOS kerning, which is what a shaper does too. Format 0 is the
    only format OpenType defines for it; a subtable for minimum values or cross-stream
    adjustment is not a pair adjustment, and is skipped.
    """
    if "kern" not in font:
        return []
    lookups: list[tuple[_PairTable, ...]] = []
    for subtable in getattr(font["kern"], "kernTables", []):
        if getattr(subtable, "format", None) != 0:
            continue
        coverage = int(getattr(subtable, "coverage", 1))
        # Apple's format flags vertical and cross-stream in the high bits; OpenType's wants
        # horizontal set, and neither minimum values nor cross-stream.
        apple = bool(getattr(subtable, "apple", False))
        horizontal = not (coverage & 0xC0) if apple else (coverage & 0b0111) == 1
        if not horizontal:
            continue
        pairs: dict[str, dict[str, int]] = {}
        for (left, right), value in sorted(subtable.kernTable.items()):
            pairs.setdefault(left, {})[right] = int(value)
        lookups.append((_GlyphPairs(pairs),))
    return lookups


#: `name` table entries: the family and the style within it, as a font's own four-face
#: (regular, italic, bold, bold italic) naming gives them. The legacy pair rather than
#: the typographic one, because it is what a renderer matches `font-family` against
#: across the most systems.
FAMILY_NAME = 1
STYLE_NAME = 2


def _name(font: TTFont, name_id: int) -> str:
    """A `name` table entry, cut to what may be written into an SVG, or empty."""
    if "name" not in font:
        return ""
    table: Any = font["name"]
    found = table.getDebugName(name_id) or ""
    # A font is untrusted input like a document: a name holding a control character
    # would make an SVG no parser accepts, so only printable characters are kept.
    return "".join(character for character in found if character.isprintable()).strip()


class FontMetrics:
    """Advance widths and pair kerning, read straight from the font's own tables.

    Kerning is applied, in measurement and in the outlines alike. It used to be ignored,
    because SVG renderers do not agree on whether to kern `<text>`, and a measurement the
    renderer will not reproduce is worse than a slightly generous one. That holds for
    `--live-text` and not for the default: outlines are positioned here, glyph by glyph,
    so no renderer has a say and every pair adjustment is reproduced exactly.

    Attributes:
        path: The file it was read from, or the path a document wrote for bytes it was
            handed. Used to open it and nothing else: no path reaches any output.
        sha256: The digest of the file's bytes, which is what Panel Core names a face by.
        family: The family name from the font's `name` table.
        style: The style within the family: `Regular`, `Italic`, `Bold Italic`.

    Pairs come from the GPOS `kern` feature, or from a legacy `kern` table in a font that
    has no GPOS kerning -- read with fontTools rather than shaped with HarfBuzz, which
    Pyodide does not ship. HarfBuzz is the test oracle instead. Only pair adjustments are
    applied: no ligatures, no contextual alternates, no mark positioning, which is all a
    Latin line of lettering needs and all that measurement can promise to reproduce.
    """

    def __init__(self, path: Path = DEFAULT_FONT_PATH, *, data: bytes | None = None) -> None:
        """Open a font and read the tables needed for measurement.

        Args:
            path: A TrueType or OpenType file. Defaults to the font that ships as an
                ordinary dependency of this package -- never a system font lookup,
                because determinism requires the same metrics everywhere.
            data: The file's bytes, already read -- from beside a document, or sent with
                one. `path` is then only the name it goes by: a family name falls back
                to its stem, so one font names itself the same from a file or from memory.

        Raises:
            OSError: The file cannot be read.
            ValueError: The font has no usable Unicode character map, so no text could
                be measured against it at all.
        """
        self.path = path
        # Read whole, once. What a font *is* is its bytes: Panel Core names a face by
        # their digest, so a drawing can be refused a file that merely shares a name.
        # It also means no file stays open behind a lazily read font.
        if data is None:
            data = Path(path).read_bytes()
        self.sha256 = self.digest(data)
        self._font = TTFont(io.BytesIO(data), lazy=True)
        # fontTools builds table objects dynamically, so `unitsPerEm` exists at runtime
        # but not in any stub. Both checkers are told, each in its own dialect.
        head = self._font["head"]
        self._units_per_em: float = head.unitsPerEm  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
        # A font with no usable Unicode cmap cannot be measured against text at all,
        # so this is worth failing on loudly rather than limping along with no glyphs.
        # fontTools raises KeyError for a font with no `cmap` table at all, rather than
        # returning None, so that case is asked about first.
        cmap = self._font.getBestCmap() if "cmap" in self._font else None
        if cmap is None:
            raise ValueError(f"{path}: font has no usable Unicode character map")
        self._cmap: dict[int, str] = cmap
        self._widths: dict[str, int] = {
            name: advance for name, (advance, _lsb) in self._font["hmtx"].metrics.items()
        }
        self._missing = self._widths.get(".notdef", 0)
        # Read on first use, then answered pair by pair: expanding every class pair up
        # front would be millions of entries for a font with a full Latin set.
        self._kerning: list[tuple[_PairTable, ...]] | None = None
        self._kerned: dict[tuple[str, str], int] = {}
        self.family = _name(self._font, FAMILY_NAME) or Path(path).stem
        self.style = _name(self._font, STYLE_NAME) or "Regular"

    @property
    def extent(self) -> tuple[float, float]:
        """How far the face reaches above and below the baseline, in em units.

        The `hhea` ascender and descender, both as positive distances: what a line of
        this face can occupy, which is what a sound effect's footprint is built from.
        """
        table: Any = self._font["hhea"]
        return table.ascent / self._units_per_em, -table.descent / self._units_per_em

    @staticmethod
    def digest(data: bytes) -> str:
        """What a font file is known by: the SHA-256 of its bytes, in hex."""
        return hashlib.sha256(data).hexdigest()

    @property
    def units_per_em(self) -> float:
        """The font's design grid size, from its `head` table."""
        return self._units_per_em

    def _raw_advance(self, character: str) -> int:
        glyph = self._cmap.get(ord(character))
        return self._widths.get(glyph, self._missing) if glyph else self._missing

    def _pair(self, left: str, right: str) -> int:
        """The kerning between two glyphs, in font units: each lookup's first answer, summed."""
        known = self._kerned.get((left, right))
        if known is not None:
            return known
        if self._kerning is None:
            self._kerning = _gpos_kerning(self._font) or _legacy_kerning(self._font)
        total = 0
        for lookup in self._kerning:
            for subtable in lookup:
                value = subtable.adjust(left, right)
                if value is not None:
                    total += value
                    break
        self._kerned[(left, right)] = total
        return total

    def advance(self, character: str) -> float:
        """Advance width of one character, in em units, before any kerning."""
        return self._raw_advance(character) / self._units_per_em

    def kerning(self, left: str, right: str) -> float:
        """The adjustment between two neighbouring characters, in em units.

        Negative tightens. Zero for a pair the font does not kern, and for a character the
        font has no glyph for.

        Example:
            >>> from scenet.solve.text import load_metrics
            >>> load_metrics().kerning("A", "V") < 0
            True
        """
        first, second = self._cmap.get(ord(left)), self._cmap.get(ord(right))
        if first is None or second is None:
            return 0.0
        return self._pair(first, second) / self._units_per_em

    def step(self, character: str, following: str | None = None) -> float:
        """How far one character moves the pen, in em units.

        Its advance, plus the kerning between it and the character after it, summed in
        font units before dividing -- so a pair the font does not kern steps exactly as
        far as its advance.

        Args:
            character: The character being set.
            following: The one after it in the same face, or `None` at the end of a run.

        Returns:
            The distance to the next character's origin.
        """
        raw = self._raw_advance(character)
        if following is not None:
            first, second = self._cmap.get(ord(character)), self._cmap.get(ord(following))
            if first is not None and second is not None:
                raw += self._pair(first, second)
        return raw / self._units_per_em

    def measure(self, text: str, font_size: float) -> float:
        """Width of a string set at a given size, kerned.

        Args:
            text: The string to measure. Not wrapped; measured as one run.
            font_size: Type size in panel units.

        Returns:
            Width in panel units: the sum of every character's `step`, which is exactly
            how far the outlines advance when they are drawn.

        Example:
            >>> from scenet.solve.text import load_metrics
            >>> metrics = load_metrics()
            >>> metrics.measure("mm", 100) > metrics.measure("ii", 100)
            True
        """
        last = len(text) - 1
        return (
            sum(
                self.step(character, text[index + 1] if index < last else None)
                for index, character in enumerate(text)
            )
            * font_size
        )

    def line_height(self, font_size: float) -> float:
        """Baseline-to-baseline distance for a given type size.

        Args:
            font_size: Type size in panel units.

        Returns:
            `font_size * LINE_HEIGHT_FACTOR`. A fixed multiple rather than the font's
            own ascent-plus-descent, because comics lettering is set to a chosen
            leading rather than to whatever the typeface suggests.
        """
        return font_size * LINE_HEIGHT_FACTOR

    def glyph_outlines(self, text: str) -> list[tuple[str, float]]:
        """Each character's outline as SVG path data, with its `step` in em units.

        The step is the advance plus the kerning to the next character, so the outlines
        advance by exactly what `measure` summed.

        Converting lettering to outlines rather than emitting `<text>` is what makes
        the output genuinely self-contained: no font to embed, no font to be missing,
        and the rendered shapes are by construction the ones that were measured. The
        cost is that the text is no longer selectable, which is why `--live-text`
        exists.
        """
        glyph_set = self._font.getGlyphSet()
        outlines: list[tuple[str, float]] = []
        last = len(text) - 1
        for index, character in enumerate(text):
            step = self.step(character, text[index + 1] if index < last else None)
            name = self._cmap.get(ord(character))
            if name is None or name not in glyph_set:
                outlines.append(("", step))
                continue
            pen = SVGPathPen(glyph_set)
            glyph_set[name].draw(pen)
            outlines.append((pen.getCommands(), step))
        return outlines


@functools.lru_cache(maxsize=8)
def load_metrics(path: str | None = None) -> FontMetrics:
    """Cached metrics. Parsing a 300 KB font per balloon would be absurd."""
    return FontMetrics(Path(path) if path else DEFAULT_FONT_PATH)


@dataclass(frozen=True, slots=True)
class Typeface:
    """A lettering family: one font file per face.

    A face left as `None` is the shipped one, loaded only when something is set in it --
    a panel with no emphasis never opens the bold italic file.

    Attributes:
        regular: Dialogue, and `spoken` captions.
        italic: Every other caption kind.
        bold_italic: Emphasis, in either.
        display: Sound effects. Bangers when not given, whatever the other faces are.

    Example:
        >>> from scenet.ir import Face
        >>> from scenet.solve.text import Typeface
        >>> Typeface().face(Face.BOLD_ITALIC).path.name
        'SourceSansPro-BoldIt.ttf'
    """

    regular: FontMetrics | None = None
    italic: FontMetrics | None = None
    bold_italic: FontMetrics | None = None
    display: FontMetrics | None = None

    def face(self, face: Face) -> FontMetrics:
        """The metrics for one face of the family."""
        chosen = {
            Face.REGULAR: self.regular,
            Face.ITALIC: self.italic,
            Face.BOLD_ITALIC: self.bold_italic,
            Face.DISPLAY: self.display,
        }[face]
        if chosen is not None:
            return chosen
        # The regular face goes through the cache key every caller has always used.
        return load_metrics(None if face is Face.REGULAR else str(SHIPPED_FACES[face]))

    def measure(self, text: Styled, font_size: float) -> float:
        """Width of styled text, each character measured in its own face.

        Kerned within a face and never across a change of face: two faces are two fonts,
        and a pair adjustment belongs to one font's pairs. Otherwise the same sum, in the
        same order, as :meth:`FontMetrics.measure <scenet.solve.text.FontMetrics.measure>`,
        so text in one face measures to the last bit exactly as the plain string does.
        """
        characters, faces = text.text, text.faces
        metrics = {face: self.face(face) for face in set(faces)}
        last = len(characters) - 1
        return (
            sum(
                metrics[face].step(
                    character,
                    characters[index + 1] if index < last and faces[index + 1] is face else None,
                )
                for index, (character, face) in enumerate(zip(characters, faces, strict=True))
            )
            * font_size
        )


def _words(text: Styled) -> tuple[list[Styled], list[Face]]:
    """Split styled text at whitespace, as `str.split` does.

    Returns:
        The words, and for each break between two of them the face of the space that
        joins them when they share a line: bold italic inside a span that runs across
        words, the line's own face anywhere else.
    """
    words: list[Styled] = []
    gaps: list[Face] = []
    start: int | None = None
    gap = Face.REGULAR
    for index, character in enumerate(text.text):
        if character.isspace():
            if start is not None:
                words.append(text.slice(start, index))
                start = None
                gap = text.faces[index]
        elif start is None:
            if words:
                gaps.append(gap)
            start = index
    if start is not None:
        words.append(text.slice(start, len(text.text)))
    return _keep_marks_with_their_words(words, gaps)


#: A double dash, a dash or an ellipsis standing as a word of its own: `out --`, `... maybe`.
_MARK = re.compile(r"^(?:-{2,}|[\u2013\u2014]+|\.{3,}|\u2026+)$")


def _keep_marks_with_their_words(
    words: list[Styled], gaps: list[Face]
) -> tuple[list[Styled], list[Face]]:
    """Join a dash or an ellipsis written apart to the word it belongs to.

    Blambot: "There should also be no space before or after an ellipsis or double dash".
    A script may still write one apart -- `the lamp is out --` -- and the space is kept
    as written. But it is never a place to break: a mark set at the start of a line, or
    alone on one, reads as a stray. So it joins the word before it, or the word after it
    when it opens the text.
    """
    if len(words) < 2:
        return words, gaps
    joined: list[Styled] = [words[0]]
    joints: list[Face] = []
    for word, gap in zip(words[1:], gaps, strict=True):
        if _MARK.match(word.text) or (len(joined) == 1 and _MARK.match(joined[0].text)):
            joined[-1] = joined[-1] + Styled.of(" ", gap) + word
        else:
            joined.append(word)
            joints.append(gap)
    return joined, joints


def _line(words: Sequence[Styled], gaps: Sequence[Face], start: int, end: int) -> Styled:
    """Words `start` up to `end` set on one line, a single space between each."""
    line = words[start]
    for index in range(start + 1, end):
        line = line + Styled.of(" ", gaps[index - 1]) + words[index]
    return line


def _wrap(
    words: Sequence[Styled],
    gaps: Sequence[Face],
    typeface: Typeface,
    font_size: float,
    measure: float,
) -> list[Styled]:
    lines: list[Styled] = []
    start = 0
    for index in range(1, len(words)):
        if typeface.measure(_line(words, gaps, start, index + 1), font_size) > measure:
            lines.append(_line(words, gaps, start, index))
            start = index
    lines.append(_line(words, gaps, start, len(words)))
    return lines


def wrap_styled(text: Styled, typeface: Typeface, font_size: float, measure: float) -> list[Styled]:
    """Greedy word wrap of styled text at a given measure.

    Greedy rather than Knuth-Plass: balloons hold a handful of words, where the
    optimal-fit algorithm's advantage vanishes, and greedy is trivially deterministic.

    A single word longer than the measure is left to overflow rather than being
    hyphenated or broken. Breaking a word mid-way in comic lettering looks like a
    mistake, and the balloon widening to fit is the correct outcome.

    Each line is measured in the faces it is set in, so a stressed word is wider here
    exactly as it will be drawn wider -- and can push its neighbour onto the next line.
    """
    words, gaps = _words(text)
    if not words:
        return []
    return _wrap(words, gaps, typeface, font_size, measure)


def wrap_to_width(text: str, metrics: FontMetrics, font_size: float, measure: float) -> list[str]:
    """Greedy word wrap of plain text at a given measure; see `wrap_styled`."""
    family = Typeface(regular=metrics)
    return [line.text for line in wrap_styled(Styled.of(text), family, font_size, measure)]


def _candidates(
    words: Sequence[Styled], gaps: Sequence[Face], typeface: Typeface, font_size: float
) -> list[float]:
    widths = {
        typeface.measure(_line(words, gaps, start, end), font_size)
        for start in range(len(words))
        for end in range(start + 1, len(words) + 1)
    }
    return sorted(widths)


def candidate_measures(words: list[str], metrics: FontMetrics, font_size: float) -> list[float]:
    """Every line measure at which the wrapping can change.

    A line is always some contiguous run of words, so the widths of all such runs are
    exactly the measures worth trying. Anything between two of them produces the same
    break points as the lower one.

    The obvious shortcut -- dividing total width by the desired line count -- looks
    equivalent and is not. For "You forgot your umbrella!" it never proposes the
    measure that fits "You forgot your", so the good two-line break is unreachable and
    the search settles for a ragged three-line block instead. Balloons hold a few
    dozen words at most, so enumerating runs costs nothing.
    """
    return _candidates(
        [Styled.of(word) for word in words],
        [Face.REGULAR] * max(len(words) - 1, 0),
        Typeface(regular=metrics),
        font_size,
    )


def layout_text(
    text: str | Styled,
    *,
    font_size: float,
    metrics: FontMetrics | None = None,
    typeface: Typeface | None = None,
    target_aspect: float = TARGET_ASPECT,
) -> TextBlock:
    """Wrap text into the best-shaped block for a balloon.

    Scored on how close the block comes to the target aspect ratio, plus a penalty per
    line. The penalty is what stops a three-word phrase being split: purely on aspect,
    breaking "I know." into two lines scores marginally better than leaving it alone,
    which is not something any letterer would do.

    Args:
        text: Plain text, set in the regular face, or styled text from `styled`.
        font_size: Type size in panel units.
        metrics: The regular face, in place of the family's.
        typeface: The family to measure in. Defaults to the shipped one.
        target_aspect: The width-to-height ratio the block aims for.

    Returns:
        The best block: its lines as plain text, and its runs the faces they are set in.
    """
    family = typeface or Typeface()
    if metrics is not None:
        family = replace(family, regular=metrics)
    content = Styled.of(text) if isinstance(text, str) else text
    words, gaps = _words(content)
    base = content.faces[0] if content.faces else Face.REGULAR
    line_height = family.face(base).line_height(font_size)
    if not words:
        return TextBlock((), 0.0, 0.0, font_size, line_height, ())

    widest_word = max(family.measure(word, font_size) for word in words)

    best: TextBlock | None = None
    best_score = math.inf
    for measure in _candidates(words, gaps, family, font_size):
        if measure < widest_word:
            # Narrower than the longest word, so it cannot change the wrapping.
            continue
        lines = _wrap(words, gaps, family, font_size, measure)
        widths = tuple(family.measure(line, font_size) for line in lines)
        block = TextBlock(
            tuple(line.text for line in lines),
            max(widths),
            len(lines) * line_height,
            font_size,
            line_height,
            widths,
            tuple(line.runs for line in lines),
        )
        score = _shape_score(block, target_aspect)
        if score < best_score:
            best, best_score = block, score

    if best is None:
        # Only reachable if every candidate measure was narrower than the longest
        # word -- a single word longer than any proposed line. Set it on one line and
        # let the balloon be as wide as it must be; refusing to letter a long word
        # would be worse than an over-wide balloon.
        whole = _line(words, gaps, 0, len(words))
        best = TextBlock(
            (whole.text,),
            widest_word,
            line_height,
            font_size,
            line_height,
            (widest_word,),
            (whole.runs,),
        )
    return best


def _shape_score(block: TextBlock, target: float) -> float:
    """How poorly a block is shaped. Lower is better.

    Aspect error is measured in log space so that being twice as wide as wanted is
    penalised equally with being half as wide. In linear space the search drifts toward
    tall narrow blocks, because a ratio can fall only to zero but rise without bound.
    """
    if block.height <= 0 or block.width <= 0:
        return math.inf
    aspect_error = abs(math.log(block.aspect / target))
    return (
        aspect_error + LINE_PENALTY * (len(block.lines) - 1) + RAGGEDNESS_WEIGHT * block.raggedness
    )


def balloon_size(block: TextBlock, padding_factor: float = PADDING_FACTOR) -> tuple[float, float]:
    """Outer dimensions of a balloon holding this text block."""
    padding = block.font_size * padding_factor
    return block.width + 2 * padding, block.height + 2 * padding
