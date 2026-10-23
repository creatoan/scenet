"""A panel's regions as an instance mask, for region-conditioned image models (#72).

One flat fill per actor, figure and mass, under the id the panel's SVG gives it -- `actor-alice`,
`mass-m0`, `figure-ana` -- so a segmentation keeps the labels the panel has. The colour of an id
is read from the SVG itself. Regions are drawn in the panel's own painter's order, so what covers
what is what the panel draws, and black is nothing.

**A character keeps its colour.** Its colour comes from its name, so Alice is the same colour in
every panel, and a regional prompt or an identity follows her down the page; a figure a picture
draws takes the colour of the part it plays. Two characters of one panel whose names land on one
colour are settled by name: the later steps to the next free one. Masses take theirs in drawing
order from a band of their own -- paler, less saturated -- so a wall is never mistaken for a
character.

This is an instance map, not a class map: two actors are two colours. What each region is --
an actor's puppet, a mass's kind and plane -- is in the semantics export, by the same id.
"""

import colorsys
import hashlib

from scenet.core import PanelCore
from scenet.emit.conditioning import Region, flat_map, regions

#: How many colours a character may take: hues evenly round the wheel, saturated and bright.
CHARACTER_SLOTS = 64

#: The golden ratio's fractional part: hues stepped by it never repeat and stay far apart.
GOLDEN = 0.6180339887498949


def _hex(hue: float, saturation: float, value: float) -> str:
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in (red, green, blue))


def character_colour(slot: int) -> str:
    """A character's colour: one of `CHARACTER_SLOTS` hues, saturated and bright.

    Example:
        >>> character_colour(0)
        '#ff2626'
    """
    return _hex(slot / CHARACTER_SLOTS, 0.85, 1.0)


def mass_colour(index: int) -> str:
    """The colour of the mass drawn `index`-th: less saturated than any character's, never dark.

    Hues step round the wheel by the golden ratio, and every other one is a little darker, so
    neighbours in drawing order are easy to tell apart.

    Example:
        >>> mass_colour(0)
        '#d97777'
    """
    value = 0.85 if index % 2 == 0 else 0.65
    return _hex((index * GOLDEN) % 1.0, 0.45, value)


def slot_of(name: str) -> int:
    """Where a character's colour starts: from its name's digest, the same in every panel.

    Example:
        >>> slot_of("alice") == slot_of("alice")
        True
    """
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % CHARACTER_SLOTS


def colours(drawn: list[Region]) -> list[str]:
    """Each region's mask colour, in the order given.

    Characters are settled in the order of their names, whatever order they are drawn in: each
    takes its own slot, or the next one no earlier name took.
    """
    slots: dict[str, int] = {}
    taken: set[int] = set()
    for who in sorted({region.who for region in drawn if region.who is not None}):
        slot = slot_of(who)
        for step in range(CHARACTER_SLOTS):
            if (slot + step) % CHARACTER_SLOTS not in taken:
                slot = (slot + step) % CHARACTER_SLOTS
                break
        slots[who] = slot
        taken.add(slot)
    filled: list[str] = []
    masses = 0
    for region in drawn:
        if region.who is not None:
            filled.append(character_colour(slots[region.who]))
        else:
            filled.append(mass_colour(masses))
            masses += 1
    return filled


def render_mask(core: PanelCore) -> str:
    """Every region of the panel in its own colour, on black.

    Args:
        core: The compiled panel.

    Returns:
        An SVG on the panel's canvas, its regions in the panel's own painter's order.
    """
    drawn = regions(core)
    return flat_map(core, list(zip(drawn, colours(drawn), strict=True)))


__all__ = [
    "CHARACTER_SLOTS",
    "GOLDEN",
    "character_colour",
    "colours",
    "mass_colour",
    "render_mask",
    "slot_of",
]
