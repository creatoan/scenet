"""Page layout: tiers of panels, or of columns of panels, into frames.

Plain arithmetic, with no constraint solver. Tiers are ordered top to bottom and panels
left to right within a tier, and each takes a share of what the margins and gutters leave,
in proportion to its weight -- the same model as CSS Grid's `fr` tracks with a `gap`. A tier
of columns is split the same way twice: across into columns, then down each column into its
panels, with the tier gutter between them. There is nothing to choose between, so nothing
for Cassowary to do: its value in this project is the priority system that settles
conflicting preferences (`docs/explanation/prior_art.md`), and a strict grid has none.

The order panels are written in is the order they are read in. In a tier of panels that is
the Z-path. In a tier of columns it is down each column before across, which is what readers
do when a panel spanning the tier blocks the way across (Cohn, *Navigating Comics*, 2013);
:class:`PageLayout <scenet.ir.PageLayout>` refuses columns where nothing blocks it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from scenet.geom import rounded
from scenet.ir import PageFormat, PageSpec

__all__ = ["LETTERING_TIERS", "Frame", "lettering_height", "resolve_frames"]

#: Type on a page is set as if every panel were one tier of a page this many tiers tall.
#: Three tiers of the default page letter at about 1.2% of the page's height, which on a
#: printed comic page is about eight points -- the size lettering is usually set at. It is
#: also exactly what a single panel letters at today when it is a third of a page tall, so
#: nothing changes for a panel that was already the size it ends up on the page.
LETTERING_TIERS = 3


@dataclass(frozen=True, slots=True)
class Frame:
    """Where one panel goes on its page.

    Attributes:
        panel: The panel's name.
        x: Left edge.
        y: Top edge.
        width: Frame width.
        height: Frame height.
    """

    panel: str
    x: float
    y: float
    width: float
    height: float


def _split(start: float, length: float, gap: float, weights: Sequence[float]) -> list[float]:
    """Share `length` between `weights`, `gap` apart, as alternating starts and sizes."""
    available = length - gap * (len(weights) - 1)
    total = sum(weights)
    spans: list[float] = []
    for weight in weights:
        size = available * weight / total
        spans += [start, size]
        start += size + gap
    return spans


def resolve_frames(page_format: PageFormat, page: PageSpec) -> tuple[Frame, ...]:
    """Lay out one page.

    Args:
        page_format: Size, margin and gutters.
        page: The tiers, already validated to have room for what they hold.

    Returns:
        One frame per panel, in reading order: tier by tier, and within a tier left to
        right -- or, for a tier of columns, column by column and top to bottom in each.

    Example:
        >>> from scenet.ir import PageFormat, PageSpec
        >>> page = PageSpec.model_validate(
        ...     {"tiers": [{"panels": [{"use": "a"}, {"use": "b", "width": 2}]}]}
        ... )
        >>> [(f.panel, f.x, f.width) for f in resolve_frames(PageFormat(), page)]
        [('a', 100.0, 586.67), ('b', 726.67, 1173.33)]
    """
    margin = page_format.margin
    usable_width = page_format.width - 2 * margin
    usable_height = page_format.height - 2 * margin

    def frame(panel: str, x: float, y: float, width: float, height: float) -> Frame:
        return Frame(
            panel=panel, x=rounded(x), y=rounded(y), width=rounded(width), height=rounded(height)
        )

    frames: list[Frame] = []
    rows = _split(
        margin, usable_height, page_format.tier_gutter, [tier.height for tier in page.tiers]
    )
    for tier, y, height in zip(page.tiers, rows[::2], rows[1::2], strict=True):
        if tier.panels:
            spans = _split(margin, usable_width, page_format.gutter, [p.width for p in tier.panels])
            frames += [
                frame(placement.use, x, y, width, height)
                for placement, x, width in zip(tier.panels, spans[::2], spans[1::2], strict=True)
            ]
            continue
        spans = _split(margin, usable_width, page_format.gutter, [c.width for c in tier.columns])
        for column, x, width in zip(tier.columns, spans[::2], spans[1::2], strict=True):
            stack = _split(y, height, page_format.tier_gutter, [p.height for p in column.panels])
            frames += [
                frame(stacked.use, x, top, width, size)
                for stacked, top, size in zip(column.panels, stack[::2], stack[1::2], strict=True)
            ]
    return tuple(frames)


def lettering_height(page_format: PageFormat) -> float:
    """The height every panel on a page takes its type size from.

    A panel letters at a fixed fraction of a height. Alone, that height is its own; on a
    page it is this one, the same for every panel, so a short panel and a tall one letter
    alike, as no letterer would do otherwise.

    Args:
        page_format: The page.

    Returns:
        A third of the height inside the margins (see `LETTERING_TIERS`).
    """
    return rounded((page_format.height - 2 * page_format.margin) / LETTERING_TIERS)
