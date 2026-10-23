"""A panel's planes as a depth map, for depth-conditioned image models (#72).

Scenet is orthographic and has no metric depth. What it has is a painter's order -- an integer
`depth` actors and masses share -- so the map is flat grey planes in that order, and claims
nothing more: the steps are ranks, not distances.

ControlNet's depth maps run **white near, black far**. That is the reverse of the backdrop's own
value ladder, where aerial perspective makes far planes paler, so none of those tones is reused:
a model handed them would read the panel inside out.

- Black is nothing nearer than infinity: the paper, the sky (whatever plane it was filed
  under, as its tone already treats it), and a supplied picture, whose content the compiler
  never saw.
- Every other depth present, ranked far to near, is one even step paler, so the frontmost is
  white.
- Figures a picture draws have no painter's order of their own. They share one plane, in front
  of the picture they are drawn against.
"""

from scenet.core import PanelCore
from scenet.emit.conditioning import Region, flat_map, regions

#: Where the figures a picture draws sit: in front of everything else in the panel, which over
#: a picture is nothing.
_FIGURES = (1, 0)


def _plane(region: Region) -> tuple[int, int]:
    return (0, region.depth) if region.depth is not None else _FIGURES


def grey(value: int) -> str:
    """A grey of one value, `#rrggbb`.

    Example:
        >>> grey(255), grey(0)
        ('#ffffff', '#000000')
    """
    return f"#{value:02x}{value:02x}{value:02x}"


def render_depth(core: PanelCore) -> str:
    """The panel's planes as grey on black, white nearest.

    Args:
        core: The compiled panel.

    Returns:
        An SVG the panel's size, its regions in the panel's own painter's order.
    """
    drawn = regions(core)
    planes = sorted({_plane(region) for region in drawn if not region.sky})
    step = {plane: round(255 * (rank + 1) / len(planes)) for rank, plane in enumerate(planes)}
    return flat_map(
        core,
        [(region, grey(0 if region.sky else step[_plane(region)])) for region in drawn],
    )


__all__ = ["grey", "render_depth"]
