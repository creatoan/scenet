"""Page layout: tiers of panels into frames.

Plain arithmetic, with no constraint solver. Tiers are ordered top to bottom and panels
left to right within a tier, and each takes a share of what the margins and gutters leave,
in proportion to its weight -- the same model as CSS Grid's `fr` tracks with a `gap`. There
is nothing to choose between, so nothing for Cassowary to do: its value in this project is
the priority system that settles conflicting preferences (`docs/explanation/prior_art.md`),
and a strict grid has none.

The order panels are written in is the order they are read in, so the reading path is the
Z-path by construction. Layouts that break it -- a tall panel beside stacked ones, an inset
-- are where readers stop following the Z-path (Cohn, *Navigating Comics*, 2013), and they
are a later piece of work, with a reading-order check of their own.
"""

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


def resolve_frames(page_format: PageFormat, page: PageSpec) -> tuple[Frame, ...]:
    """Lay out one page.

    Args:
        page_format: Size, margin and gutters.
        page: The tiers, already validated to have room for what they hold.

    Returns:
        One frame per panel, in reading order: tier by tier, left to right.

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

    tiers_height = usable_height - page_format.tier_gutter * (len(page.tiers) - 1)
    total_height = sum(tier.height for tier in page.tiers)

    frames: list[Frame] = []
    y = margin
    for tier in page.tiers:
        height = tiers_height * tier.height / total_height
        row_width = usable_width - page_format.gutter * (len(tier.panels) - 1)
        total_width = sum(placement.width for placement in tier.panels)
        x = margin
        for placement in tier.panels:
            width = row_width * placement.width / total_width
            frames.append(
                Frame(
                    panel=placement.use,
                    x=rounded(x),
                    y=rounded(y),
                    width=rounded(width),
                    height=rounded(height),
                )
            )
            x += width + page_format.gutter
        y += height + page_format.tier_gutter
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
