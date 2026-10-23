"""What a panel holds, as structure, for whatever writes a prompt from it (#72).

**Not a prompt.** Prompt dialects differ per model and change every few months, and turning
structure into prose is the language step that prior art leaves to whatever is in the loop,
not to a compiler. So this hands over the structure: the camera, the setting, every actor --
reference, pose, expression, marks, facing, whom they look at, depth -- every figure a picture
draws, and every balloon, caption and sound effect in reading order with its box.

Where Panel Core already has words, they are copied, never phrased again: the panel's
`description` and each entry's `label`, which accessible output reads (#76).
"""

from typing import Any

from scenet.core import CoreBackdrop, PanelCore
from scenet.emit.conditioning import canvas, corners, fraction_box, to_json
from scenet.ir import Weather


def _setting(backdrop: CoreBackdrop | None) -> dict[str, Any] | None:
    """Where and when: the place, the hour, the weather, the masses, a supplied picture."""
    if backdrop is None:
        return None
    air = backdrop.atmosphere
    image = backdrop.image
    return {
        "place": backdrop.place,
        # Recorded on the backdrop; a Core written before that has it only in the air.
        "time": backdrop.time or (air.time if air is not None else None),
        # No atmosphere is what clear weather is.
        "weather": air.weather if air is not None else Weather.CLEAR,
        "masses": [
            {"id": mass.id, "kind": mass.kind, "plane": mass.plane, "depth": mass.depth}
            for mass in backdrop.masses
        ],
        "image": None if image is None else {"href": image.href, "fit": image.fit},
    }


def _lettering(core: PanelCore) -> list[dict[str, Any]]:
    """Every balloon, caption and sound effect, in the one order a reader takes them."""
    entries: list[dict[str, Any]] = [
        {
            "order": balloon.order,
            "id": balloon.id,
            "type": "balloon",
            "kind": balloon.kind,
            "by": balloon.speaker,
            "label": balloon.label,
            "box": fraction_box(
                core, corners(balloon.box.x, balloon.box.y, balloon.box.width, balloon.box.height)
            ),
        }
        for balloon in core.balloons
    ]
    entries += [
        {
            "order": caption.order,
            "id": caption.id,
            "type": "caption",
            "kind": caption.kind,
            "by": caption.speaker,
            "label": caption.label,
            "box": fraction_box(
                core, corners(caption.box.x, caption.box.y, caption.box.width, caption.box.height)
            ),
        }
        for caption in core.captions
    ]
    entries += [
        {
            "order": effect.order,
            "id": effect.id,
            "type": "sfx",
            "kind": None,
            "by": effect.source,
            "label": effect.label,
            "box": fraction_box(core, effect.zone),
        }
        for effect in core.sfx
    ]
    return sorted(entries, key=lambda entry: entry["order"])


def render_semantics(core: PanelCore) -> str:
    """What the panel holds, as JSON.

    Actors are listed in Panel Core's order, the order the pose export lists people in.
    Facing is read from the mirror: a mirrored puppet faces left.

    Args:
        core: The compiled panel.

    Returns:
        The document, written as Panel Core is.
    """
    camera = core.camera
    width, height = canvas(core)
    payload: dict[str, Any] = {
        "canvas_width": width,
        "canvas_height": height,
        "direction": core.direction,
        "description": core.description,
        "camera": None
        if camera is None
        else {"shot": camera.shot, "angle": camera.angle, "pullback": camera.pullback},
        "setting": _setting(core.backdrop),
        "actors": [
            {
                "id": actor.id,
                "reference": actor.reference,
                "pose": actor.pose,
                "expression": actor.expression,
                "marks": list(actor.marks),
                "facing": "left" if actor.transform.mirrored else "right",
                "looking_at": actor.looking_at,
                "depth": actor.depth,
            }
            for actor in core.actors
        ],
        "figures": [{"figure": figure.figure, "actor": figure.actor} for figure in core.figures],
        "lettering": _lettering(core),
    }
    return to_json(payload)


__all__ = ["render_semantics"]
