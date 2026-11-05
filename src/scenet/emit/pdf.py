"""Panel Core into a PDF a printer takes (#80).

The SVG is for screens; this is for print. It draws exactly what the SVG draws -- the same
marks, from the same numbers (`scenet.emit.marks`) -- but says it in inks rather than
colours, because print has a convention a screen does not: **lettering goes on the black
plate only**, overprinting whatever is under it, so type stays sharp when the colour plates
drift out of register. So every paint is set by what it *is*, never by converting its hex:

- ink -- every line and letter -- is 100% K and overprints;
- the paper -- a balloon, the panel's ground, letters reversed out -- is no ink at all, and
  knocks out what is under it;
- a grey is a K tint, `1 - L` for its OKLab lightness `L`, with no press curve; a mass dark
  enough to be near black prints rich black instead, C40 K100, for even coverage;
- a tinted palette prints its greys, the twins every colour was chosen against (#244).

Nothing is decided here that the SVG does not already show. A page unit prints as a tenth
of a millimetre. The fog veil, which only SVG's noise filter can draw, is left out, and
:func:`print_notes` says so.

Deterministic, like every other output: objects in a fixed order, nothing compressed (zlib
implementations differ from one platform to the next), no dates, and an `/ID` taken from
the content. No PDF/X conformance is claimed: that needs a preflight tool this project does
not run.
"""

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from scenet.core import Box, CoreImage, PageCore, PanelCore
from scenet.emit.geometry import PlacedRun
from scenet.emit.geometry import Pointer as PointerGeometry
from scenet.emit.marks import (
    Circle,
    Ellipse,
    Glyph,
    Line,
    Mark,
    Paint,
    Picture,
    Pointer,
    Polygon,
    Rect,
    Role,
    Segment,
    Shape,
    Text,
    Veil,
    marks,
)
from scenet.emit.pdf_fonts import WIDTH_PLACES, Part, pdf_font, refusal
from scenet.emit.pdf_fonts import width as advance_width
from scenet.emit.pdf_images import Embedded, embed
from scenet.emit.svg import GLYPH_SCALE_PLACES, fmt, typeface_of
from scenet.ir import Direction
from scenet.solve.text import FontMetrics

#: A page unit, printed: a tenth of a millimetre, in PDF points (72 to the inch).
POINTS_PER_UNIT = 72 / 254

#: Places for the scale from units to points. Two -- right for a coordinate -- would write
#: 0.28 and print every page 1.2% small.
SCALE_PLACES = 6

#: Places for an ink's percentage, as a fraction of 1.
INK_PLACES = 4

#: The rich black a large near-black area prints in: C40 K100, well within any printer's
#: ink limit. Small type stays 100% K, which a plate drifting out of register cannot blur.
RICH_BLACK = (0.4, 0.0, 0.0, 1.0)

#: How dark, in OKLab lightness, a mass must be to print rich black: the night foreground,
#: the darkest rung of the ladder (`solve/backdrop.py`).
RICH_BLACK_LIGHTNESS = 0.10

#: The resolution printers ask a picture to have at its printed size.
PRINT_DPI = 300

#: How round a quarter of a circle is, drawn as one cubic curve.
KAPPA = 4 * (math.sqrt(2) - 1) / 3

#: What a PDF reader is told made the file. No version: a release would change every byte.
PRODUCER = "Scenet"

INK = (0.0, 0.0, 0.0, 1.0)
NO_INK = (0.0, 0.0, 0.0, 0.0)

#: Places for where a line set as text starts, so its glyphs land on the outlines' origins.
TEXT_PLACES = 6

#: The faces a document's text is set in, by their resource name, each with every character
#: lettered in it: what goes into the file, once each.
Faces = dict[str, tuple[FontMetrics, set[str]]]


def lightness(colour: str) -> float:
    """OKLab lightness of an sRGB `#rrggbb` colour, grey or not.

    The solver's own `lightness` refuses anything with a hue, because every decision it
    takes is on a grey. Print has one fill that is not quite grey -- a figure's, `#e8e6e1`
    -- so the whole conversion is spelt out here.
    """
    red, green, blue = (_linear(int(colour[index : index + 2], 16) / 255) for index in (1, 3, 5))
    long = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    return (
        0.2104542553 * math.cbrt(long)
        + 0.7936177850 * math.cbrt(medium)
        - 0.0040720468 * math.cbrt(short)
    )


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def ink(paint: Paint) -> tuple[float, float, float, float]:
    """The CMYK a paint prints in, by what it is.

    Args:
        paint: A fill or a stroke.

    Returns:
        Cyan, magenta, yellow and black, each from 0 to 1.
    """
    if paint.role in {Role.INK, Role.SOLID}:
        return INK
    if paint.role is Role.PAPER:
        return NO_INK
    level = lightness(paint.grey)
    if paint.role is Role.MASS and level <= RICH_BLACK_LIGHTNESS:
        return RICH_BLACK
    return (0.0, 0.0, 0.0, min(1.0, max(0.0, 1.0 - level)))


def overprints(paint: Paint) -> bool:
    """Whether a paint prints over what is under it rather than knocking it out: ink does."""
    return paint.role is Role.INK


def printed_panels(
    pages: Sequence[PageCore], panels: Mapping[str, PanelCore]
) -> dict[str, PanelCore]:
    """The panels a print PDF draws: those on a page, or every panel when there are none.

    Args:
        pages: The document's pages.
        panels: Every panel's compiled Core, by name.

    Returns:
        The panels printed, in the order they are printed.
    """
    if not pages:
        return dict(panels)
    return {frame.panel: panels[frame.panel] for page in pages for frame in page.frames}


def print_notes(
    panels: Mapping[str, PanelCore],
    *,
    live_text: bool = False,
    fonts: Mapping[str, FontMetrics] | None = None,
) -> list[str]:
    """What print leaves out or changes, one sentence each, for the panels printed.

    Args:
        panels: The panels the PDF draws, by name.
        live_text: The PDF letters in text, so a face that may not be embedded is said.
        fonts: The declared fonts the panels were lettered in, by digest.

    Returns:
        The notes, in the panels' order.
    """
    notes: list[str] = []
    for name, core in panels.items():
        if live_text:
            for metrics in _faces_lettered(core, fonts):
                reason = refusal(metrics)
                if reason is not None:
                    notes.append(
                        f"the face {metrics.family} {metrics.style} in panel {name!r} is not "
                        f"embedded: {reason}; its lettering prints in outlines"
                    )
        air = core.backdrop.atmosphere if core.backdrop is not None else None
        if air is not None and air.veil is not None:
            notes.append(
                f"print leaves out the fog and cloud over panel {name!r}: only SVG can draw them"
            )
        if core.as_mono() != core:
            notes.append(f"panel {name!r} is tinted; print draws it in its greys")
        image = core.backdrop.image if core.backdrop is not None else None
        if image is not None:
            dpi = resolution(image)
            if dpi < PRINT_DPI:
                notes.append(
                    f"the picture {image.href!r} in panel {name!r} prints at {dpi} dpi at its "
                    f"size; printers ask for {PRINT_DPI}"
                )
    return notes


def resolution(image: CoreImage) -> int:
    """How many of a picture's pixels fall to the inch where it is printed, the lower way.

    A unit prints as a tenth of a millimetre, so an inch is 254 units.
    """
    across = image.pixels[0] * 254 / image.box.width
    down = image.pixels[1] * 254 / image.box.height
    return math.floor(min(across, down))


def render_pdf(
    pages: Sequence[PageCore],
    panels: Mapping[str, PanelCore],
    *,
    fonts: Mapping[str, FontMetrics] | None = None,
    images: Mapping[str, bytes] | None = None,
    live_text: bool = False,
) -> bytes:
    r"""Draw a document as a print PDF.

    One PDF page per page, its TrimBox the page; or, for a document with no pages, one per
    panel at its own size. Lettering is 100% K and overprints; see the module docstring
    for every other ink.

    Args:
        pages: The document's pages, in order -- empty for a document without any.
        panels: Every panel's compiled Core, by name.
        fonts: The declared fonts the panels were lettered in, by digest.
        images: The supplied pictures' bytes, by digest -- what
            :attr:`Book.images <scenet.pipeline.Book.images>` holds. A picture is always
            carried inside the PDF, pixels unchanged; see `scenet.emit.pdf_images`.
        live_text: Letter balloons and captions in text, their faces embedded, rather than
            in outlines (#284). Each glyph lands where its outline would; a face whose
            licence forbids embedding stays in outlines, as :func:`print_notes` says.

    Returns:
        The PDF's bytes.

    Raises:
        ValueError: A page places a panel that was not given, a Core names a font that was
            not, a picture's bytes were not handed over, or a picture is one no PDF reader
            decodes.

    Example:
        >>> from scenet import compile_book
        >>> from scenet.emit.pdf import render_pdf
        >>> book = compile_book("cast: {a: {reference: alice}}\npanels: {one: {}}")
        >>> cores = {name: result.core for name, result in book.panels.items()}
        >>> render_pdf(book.pages, cores)[:8]
        b'%PDF-1.6'
    """
    # Only what is printed is carried: a panel on no page brings no picture, in the order
    # the pages print them, so every caller -- the CLI hands over the printed panels, the
    # playground all of them -- writes the same file.
    drawn = (
        [panels[frame.panel] for page in pages for frame in page.frames if frame.panel in panels]
        if pages
        else list(panels.values())
    )
    pictures = {
        _picture_name(core.backdrop.image): core.backdrop.image
        for core in drawn
        if core.backdrop is not None and core.backdrop.image is not None
    }
    document = _Document(
        pictures={name: _embedded(image, images) for name, image in pictures.items()}
    )
    lettering = _Lettering(fonts, live_text, document.faces)
    if pages:
        for page in pages:
            document.add_page(
                page.width, page.height, _page_content(page, panels, lettering), bleed=page.bleed
            )
    else:
        for core in panels.values():
            document.add_page(core.width, core.height, _lone_content(core, lettering))
    # A page says which way it is read; without pages each PDF page is a panel, read the
    # way the panels are.
    rtl = (
        any(page.direction is Direction.RTL for page in pages)
        if pages
        else any(core.direction is Direction.RTL for core in panels.values())
    )
    return document.write(rtl=rtl)


def _picture_name(image: CoreImage) -> str:
    """A picture's resource name: from its bytes, so one drawn twice is carried once."""
    return f"Im{image.sha256[:16]}"


def _embedded(image: CoreImage, images: Mapping[str, bytes] | None) -> Embedded:
    data = (images or {}).get(image.sha256)
    if data is None:
        raise ValueError(
            f"the panel is drawn over {image.href!r} (sha256 {image.sha256[:12]}...), and those "
            "bytes were not handed over to print; pass Book.images"
        )
    return embed(data, image.media_type, image.href)


@dataclass(frozen=True, slots=True)
class _Lettering:
    """How a document is lettered.

    The fonts it names, whether in text or in outlines, and the faces its text has been set
    in so far.
    """

    fonts: Mapping[str, FontMetrics] | None
    live_text: bool
    faces: Faces


def _lone_content(core: PanelCore, lettering: _Lettering) -> list[str]:
    return ["q", *_clip(core), *_content(core, lettering), "Q"]


def _page_content(
    page: PageCore, panels: Mapping[str, PanelCore], lettering: _Lettering
) -> list[str]:
    """A page: its sheet, then every panel at its frame, in reading order.

    An inset read before its parent stays on top all the same, as on the SVG page: the
    parent is cut around the inset's clearance, its `exclusions`, and the clearance is
    painted white just before its inset.
    """
    lines = _painted(Mark("page", Rect(0.0, 0.0, page.width, page.height), fill=_WHITE))
    for frame in page.frames:
        core = panels.get(frame.panel)
        if core is None:
            raise ValueError(f"the page places panel '{frame.panel}', which was not given")
        if frame.clearance is not None:
            ring = frame.clearance
            lines += _painted(
                Mark("page", Rect(ring.x, ring.y, ring.width, ring.height), fill=_WHITE)
            )
        lines += ["q", f"1 0 0 1 {fmt(frame.x)} {fmt(frame.y)} cm", *_clip(core)]
        for hole in core.exclusions:
            lines.append(_hole(core, hole))
        lines += [*_content(core, lettering), "Q"]
    return lines


_WHITE = Paint("#ffffff", Role.PAPER, "#ffffff")


def _clip(core: PanelCore) -> list[str]:
    """Crop a panel to its frame: its rectangle, or the outline of a slanted one."""
    if core.outline is not None:
        return [_polygon(core.outline, closed=True), "W n"]
    return [f"0 0 {fmt(core.width)} {fmt(core.height)} re W n"]


def _hole(core: PanelCore, hole: Box) -> str:
    """Cut an inset's clearance out of the panel it is set into, by the even-odd rule."""
    return (
        f"0 0 {fmt(core.width)} {fmt(core.height)} re "
        f"{fmt(hole.x)} {fmt(hole.y)} {fmt(hole.width)} {fmt(hole.height)} re W* n"
    )


def panel_content(
    core: PanelCore, fonts: Mapping[str, FontMetrics] | None = None, *, live_text: bool = False
) -> list[str]:
    """A panel's marks as PDF content, one `q ... Q` block each, in painting order.

    The veil is left out: it is noise only SVG can draw.

    Args:
        core: The compiled panel.
        fonts: The declared fonts it was lettered in, by digest.
        live_text: Each line of a balloon or a caption set as text, one `BT ... ET` in its
            block, rather than in outlines.

    Returns:
        The content lines, in the panel's own units.

    Raises:
        ValueError: The panel is drawn over a supplied picture, or names a font not given.
    """
    return _content(core, _Lettering(fonts, live_text, {}))


def _content(core: PanelCore, lettering: _Lettering) -> list[str]:
    family = typeface_of(core, fonts=lettering.fonts)
    lines: list[str] = []
    for mark in marks(core, family, live_text=lettering.live_text):
        if mark.is_veil:
            continue
        if isinstance(mark.shape, Text):
            lines += _text(mark, mark.shape, lettering.faces)
        else:
            lines += _painted(mark)
    return lines


def _faces_lettered(core: PanelCore, fonts: Mapping[str, FontMetrics] | None) -> list[FontMetrics]:
    """The faces a panel's balloons and captions are lettered in, each once, in order."""
    faces: dict[str, FontMetrics] = {}
    for mark in marks(core, typeface_of(core, fonts=fonts), live_text=True):
        if isinstance(mark.shape, Text):
            for placed in mark.shape.runs:
                faces.setdefault(placed.metrics.sha256, placed.metrics)
    return list(faces.values())


def _text(mark: Mark, line: Text, faces: Faces) -> list[str]:
    """One line of lettering set as text, each run in its embedded face.

    Each run starts at its first glyph's origin, and every glyph after lands on the step the
    solver measured: the adjustment after a glyph is its width as the font's `W` array
    writes it, less that step, so a reader's arithmetic and the outlines' agree. A character
    the face lacks is stepped over, as its outline -- none -- is. A run in a face that may
    not be embedded is drawn in its outlines after the text, in the same ink.
    """
    set_as_text: list[str] = []
    outlined: list[str] = []
    for placed in line.runs:
        if refusal(placed.metrics) is not None:
            outlined += _outlined_run(placed, line.baseline)
            continue
        name = f"F{placed.metrics.sha256[:16]}"
        lettered = faces.setdefault(name, (placed.metrics, set()))[1]
        size = fmt(line.font_size, TEXT_PLACES)
        set_as_text += [
            f"/{name} 1 Tf",
            f"{size} 0 0 -{size} {fmt(placed.origins[0], TEXT_PLACES)} "
            f"{fmt(line.baseline, TEXT_PLACES)} Tm",
            f"[{_shown(placed, lettered)}] TJ",
        ]
    lines = ["q", *_state(mark.fill, None)]
    if set_as_text:
        lines += ["BT", *set_as_text, "ET"]
    return [*lines, *outlined, "Q"]


def _shown(placed: PlacedRun, lettered: set[str]) -> str:
    """A run as a `TJ` array: its glyphs by code, and between them what steps them."""
    metrics, text = placed.metrics, placed.run.text
    parts: list[str] = []
    codes: list[str] = []
    adjustment = 0.0
    last = len(text) - 1
    for index, character in enumerate(text):
        step = metrics.step(character, text[index + 1] if index < last else None) * 1000
        code = metrics.glyph_id(character)
        if code is None:
            adjustment -= step
            continue
        written = fmt(adjustment, WIDTH_PLACES)
        if written != "0":
            if codes:
                parts.append(f"<{''.join(codes)}>")
                codes = []
            parts.append(written)
        codes.append(f"{code:04X}")
        lettered.add(character)
        adjustment = float(fmt(advance_width(metrics, character), WIDTH_PLACES)) - step
    if codes:
        parts.append(f"<{''.join(codes)}>")
    return " ".join(parts)


def _outlined_run(placed: PlacedRun, baseline: float) -> list[str]:
    """A run in its glyphs' outlines, as print letters without live text."""
    lines: list[str] = []
    for character, origin in zip(placed.run.text, placed.origins, strict=True):
        path = placed.metrics.glyph_pdf_path(character)
        if path:
            glyph = Glyph(placed.metrics, character, origin, baseline, placed.scale)
            lines += ["q", *_glyph_transform(glyph), path, "f", "Q"]
    return lines


def _painted(mark: Mark) -> list[str]:
    """One mark, in a graphics state of its own."""
    if isinstance(mark.shape, Picture):
        # An image is drawn in the unit square, its first row at the top: mapped onto the
        # box Panel Core placed it in, which already has its proportions.
        box = mark.shape.image.box
        return [
            "q",
            f"{fmt(box.width)} 0 0 {fmt(-box.height)} {fmt(box.x)} {fmt(box.y + box.height)} cm",
            f"/{_picture_name(mark.shape.image)} Do",
            "Q",
        ]
    head = ["q"]
    if mark.stroke is not None:
        head.append(f"{fmt(mark.width)} w")
        head.append("1 J 1 j" if mark.rounded else "0 J 0 j")
        if mark.dash:
            head.append(f"[{' '.join(fmt(length) for length in mark.dash)}] 0 d")
    transform, path = _path(mark.shape)
    head += transform
    if mark.fill is not None and mark.stroke is not None and mark.stroke_first:
        return [
            *head,
            *_state(None, mark.stroke),
            path,
            "S",
            *_state(mark.fill, None),
            path,
            "f",
            "Q",
        ]
    operator = (
        "B" if mark.fill is not None and mark.stroke is not None else "f" if mark.fill else "S"
    )
    return [*head, *_state(mark.fill, mark.stroke), path, operator, "Q"]


def _state(fill: Paint | None, stroke: Paint | None) -> list[str]:
    """Inks, overprint and opacity for a fill, a stroke or both."""
    parts: list[str] = []
    opacity = 1.0
    if fill is not None:
        parts.append(f"{_cmyk(ink(fill))} k")
        opacity = fill.opacity
    if stroke is not None:
        parts.append(f"{_cmyk(ink(stroke))} K")
        opacity = stroke.opacity
    name = _GraphicsState(
        fill_overprint=fill is not None and overprints(fill),
        stroke_overprint=stroke is not None and overprints(stroke),
        opacity=opacity,
    ).name
    return [f"/{name} gs", *parts]


def _cmyk(values: tuple[float, float, float, float]) -> str:
    return " ".join(fmt(value, INK_PLACES) for value in values)


@dataclass(frozen=True, slots=True)
class _GraphicsState:
    """An ExtGState: overprint on fill and stroke apart, and opacity."""

    fill_overprint: bool
    stroke_overprint: bool
    opacity: float

    @property
    def name(self) -> str:
        """A name that says what it is, so the same state is always the same name."""
        return (
            f"GS{int(self.fill_overprint)}{int(self.stroke_overprint)}{round(self.opacity * 100)}"
        )

    def dictionary(self) -> str:
        """The ExtGState dictionary."""
        alpha = f" /ca {fmt(self.opacity)} /CA {fmt(self.opacity)}" if self.opacity < 1 else ""
        return (
            f"<< /Type /ExtGState /op {str(self.fill_overprint).lower()} "
            f"/OP {str(self.stroke_overprint).lower()} /OPM 1{alpha} >>"
        )

    @classmethod
    def parse(cls, name: str) -> "_GraphicsState":
        """The state a name stands for."""
        return cls(
            fill_overprint=name[2] == "1",
            stroke_overprint=name[3] == "1",
            opacity=int(name[4:]) / 100,
        )


def _path(shape: Shape) -> tuple[list[str], str]:  # noqa: PLR0911 -- one return per shape
    """A shape as a PDF path, with any transform it is drawn through."""
    if isinstance(shape, Rect):
        return [], _rect(shape)
    if isinstance(shape, Circle):
        return [], _ellipse(shape.cx, shape.cy, shape.r, shape.r)
    if isinstance(shape, Ellipse):
        return [], _ellipse(shape.cx, shape.cy, shape.rx, shape.ry)
    if isinstance(shape, Polygon):
        return [], _polygon(shape.points, closed=shape.closed)
    if isinstance(shape, Line | Segment):
        return [], _polygon((shape.start, shape.end), closed=False)
    if isinstance(shape, Pointer):
        return [], _pointer(shape.shape)
    if isinstance(shape, Glyph):
        return _glyph_transform(shape), shape.metrics.glyph_pdf_path(shape.char)
    if isinstance(shape, Veil):  # pragma: no cover - the veil is filtered out above
        return [], ""
    raise TypeError(f"no PDF path for {shape!r}")  # pragma: no cover


def _r(value: float) -> float:
    """A coordinate as the SVG writes it, so both formats draw from the same numbers."""
    return float(fmt(value))


def _xy(x: float, y: float) -> str:
    return f"{fmt(x)} {fmt(y)}"


def _polygon(points: Iterable[tuple[float, float]], *, closed: bool) -> str:
    pairs = list(points)
    path = [f"{_xy(*pairs[0])} m", *(f"{_xy(*pair)} l" for pair in pairs[1:])]
    if closed:
        path.append("h")
    return " ".join(path)


def _rect(rect: Rect) -> str:
    """A rectangle, its corners rounded as SVG rounds them.

    A rounded one starts where SVG's does, at `(x + r, y)`, and runs the same way round, so a
    whisper's dashes fall in the same places.
    """
    x, y, width, height = _r(rect.x), _r(rect.y), _r(rect.width), _r(rect.height)
    if rect.radius <= 0:
        return f"{fmt(x)} {fmt(y)} {fmt(width)} {fmt(height)} re"
    r = min(_r(rect.radius), width / 2, height / 2)
    k = r * KAPPA
    right, bottom = x + width, y + height
    return " ".join(
        [
            f"{_xy(x + r, y)} m",
            f"{_xy(right - r, y)} l",
            _curve((right - r + k, y), (right, y + r - k), (right, y + r)),
            f"{_xy(right, bottom - r)} l",
            _curve((right, bottom - r + k), (right - r + k, bottom), (right - r, bottom)),
            f"{_xy(x + r, bottom)} l",
            _curve((x + r - k, bottom), (x, bottom - r + k), (x, bottom - r)),
            f"{_xy(x, y + r)} l",
            _curve((x, y + r - k), (x + r - k, y), (x + r, y)),
            "h",
        ]
    )


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> str:
    """An ellipse in four quarter arcs, from its rightmost point, the way SVG draws one."""
    cx, cy, rx, ry = _r(cx), _r(cy), _r(rx), _r(ry)
    kx, ky = rx * KAPPA, ry * KAPPA
    return " ".join(
        [
            f"{_xy(cx + rx, cy)} m",
            _curve((cx + rx, cy + ky), (cx + kx, cy + ry), (cx, cy + ry)),
            _curve((cx - kx, cy + ry), (cx - rx, cy + ky), (cx - rx, cy)),
            _curve((cx - rx, cy - ky), (cx - kx, cy - ry), (cx, cy - ry)),
            _curve((cx + kx, cy - ry), (cx + rx, cy - ky), (cx + rx, cy)),
            "h",
        ]
    )


def _curve(
    first: tuple[float, float], second: tuple[float, float], end: tuple[float, float]
) -> str:
    return f"{_xy(*first)} {_xy(*second)} {_xy(*end)} c"


def _pointer(shape: PointerGeometry) -> str:
    """A tail. A curved one's two quadratic sides become the cubics PDF draws."""
    left = (_r(shape.left[0]), _r(shape.left[1]))
    tip = (_r(shape.tip[0]), _r(shape.tip[1]))
    right = (_r(shape.right[0]), _r(shape.right[1]))
    if shape.control is None:
        return f"{_xy(*left)} m {_xy(*tip)} l {_xy(*right)} l h"
    control = (_r(shape.control[0]), _r(shape.control[1]))
    return " ".join(
        [f"{_xy(*left)} m", _quadratic(left, control, tip), _quadratic(tip, control, right), "h"]
    )


def _quadratic(
    start: tuple[float, float], control: tuple[float, float], end: tuple[float, float]
) -> str:
    """A quadratic Bézier as the cubic that draws exactly the same curve."""
    first = (start[0] + 2 / 3 * (control[0] - start[0]), start[1] + 2 / 3 * (control[1] - start[1]))
    second = (end[0] + 2 / 3 * (control[0] - end[0]), end[1] + 2 / 3 * (control[1] - end[1]))
    return _curve(first, second, end)


def _glyph_transform(glyph: Glyph) -> list[str]:
    """Place a glyph as the SVG does: translate, turn, then scale and flip font units."""
    scale = fmt(glyph.scale, GLYPH_SCALE_PLACES)
    flipped = fmt(-glyph.scale, GLYPH_SCALE_PLACES)
    parts = [f"1 0 0 1 {fmt(glyph.x)} {fmt(glyph.y)} cm"]
    if glyph.angle:
        turn = math.radians(float(fmt(glyph.angle)))
        cos, sin = fmt(math.cos(turn), 6), fmt(math.sin(turn), 6)
        parts.append(f"{cos} {sin} {fmt(-math.sin(turn), 6)} {cos} 0 0 cm")
    parts.append(f"{scale} 0 0 {flipped} 0 0 cm")
    return parts


@dataclass
class _Document:
    """The objects of a PDF, written in a fixed order."""

    pages: list[tuple[float, float, float, list[str]]] = field(default_factory=list)
    pictures: dict[str, Embedded] = field(default_factory=dict)
    faces: Faces = field(default_factory=dict)

    def add_page(
        self, width: float, height: float, content: list[str], *, bleed: float = 0.0
    ) -> None:
        """A page trimmed to `width` by `height` units, with `bleed` around it."""
        self.pages.append((width, height, bleed, content))

    def write(self, *, rtl: bool) -> bytes:
        """The whole file.

        Catalog 1, pages 2, then each page and its content, then each picture and its soft
        mask, once however many pages draw it, then each face text is set in, five objects
        each (`scenet.emit.pdf_fonts`), then the document info.
        """
        count = len(self.pages)
        kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(count))
        reading = " /ViewerPreferences << /Direction /R2L >>" if rtl else ""
        objects = [
            f"<< /Type /Catalog /Pages 2 0 R{reading} >>".encode(),
            f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        ]
        numbers: dict[str, int] = {}
        pictures: list[bytes] = []
        next_number = 3 + 2 * count
        for name, picture in self.pictures.items():
            numbers[name] = next_number
            mask = ""
            if picture.mask is not None:
                mask = f" /SMask {next_number + 1} 0 R"
            pictures.append(_stream(picture.dictionary + mask, picture.data))
            next_number += 1
            if picture.mask is not None:
                pictures.append(_stream(*picture.mask))
                next_number += 1
        for name, (metrics, characters) in self.faces.items():
            numbers[name] = next_number
            pictures += [_part(part) for part in pdf_font(metrics, characters).objects(next_number)]
            next_number += 5

        scale = fmt(POINTS_PER_UNIT, SCALE_PLACES)
        for index, (width, height, bleed, content) in enumerate(self.pages):
            k = POINTS_PER_UNIT
            sheet = _box(0.0, 0.0, (width + 2 * bleed) * k, (height + 2 * bleed) * k)
            trim = _box(bleed * k, bleed * k, (width + bleed) * k, (height + bleed) * k)
            states = sorted({part.split()[0][1:] for part in content if part.endswith(" gs")})
            graphics = " ".join(
                f"/{name} {_GraphicsState.parse(name).dictionary()}" for name in states
            )
            drawn = sorted({part.split()[0][1:] for part in content if part.endswith(" Do")})
            images = " ".join(f"/{name} {numbers[name]} 0 R" for name in drawn)
            xobjects = f" /XObject << {images} >>" if drawn else ""
            named = sorted({part.split()[0][1:] for part in content if part.endswith(" Tf")})
            faces = " ".join(f"/{name} {numbers[name]} 0 R" for name in named)
            xobjects += f" /Font << {faces} >>" if named else ""
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox {sheet} /TrimBox {trim} "
                    f"/BleedBox {sheet} /Resources << /ExtGState << {graphics} >>{xobjects} >> "
                    f"/Contents {4 + 2 * index} 0 R >>"
                ).encode()
            )
            flip = f"{scale} 0 0 -{scale} {fmt(bleed * k, 4)} {fmt((height + bleed) * k, 4)} cm"
            objects.append(_stream("", "\n".join(["4 M", flip, *content, ""]).encode()))
        objects += pictures
        objects.append(f"<< /Producer ({PRODUCER}) >>".encode())

        output = bytearray(b"%PDF-1.6\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(output))
            output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
        identifier = hashlib.sha256(bytes(output)).hexdigest()[:32]
        xref = len(output)
        output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        for offset in offsets:
            output += f"{offset:010d} 00000 n \n".encode()
        output += (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {len(objects)} 0 R "
            f"/ID [<{identifier}> <{identifier}>] >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
        return bytes(output)


def _box(left: float, bottom: float, right: float, top: float) -> str:
    return f"[{fmt(left, 4)} {fmt(bottom, 4)} {fmt(right, 4)} {fmt(top, 4)}]"


def _part(part: Part) -> bytes:
    """An object a font is carried in: a dictionary, or a stream."""
    entries, data = part
    return _stream(entries, data) if data is not None else f"<< {entries} >>".encode()


def _stream(entries: str, data: bytes) -> bytes:
    """A stream object: its dictionary, its length, its bytes."""
    head = f"<< {entries} /Length {len(data)} >>" if entries else f"<< /Length {len(data)} >>"
    return head.encode() + b"\nstream\n" + data + b"\nendstream"
