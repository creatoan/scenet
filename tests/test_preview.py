"""The pose and the boxes, drawn to be looked at (#238).

The pose and boxes exports are JSON: a model reads them, a person cannot. The playground shows
each as a picture, drawn here rather than in the page, so that the page holds no drawing code
and the picture is tested where the export is. Each preview reads what its export reads -- the
same keypoints, the same boxes -- so what is shown is what is written.
"""

import json
import xml.etree.ElementTree as ET
from typing import Any

from scenet.core import PanelCore
from scenet.emit.boxes import render_boxes
from scenet.emit.conditioning import canvas
from scenet.emit.mask import render_mask
from scenet.emit.pose import COCO_18, keypoints
from scenet.emit.preview import (
    OPENPOSE_COLOURS,
    OPENPOSE_LIMBS,
    render_boxes_preview,
    render_pose_preview,
)
from scenet.pipeline import compile_source
from tests.images import contract, png

SVG = "{http://www.w3.org/2000/svg}"

DUEL = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot}
cast:
  alice: {reference: alice, pose: pointing, expression: angry}
  bob: {reference: bob, facing: left}
staging: [alice left_of bob]
"""

FIGURES = {
    "ana": {
        "face": {"center": [250, 180], "radius": 50},
        "body": [[180, 140], [320, 140], [340, 600], [160, 600]],
    },
}


def _figures() -> PanelCore:
    return compile_source(
        "panel: {size: [900, 600]}\nsetting: {image: art/p.png, fit: contain}\n"
        "cast:\n  ANA: {figure: ana}\n  bob: {reference: bob}\n",
        base={"art/p.png": png(900, 600), "art/p.art.yaml": contract((900, 600), FIGURES)},
    ).core


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg.encode("utf-8"))


def _groups(svg: str) -> dict[str, ET.Element]:
    return {group.get("id", ""): group for group in _root(svg).iter(f"{SVG}g")}


def _canvas_of(svg: str) -> tuple[int, int]:
    root = _root(svg)
    return int(root.get("width", "")), int(root.get("height", ""))


class TestTheOpenPoseColours:
    def test_one_colour_per_point_and_seventeen_limbs(self):
        """As ControlNet's OpenPose annotator draws them: 18 points, 17 limbs."""
        assert len(OPENPOSE_COLOURS) == len(COCO_18) == 18
        assert len(OPENPOSE_LIMBS) == 17

    def test_the_usual_colours_from_red_round_the_wheel(self):
        assert OPENPOSE_COLOURS[:3] == ("#ff0000", "#ff5500", "#ffaa00")
        assert OPENPOSE_COLOURS[-1] == "#ff0055"

    def test_the_limbs_join_the_neck_to_the_shoulders_first(self):
        neck, right_shoulder, left_shoulder = (
            COCO_18.index(name) for name in ("neck", "right_shoulder", "left_shoulder")
        )
        assert OPENPOSE_LIMBS[:2] == ((neck, right_shoulder), (neck, left_shoulder))

    def test_the_ear_to_shoulder_limbs_are_left_out_as_openpose_leaves_them(self):
        for side in ("right", "left"):
            limb = (COCO_18.index(f"{side}_shoulder"), COCO_18.index(f"{side}_ear"))
            assert limb not in OPENPOSE_LIMBS


class TestThePosePreview:
    def test_it_is_on_the_exports_canvas(self):
        core = compile_source(DUEL).core
        assert _canvas_of(render_pose_preview(core)) == canvas(core)

    def test_one_skeleton_per_actor(self):
        core = compile_source(DUEL).core
        skeletons = [name for name in _groups(render_pose_preview(core)) if name]
        assert skeletons == ["pose-alice", "pose-bob"]

    def test_a_point_wherever_the_pose_export_has_one_in_its_colour(self):
        core = compile_source(DUEL).core
        groups = _groups(render_pose_preview(core))
        for actor in core.actors:
            values = keypoints(core, actor)
            present = [
                (values[3 * index], values[3 * index + 1], OPENPOSE_COLOURS[index])
                for index in range(len(COCO_18))
                if values[3 * index + 2] > 0
            ]
            drawn = [
                (float(dot.get("cx", "")), float(dot.get("cy", "")), dot.get("fill"))
                for dot in groups[f"pose-{actor.id}"].iter(f"{SVG}circle")
            ]
            assert [(round(x, 1), round(y, 1), c) for x, y, c in present] == [
                (round(x, 1), round(y, 1), c) for x, y, c in drawn
            ]

    def test_a_limb_only_between_two_points_that_are_there(self):
        """A close-up's legs are off the panel, so are their points, so are the limbs to them."""
        core = compile_source(DUEL.replace("full_shot", "close_up")).core
        groups = _groups(render_pose_preview(core))
        for actor in core.actors:
            values = keypoints(core, actor)
            there = {index for index in range(len(COCO_18)) if values[3 * index + 2] > 0}
            expected = [
                OPENPOSE_COLOURS[number]
                for number, (start, end) in enumerate(OPENPOSE_LIMBS)
                if start in there and end in there
            ]
            limbs = [line.get("stroke") for line in groups[f"pose-{actor.id}"].iter(f"{SVG}line")]
            assert limbs == expected
            assert len(limbs) < len(OPENPOSE_LIMBS)

    def test_a_figure_a_picture_draws_has_no_skeleton(self):
        core = _figures()
        skeletons = [name for name in _groups(render_pose_preview(core)) if name]
        assert skeletons == ["pose-bob"]

    def test_the_same_panel_draws_the_same_bytes(self):
        assert render_pose_preview(compile_source(DUEL).core) == render_pose_preview(
            compile_source(DUEL).core
        )


def _boxes(core: PanelCore) -> list[dict[str, Any]]:
    return json.loads(render_boxes(core))["boxes"]


def _mask_fills(core: PanelCore) -> dict[str, str]:
    """Each region's colour in the mask, by its id."""
    fills: dict[str, str] = {}
    for element in _root(render_mask(core)).iter():
        identifier, fill = element.get("id"), element.get("fill")
        if identifier is not None and fill is not None:
            fills[identifier] = fill
    return fills


class TestTheBoxesPreview:
    def test_it_is_on_the_exports_canvas(self):
        core = compile_source(DUEL).core
        assert _canvas_of(render_boxes_preview(core)) == canvas(core)

    def test_one_rectangle_per_box_where_the_export_puts_it(self):
        core = compile_source(DUEL).core
        width, height = canvas(core)
        rectangles = [
            group.find(f"{SVG}rect")
            for name, group in _groups(render_boxes_preview(core)).items()
            if name
        ]
        assert len(rectangles) == len(_boxes(core))
        for rectangle, box in zip(rectangles, _boxes(core), strict=True):
            assert rectangle is not None
            xmin, ymin, xmax, ymax = box["box"]
            assert float(rectangle.get("x", "")) == round(xmin * width, 2)
            assert float(rectangle.get("y", "")) == round(ymin * height, 2)
            assert float(rectangle.get("width", "")) == round((xmax - xmin) * width, 2)
            assert float(rectangle.get("height", "")) == round((ymax - ymin) * height, 2)

    def test_each_box_is_labelled_with_its_phrase(self):
        core = compile_source(DUEL).core
        labels = [text.text for text in _root(render_boxes_preview(core)).iter(f"{SVG}text")]
        assert labels == [box["phrase"] for box in _boxes(core)]

    def test_each_box_is_in_its_region_s_mask_colour(self):
        """So the boxes and the mask, side by side, say who is who in one colour."""
        core = _figures()
        fills = _mask_fills(core)
        groups = _groups(render_boxes_preview(core))
        assert [name for name in groups if name] == ["box-actor-bob", "box-figure-ana"]
        for name, group in groups.items():
            if not name:
                continue
            region = name.removeprefix("box-")
            rectangle = group.find(f"{SVG}rect")
            assert rectangle is not None
            assert rectangle.get("stroke") == fills[region]

    def test_the_same_panel_draws_the_same_bytes(self):
        assert render_boxes_preview(compile_source(DUEL).core) == render_boxes_preview(
            compile_source(DUEL).core
        )
