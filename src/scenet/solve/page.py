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
:class:`PageLayout <scenet.ir.PageLayout>` refuses columns where nothing blocks it. An
inset is where readers agree least, splitting about evenly between it and the panel it
sits in, so it is read after its parent unless it says otherwise.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from scenet.errors import RuleViolationError
from scenet.geom import BBox, rounded
from scenet.ir import (
    Corner,
    InsetOrder,
    PageFormat,
    PageSpec,
    PanelPlacement,
    StackedPanel,
)

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
        inset_of: For an inset, the panel it is set into; `None` otherwise.
        clearance: For an inset, the area it covers with its ring of white: the frame
            grown by a gutter on every side. It is painted white under the inset, and
            its parent's lettering keeps clear of it. `None` for a panel that is no inset.
    """

    panel: str
    x: float
    y: float
    width: float
    height: float
    inset_of: str | None = None
    clearance: BBox | None = None


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


def _frame(panel: str, area: BBox, *, inset_of: str | None = None, gutter: float = 0.0) -> Frame:
    """A frame with every value rounded, and an inset's clearance worked out from it."""
    x, y = rounded(area.x), rounded(area.y)
    width, height = rounded(area.width), rounded(area.height)
    clearance = (
        BBox(
            rounded(x - gutter),
            rounded(y - gutter),
            rounded(width + 2 * gutter),
            rounded(height + 2 * gutter),
        )
        if inset_of is not None
        else None
    )
    return Frame(panel, x, y, width, height, inset_of=inset_of, clearance=clearance)


def _with_insets(
    placement: PanelPlacement | StackedPanel,
    area: BBox,
    gutter: float,
    loc: tuple[str | int, ...],
) -> list[Frame]:
    """A panel's frame and its insets' frames, in the order they are read.

    An inset sits a gutter in from both edges of its corner, and its ring of white is a
    gutter wide, so the ring meets its parent's edge: the parent reads as a panel with a
    corner cut out, and the inset as a panel of its own.

    Raises:
        RuleViolationError: Rule `page-layout`, when an inset comes within a gutter of
            another inset in the same panel.
    """
    parent = _frame(placement.use, area)
    before: list[Frame] = []
    after: list[Frame] = []
    cleared: list[tuple[str, BBox]] = []
    for index, inset in enumerate(placement.insets):
        width, height = area.width * inset.size, area.height * inset.size
        left = inset.at in (Corner.TOP_LEFT, Corner.BOTTOM_LEFT)
        top = inset.at in (Corner.TOP_LEFT, Corner.TOP_RIGHT)
        x = area.x + gutter if left else area.right - gutter - width
        y = area.y + gutter if top else area.bottom - gutter - height
        frame = _frame(inset.use, BBox(x, y, width, height), inset_of=placement.use, gutter=gutter)
        drawn = BBox(frame.x, frame.y, frame.width, frame.height)
        for name, clearance in cleared:
            if clearance.overlap_area(drawn):
                raise RuleViolationError(
                    f"insets '{name}' and '{inset.use}' in panel '{placement.use}' overlap; "
                    "each needs a gutter clear of the other, so put them in other corners or "
                    "make them smaller",
                    rule="page-layout",
                    loc=(*loc, "insets", index),
                )
        cleared.append(
            (inset.use, BBox(x - gutter, y - gutter, width + 2 * gutter, height + 2 * gutter))
        )
        (before if inset.read is InsetOrder.BEFORE else after).append(frame)
    return [*before, parent, *after]


def resolve_frames(page_format: PageFormat, page: PageSpec, *, index: int = 0) -> tuple[Frame, ...]:
    """Lay out one page.

    Args:
        page_format: Size, margin and gutters.
        page: The tiers, already validated to have room for what they hold.
        index: The page's position among the pages, from 0, to locate a mistake.

    Returns:
        One frame per panel, in reading order: tier by tier, and within a tier left to
        right -- or, for a tier of columns, column by column and top to bottom in each.
        An inset comes right after the panel it is set into, or right before it when it
        says `read: before`.

    Raises:
        RuleViolationError: Rule `page-layout`, for two insets in one panel that overlap.
            It is found here, where the frames are worked out, and `scenet check` runs
            this too, so the finding is still located.

    Example:
        >>> from scenet.ir import PageFormat, PageSpec
        >>> page = PageSpec.model_validate(
        ...     {"tiers": [{"panels": [{"use": "a"}, {"use": "b", "width": 2}]}]}
        ... )
        >>> [(f.panel, f.x, f.width) for f in resolve_frames(PageFormat(), page)]
        [('a', 100.0, 586.67), ('b', 726.67, 1173.33)]
    """
    margin = page_format.margin
    gutter = page_format.gutter
    usable_width = page_format.width - 2 * margin
    usable_height = page_format.height - 2 * margin

    frames: list[Frame] = []
    rows = _split(
        margin, usable_height, page_format.tier_gutter, [tier.height for tier in page.tiers]
    )
    for tier_index, (tier, y, height) in enumerate(
        zip(page.tiers, rows[::2], rows[1::2], strict=True)
    ):
        loc: tuple[str | int, ...] = ("pages", index, "tiers", tier_index)
        if tier.panels:
            spans = _split(margin, usable_width, gutter, [p.width for p in tier.panels])
            for panel_index, (placement, x, width) in enumerate(
                zip(tier.panels, spans[::2], spans[1::2], strict=True)
            ):
                frames += _with_insets(
                    placement, BBox(x, y, width, height), gutter, (*loc, "panels", panel_index)
                )
            continue
        spans = _split(margin, usable_width, gutter, [c.width for c in tier.columns])
        for column_index, (column, x, width) in enumerate(
            zip(tier.columns, spans[::2], spans[1::2], strict=True)
        ):
            stack = _split(y, height, page_format.tier_gutter, [p.height for p in column.panels])
            for panel_index, (stacked, top, size) in enumerate(
                zip(column.panels, stack[::2], stack[1::2], strict=True)
            ):
                frames += _with_insets(
                    stacked,
                    BBox(x, top, width, size),
                    gutter,
                    (*loc, "columns", column_index, "panels", panel_index),
                )
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
