"""A `null` in an override leaves an inherited cast member out of that panel.

Until now a panel could add to what it inherits and change it, but never take anything
away: `merge` replaces and recurses, and a scene's shared cast was in every panel whether
it belonged there or not. JSON Merge Patch (RFC 7386) settled this long ago: "If the value
is null, remove". So `cast: {bob: null}` takes Bob out of that panel, and the staging
relations that name him with him -- each with a `dropped-relation` note, as a comic
script's `(OP)` already does.
"""

import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from scenet import compile_book, compile_script
from scenet.compose import merge, settle
from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.frontends.yaml_front import parse_panel, parse_scene
from scenet.ir import SayEvent, Side
from scenet.schema import panel_schema, scene_schema

SCENE = """\
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third}
staging:
  - alice left_of bob
  - alice looking_at bob
panels:
  both:
    script: [{say: {by: alice, text: Hi.}}]
  alone:
    over: both
    cast: {bob: null}
"""


class TestMerge:
    def test_a_null_survives_the_merge_to_remove_what_lies_beneath(self):
        """Kept until the document is complete, so a member a panel has from the
        scene's defaults is removed as surely as one it has from the panel it is over."""
        merged = merge({"cast": {"bob": {"pose": "idle"}}}, {"cast": {"bob": None}})
        assert merged == {"cast": {"bob": None}}
        assert merge({"cast": {"bob": {"reference": "bob"}}}, merged)["cast"] == {"bob": None}

    def test_settling_removes_it(self):
        settled, dropped = settle({"cast": {"alice": {"reference": "alice"}, "bob": None}})
        assert settled == {"cast": {"alice": {"reference": "alice"}}}
        assert dropped == ()

    def test_settling_drops_the_relations_that_name_who_left(self):
        document = {
            "cast": {"alice": {}, "bob": None, "carol": {}},
            "staging": ["alice left_of carol", "bob left_of carol", "carol looking_at bob"],
        }
        settled, dropped = settle(document)
        assert settled["staging"] == ["alice left_of carol"]
        assert [(item.index, item.actor) for item in dropped] == [(1, "bob"), (2, "bob")]

    def test_a_null_inside_a_list_is_left_alone(self):
        """Merge Patch reaches into mappings only; a list is a value, replaced whole."""
        settled, _ = settle({"script": [{"say": {"by": "a", "text": "Hi.", "prefer": None}}]})
        assert settled["script"][0]["say"]["prefer"] is None


class TestAScene:
    def test_the_panel_has_everyone_but_him(self):
        panels = parse_scene(SCENE)
        assert set(panels["both"].cast) == {"alice", "bob"}
        assert set(panels["alone"].cast) == {"alice"}
        assert panels["alone"].staging == ()

    def test_from_the_scenes_own_cast_too(self):
        """Bob is a default here, not something `both` wrote: the null still reaches him."""
        source = SCENE.replace("    over: both\n", "")
        assert set(parse_scene(source)["alone"].cast) == {"alice"}

    def test_through_a_panel_that_changed_him(self):
        source = SCENE.replace(
            "    script: [{say: {by: alice, text: Hi.}}]\n",
            "    cast: {bob: {pose: arms_crossed}}\n    script: [{say: {by: alice, text: Hi.}}]\n",
        )
        assert set(parse_scene(source)["alone"].cast) == {"alice"}

    def test_check_notes_each_relation_dropped(self):
        found = diagnose_source(SCENE)
        assert {(item.rule, item.level) for item in found} == {("dropped-relation", "note")}
        assert [item.path for item in found] == [("panels", "alone", "cast", "bob")] * 2
        assert "alice looking_at bob" in found[1].message

    def test_a_panel_that_removes_him_alone_is_not_noted(self):
        source = SCENE.replace("staging:\n  - alice left_of bob\n  - alice looking_at bob\n", "")
        assert diagnose_source(source) == []

    def test_a_single_panel_may_write_it_too(self):
        panel = parse_panel("cast: {alice: {reference: alice}, bob: null}")
        assert set(panel.cast) == {"alice"}


class TestAScript:
    SCRIPT = (
        "---\ncast:\n  ALICE: {reference: alice}\n  BOB: {reference: bob}\n"
        "staging: [ALICE left_of BOB]\n---\n"
        "PANEL 1\nALICE\nHi.\n\nPANEL 2\n@cast: {BOB: null}\nALICE\nAlone.\n"
    )

    def test_cast_null_leaves_him_out_of_that_panel(self):
        book = compile_script(self.SCRIPT)
        assert {actor.id for actor in book.panels["1"].core.actors} == {"ALICE", "BOB"}
        assert {actor.id for actor in book.panels["2"].core.actors} == {"ALICE"}

    def test_with_a_note_at_the_cast_line(self):
        (found,) = diagnose_script(self.SCRIPT)
        assert (found.rule, found.level) == ("dropped-relation", "note")
        assert found.region is not None
        assert found.region.start.line == 12


class TestTheSchema:
    def test_a_null_cast_member_is_valid(self):
        for schema, source in (
            (scene_schema(), SCENE),
            (panel_schema(), "cast: {alice: {reference: alice}, bob: null}"),
        ):
            errors = list(Draft202012Validator(schema).iter_errors(yaml.safe_load(source)))
            assert errors == [], [error.message for error in errors]

    def test_and_says_what_it_does(self):
        text = json.dumps(panel_schema()["properties"]["cast"])
        assert "null" in text
        assert "leaves" in text.lower()


HEARD = """\
cast:
  bob: {reference: bob, at: right_third}
  carol: {reference: alice, at: left_third}
staging:
  - bob looking_at carol
  - carol left_of bob
panels:
  both:
    script: [{say: {by: carol, text: Hello.}}]
  heard:
    cast: {carol: null}
    script: [{say: {by: carol, text: Over here!, off_panel: true}}]
"""


class TestHeardFromOffPanel:
    """Left out, then heard from off panel: as a comic script's `CAROL (OP)` has it.

    She is in the scene, not in the frame, so `bob looking_at carol` still holds -- Bob
    turns toward the side she is heard from -- and her tail ends on the side she was
    written to stand on. Everything else that names her goes, as before (#258).
    """

    LOOK = {"subject": "bob", "predicate": "looking_at", "object": "carol"}

    @staticmethod
    def document(*staging: object, off_panel: object = True) -> dict[str, object]:
        return {
            "cast": {"bob": {}, "carol": None},
            "staging": list(staging),
            "script": [{"say": {"by": "carol", "text": "Hi.", "off_panel": off_panel}}],
        }

    @pytest.mark.parametrize("look", ["bob looking_at carol", LOOK])
    def test_settling_keeps_a_look_at_her(self, look: object):
        settled, dropped = settle(self.document(look, "carol left_of bob"))
        assert settled["staging"] == [look]
        assert [item.relation for item in dropped] == ["carol left_of bob"]

    def test_only_while_she_is_heard_from_off_panel(self):
        document = self.document("bob looking_at carol")
        document["script"] = []
        settled, dropped = settle(document)
        assert settled["staging"] == []
        assert [item.actor for item in dropped] == ["carol"]

    def test_not_by_somebody_left_out_too(self):
        document = self.document("bob looking_at carol")
        document["cast"] = {"bob": None, "carol": None}
        settled, dropped = settle(document)
        assert settled["staging"] == []
        assert [item.actor for item in dropped] == ["bob"]

    def test_her_line_ends_on_the_side_she_stood(self):
        beneath = {"cast": {"bob": {}, "carol": {"at": "left_third"}}}
        settled, _ = settle(self.document(), beneath=beneath)
        assert settled["script"][0]["say"]["off_panel"] == "left"

    @pytest.mark.parametrize(
        ("off_panel", "at", "side"),
        [("right", "left_third", "right"), (True, "center", True), (True, None, True)],
    )
    def test_unless_a_side_is_named_or_she_stood_on_neither(
        self, off_panel: object, at: str | None, side: object
    ):
        beneath = {"cast": {"carol": {"at": at} if at else {}}}
        settled, _ = settle(self.document(off_panel=off_panel), beneath=beneath)
        assert settled["script"][0]["say"]["off_panel"] == side

    def test_with_nothing_beneath_it_is_left_as_written(self):
        settled, _ = settle(self.document())
        assert settled["script"][0]["say"]["off_panel"] is True

    def test_in_a_scene(self):
        panel = parse_scene(HEARD)["heard"]
        assert set(panel.cast) == {"bob"}
        assert [(item.subject, item.predicate.value, item.object) for item in panel.staging] == [
            ("bob", "looking_at", "carol")
        ]
        (line,) = panel.script
        assert isinstance(line, SayEvent)
        assert line.off_panel == Side.LEFT

    def test_bob_looks_her_way(self):
        (bob,) = compile_book(HEARD).panels["heard"].core.actors
        assert bob.gaze_aim is not None
        assert bob.gaze_aim[0] == pytest.approx(-1.0)  # she stood at left_third

    def test_from_wherever_she_was_written_to_stand(self):
        """Cast by the panel it is over, not by the scene: still found."""
        source = (
            "cast:\n  bob: {reference: bob, at: center}\n"
            "staging: [bob looking_at carol]\n"
            "panels:\n"
            "  both:\n"
            "    cast: {carol: {reference: alice, at: right_third}}\n"
            "    script: [{say: {by: carol, text: Hello.}}]\n"
            "  heard:\n"
            "    over: both\n"
            "    cast: {carol: null}\n"
            "    script: [{say: {by: carol, text: Over here!, off_panel: true}}]\n"
        )
        (line,) = parse_scene(source)["heard"].script
        assert isinstance(line, SayEvent)
        assert line.off_panel == Side.RIGHT

    def test_only_what_cannot_hold_is_noted(self):
        found = diagnose_source(HEARD)
        assert [(item.rule, item.path) for item in found] == [
            ("dropped-relation", ("panels", "heard", "cast", "carol"))
        ]
        assert "carol left_of bob" in found[0].message

    def test_in_a_script_too(self):
        """`@cast: {CAROL: null}` leaves her out; it does not draw her."""
        script = (
            "---\ncast:\n"
            "  BOB: {reference: bob, at: right_third}\n"
            "  CAROL: {reference: alice, at: left_third}\n"
            "staging: [BOB looking_at CAROL]\n---\n"
            "PANEL 1\nCAROL\nHello.\n\n"
            "PANEL 2\n@cast: {CAROL: null}\nCAROL (OP)\nOver here!\n"
        )
        assert diagnose_script(script) == []
        panel = compile_script(script).panels["2"]
        (bob,) = panel.core.actors
        assert bob.gaze_aim is not None
        assert bob.gaze_aim[0] == pytest.approx(-1.0)
        (balloon,) = panel.core.balloons
        assert balloon.off_panel == Side.LEFT
