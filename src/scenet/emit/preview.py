"""The pose and the boxes exports, drawn to be looked at (#238).

The pose and the boxes are JSON, which a model reads and a person cannot. These draw each as
a picture on the exports' own canvas, for the playground to show beside the depth map and the
mask. They read what the exports read -- the same keypoints, the same boxes -- so what is shown
is what is written, and they are no export themselves: a model is handed the JSON.

**The pose** is drawn as ControlNet's OpenPose annotator draws a skeleton, so it looks like
what a reader who works with these models has seen: each limb and each point in the usual
OpenPose colour, on black. A limb is drawn only between two points that are there.

**The boxes** are labelled rectangles, each in its region's colour in the mask, so the two side
by side say who is who in one colour. The label is the phrase the export pairs the box with.
"""

from xml.sax.saxutils import escape

from scenet.core import PanelCore
from scenet.emit.boxes import boxes
from scenet.emit.conditioning import canvas, regions
from scenet.emit.mask import colours
from scenet.emit.pose import COCO_18, keypoints
from scenet.emit.svg import attr, fmt

#: Each COCO-18 point's colour, in OpenPose's order: red round the wheel to rose. A limb
#: takes the colour at its own position in :data:`OPENPOSE_LIMBS`.
OPENPOSE_COLOURS: tuple[str, ...] = (
    "#ff0000",
    "#ff5500",
    "#ffaa00",
    "#ffff00",
    "#aaff00",
    "#55ff00",
    "#00ff00",
    "#00ff55",
    "#00ffaa",
    "#00ffff",
    "#00aaff",
    "#0055ff",
    "#0000ff",
    "#5500ff",
    "#aa00ff",
    "#ff00ff",
    "#ff00aa",
    "#ff0055",
)

#: The limbs OpenPose draws, as pairs of COCO-18 points: the neck to each shoulder, down each
#: arm, the neck to each hip and down each leg, then the head. Its two ear-to-shoulder limbs
#: are left out, as its own drawing leaves them out.
OPENPOSE_LIMBS: tuple[tuple[int, int], ...] = (
    (1, 2),
    (1, 5),
    (2, 3),
    (3, 4),
    (5, 6),
    (6, 7),
    (1, 8),
    (8, 9),
    (9, 10),
    (1, 11),
    (11, 12),
    (12, 13),
    (1, 0),
    (0, 14),
    (14, 16),
    (0, 15),
    (15, 17),
)

#: The width OpenPose's drawing is sized for. A canvas twice as wide draws twice as thick, so
#: a skeleton looks the same on any panel.
REFERENCE_WIDTH = 512


def _open(width: int, height: int) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#000000"/>',
    ]


def render_pose_preview(core: PanelCore) -> str:
    """Every actor's skeleton, as the pose export places it, in OpenPose's colours on black.

    Args:
        core: The compiled panel.

    Returns:
        An SVG on the exports' canvas: one group per actor, `pose-<id>`, its limbs then its
        points. Figures a picture draws were never posed and have none.
    """
    width, height = canvas(core)
    unit = max(width, height) / REFERENCE_WIDTH
    lines = _open(width, height)
    for actor in core.actors:
        values = keypoints(core, actor)
        points = {
            index: (values[3 * index], values[3 * index + 1])
            for index in range(len(COCO_18))
            if values[3 * index + 2] > 0.0
        }
        lines.append(
            f'  <g id={attr("pose-" + actor.id)} stroke-width="{fmt(4 * unit)}" '
            'stroke-linecap="round" stroke-opacity="0.6">'
        )
        for number, (start, end) in enumerate(OPENPOSE_LIMBS):
            if start in points and end in points:
                (x1, y1), (x2, y2) = points[start], points[end]
                lines.append(
                    f'    <line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
                    f'stroke="{OPENPOSE_COLOURS[number]}"/>'
                )
        for index, (x, y) in points.items():
            lines.append(
                f'    <circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(4 * unit)}" '
                f'fill="{OPENPOSE_COLOURS[index]}"/>'
            )
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_boxes_preview(core: PanelCore) -> str:
    """Every box the boxes export writes, labelled with its phrase, in its mask colour.

    Args:
        core: The compiled panel.

    Returns:
        An SVG on the exports' canvas: one group per box, `box-<region>` -- `box-actor-alice`,
        `box-figure-ana` -- in the export's order.
    """
    width, height = canvas(core)
    unit = max(width, height) / REFERENCE_WIDTH
    drawn = regions(core)
    colour = dict(zip((region.id for region in drawn), colours(drawn), strict=True))
    size = 12 * unit
    lines = _open(width, height)
    for item in boxes(core):
        xmin, ymin, xmax, ymax = item.box
        fill = colour[item.region]
        lines.extend(
            [
                f"  <g id={attr('box-' + item.region)}>",
                f'    <rect x="{fmt(xmin * width)}" y="{fmt(ymin * height)}" '
                f'width="{fmt((xmax - xmin) * width)}" height="{fmt((ymax - ymin) * height)}" '
                f'fill="{fill}" fill-opacity="0.2" stroke="{fill}" '
                f'stroke-width="{fmt(2 * unit)}"/>',
                f'    <text x="{fmt(xmin * width + 4 * unit)}" y="{fmt(ymin * height + size)}" '
                f'font-family="sans-serif" font-size="{fmt(size)}" fill="{fill}">'
                f"{escape(item.phrase)}</text>",
                "  </g>",
            ]
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


__all__ = [
    "OPENPOSE_COLOURS",
    "OPENPOSE_LIMBS",
    "REFERENCE_WIDTH",
    "render_boxes_preview",
    "render_pose_preview",
]
