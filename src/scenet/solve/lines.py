"""Where the letters of a balloon or a caption sit, worked out once, for Panel Core to record.

A line of lettering was laid out twice: once by the solver, measuring it to size the box, and
again by every emitter, walking a cursor along it with the font's kerning to find where each
letter went. The second walk was a layout decision made where none belongs, and it ran
against whatever build of the font reader the renderer had. This is the one walk. Its answer
is written into Panel Core as :class:`CoreLine <scenet.core.CoreLine>`, and an emitter only
looks outlines up and puts them there.

Everything here is computed from the Core's own rounded numbers -- the box, the type size and
the line height as a reader of the Core has them -- so that what a Core says is what a reader
could check it against.
"""

from collections.abc import Sequence

from scenet.core import Box, CoreLine, CoreRun
from scenet.geom import rounded
from scenet.ir import Face
from scenet.solve.text import Styled, Typeface

#: How far below the top of a line its baseline sits, as a fraction of the type size.
ASCENT = 0.74


def runs_of(
    lines: Sequence[str], runs: Sequence[Sequence[CoreRun]], index: int, base: Face
) -> tuple[CoreRun, ...]:
    """One line's runs: as recorded when it has emphasis, the whole line in `base` if not."""
    return tuple(runs[index]) if runs else (CoreRun(text=lines[index], face=base),)


def set_lines(
    box: Box,
    lines: Sequence[str],
    runs: Sequence[Sequence[CoreRun]],
    *,
    font_size: float,
    line_height: float,
    base: Face,
    centred: bool,
    family: Typeface,
) -> tuple[CoreLine, ...]:
    """Where each line of a box's lettering sits, and each of its letters.

    Text is laid out from the top of the box: padding, then one line height per line, each
    baseline where the solver's measurement assumed it. The padding is derived from the box,
    so it cannot drift from what sized the box. A balloon centres each line; a caption sets
    them flush left, inside that same padding.

    Args:
        box: The box, as Panel Core records it.
        lines: The resolved lines.
        runs: Their runs, or none when no line has emphasis.
        font_size: The type size, as Panel Core records it.
        line_height: The baseline-to-baseline distance, as Panel Core records it.
        base: The face a line without emphasis is set in.
        centred: Whether each line is centred in the box.
        family: The faces the lettering is measured in.

    Returns:
        One :class:`CoreLine <scenet.core.CoreLine>` for each line, every number rounded.
    """
    padding = (box.height - len(lines) * line_height) / 2
    ascent = font_size * ASCENT
    placed: list[CoreLine] = []
    for index in range(len(lines)):
        baseline = box.y + padding + index * line_height + ascent
        cut = runs_of(lines, runs, index, base)
        styled = Styled("", ())
        for run in cut:
            styled += Styled.of(run.text, run.face)
        width = family.measure(styled, font_size)
        start = box.x + (box.width - width) / 2 if centred else box.x + padding
        origin = rounded(start)
        offsets: list[tuple[float, ...]] = []
        cursor = start
        for run in cut:
            metrics = family.face(run.face)
            along: list[float] = []
            last = len(run.text) - 1
            for position, character in enumerate(run.text):
                # Where the letter lands is rounded as a position and then taken from the
                # line's origin, so origin plus offset is that position to the hundredth.
                along.append(rounded(rounded(cursor) - origin))
                step = metrics.step(character, run.text[position + 1] if position < last else None)
                cursor += step * font_size
            offsets.append(tuple(along))
        placed.append(
            CoreLine(
                origin=(origin, rounded(baseline)),
                width=rounded(width),
                offsets=tuple(offsets),
            )
        )
    return tuple(placed)
