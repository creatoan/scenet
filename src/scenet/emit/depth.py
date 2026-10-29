"""A panel's planes as a depth map, for depth-conditioned image models (#72).

Scenet is orthographic and has no metric depth. What it has is a painter's order -- an integer
`depth` actors and masses share -- so the map is grey planes in that order, and claims
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

**A surface that lies flat recedes** (#227). A ground, a floor or a stretch of water is not a
wall at one distance, and one flat grey tells a model it is: the floor comes out painted as a
backdrop, with figures pasted on it. Depth models are trained on relative *inverse* depth, and
through a pinhole camera a flat ground's inverse depth grows in proportion to how far below the
horizon it is seen -- a straight ramp in screen height. So each is a ramp from the horizon,
at its own step, to the panel's bottom edge; a ceiling the same, up to the top edge. That
claims what the kind already says, that the surface recedes to the horizon, and still no
distance between two regions:

- **At the horizon, its own step**, so it is never darker than its plane and the painter's
  order holds everywhere. Scenet stands walls and buildings on the horizon line itself, so the
  true disparity there, black, would put the ground behind what stands on it.
- **At the edge, the farthest figure's step**, white when there is none, so no figure is ever
  darker than the floor around its feet. A ground in the foreground plane, already a step above
  every actor, stays flat: a ramp would only darken it.
"""

from scenet.core import PanelCore
from scenet.emit.conditioning import Ramp, Region, flat_map, regions
from scenet.ir import MassKind
from scenet.solve.backdrop import GROUND_KINDS

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


def recedes(core: PanelCore, region: Region) -> tuple[float, float] | None:
    """Where a surface that lies flat recedes from and to, as heights: `(far, near)`.

    A ground, floor or water runs from the horizon down to the panel's bottom edge, a ceiling
    from the horizon up to its top edge. A backdrop that sets no horizon -- a hand-edited one
    -- recedes from the mass's own far edge instead: a ground's top, a ceiling's bottom.

    Args:
        core: The panel.
        region: One of its regions.

    Returns:
        The two heights, or None for anything that does not lie flat, or that has no room to
        recede toward the reader.

    Example:
        >>> from scenet import compile_source
        >>> from scenet.emit.conditioning import regions
        >>> core = compile_source(
        ...     "{panel: {size: [900, 560]}, setting: {place: street},"
        ...     " cast: {a: {reference: alice}}}"
        ... ).core
        >>> [recedes(core, region) for region in regions(core)][-2:]
        [(308.0, 560.0), None]
    """
    horizon = core.backdrop.horizon if core.backdrop is not None else None
    heights = [y for _, y in region.polygon]
    if region.kind in GROUND_KINDS:
        far = min(heights) if horizon is None else horizon
        return (far, core.height) if far < core.height else None
    if region.kind is MassKind.CEILING:
        far = max(heights) if horizon is None else horizon
        return (far, 0.0) if far > 0.0 else None
    return None


def render_depth(core: PanelCore) -> str:
    """The panel's planes as grey on black, white nearest, and its flat surfaces receding.

    Args:
        core: The compiled panel.

    Returns:
        An SVG the panel's size, its regions in the panel's own painter's order.
    """
    drawn = regions(core)
    planes = sorted({_plane(region) for region in drawn if not region.sky})
    step = {plane: round(255 * (rank + 1) / len(planes)) for rank, plane in enumerate(planes)}
    # As pale as a receding surface may get: no figure is darker than the floor it stands on.
    edge = min((step[_plane(region)] for region in drawn if region.who is not None), default=255)

    def fill(region: Region) -> str | Ramp:
        if region.sky:
            return grey(0)
        own = step[_plane(region)]
        run = recedes(core, region)
        if run is None or edge <= own:
            return grey(own)
        return Ramp(start=grey(own), end=grey(edge), begins=run[0], ends=run[1])

    return flat_map(core, [(region, fill(region)) for region in drawn])


__all__ = ["grey", "recedes", "render_depth"]
