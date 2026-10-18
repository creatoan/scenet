"""Panel Core into SVG.

Purely mechanical: every position here was decided by the solver. The emitter makes
no layout decisions, which is what keeps rendering swappable and golden tests
meaningful.

Numbers are formatted through one helper at fixed precision so that output is
byte-identical across platforms, whose float repr differs in the last digit.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from xml.sax.saxutils import escape, quoteattr

from scenet.core import (
    CoreActor,
    CoreAtmosphere,
    CoreBalloon,
    CoreCaption,
    CoreMass,
    CoreRun,
    CoreSfx,
    FaceDisc,
    FaceMark,
    PanelCore,
    Tail,
)
from scenet.ir import BalloonKind, Face
from scenet.solve.text import FontMetrics, Styled, Typeface

STROKE = "#111111"
FILL_FIGURE = "#e8e6e1"
FILL_BALLOON = "#ffffff"
FILL_PANEL = "#ffffff"

FIGURE_STROKE_WIDTH = 3.0
BALLOON_STROKE_WIDTH = 3.0

# Corner rounding of a speech balloon, as a fraction of its smaller side.
BALLOON_CORNER = 0.42

# Half-width of a tail where it meets the balloon, as a fraction of balloon height.
TAIL_BASE_FRACTION = 0.18

CAPTION_STROKE_WIDTH = 2.5

# Falling weather is drawn at less than full opacity so it reads as passing through the
# panel rather than as marks on top of it. *Which* tone it uses was chosen by the solver
# and travels in `CoreAtmosphere.fall_tone`.
WEATHER_OPACITY = 0.85


#: Decimal places for a glyph's scale. The scale is size/unitsPerEm, and a font's units are
#: a thousand or more to the em, so two places -- right for a coordinate -- wrote 0.035 as
#: 0.04 and drew every letter 14% larger than it was measured. Six keep the drawn size
#: within a millionth of an em of the measured one.
GLYPH_SCALE_PLACES = 6

#: How a run in another face than its line's is marked in live text. A `<tspan>` only
#: where the face changes, so a line without emphasis is exactly the `<text>` it was.
FACE_ATTRIBUTES: dict[Face, str] = {
    Face.REGULAR: ' font-style="normal"',
    Face.ITALIC: ' font-style="italic"',
    Face.BOLD_ITALIC: ' font-weight="bold" font-style="italic"',
}


def fmt(value: float, places: int = 2) -> str:
    """Format a number for SVG output.

    Trailing zeros are stripped so `100.00` prints as `100`, which keeps files small
    and diffs readable without making them any less exact.

    Two places is a hundredth of a panel unit, which is exact for a coordinate. It is
    not for a factor: a glyph's scale multiplies a thousand font units, so it takes
    `places=6`.
    """
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _points(pairs: list[tuple[float, float]]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in pairs)


def render(
    core: PanelCore,
    *,
    metrics: FontMetrics | None = None,
    fonts: Mapping[str, FontMetrics] | None = None,
    live_text: bool = False,
    id_prefix: str = "",
    aria: bool = True,
) -> str:
    """Render a compiled panel as a standalone SVG document.

    Args:
        core: The compiled panel.
        metrics: The regular face the lettering was measured in, in place of the
            shipped one, for a Core compiled with the same `metrics`.
        fonts: The declared fonts the lettering was measured in, by digest -- what
            :attr:`CompileResult.fonts <scenet.pipeline.CompileResult.fonts>` holds. Each
            face :attr:`PanelCore.fonts <scenet.core.PanelCore.fonts>` names must be here.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        id_prefix: Put in front of every `id` the panel writes, and every reference to
            one. Nothing a single panel needs; it is what lets a strip hold several
            panels in one document, where ids must be unique. Empty by default, so a
            panel on its own is byte-identical to what it always was.
        aria: Make the panel one image a screen reader can read, named with what it shows
            and then everything said in it, in reading order -- see
            :func:`accessible_name`. `False` writes none of it, for anyone who
            post-processes the SVG: exactly what was written before it existed.

    Raises:
        ValueError: The Core names a font that was not handed over. Drawing its lettering
            in another face would draw text that does not fit the balloons around it.
    """
    family = typeface_of(core, metrics=metrics, fonts=fonts)
    named, names = accessible_name(core, id_prefix) if aria else ("", [])
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(core.width)}" '
        f'height="{fmt(core.height)}" viewBox="0 0 {fmt(core.width)} {fmt(core.height)}"'
        f"{named}>",
        *names,
        *panel_body(core, family, live_text=live_text, id_prefix=id_prefix),
        "</svg>",
    ]
    return "\n".join(lines) + "\n"


def accessible_name(core: PanelCore, id_prefix: str = "") -> tuple[str, list[str]]:
    """What makes a panel one image a screen reader can read: its attributes and children.

    The panel is `role="img"`, named through `aria-labelledby` by a `<title>` -- its
    description -- and a `<desc>` -- every balloon, caption and sound effect's label, in
    `order`. Both go in the *name*, which is announced, rather than the description, which
    often is not (NVDA, JAWS). An image's children are presentational, so nothing inside
    it is named, and the order is this one sequence whatever order things are painted in.

    The ids are a hash of the text they name. A page holding several inlined SVGs -- the
    VS Code preview, a web comic -- finds the first element with an id, so two panels that
    share one must share its text. With no words, the title alone names the panel, and no
    `aria-labelledby` is written: with no `<desc>` beside it, Blink would also read the
    title as the description. With neither, nothing is written; an image with no name is
    worse than none. Every word was resolved in the pipeline; this only copies.

    Args:
        core: The compiled panel.
        id_prefix: Put in front of each id, as in :func:`render`.

    Returns:
        The attributes for the panel's root or group, with a leading space, and the lines
        to write as its first children.
    """
    title = core.description
    lettered = sorted([*core.balloons, *core.captions, *core.sfx], key=lambda item: item.order)
    words = " ".join(item.label for item in lettered if item.label)
    if not words:
        if title is None:
            return "", []
        return ' role="img"', [f"  <title>{escape(title)}</title>"]
    key = hashlib.sha256(f"{title or ''}\0{words}".encode()).hexdigest()[:12]
    base = f"{id_prefix}scenet-{key}"
    named: list[str] = []
    lines: list[str] = []
    if title is not None:
        named.append(f"{base}-title")
        lines.append(f"  <title id={attr(named[-1])}>{escape(title)}</title>")
    named.append(f"{base}-desc")
    lines.append(f"  <desc id={attr(named[-1])}>{escape(words)}</desc>")
    return f' role="img" aria-labelledby={attr(" ".join(named))}', lines


def panel_body(
    core: PanelCore, family: Typeface, *, live_text: bool = False, id_prefix: str = ""
) -> list[str]:
    """A panel's contents, without the document around them: what a strip or page places.

    Args:
        core: The compiled panel.
        family: The faces its lettering was measured in, from :func:`typeface_of`.
        live_text: Emit lettering as `<text>` rather than glyph outlines.
        id_prefix: Put in front of every `id` the panel writes, and every reference to one.

    Returns:
        The lines between the root's opening tag and its closing one, none of them empty.
    """
    backdrop = core.backdrop
    air = backdrop.atmosphere if backdrop is not None else None

    parts: list[str] = []
    if air is not None:
        parts.append(_atmosphere_filter(air, id_prefix))
    # A panel that is not a rectangle -- one in a slanted tier -- is drawn whole and
    # cropped to its outline, the way the margin crops a rectangle. A rectangle gets no
    # wrapper at all, so it stays byte-identical to what it always was.
    outline = _points(list(core.outline)) if core.outline is not None else None
    if outline is not None:
        parts.append(
            f'  <clipPath id="{id_prefix}outline"><polygon points="{outline}"/></clipPath>'
        )
        parts.append(f'  <g clip-path="url(#{id_prefix}outline)">')
    parts.append(
        f'  <rect x="0" y="0" width="{fmt(core.width)}" height="{fmt(core.height)}" '
        f'fill="{FILL_PANEL}"/>'
    )

    # Masses and actors share one painter's order, which is the whole point of `plane`
    # mapping onto `depth`: a far mass, the cast, and a foreground mass fall into place
    # in a single sort with no layering code of their own. Ties break on id, exactly as
    # they did when actors sorted alone.
    drawn: list[tuple[int, str, str]] = [
        (actor.depth, actor.id, _render_actor(actor, id_prefix)) for actor in core.actors
    ]
    if backdrop is not None:
        drawn += [(mass.depth, mass.id, _render_mass(mass, id_prefix)) for mass in backdrop.masses]
    drawn.sort(key=lambda item: (item[0], item[1]))

    parts.extend(body for depth, _, body in drawn if depth < 0)

    # The veil sits over the backdrop and under the cast. Fog between the reader and the
    # figures would be the more literal reading and would bury them; comics put it behind.
    if air is not None:
        parts.append(_render_veil(core, air, id_prefix))

    parts.append(f'  <g stroke="{STROKE}" stroke-linecap="round" stroke-linejoin="round">')
    parts.extend(body for depth, _, body in drawn if depth >= 0)

    # Balloons and captions sit above the figures and share one reading order, so they
    # are emitted as one sequence rather than one layer stacked on the other.
    # Sound effects are part of the picture: over the figures, under every balloon and
    # caption, which were placed knowing where they are and paid to cover them.
    if core.sfx:
        display = family.face(Face.DISPLAY)
        parts.extend(_render_sfx(effect, display, id_prefix) for effect in core.sfx)

    lettering = sorted([*core.balloons, *core.captions], key=lambda item: item.order)
    for item in lettering:
        if isinstance(item, CoreCaption):
            parts.append(_render_caption(item, family, live_text=live_text, id_prefix=id_prefix))
        else:
            parts.append(_render_balloon(item, family, live_text=live_text, id_prefix=id_prefix))

    parts.append("  </g>")

    # Falling weather goes over everything but the frame. It is between the reader and
    # the panel rather than inside it, which is why it crosses the figures.
    if air is not None:
        parts.append(_render_falling(air, id_prefix))

    if outline is not None:
        parts.append("  </g>")
        parts.append(
            f'  <polygon points="{outline}" fill="none" stroke="{STROKE}" stroke-width="6"/>'
        )
    else:
        parts.append(
            f'  <rect x="0" y="0" width="{fmt(core.width)}" height="{fmt(core.height)}" '
            f'fill="none" stroke="{STROKE}" stroke-width="6"/>'
        )
    return [part for part in parts if part]


def _render_mass(mass: CoreMass, id_prefix: str) -> str:
    """One tonal mass: a flat fill, and nothing else.

    No outline, deliberately. A stroked mass reads as a drawn object, and the argument
    for masses in the first place is that a backdrop is read from the arrangement of
    values rather than from drawn detail.
    """
    return (
        f"    <polygon id={attr(id_prefix + 'mass-' + mass.id)} "
        f'points="{_points(list(mass.polygon))}" fill="{mass.tone}" stroke="none"/>'
    )


def _filter_id(atmosphere: CoreAtmosphere, id_prefix: str) -> str:
    """An id for the turbulence filter.

    The seed alone does not make it unique in a strip: two panels with the same setting
    share a seed, and so used to define one filter twice. The prefix does.
    """
    veil = atmosphere.veil
    return f"{id_prefix}scenet-veil-{0 if veil is None else veil.seed}"


def _atmosphere_filter(atmosphere: CoreAtmosphere, id_prefix: str) -> str:
    """The `feTurbulence` filter, written out from parameters the solver resolved.

    Perlin noise is built into SVG and the specification includes reference code, so a
    fixed seed is reproducible **by definition**: the emitted text is byte-identical.
    Browsers agree only approximately on what to paint from it, and that is fine -- the
    determinism contract is on the SVG text and has never been on pixels. See
    `docs/reference/language.md`.

    The colour matrix flattens the noise to one tone and takes the alpha from it, so the
    veil is a cloud of the atmosphere colour rather than coloured static.
    """
    veil = atmosphere.veil
    if veil is None:
        return ""
    red, green, blue = _channels(veil.tone)
    matrix = (
        f"0 0 0 0 {fmt(red)} 0 0 0 0 {fmt(green)} 0 0 0 0 {fmt(blue)} "
        f"{fmt(veil.opacity)} {fmt(veil.opacity / 2)} 0 0 0"
    )
    return (
        f"  <filter id={attr(_filter_id(atmosphere, id_prefix))} "
        'x="0%" y="0%" width="100%" height="100%" color-interpolation-filters="sRGB">\n'
        f'    <feTurbulence type="fractalNoise" baseFrequency="{veil.frequency}" '
        f'numOctaves="{veil.octaves}" seed="{veil.seed}" result="noise"/>\n'
        f'    <feColorMatrix in="noise" type="matrix" values="{matrix}"/>\n'
        "  </filter>"
    )


def _channels(tone: str) -> tuple[float, float, float]:
    """A `#rrggbb` tone as the three `0 .. 1` values a colour matrix wants.

    Format conversion rather than a decision: the tone itself was chosen by the solver.
    """
    red, green, blue = (int(tone[index : index + 2], 16) / 255.0 for index in (1, 3, 5))
    return red, green, blue


def _render_veil(core: PanelCore, atmosphere: CoreAtmosphere, id_prefix: str) -> str:
    """The rectangle the turbulence filter is painted through."""
    if atmosphere.veil is None:
        return ""
    return (
        f'  <rect x="0" y="0" width="{fmt(core.width)}" height="{fmt(core.height)}" '
        f'fill="{atmosphere.veil.tone}" filter="url(#{_filter_id(atmosphere, id_prefix)})"/>'
    )


def _render_falling(atmosphere: CoreAtmosphere, id_prefix: str) -> str:
    """Rain or snow, every mark of which was resolved during compilation."""
    if not atmosphere.streaks and not atmosphere.flecks:
        return ""
    marks = [
        f"  <g id={attr(id_prefix + 'weather')} "
        f'fill="{atmosphere.fall_tone}" stroke="{atmosphere.fall_tone}" '
        f'fill-opacity="{fmt(WEATHER_OPACITY)}" stroke-opacity="{fmt(WEATHER_OPACITY)}">'
    ]
    for streak in atmosphere.streaks:
        (x1, y1), (x2, y2) = streak.start, streak.end
        marks.append(
            f'    <line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
            f'stroke-width="{fmt(atmosphere.streak_width)}" stroke-linecap="round"/>'
        )
    for fleck in atmosphere.flecks:
        marks.append(
            f'    <circle cx="{fmt(fleck.cx)}" cy="{fmt(fleck.cy)}" r="{fmt(fleck.r)}" '
            'stroke="none"/>'
        )
    marks.append("  </g>")
    return "\n".join(marks)


def attr(value: str) -> str:
    r"""Quote a string for use as an XML attribute value, delimiters included.

    Returns the value *with* its surrounding quotes, because choosing the quote
    character is part of escaping correctly -- `quoteattr` picks whichever one avoids
    the most escaping.

    This exists because `xml.sax.saxutils.escape` does **not** escape quotation marks.
    That is fine for element content and wrong for an attribute: identifiers here come
    from user documents -- a cast key, a panel name -- and one containing a double quote
    would close the attribute early and let the rest of it be read as markup. The output
    is injected with `innerHTML` by the browser playground, so that is a scripting
    vector, not merely malformed XML.

    Args:
        value: Any string, trusted or not.

    Returns:
        The value, escaped and wrapped in quotes.

    Example:
        >>> from scenet.emit.svg import attr
        >>> attr("alice")
        '"alice"'
        >>> attr('a" onload=x')
        '\'a" onload=x\''
    """
    return quoteattr(value)


def _render_actor(actor: CoreActor, id_prefix: str) -> str:
    lines = [
        f'    <g id={attr(id_prefix + "actor-" + actor.id)} fill="{FILL_FIGURE}" '
        f'stroke-width="{fmt(FIGURE_STROKE_WIDTH)}">'
    ]

    # Limbs are drawn as thick round-capped strokes rather than outlined capsules:
    # one path element each instead of a constructed outline, and the joins between
    # segments merge cleanly.
    for capsule in actor.capsules:
        (x1, y1), (x2, y2) = capsule.start, capsule.end
        lines.append(
            f'      <path d="M{fmt(x1)} {fmt(y1)} L{fmt(x2)} {fmt(y2)}" '
            f'fill="none" stroke="{STROKE}" stroke-width="{fmt(capsule.width)}"/>'
        )
        lines.append(
            f'      <path d="M{fmt(x1)} {fmt(y1)} L{fmt(x2)} {fmt(y2)}" '
            f'fill="none" stroke="{FILL_FIGURE}" '
            f'stroke-width="{fmt(max(capsule.width - 2 * FIGURE_STROKE_WIDTH, 1.0))}"/>'
        )

    for blob in actor.blobs:
        cx, cy = blob.centre
        lines.append(
            f'      <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(blob.radius)}" '
            f'fill="{FILL_FIGURE}" stroke="{STROKE}" stroke-width="{fmt(FIGURE_STROKE_WIDTH)}"/>'
        )

    # The face goes on last, over the head blob it sits inside. Every coordinate here
    # was decided during compilation, curves included -- there is nothing to draw but
    # the polylines and discs as given.
    lines.extend(_render_mark(f"{id_prefix}face-{actor.id}", mark) for mark in actor.face_marks)

    # Emanata last of all, inside the actor's group so that whoever stands in front of
    # this character stands in front of their sweat too.
    lines.extend(_render_mark(f"{id_prefix}emanata-{actor.id}", mark) for mark in actor.emanata)

    lines.append("    </g>")
    return "\n".join(lines)


def _render_mark(prefix: str, mark: FaceMark) -> str:
    """One mark of a drawn face, or of the emanata around it.

    Ids carry the actor, because two characters in one panel have the same features
    and duplicate ids in one SVG document are malformed. They carry what the mark
    belongs to as well, so a face's marks and its emanata can never collide either.
    """
    element_id = f"{prefix}-{mark.id}"
    if isinstance(mark, FaceDisc):
        cx, cy = mark.centre
        fill = STROKE if mark.filled else FILL_BALLOON
        stroke = "none" if mark.filled else STROKE
        return (
            f'      <circle id={attr(element_id)} cx="{fmt(cx)}" cy="{fmt(cy)}" '
            f'r="{fmt(mark.radius)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{fmt(mark.width)}"/>'
        )
    element = "polygon" if mark.closed else "polyline"
    return (
        f"      <{element} id={attr(element_id)} "
        f'points="{_points(list(mark.points))}" fill="none" stroke="{STROKE}" '
        f'stroke-width="{fmt(mark.width)}"/>'
    )


def typeface_of(
    core: PanelCore,
    *,
    metrics: FontMetrics | None = None,
    fonts: Mapping[str, FontMetrics] | None = None,
) -> Typeface:
    """The family a Core's lettering was measured in, from the fonts handed over.

    Args:
        core: The compiled panel.
        metrics: A regular face given by hand, as it was given to the compile.
        fonts: Declared fonts by digest.

    Returns:
        The shipped family, with each face the Core names in its declared font.

    Raises:
        ValueError: A face the Core names is in none of the fonts given.
    """
    family = Typeface(regular=metrics)
    available = dict(fonts or {})
    if metrics is not None:
        available.setdefault(metrics.sha256, metrics)
    for face, font in core.fonts.items():
        found = available.get(font.sha256)
        if found is None:
            raise ValueError(
                f"this panel was lettered in {font.family} {font.style} (sha256 "
                f"{font.sha256[:12]}), and that font was not given to the renderer; pass "
                "the fonts its compile returned as `fonts=`"
            )
        family = replace(family, **{face.value: found})
    return family


def _render_sfx(effect: CoreSfx, metrics: FontMetrics, id_prefix: str) -> str:
    """A sound effect: each letter's outline, where the solver put it and turned it.

    One path per letter, its outline stroked behind its fill with `paint-order`, so a
    solid effect is ink with a paper halo and a hollow one is the outline alone. The
    stroke is in the glyph's own font units, since the path is scaled down to the type
    size. Nothing is decided here: the origin, the angle and both colours are the Core's.
    """
    scale = effect.font_size / metrics.units_per_em
    stroke = fmt(effect.stroke_width / scale)
    outlines: dict[str, str] = {}
    lines = [f"    <g id={attr(id_prefix + 'sfx-' + effect.id)}>"]
    for glyph in effect.glyphs:
        if glyph.char not in outlines:
            outlines[glyph.char] = metrics.glyph_outlines(glyph.char)[0][0]
        path = outlines[glyph.char]
        if not path:
            continue
        x, y = glyph.origin
        turn = f" rotate({fmt(glyph.angle)})" if glyph.angle else ""
        lines.append(
            f'      <path d="{path}" fill="{effect.fill}" stroke="{effect.stroke}" '
            f'stroke-width="{stroke}" stroke-linejoin="round" paint-order="stroke" '
            f'transform="translate({fmt(x)} {fmt(y)}){turn} '
            f'scale({fmt(scale, GLYPH_SCALE_PLACES)} {fmt(-scale, GLYPH_SCALE_PLACES)})"/>'
        )
    lines.append("    </g>")
    return "\n".join(lines)


def _runs_of(
    lines: tuple[str, ...], runs: tuple[tuple[CoreRun, ...], ...], index: int, base: Face
) -> tuple[CoreRun, ...]:
    """One line's runs: as recorded when it has emphasis, the whole line in `base` if not."""
    return runs[index] if runs else (CoreRun(text=lines[index], face=base),)


def _width(runs: Sequence[CoreRun], font_size: float, family: Typeface) -> float:
    """A line's width, measured exactly as the solver measured it."""
    line = Styled("", ())
    for run in runs:
        line += Styled.of(run.text, run.face)
    return family.measure(line, font_size)


def _render_balloon(
    balloon: CoreBalloon, family: Typeface, *, live_text: bool, id_prefix: str
) -> str:
    box = balloon.box
    lines = [f"    <g id={attr(id_prefix + 'balloon-' + balloon.id)}>"]

    lines.append(_tail_shape(balloon))
    lines.append(_balloon_outline(balloon))

    # Text is laid out from the top of the box: padding, then one line height per
    # line, landing each baseline where the solver's measurement assumed it.
    padding = (box.height - len(balloon.lines) * balloon.line_height) / 2
    ascent = balloon.font_size * 0.74
    for index in range(len(balloon.lines)):
        runs = _runs_of(balloon.lines, balloon.runs, index, Face.REGULAR)
        baseline = box.y + padding + index * balloon.line_height + ascent
        width = _width(runs, balloon.font_size, family)
        start_x = box.x + (box.width - width) / 2
        lines.append(
            _live_text(runs, start_x, baseline, balloon.font_size, family, base=Face.REGULAR)
            if live_text
            else _outlined_text(runs, start_x, baseline, balloon.font_size, family)
        )

    lines.append("    </g>")
    return "\n".join(lines)


def _render_caption(
    caption: CoreCaption, family: Typeface, *, live_text: bool, id_prefix: str
) -> str:
    """A caption box: a plain rectangle with its text set flush left.

    Square corners, because a caption is a box and not a balloon -- rounding it would
    read as a speech balloon that had lost its tail.

    Left alignment is a **convention**, not a rule the way reading order is. Multiple
    lettering references describe it as the norm while calling it a house preference,
    so it is implemented as the default and recorded as a choice. It is also the one
    place captions deliberately differ from balloons, which centre their text.
    """
    box = caption.box
    lines = [f"    <g id={attr(id_prefix + 'caption-' + caption.id)}>"]
    lines.append(
        f'      <rect x="{fmt(box.x)}" y="{fmt(box.y)}" width="{fmt(box.width)}" '
        f'height="{fmt(box.height)}" fill="{caption.fill}" stroke="{STROKE}" '
        f'stroke-width="{fmt(CAPTION_STROKE_WIDTH)}"/>'
    )

    # Padding is derived from the box the solver produced rather than restated as a
    # constant here, so the emitter cannot drift out of agreement with it. The box was
    # padded equally on both axes, so the vertical inset gives the horizontal one too.
    padding = (box.height - len(caption.lines) * caption.line_height) / 2
    ascent = caption.font_size * 0.74
    base = Face.ITALIC if caption.italic else Face.REGULAR
    for index in range(len(caption.lines)):
        runs = _runs_of(caption.lines, caption.runs, index, base)
        baseline = box.y + padding + index * caption.line_height + ascent
        lines.append(
            _live_text(
                runs,
                box.x + padding,
                baseline,
                caption.font_size,
                family,
                base=base,
                ink=caption.ink,
            )
            if live_text
            else _outlined_text(
                runs, box.x + padding, baseline, caption.font_size, family, ink=caption.ink
            )
        )

    lines.append("    </g>")
    return "\n".join(lines)


def _balloon_outline(balloon: CoreBalloon) -> str:
    box = balloon.box
    dash = ' stroke-dasharray="12 9"' if balloon.kind is BalloonKind.WHISPER else ""

    if balloon.kind is BalloonKind.SHOUT:
        return (
            f'      <polygon points="{_points(_burst(balloon))}" fill="{FILL_BALLOON}" '
            f'stroke="{STROKE}" stroke-width="{fmt(BALLOON_STROKE_WIDTH)}"/>'
        )
    if balloon.kind is BalloonKind.THOUGHT:
        return (
            f'      <ellipse cx="{fmt(box.x + box.width / 2)}" '
            f'cy="{fmt(box.y + box.height / 2)}" rx="{fmt(box.width / 2)}" '
            f'ry="{fmt(box.height / 2)}" fill="{FILL_BALLOON}" stroke="{STROKE}" '
            f'stroke-width="{fmt(BALLOON_STROKE_WIDTH)}"/>'
        )

    radius = min(box.width, box.height) * BALLOON_CORNER
    return (
        f'      <rect x="{fmt(box.x)}" y="{fmt(box.y)}" width="{fmt(box.width)}" '
        f'height="{fmt(box.height)}" rx="{fmt(radius)}" ry="{fmt(radius)}" '
        f'fill="{FILL_BALLOON}" stroke="{STROKE}" '
        f'stroke-width="{fmt(BALLOON_STROKE_WIDTH)}"{dash}/>'
    )


def _burst(balloon: CoreBalloon) -> list[tuple[float, float]]:
    """A spiky outline for a shout.

    Spike count follows the balloon's perimeter so a long balloon does not end up with
    a handful of enormous points.
    """
    box = balloon.box
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    rx, ry = box.width / 2, box.height / 2
    spikes = max(10, int((box.width + box.height) / 26) * 2)
    points: list[tuple[float, float]] = []
    for index in range(spikes * 2):
        angle = math.pi * index / spikes
        reach = 1.22 if index % 2 == 0 else 0.94
        points.append((cx + math.cos(angle) * rx * reach, cy + math.sin(angle) * ry * reach))
    return points


def _tail_shape(balloon: CoreBalloon) -> str:
    """The pointer from balloon to mouth.

    A thought balloon gets a trail of shrinking circles instead of a triangle, which
    is the established convention and reads instantly.
    """
    tail: Tail = balloon.tail
    (sx, sy), (ex, ey) = tail.start, tail.end

    if balloon.kind is BalloonKind.THOUGHT:
        bubbles: list[str] = []
        for index, t in enumerate((0.35, 0.62, 0.85)):
            x = sx + (ex - sx) * t
            y = sy + (ey - sy) * t
            radius = balloon.font_size * (0.34 - index * 0.09)
            bubbles.append(
                f'      <circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(radius)}" '
                f'fill="{FILL_BALLOON}" stroke="{STROKE}" '
                f'stroke-width="{fmt(BALLOON_STROKE_WIDTH)}"/>'
            )
        return "\n".join(bubbles)

    # A tapered triangle: wide where it leaves the balloon, a point at the mouth.
    base = max(balloon.box.height * TAIL_BASE_FRACTION, balloon.font_size * 0.35)
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * base / 2, dx / length * base / 2

    if tail.control is not None:
        cx, cy = tail.control
        path = (
            f"M{fmt(sx + nx)} {fmt(sy + ny)} "
            f"Q{fmt(cx)} {fmt(cy)} {fmt(ex)} {fmt(ey)} "
            f"Q{fmt(cx)} {fmt(cy)} {fmt(sx - nx)} {fmt(sy - ny)} Z"
        )
    else:
        path = (
            f"M{fmt(sx + nx)} {fmt(sy + ny)} L{fmt(ex)} {fmt(ey)} L{fmt(sx - nx)} {fmt(sy - ny)} Z"
        )
    return (
        f'      <path d="{path}" fill="{FILL_BALLOON}" stroke="{STROKE}" '
        f'stroke-width="{fmt(BALLOON_STROKE_WIDTH)}"/>'
    )


def _outlined_text(
    runs: Sequence[CoreRun],
    x: float,
    baseline: float,
    font_size: float,
    family: Typeface,
    *,
    ink: str = STROKE,
) -> str:
    """One line of lettering as glyph outlines, each run drawn from its own face.

    Glyph coordinates are y-up in font units, so each is scaled by size/unitsPerEm and
    flipped. The result depends on no font being installed anywhere.

    `ink` defaults to the stroke colour, which is what every balloon uses. A caption
    passes the value its tone resolved to, so a dark box gets reversed type -- and the
    choice was still the solver's, not this function's.
    """
    cursor = x
    glyphs: list[str] = []
    for run in runs:
        metrics: FontMetrics = family.face(run.face)
        scale = font_size / metrics.units_per_em
        for path, advance in metrics.glyph_outlines(run.text):
            if path:
                glyphs.append(
                    f'      <path d="{path}" fill="{ink}" stroke="none" '
                    f'transform="translate({fmt(cursor)} {fmt(baseline)}) '
                    f"scale({fmt(scale, GLYPH_SCALE_PLACES)} "
                    f'{fmt(-scale, GLYPH_SCALE_PLACES)})"/>'
                )
            cursor += advance * font_size
    return "\n".join(glyphs)


def _live_text(
    runs: Sequence[CoreRun],
    x: float,
    baseline: float,
    font_size: float,
    family: Typeface,
    *,
    base: Face,
    ink: str = STROKE,
) -> str:
    """One line of lettering as a real `<text>` element.

    Selectable and editable, at the cost of depending on the reader having a
    metrically compatible font. Offered as an option, never the default. A run in
    another face than the line's -- emphasis -- is a `<tspan>` saying which.

    The family named is the one measured, from the font's own `name` table: the shipped
    Source Sans Pro, or the author's. Quoted as any attribute is, since a font is as
    untrusted as the document that named it.
    """
    style = ' font-style="italic"' if base is Face.ITALIC else ""
    named = family.face(base).family
    content = "".join(
        escape(run.text)
        if run.face is base
        else f"<tspan{_run_attributes(run.face, named, family)}>{escape(run.text)}</tspan>"
        for run in runs
    )
    return (
        f'      <text x="{fmt(x)}" y="{fmt(baseline)}" font-size="{fmt(font_size)}" '
        f'font-family={attr(named + ", sans-serif")}{style} fill="{ink}" '
        f'stroke="none">{content}</text>'
    )


def _run_attributes(face: Face, named: str, family: Typeface) -> str:
    """What a `<tspan>` says about its face: style and weight, and a family when it differs."""
    attributes = FACE_ATTRIBUTES[face]
    own = family.face(face).family
    if own != named:
        attributes += f" font-family={attr(own + ', sans-serif')}"
    return attributes
