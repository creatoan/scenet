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

from scenet.core import PanelCore
from scenet.emit.conditioning import canvas, figure_extent, fraction_box, to_json
from scenet.solve.describe import name, traits


def render_boxes(core: PanelCore) -> str:
    """Every actor's and figure's box and phrase, as JSON.

    Actors first, in Panel Core's order, then figures a picture draws, cast or not.

    Args:
        core: The compiled panel.

    Returns:
        The document, written as Panel Core is.
    """
    boxes: list[dict[str, object]] = []
    for actor in core.actors:
        box = fraction_box(core, actor.hull)
        if box is not None:
            phrase = ", ".join([name(actor.id), *traits(actor.pose, actor.expression, actor.marks)])
            boxes.append({"id": actor.id, "phrase": phrase, "box": box})
    for figure in core.figures:
        box = fraction_box(core, figure_extent(figure))
        if box is not None:
            boxes.append(
                {"id": figure.figure, "phrase": name(figure.actor or figure.figure), "box": box}
            )
    width, height = canvas(core)
    return to_json({"canvas_width": width, "canvas_height": height, "boxes": boxes})


__all__ = ["render_boxes"]
