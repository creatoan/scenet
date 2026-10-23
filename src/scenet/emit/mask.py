"""A panel's regions as an instance mask, for region-conditioned image models (#72).

One flat fill per actor, figure and mass, under the id the panel's SVG gives it -- `actor-alice`,
`mass-m0`, `figure-ana` -- so a segmentation keeps the labels the panel has. The colour of an id
is read from the SVG itself; the colours only have to differ. Regions are drawn in the panel's
own painter's order, so what covers what is what the panel draws, and black is nothing.

This is an instance map, not a class map: two actors are two colours. What each region is --
an actor's puppet, a mass's kind and plane -- is in the semantics export, by the same id.
"""

import colorsys

from scenet.core import PanelCore
from scenet.emit.conditioning import flat_map, regions

#: The golden ratio's fractional part: hues stepped by it never repeat and stay far apart.
GOLDEN = 0.6180339887498949


def colour(index: int) -> str:
    """The mask colour of the region drawn `index`-th: bright, saturated, never black.

    Hues step round the wheel by the golden ratio, and every other one is a little darker, so
    neighbours in drawing order are easy to tell apart.

    Example:
        >>> colour(0)
        '#ff4040'
    """
    hue = (index * GOLDEN) % 1.0
    value = 1.0 if index % 2 == 0 else 0.8
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.75, value)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in (red, green, blue))


def render_mask(core: PanelCore) -> str:
    """Every region of the panel in its own colour, on black.

    Args:
        core: The compiled panel.

    Returns:
        An SVG the panel's size, its regions in the panel's own painter's order.
    """
    return flat_map(core, [(region, colour(index)) for index, region in enumerate(regions(core))])


__all__ = ["GOLDEN", "colour", "render_mask"]
