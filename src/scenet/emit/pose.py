"""Each actor's skeleton as OpenPose JSON, for pose-conditioned image models (#72).

The [OpenPose output format](https://github.com/CMU-Perceptual-Computing-Lab/openpose/blob/master/doc/02_output.md)
as ControlNet's tooling reads it: `people[].pose_keypoints_2d`, flat `x, y, confidence`
triplets in the COCO-18 body order, in pixels of a canvas `canvas_width` by `canvas_height`.

**Left and right.** Scenet names a joint by the side of the screen it is on in the puppet's
rest pose, and mirrors a figure facing left; OpenPose names a point by the subject's own side.
Every Scenet body faces the reader, turned one way or the other, and a body facing the reader
has its right on the reader's left. So the subject's right is `_l` on a figure facing right and
`_r` on one facing left -- on the reader's left either way.

A point is missing -- `0, 0, 0`, as OpenPose writes a part it did not detect -- when the puppet
has no joint or feature by that name, when it is outside what the panel draws, and always for
the ears, which no puppet draws. `root`, `spine` and `head` have no COCO-18 counterpart.
Figures a picture draws were never posed and have no skeleton, so they are not in `people`.
"""

from scenet.core import CoreActor, PanelCore
from scenet.emit.conditioning import canvas, drawn_at, to_json

#: The COCO-18 body points, in OpenPose's order.
COCO_18: tuple[str, ...] = (
    "nose",
    "neck",
    "right_shoulder",
    "right_elbow",
    "right_wrist",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
    "right_hip",
    "right_knee",
    "right_ankle",
    "left_hip",
    "left_knee",
    "left_ankle",
    "right_eye",
    "left_eye",
    "right_ear",
    "left_ear",
)

#: Where each point comes from: a joint or a face feature, `{R}` the suffix of the subject's
#: right and `{L}` of their left. None for a point no puppet has.
SOURCES: tuple[tuple[str, str] | None, ...] = (
    ("features", "nose"),
    ("joints", "neck"),
    ("joints", "shoulder_{R}"),
    ("joints", "elbow_{R}"),
    ("joints", "wrist_{R}"),
    ("joints", "shoulder_{L}"),
    ("joints", "elbow_{L}"),
    ("joints", "wrist_{L}"),
    ("joints", "hip_{R}"),
    ("joints", "knee_{R}"),
    ("joints", "ankle_{R}"),
    ("joints", "hip_{L}"),
    ("joints", "knee_{L}"),
    ("joints", "ankle_{L}"),
    ("features", "eye_{R}"),
    ("features", "eye_{L}"),
    None,
    None,
)

MISSING = (0.0, 0.0, 0.0)


def keypoints(core: PanelCore, actor: CoreActor) -> list[float]:
    """One actor as COCO-18: fifty-four numbers, `x, y, confidence` per point.

    Args:
        core: The panel, whose frame and outline decide what is drawn.
        actor: The actor.

    Returns:
        The flat triplets, a missing point as `0, 0, 0` and any other at confidence 1.
    """
    # The suffixes of the subject's right and left: the reader's left, either way.
    right, left = ("r", "l") if actor.transform.mirrored else ("l", "r")
    values: list[float] = []
    for source in SOURCES:
        point = None
        if source is not None:
            table, name = source
            named = actor.joints if table == "joints" else actor.features
            point = named.get(name.format(R=right, L=left))
        values.extend((*point, 1.0) if point is not None and drawn_at(core, point) else MISSING)
    return values


def render_pose(core: PanelCore) -> str:
    """Every actor's pose as OpenPose JSON.

    One person per actor, in Panel Core's order -- the order the semantics export lists the
    actors in -- so `people[i]` is the i-th actor. Coordinates are pixels of the panel's canvas,
    as OpenPose writes them; a tool that wants fractions divides by the canvas size.

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
            "people": [{"pose_keypoints_2d": keypoints(core, actor)} for actor in core.actors],
        }
    )


__all__ = ["COCO_18", "MISSING", "SOURCES", "keypoints", "render_pose"]
