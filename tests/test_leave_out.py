"""A `null` in an override leaves an inherited cast member out of that panel.

Until now a panel could add to what it inherits and change it, but never take anything
away: `merge` replaces and recurses, and a scene's shared cast was in every panel whether
it belonged there or not. JSON Merge Patch (RFC 7386) settled this long ago: "If the value
is null, remove". So `cast: {bob: null}` takes Bob out of that panel, and the staging
relations that name him with him -- each with a `dropped-relation` note, as a comic
script's `(OP)` already does.
"""

import json

import yaml
from jsonschema import Draft202012Validator

from scenet import compile_script
from scenet.compose import merge, settle
from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.frontends.yaml_front import parse_panel, parse_scene
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
