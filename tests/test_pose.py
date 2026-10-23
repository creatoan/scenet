"""The pose export: each actor's skeleton as OpenPose COCO-18 JSON (#72).

What ControlNet's OpenPose tooling reads: `people[].pose_keypoints_2d`, flat `x, y,
confidence` triplets in COCO-18 order, on a canvas `canvas_width` by `canvas_height`. The one
thing that cannot be got wrong silently is left and right: Scenet names joints by the side of
the screen they are on in the rest pose, OpenPose by the subject's own side, and a swap would
hand a model every figure turned away from the reader.
"""

import json
import math
from typing import Any

import pytest

from scenet.core import PanelCore
from scenet.emit.pose import COCO_18, render_pose
from scenet.pipeline import compile_source
from tests.images import contract, png

#: A full shot, so every joint is inside the panel. Alice faces right, Bob left.
DUEL = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot}
cast:
  alice: {reference: alice, pose: pointing}
  bob: {reference: bob, pose: standing_neutral, facing: left}
staging: [alice left_of bob]
"""


def _people(core: PanelCore) -> list[list[float]]:
    payload: Any = json.loads(render_pose(core))
    return [person["pose_keypoints_2d"] for person in payload["people"]]


def _points(keypoints: list[float]) -> dict[str, tuple[float, float, float]]:
    return {
        name: (keypoints[3 * index], keypoints[3 * index + 1], keypoints[3 * index + 2])
        for index, name in enumerate(COCO_18)
    }


def _duel() -> PanelCore:
    return compile_source(DUEL).core


def _person(core: PanelCore, actor: str) -> dict[str, tuple[float, float, float]]:
    index = [each.id for each in core.actors].index(actor)
    return _points(_people(core)[index])


class TestTheFormat:
    def test_coco_18_names_its_points_in_openpose_s_order(self):
        assert COCO_18 == (
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

    def test_one_person_per_actor_with_fifty_four_numbers(self):
        core = _duel()
        people = _people(core)
        assert len(people) == len(core.actors) == 2
        assert all(len(keypoints) == 54 for keypoints in people)

    def test_the_document_is_what_the_tooling_reads(self):
        payload = json.loads(render_pose(_duel()))
        assert sorted(payload) == ["canvas_height", "canvas_width", "people"]
        assert payload["canvas_width"] == 1000
        assert payload["canvas_height"] == 800
        assert all(sorted(person) == ["pose_keypoints_2d"] for person in payload["people"])

    def test_the_canvas_is_the_panel_rounded_up_to_whole_pixels(self):
        core = _duel().model_copy(update={"width": 600.25, "height": 599.0})
        payload = json.loads(render_pose(core))
        assert (payload["canvas_width"], payload["canvas_height"]) == (601, 599)

    def test_it_is_written_as_panel_core_is(self):
        text = render_pose(_duel())
        assert text.endswith("}\n")
        assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
        assert render_pose(_duel()) == text

    def test_people_follow_panel_core_s_actors(self):
        core = _duel()
        for actor, keypoints in zip(core.actors, _people(core), strict=True):
            assert _points(keypoints)["neck"][:2] == actor.joints["neck"]


class TestEachPointComesFromItsJoint:
    def test_facing_right(self):
        """Unmirrored, `_l` is on the screen's left: the subject's right, facing the reader."""
        core = _duel()
        alice = core.actor("alice")
        assert not alice.transform.mirrored
        points = _person(core, "alice")
        expected = {
            "nose": alice.features["nose"],
            "neck": alice.joints["neck"],
            "right_shoulder": alice.joints["shoulder_l"],
            "right_elbow": alice.joints["elbow_l"],
            "right_wrist": alice.joints["wrist_l"],
            "left_shoulder": alice.joints["shoulder_r"],
            "left_elbow": alice.joints["elbow_r"],
            "left_wrist": alice.joints["wrist_r"],
            "right_hip": alice.joints["hip_l"],
            "right_knee": alice.joints["knee_l"],
            "right_ankle": alice.joints["ankle_l"],
            "left_hip": alice.joints["hip_r"],
            "left_knee": alice.joints["knee_r"],
            "left_ankle": alice.joints["ankle_r"],
            "right_eye": alice.features["eye_l"],
            "left_eye": alice.features["eye_r"],
        }
        for name, point in expected.items():
            assert points[name] == (*point, 1.0), name

    def test_facing_left(self):
        """Mirrored, `_r` is on the screen's left, and that is the subject's right."""
        core = _duel()
        bob = core.actor("bob")
        assert bob.transform.mirrored
        points = _person(core, "bob")
        for side, suffix in (("right", "r"), ("left", "l")):
            for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
                assert points[f"{side}_{joint}"][:2] == bob.joints[f"{joint}_{suffix}"]
            assert points[f"{side}_eye"][:2] == bob.features[f"eye_{suffix}"]

    @pytest.mark.parametrize("actor", ["alice", "bob"])
    def test_the_subject_s_right_is_on_the_screen_s_left_either_way(self, actor: str):
        """A body facing the reader: its right shoulder, hip and eye are on the reader's left."""
        points = _person(_duel(), actor)
        for part in ("shoulder", "hip", "eye"):
            assert points[f"right_{part}"][0] < points[f"left_{part}"][0], part

    def test_alice_points_with_her_left_hand(self):
        """`pointing` raises `wrist_r`, toward the way she faces: her left, facing right."""
        core = _duel()
        points = _person(core, "alice")
        assert points["left_wrist"][:2] == core.actor("alice").joints["wrist_r"]
        assert points["left_wrist"][0] > points["left_shoulder"][0]


class TestWhatIsMissing:
    def test_ears_are_never_drawn_so_never_detected(self):
        for keypoints in _people(_duel()):
            points = _points(keypoints)
            assert points["right_ear"] == points["left_ear"] == (0.0, 0.0, 0.0)

    def test_root_spine_and_head_have_no_counterpart(self):
        core = _duel()
        alice = core.actor("alice")
        found = {point[:2] for point in _person(core, "alice").values()}
        for joint in ("root", "spine", "head"):
            assert alice.joints[joint] not in found

    def test_a_joint_the_puppet_does_not_name_is_missing(self):
        core = _duel()
        alice = core.actor("alice")
        joints = {name: point for name, point in alice.joints.items() if name != "knee_l"}
        core = core.model_copy(
            update={"actors": (alice.model_copy(update={"joints": joints}), *core.actors[1:])}
        )
        assert _person(core, "alice")["right_knee"] == (0.0, 0.0, 0.0)

    def test_a_medium_shot_crops_the_legs(self):
        core = compile_source(DUEL.replace("full_shot", "medium_shot")).core
        points = _person(core, "alice")
        for name in ("right_knee", "left_knee", "right_ankle", "left_ankle"):
            assert points[name] == (0.0, 0.0, 0.0), name
        assert points["neck"][2] == 1.0

    @pytest.mark.parametrize(
        ("where", "kept"),
        [
            ((0.0, 0.0), True),
            ((1000.0, 800.0), True),
            ((1000.01, 400.0), False),
            ((500.0, 800.01), False),
            ((-0.01, 400.0), False),
            ((500.0, -0.01), False),
        ],
    )
    def test_the_edge_of_the_panel_is_inside_it(self, where: tuple[float, float], kept: bool):
        core = _duel()
        alice = core.actor("alice")
        moved = alice.model_copy(update={"joints": {**alice.joints, "neck": where}})
        core = core.model_copy(update={"actors": (moved, *core.actors[1:])})
        expected = (*where, 1.0) if kept else (0.0, 0.0, 0.0)
        assert _person(core, "alice")["neck"] == expected

    def test_a_slanted_edge_crops_like_the_frame(self):
        """A panel in a slanted tier is drawn clipped to its outline."""
        core = _duel()
        alice = core.actor("alice")
        x, y = alice.joints["neck"]
        outline = ((0.0, 0.0), (x - 1.0, 0.0), (x - 1.0, 800.0), (0.0, 800.0))
        cropped = _person(core.model_copy(update={"outline": outline}), "alice")
        assert cropped["neck"] == (0.0, 0.0, 0.0)
        whole = ((0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0), (0.0, 800.0))
        assert _person(core.model_copy(update={"outline": whole}), "alice")["neck"] == (
            x,
            y,
            1.0,
        )

    def test_a_core_written_before_joints_gives_a_person_of_zeros(self):
        """So `people` still lines up with `actors`."""
        core = _duel()
        old = core.model_copy(
            update={
                "actors": tuple(
                    actor.model_copy(update={"joints": {}, "features": {}}) for actor in core.actors
                )
            }
        )
        people = _people(old)
        assert len(people) == 2
        assert all(value == 0.0 for keypoints in people for value in keypoints)


class TestFiguresAPictureDraws:
    def test_have_no_pose(self):
        """Nobody posed them: the picture draws them, and there is no skeleton to export."""
        core = compile_source(
            "setting: {image: art/p.png}\ncast: {ana: {figure: ana}}\n",
            base={
                "art/p.png": png(800, 600),
                "art/p.art.yaml": contract(
                    (800, 600), {"ana": {"face": {"center": [400, 200], "radius": 60}}}
                ),
            },
        ).core
        payload = json.loads(render_pose(core))
        assert payload["people"] == []
        assert payload["canvas_width"] == 1000


class TestReadingDirection:
    def test_a_panel_read_right_to_left_has_the_same_pose(self):
        """The scene is never mirrored: only what reading decides follows `direction`."""
        source = DUEL + "script:\n  - say: {by: alice, text: Hi.}\n  - say: {by: bob, text: Yes.}\n"
        ltr = compile_source(source).core
        rtl = compile_source("direction: rtl\n" + source).core
        assert render_pose(rtl) == render_pose(ltr)


def test_every_coordinate_is_a_number_on_the_canvas():
    payload = json.loads(render_pose(_duel()))
    for person in payload["people"]:
        for x, y, confidence in zip(*[iter(person["pose_keypoints_2d"])] * 3, strict=True):
            assert confidence in (0.0, 1.0)
            assert math.isfinite(x)
            assert math.isfinite(y)
            assert 0.0 <= x <= payload["canvas_width"]
            assert 0.0 <= y <= payload["canvas_height"]
