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
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

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

#: The shipped family, face by face.
SHIPPED_FACES: dict[Face, Path] = {
    Face.REGULAR: DEFAULT_FONT_PATH,
    Face.ITALIC: ITALIC_FONT_PATH,
    Face.BOLD_ITALIC: BOLD_ITALIC_FONT_PATH,
}

#: A run of text in one face: what a line of lettering is made of.
Run = tuple[str, Face]


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


class FontMetrics:
    """Advance widths read straight from the font's own tables.

    Kerning is deliberately ignored. Reading `kern`/`GPOS` would tighten measurement
    slightly, but SVG renderers do not agree on whether to apply it, and a measurement
    the renderer will not reproduce is worse than a slightly generous one. Erring wide
    means balloons are never too small for their text.
    """

    def __init__(self, path: Path = DEFAULT_FONT_PATH) -> None:
        """Open a font and read the tables needed for measurement.

        Args:
            path: A TrueType or OpenType file. Defaults to the font that ships as an
                ordinary dependency of this package -- never a system font lookup,
                because determinism requires the same metrics everywhere.

        Raises:
            ValueError: The font has no usable Unicode character map, so no text could
                be measured against it at all.
        """
        self.path = path
        self._font = TTFont(str(path), lazy=True)
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

    @property
    def units_per_em(self) -> float:
        """The font's design grid size, from its `head` table."""
        return self._units_per_em

    def advance(self, character: str) -> float:
        """Advance width of one character, in em units."""
        glyph = self._cmap.get(ord(character))
        raw = self._widths.get(glyph, self._missing) if glyph else self._missing
        return raw / self._units_per_em

    def measure(self, text: str, font_size: float) -> float:
        """Width of a string set at a given size.

        Args:
            text: The string to measure. Not wrapped; measured as one run.
            font_size: Type size in panel units.

        Returns:
            Width in panel units. Slightly generous, since kerning is ignored -- which
            errs toward balloons a shade too large rather than text that overflows.

        Example:
            >>> from scenet.solve.text import load_metrics
            >>> metrics = load_metrics()
            >>> metrics.measure("mm", 100) > metrics.measure("ii", 100)
            True
        """
        return sum(self.advance(character) for character in text) * font_size

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
        """Each character's outline as SVG path data, with its advance in em units.

        Converting lettering to outlines rather than emitting `<text>` is what makes
        the output genuinely self-contained: no font to embed, no font to be missing,
        and the rendered shapes are by construction the ones that were measured. The
        cost is that the text is no longer selectable, which is why `--live-text`
        exists.
        """
        glyph_set = self._font.getGlyphSet()
        outlines: list[tuple[str, float]] = []
        for character in text:
            name = self._cmap.get(ord(character))
            if name is None or name not in glyph_set:
                outlines.append(("", self.advance(character)))
                continue
            pen = SVGPathPen(glyph_set)
            glyph_set[name].draw(pen)
            outlines.append((pen.getCommands(), self.advance(character)))
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

    Example:
        >>> from scenet.ir import Face
        >>> from scenet.solve.text import Typeface
        >>> Typeface().face(Face.BOLD_ITALIC).path.name
        'SourceSansPro-BoldIt.ttf'
    """

    regular: FontMetrics | None = None
    italic: FontMetrics | None = None
    bold_italic: FontMetrics | None = None

    def face(self, face: Face) -> FontMetrics:
        """The metrics for one face of the family."""
        chosen = {
            Face.REGULAR: self.regular,
            Face.ITALIC: self.italic,
            Face.BOLD_ITALIC: self.bold_italic,
        }[face]
        if chosen is not None:
            return chosen
        # The regular face goes through the cache key every caller has always used.
        return load_metrics(None if face is Face.REGULAR else str(SHIPPED_FACES[face]))

    def measure(self, text: Styled, font_size: float) -> float:
        """Width of styled text, each character measured in its own face.

        The same sum, in the same order, as
        :meth:`FontMetrics.measure <scenet.solve.text.FontMetrics.measure>`: text in one
        face measures to the last bit exactly as the plain string does, which is what
        keeps every panel without emphasis laid out as it was before emphasis existed.
        """
        faces = {face: self.face(face) for face in set(text.faces)}
        return (
            sum(
                faces[face].advance(character)
                for character, face in zip(text.text, text.faces, strict=True)
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
    return words, gaps


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
