"""The language's limits: every size, count and length has a bound.

A language with no upper bound on anything lets one line make the compiler allocate
without end: `size: [1e12, 1e12]` with `weather: rain` asked for some 10^20 streaks of rain.
So each has a limit, generous for real comics, and going past one is one finding, at the
value, that says what the limit is: rule `limit`.

The limits are here, in one place, and every other module reads them: the models' own
bounds, so the JSON Schemas state them; the readers of the files a document names; and the
page that lists them, `docs/reference/language/limits.md`, which a test holds to this module.

A file is read whole, so each file a document names, and the document itself, is bounded
too: a file larger than its bound is refused by its size, before a byte of it is read, under
the rule of the file it is (`image-file`, `font-file`). Those bounds are a number of bytes and
a module attribute, :data:`DOCUMENT_BYTES`, :data:`IMAGE_BYTES` and :data:`FONT_BYTES`, read
at the moment of each read: a host that wants tighter ones sets them before it compiles.

A :class:`Limits` other than :data:`LIMITS` may only tighten them: what a host that compiles
documents it does not trust can ask of :func:`exceeded`, for one request.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields

from scenet.errors import LimitsError

__all__ = [
    "DOCUMENT_BYTES",
    "FONT_BYTES",
    "IMAGE_BYTES",
    "LIMITS",
    "LIMIT_RULE",
    "WHAT",
    "Exceeded",
    "Limits",
    "describe",
    "exceeded",
    "past",
]

#: The rule every limit is reported under.
LIMIT_RULE = "limit"

#: One mebibyte.
_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Limits:
    """Every bound the language sets, with what each bounds.

    Lengths are in panel units, where a tenth of a millimetre is one unit printed; counts and
    sizes are whole numbers.

    Attributes:
        panel_side: A panel's width or height, in panel units: one metre printed.
        page_side: A page's width or height, in panel units.
        panels_per_page: How many panels one page lays out, insets included.
        pages_per_document: How many pages one document lays out.
        panels_per_document: How many panels one document holds.
        actors_per_panel: How many cast members one panel has.
        events_per_panel: How many lines, captions and sounds one panel's script holds.
        characters_per_text: How many characters one line, caption, sound or description
            holds.
        image_bytes: How large a supplied picture's file may be. A 600 dpi A4 page, the
            largest a printer asks for, is a PNG of some 30 to 60 MiB.
        image_pixels: How many pixels a supplied picture may have, its width times its height.
        font_bytes: How large a font file may be. A font that covers Chinese, Japanese or
            Korean is some 20 MiB.
        document_bytes: How large a document may be, in UTF-8, and the text files it names: a
            puppet file, an artwork contract. A hundred-page comic script is well under a
            megabyte.

    Example:
        >>> from scenet.limits import LIMITS, Limits
        >>> LIMITS.actors_per_panel
        50
        >>> Limits(actors_per_panel=4).panel_side == LIMITS.panel_side
        True
    """

    panel_side: float = 10_000.0
    page_side: float = 10_000.0
    panels_per_page: int = 200
    pages_per_document: int = 1_000
    panels_per_document: int = 10_000
    actors_per_panel: int = 50
    events_per_panel: int = 100
    characters_per_text: int = 2_000
    image_bytes: int = 128 * _MIB
    image_pixels: int = 200_000_000
    font_bytes: int = 64 * _MIB
    document_bytes: int = 8 * _MIB

    def __post_init__(self) -> None:
        """Refuse a limit past the language's own, or one that leaves nothing.

        Raises:
            LimitsError: A limit is not positive, or is past :data:`LIMITS`'s.
        """
        for item in fields(self):
            value = getattr(self, item.name)
            bound = item.default
            if value <= 0 or (isinstance(bound, (int, float)) and value > bound):
                raise LimitsError(
                    f"{item.name} must be above 0 and at most the language's {bound}, not {value}"
                )


#: The language's limits. A document past one of them is refused wherever it is read.
LIMITS = Limits()

#: The most Scenet reads of a document, and of the text files it names: a puppet file, an
#: artwork contract. Read at each read.
DOCUMENT_BYTES = LIMITS.document_bytes

#: The most Scenet reads of a picture to letter over. Read at each read.
IMAGE_BYTES = LIMITS.image_bytes

#: The most Scenet reads of a lettering face. Read at each read.
FONT_BYTES = LIMITS.font_bytes

#: What each limit bounds, as a finding says it: the limit, then the value past it.
WHAT: Mapping[str, str] = {
    "panel_side": "a panel is at most {limit} units on a side in Scenet, and this is {value}",
    "page_side": "a page is at most {limit} units on a side in Scenet, and this is {value}",
    "panels_per_page": "a page lays out at most {limit} panels in Scenet, and this one {value}",
    "pages_per_document": (
        "a document lays out at most {limit} pages in Scenet, and this one {value}"
    ),
    "panels_per_document": (
        "a document holds at most {limit} panels in Scenet, and this one {value}"
    ),
    "actors_per_panel": "a panel casts at most {limit} people in Scenet, and this one {value}",
    "events_per_panel": (
        "a panel's script holds at most {limit} lines, captions and sounds in Scenet, and this "
        "one {value}"
    ),
    "characters_per_text": "a text is at most {limit} characters in Scenet, and this one {value}",
    "image_bytes": "a picture is at most {limit} bytes in Scenet, and this one {value}",
    "image_pixels": "a picture has at most {limit} pixels in Scenet, and this one {value}",
    "font_bytes": "a font file is at most {limit} bytes in Scenet, and this one {value}",
    "document_bytes": "a document is at most {limit} bytes in Scenet, and this one {value}",
}


def past(name: str, value: float, limit: float) -> str:
    """The message for a value past a limit, which says the limit.

    Example:
        >>> from scenet.limits import past
        >>> past("actors_per_panel", 200, 50)
        'a panel casts at most 50 people in Scenet, and this one 200'
    """
    return WHAT[name].format(limit=_number(limit), value=_number(value))


def _number(value: float) -> str:
    """A number as a message writes it: `10000`, `2.5`, `1e+12`."""
    if isinstance(value, float) and (not value.is_integer() or abs(value) >= 1e9):
        return f"{value:g}"
    return f"{int(value)}"


@dataclass(frozen=True, slots=True)
class Exceeded:
    """One value past a limit a host asked for.

    Attributes:
        loc: Where, as a finding's path.
        message: What it is, and the limit.
    """

    loc: tuple[str | int, ...]
    message: str


def exceeded(
    panels: Mapping[str, object], limits: Limits, *, scene: bool = True
) -> Iterator[Exceeded]:
    """Every value of a read document past a tighter limit than the language's.

    The language's own limits are checked wherever a document is read; this is for a host
    that asks for less, per request -- a server compiling documents it does not trust.

    Args:
        panels: The document's panels, as read: panel name to its `PanelIR`.
        limits: The limits to hold it to.
        scene: Whether the document is a scene, whose panels are found under `panels`.

    Example:
        >>> from scenet import parse_scene
        >>> from scenet.limits import Limits, exceeded
        >>> panels = parse_scene("cast: {a: {reference: alice}, b: {reference: bob}}")
        >>> [found.loc for found in exceeded(panels, Limits(actors_per_panel=1), scene=False)]
        [('cast',)]
    """
    # Imported here: the models import this module for their bounds.
    from scenet.ir import CaptionEvent, PanelIR, SayEvent, SfxEvent  # noqa: PLC0415

    if len(panels) > limits.panels_per_document:
        yield Exceeded(
            ("panels",), past("panels_per_document", len(panels), limits.panels_per_document)
        )
    for name, panel in panels.items():
        if not isinstance(panel, PanelIR):
            continue
        at: tuple[str | int, ...] = ("panels", name) if scene else ()
        if max(panel.panel.size) > limits.panel_side:
            yield Exceeded(
                (*at, "panel", "size"), past("panel_side", max(panel.panel.size), limits.panel_side)
            )
        if len(panel.cast) > limits.actors_per_panel:
            yield Exceeded(
                (*at, "cast"), past("actors_per_panel", len(panel.cast), limits.actors_per_panel)
            )
        if len(panel.script) > limits.events_per_panel:
            yield Exceeded(
                (*at, "script"),
                past("events_per_panel", len(panel.script), limits.events_per_panel),
            )
        for index, event in enumerate(panel.script):
            if (
                isinstance(event, (SayEvent, CaptionEvent, SfxEvent))
                and len(event.text) > limits.characters_per_text
            ):
                verb = (
                    "say"
                    if isinstance(event, SayEvent)
                    else "caption"
                    if isinstance(event, CaptionEvent)
                    else "sfx"
                )
                yield Exceeded(
                    (*at, "script", index, verb, "text"),
                    past("characters_per_text", len(event.text), limits.characters_per_text),
                )


_UNITS = (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10))


def describe(size: int) -> str:
    """A number of bytes in words, in the largest unit it is a whole number of.

    Args:
        size: The number of bytes.

    Returns:
        `8 MiB`, say, or `10 bytes`.

    Example:
        >>> from scenet.limits import describe
        >>> describe(2048), describe(2049), describe(1)
        ('2 KiB', '2049 bytes', '1 byte')
    """
    for unit, scale in _UNITS:
        if size >= scale and size % scale == 0:
            return f"{size // scale} {unit}"
    return "1 byte" if size == 1 else f"{size} bytes"
