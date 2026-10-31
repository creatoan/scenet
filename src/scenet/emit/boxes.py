"""Each figure's extent with a phrase, for box-conditioned image models (#72).

"This entity, here", as GLIGEN takes it: a phrase and a box per actor and per figure a picture
draws, the box as `[xmin, ymin, xmax, ymax]` fractions of the panel -- what diffusers' GLIGEN
pipeline reads as `gligen_boxes`, beside the phrases as `gligen_phrases`.

An actor's box is its hull's bounds: the silhouette staging spaced the cast by, which leaves
emanata out so that a figure who starts sweating does not move. A figure's is its body and
face as the picture's contract declares them. Each is clipped to the panel, and one wholly
outside it has no box.

The phrase is the description's own words for a figure (:func:`traits
<scenet.solve.describe.traits>`): its name, how it stands, its face, its marks. Where it is on
the panel is the box's to say.
"""

from dataclasses import dataclass

from scenet.core import PanelCore
from scenet.emit.conditioning import canvas, figure_extent, fraction_box, to_json
from scenet.solve.describe import name, traits


@dataclass(frozen=True, slots=True)
class Boxed:
    """One box the export writes, and whose region it is.

    Attributes:
        id: What the export calls it: the actor's id, or the figure's name in its contract.
        region: The id the panel's SVG and the mask give it: `actor-alice`, `figure-ana`.
        phrase: The description's own words for it.
        box: `[xmin, ymin, xmax, ymax]` as fractions of the panel.
    """

    id: str
    region: str
    phrase: str
    box: list[float]


def boxes(core: PanelCore) -> list[Boxed]:
    """Every actor's and figure's box and phrase, in the order the export writes them.

    Actors first, in Panel Core's order, then figures a picture draws, cast or not. One wholly
    outside the panel has no box.
    """
    found: list[Boxed] = []
    for actor in core.actors:
        box = fraction_box(core, actor.hull)
        if box is not None:
            phrase = ", ".join([name(actor.id), *traits(actor.pose, actor.expression, actor.marks)])
            found.append(Boxed(actor.id, f"actor-{actor.id}", phrase, box))
    for figure in core.figures:
        box = fraction_box(core, figure_extent(figure))
        if box is not None:
            found.append(
                Boxed(
                    figure.figure,
                    f"figure-{figure.figure}",
                    name(figure.actor or figure.figure),
                    box,
                )
            )
    return found


def render_boxes(core: PanelCore) -> str:
    """Every actor's and figure's box and phrase, as JSON.

    Actors first, in Panel Core's order, then figures a picture draws, cast or not.

    Args:
        core: The compiled panel.

    Returns:
        The document, written as Panel Core is.
    """
    width, height = canvas(core)
    return to_json(
        {
            "canvas_width": width,
            "canvas_height": height,
            "boxes": [
                {"id": item.id, "phrase": item.phrase, "box": item.box} for item in boxes(core)
            ],
        }
    )


__all__ = ["Boxed", "boxes", "render_boxes"]
