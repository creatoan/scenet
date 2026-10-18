"""An author's lettering face, read from the font files a document declares.

The shipped face is Source Sans Pro, which `THIRD_PARTY_NOTICES.md` already calls a
placeholder. The faces letterers actually use -- Blambot's, Comicraft's -- are commercial
or free only on their own terms, so the project can never ship one; an author can declare
one. `lettering: {font: ...}` names the files, and this module reads them.

Two choices are made here and nowhere else:

- **A font is known by its bytes.** Files are cached by the digest of what is in them,
  not by where they are, so a file replaced in place -- the playground does it on every
  upload -- is read again; and Panel Core records the digest, so a drawing can refuse a
  file that merely shares a name with the one that was measured.
- **A face the document does not name stands in from one it does.** Italic captions fall
  back to the regular face, emphasis to the italic and then the regular: a family drawn
  from one file is a whole family, which a mix of the author's face and the shipped one
  would not be. The compiler says so when a stand-in is actually used. The display face
  is the exception: sound effects are not text, so an author's text faces never stand in
  for it, and it stays Bangers unless the document names one of its own.

Every failure -- a path that is absolute or has no folder to be read from, a file that is
missing, a file that is not a font -- is rule `font-file`, located at the face it names.
"""

from dataclasses import dataclass
from pathlib import Path

from scenet.errors import PanelSyntaxError
from scenet.ir import Face, LetteringSpec
from scenet.paths import Folder, read_relative
from scenet.solve.text import FontMetrics, Typeface

__all__ = ["FONT_RULE", "Lettering", "load_font", "typeface_for"]

#: The rule every font fault is reported under.
FONT_RULE = "font-file"

#: Fonts read so far, by the digest of their bytes.
_BY_CONTENT: dict[str, FontMetrics] = {}


@dataclass(frozen=True, slots=True)
class Lettering:
    """A panel's lettering family, read.

    Attributes:
        typeface: Every face, the author's where they named one.
        declared: The faces the document named a file for. Empty when it named none and
            letters in the shipped family.
    """

    typeface: Typeface
    declared: frozenset[Face] = frozenset()

    def stands_in(self, face: Face) -> bool:
        """Whether `face` is set in another face, because the document named no file for it."""
        return bool(self.declared) and face not in self.declared


def load_font(declared: str, base: Folder | None, *, loc: tuple[str | int, ...]) -> FontMetrics:
    """Read one declared font file.

    Args:
        declared: The path as the document wrote it.
        base: The document's folder, or the files sent with it.
        loc: Where in the document it was written, for the finding.

    Returns:
        Its metrics, shared with every other document declaring the same bytes.

    Raises:
        PanelSyntaxError: Rule `font-file`. The message names the path as written, never
            as resolved: findings are output too, and an absolute path in one would make
            it differ between two checkouts.
    """
    data = read_relative(declared, base, what="font", rule=FONT_RULE, loc=loc)

    known = _BY_CONTENT.get(FontMetrics.digest(data))
    if known is not None:
        return known
    try:
        metrics = FontMetrics(Path(declared), data=data)
    # A file that is not a font can fail inside fontTools in more ways than it documents,
    # and the bytes came from whoever wrote the document. Whatever the failure, the
    # answer to the author is the same.
    except Exception as exc:
        raise PanelSyntaxError(
            f"font file {declared!r} is not a font that can be measured: a TrueType or "
            "OpenType file with a Unicode character map is needed",
            rule=FONT_RULE,
            loc=loc,
        ) from exc
    _BY_CONTENT[metrics.sha256] = metrics
    return metrics


def typeface_for(spec: LetteringSpec, base: Folder | None) -> Lettering:
    """The family a panel letters in: the shipped one, or the files it declares.

    Args:
        spec: The panel's `lettering` block.
        base: The document's folder, the files sent with it, or `None` for text with
            neither.

    Returns:
        The family, and which faces were named.

    Raises:
        PanelSyntaxError: Rule `font-file`, for the first face that cannot be read.

    Example:
        >>> from scenet.ir import LetteringSpec
        >>> from scenet.lettering import typeface_for
        >>> typeface_for(LetteringSpec(), None).declared
        frozenset()
    """
    font = spec.font
    if font is None:
        return Lettering(Typeface())
    where = ("lettering", "font")
    regular = load_font(font.regular, base, loc=(*where, "regular"))
    italic = load_font(font.italic, base, loc=(*where, "italic")) if font.italic else None
    bold_italic = (
        load_font(font.bold_italic, base, loc=(*where, "bold_italic")) if font.bold_italic else None
    )
    display = load_font(font.display, base, loc=(*where, "display")) if font.display else None
    declared = {Face.REGULAR}
    if display is not None:
        declared.add(Face.DISPLAY)
    if italic is not None:
        declared.add(Face.ITALIC)
    if bold_italic is not None:
        declared.add(Face.BOLD_ITALIC)
    return Lettering(
        Typeface(
            regular=regular,
            italic=italic or regular,
            bold_italic=bold_italic or italic or regular,
            display=display,
        ),
        frozenset(declared),
    )
