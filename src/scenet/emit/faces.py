"""The faces an emitter looks lettering up in, and where Panel Core put each letter.

An emitter makes no layout decision. Panel Core gives every line of a balloon or a caption its
baseline origin and the offset of each character along it, so what an emitter does with a line
is: for each character, take the outline of that character in that face, and put it there. It
reads no advance and no kerning, and it needs no more of a face than its outlines, its glyph
numbers and the widths a PDF font dictionary lists.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from scenet.core import CoreLine, CoreRun, CoreSfx
from scenet.ir import Face
from scenet.solve.text import FontMetrics


class Faces(Protocol):
    """Somewhere to find the font a face of the lettering is set in."""

    def face(self, face: Face) -> FontMetrics:
        """The font a face is set in."""
        ...


@dataclass(frozen=True, slots=True)
class PlacedRun:
    """Where each letter of one run lands along its line, as Panel Core says.

    Attributes:
        run: The run.
        metrics: The face it is lettered in.
        scale: Font units to panel units: the type size over the face's units per em.
        origins: The left edge of each character of `run.text`, in panel units, whether
            or not the character has an outline to draw.
        steps: How far the pen moves from each character to the next, in panel units: the
            distance between their origins in Panel Core, and for the last character of the
            line, to the end of the line.
    """

    run: CoreRun
    metrics: FontMetrics
    scale: float
    origins: tuple[float, ...]
    steps: tuple[float, ...]


def place_line(
    line: CoreLine, runs: Sequence[CoreRun], font_size: float, faces: Faces
) -> list[PlacedRun]:
    """One line's runs, each letter at the origin Panel Core gives it.

    Args:
        line: The line's setting.
        runs: The line's runs: as recorded, or the whole line in its one face.
        font_size: The type size, in panel units.
        faces: The faces the lettering is set in.

    Returns:
        One placed run for each of `runs`.
    """
    x, _ = line.origin
    end = x + line.width
    absolute = [[x + offset for offset in offsets] for offsets in line.offsets]
    every = [position for run in absolute for position in run]
    following = [*every[1:], end]
    placed: list[PlacedRun] = []
    used = 0
    for run, origins in zip(runs, absolute, strict=True):
        metrics = faces.face(run.face)
        steps = tuple(following[used + index] - origin for index, origin in enumerate(origins))
        used += len(origins)
        placed.append(
            PlacedRun(
                run=run,
                metrics=metrics,
                scale=font_size / metrics.units_per_em,
                origins=tuple(origins),
                steps=steps,
            )
        )
    return placed


def sfx_scale(effect: CoreSfx, metrics: FontMetrics) -> float:
    """Font units to panel units for a sound effect's letters."""
    return effect.font_size / metrics.units_per_em
