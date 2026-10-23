"""Panel Core records the staging an export needs: joints, feature points, the camera (#72).

Each of these was solved before and thrown away: joints and feature points lived only on the
posed puppets, the camera only on `CompileResult`, who looks at whom only in the IR, and the
place and the hour only as tones. An emitter reads Core and nothing else, so each is recorded
-- and each is left out of the JSON when unused, so a Core written before them reads and writes
back byte for byte, and `format_version` stays 1.
"""

import json
from pathlib import Path

import pytest

from scenet.core import CORE_FORMAT_VERSION, CoreCamera, PanelCore
from scenet.geom import rounded
from scenet.ir import CameraAngle, ShotType, TimeOfDay
from scenet.pipeline import compile_file, compile_source
from scenet.places import Place, place_of
from tests.images import contract, png

ROOT = Path(__file__).resolve().parents[1]
#: Core documents exactly as 0.11.1 and the main branch before #72 wrote them.
OLD = ROOT / "tests" / "data" / "core-0.11.1"

DUEL = """\
camera: {shot: full_shot, angle: low}
cast:
  alice: {reference: alice, pose: pointing}
  bob: {reference: bob, pose: arms_crossed, facing: left}
staging:
  - alice left_of bob
  - alice looking_at bob
script:
  - say: {by: alice, text: "You forgot your umbrella!"}
"""


def _duel() -> PanelCore:
    return compile_source(DUEL).core


class TestJoints:
    def test_every_joint_of_the_puppet_is_recorded_where_it_was_posed(self):
        result = compile_source(DUEL)
        for actor in result.core.actors:
            posed = result.posed[actor.id].joints
            assert set(actor.joints) == set(posed)
            for name, point in posed.items():
                assert actor.joints[name] == (rounded(point.x), rounded(point.y))

    def test_the_shipped_puppets_have_sixteen(self):
        joints = _duel().actor("alice").joints
        assert sorted(joints) == sorted(
            [
                "root",
                "spine",
                "neck",
                "head",
                *(f"{part}_{side}" for part in ("shoulder", "elbow", "wrist") for side in "lr"),
                *(f"{part}_{side}" for part in ("hip", "knee", "ankle") for side in "lr"),
            ]
        )

    def test_facing_left_mirrors_them(self):
        """`_l` is screen left in the rest pose; a figure facing left has it on the right."""
        core = _duel()
        alice, bob = core.actor("alice"), core.actor("bob")
        assert not alice.transform.mirrored
        assert alice.joints["shoulder_l"][0] < alice.joints["shoulder_r"][0]
        assert bob.transform.mirrored
        assert bob.joints["shoulder_l"][0] > bob.joints["shoulder_r"][0]

    def test_they_are_written_in_the_document(self):
        payload = json.loads(_duel().to_json())
        assert payload["actors"][0]["joints"]["neck"] == list(_duel().actors[0].joints["neck"])


class TestFeatures:
    def test_every_feature_point_is_recorded(self):
        result = compile_source(DUEL)
        for actor in result.core.actors:
            features = result.posed[actor.id].features
            assert set(actor.features) == {feature.value for feature in features}
            for feature, resolved in features.items():
                centre = resolved.centre
                assert actor.features[feature.value] == (rounded(centre.x), rounded(centre.y))

    def test_they_are_there_when_the_face_is_too_small_to_draw(self):
        """Face marks go below a radius; where the eyes are does not."""
        core = compile_source(
            "{panel: {size: [400.0, 400.0]}, camera: {shot: long_shot},"
            " cast: {a: {reference: alice}}}"
        ).core
        actor = core.actor("a")
        assert actor.face_marks == ()
        assert {"eye_l", "eye_r", "nose"} <= set(actor.features)

    def test_the_expression_does_not_move_them(self):
        """Feature points are where the anatomy is; an expression moves the marks."""
        plain = compile_source("{cast: {a: {reference: alice}}}").core.actor("a")
        angry = compile_source("{cast: {a: {reference: alice, expression: angry}}}").core
        assert angry.actor("a").features == plain.features


class TestLookingAt:
    def test_whom_an_actor_looks_at(self):
        core = _duel()
        assert core.actor("alice").looking_at == "bob"
        assert core.actor("bob").looking_at is None

    def test_somebody_heard_from_off_panel(self):
        core = compile_source(
            "cast: {bob: {reference: bob}}\n"
            "staging: [bob looking_at carol]\n"
            "script:\n  - say: {by: carol, text: Hello, off_panel: left}\n"
        ).core
        assert core.actor("bob").looking_at == "carol"

    def test_it_is_left_out_of_the_document_when_nobody_is_looked_at(self):
        payload = json.loads(_duel().to_json())
        actors = {actor["id"]: actor for actor in payload["actors"]}
        assert actors["alice"]["looking_at"] == "bob"
        assert "looking_at" not in actors["bob"]


class TestCamera:
    def test_the_camera_result_is_recorded(self):
        result = compile_source(DUEL)
        camera, solved = result.core.camera, result.camera
        assert camera is not None
        assert solved is not None
        assert camera == CoreCamera(
            shot=ShotType.FULL_SHOT,
            angle=CameraAngle.LOW,
            reference=solved.reference,
            scale=rounded(solved.scale),
            headroom=rounded(solved.headroom),
            footroom=rounded(solved.footroom),
            pullback=rounded(solved.pullback),
        )

    def test_the_angle_is_the_one_asked_for(self):
        for angle in CameraAngle:
            core = compile_source(
                f"{{camera: {{angle: {angle.value}}}, cast: {{a: {{reference: alice}}}}}}"
            ).core
            assert core.camera is not None
            assert core.camera.angle is angle

    def test_a_camera_that_retreated_says_how_far(self):
        result = compile_source(
            "{panel: {size: [600.0, 400.0]}, camera: {shot: close_up},"
            " cast: {a: {reference: alice}, b: {reference: bob}}, staging: [a left_of b]}"
        )
        assert result.core.camera is not None
        assert result.core.camera.pullback < 1.0
        assert result.core.camera.shot is ShotType.CLOSE_UP

    def test_there_is_none_for_a_cast_a_picture_draws(self):
        result = _figures()
        assert result.camera is None
        assert result.core.camera is None
        assert "camera" not in json.loads(result.core.to_json())


def _figures():
    return compile_source(
        "setting: {image: art/p.png}\ncast: {ana: {figure: ana}}\n"
        "script:\n  - say: {by: ana, text: Hi.}\n",
        base={
            "art/p.png": png(800, 600),
            "art/p.art.yaml": contract(
                (800, 600), {"ana": {"face": {"center": [400, 200], "radius": 60}}}
            ),
        },
    )


class TestTheBackdrop:
    def test_a_named_place_is_recorded(self):
        backdrop = compile_source(
            "{cast: {a: {reference: alice}}, setting: {place: street, time: night}}"
        ).core.backdrop
        assert backdrop is not None
        assert backdrop.place is Place.STREET
        assert backdrop.time is TimeOfDay.NIGHT

    def test_masses_written_out_as_a_place_are_that_place(self):
        """The same matcher the description names the place by: one answer, not two."""
        written = compile_source(
            "{cast: {a: {reference: alice}}, setting: {place: docks}}"
        ).core.backdrop
        assert written is not None
        assert place_of(()) is None
        assert written.place is Place.DOCKS

    def test_masses_of_no_place_have_none(self):
        backdrop = compile_source(
            "{cast: {a: {reference: alice}}, setting: {masses: [{kind: wall}]}}"
        ).core.backdrop
        assert backdrop is not None
        assert backdrop.place is None
        assert backdrop.time is TimeOfDay.DAY
        assert (
            "place"
            not in json.loads(
                compile_source(
                    "{cast: {a: {reference: alice}}, setting: {masses: [{kind: wall}]}}"
                ).core.to_json()
            )["backdrop"]
        )

    def test_the_hour_of_a_clear_sky_is_recorded(self):
        """The atmosphere is None in clear weather, and it was the only record of the hour."""
        backdrop = compile_source(
            "{cast: {a: {reference: alice}}, setting: {place: field, time: dusk}}"
        ).core.backdrop
        assert backdrop is not None
        assert backdrop.atmosphere is None
        assert backdrop.time is TimeOfDay.DUSK

    def test_nothing_is_said_of_a_picture_s_place_or_hour(self):
        """They are in the picture, which the compiler has never seen."""
        backdrop = _figures().core.backdrop
        assert backdrop is not None
        assert backdrop.image is not None
        assert backdrop.place is None
        assert backdrop.time is None


class TestOldDocuments:
    @pytest.mark.parametrize("path", sorted(OLD.glob("*.core.json")), ids=lambda path: path.name)
    def test_a_core_written_before_reads_and_writes_as_it_did(self, path: Path):
        text = path.read_text(encoding="utf-8")
        core = PanelCore.from_json(text)
        assert core.to_json() == text
        assert core.camera is None
        assert all(actor.joints == {} and actor.features == {} for actor in core.actors)

    def test_there_are_old_documents_to_read(self):
        names = {path.name for path in OLD.glob("*.core.json")}
        assert len(names) >= 5

    def test_the_format_version_is_still_one(self):
        assert CORE_FORMAT_VERSION == 1
        assert json.loads(_duel().to_json())["format_version"] == 1


class TestTheGallery:
    def test_every_puppet_panel_records_its_camera_and_joints(self):
        result = compile_file(ROOT / "examples" / "duel.panel.yaml")
        assert result.core.camera is not None
        assert all(actor.joints for actor in result.core.actors)
