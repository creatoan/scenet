"""A panel's description: what it shows, in words, for a reader who cannot see it.

Written as `description:` in YAML, or kept from a comic script's prose, which is already a
text rendering of the panel. It is carried, never interpreted -- the compiler draws nothing
from it -- and it is what accessible output (#76) reads out, so the rules that matter are
the ones that keep it from being silently wrong: it describes one panel, so it is not a
default a scene's panels inherit, and a panel drawn `over:` another is a different picture
and does not inherit its parent's.
"""

import pytest
import yaml
from jsonschema import Draft202012Validator

from scenet.diagnostics import Diagnostic, diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_panel, parse_scene
from scenet.schema import panel_schema, scene_schema

CAST = "cast: {alice: {reference: alice}}\n"

SCENE = """\
cast: {alice: {reference: alice}}
panels:
  first:
    description: Alice waits in the rain.
  second:
    over: first
"""

FRONT = "---\ncast: {ALICE: {reference: alice}}\n---\n"


def _script(body: str, front: str = FRONT) -> str:
    return f"{front}{body}"


def _only(findings: list[Diagnostic]) -> Diagnostic:
    assert len(findings) == 1, [(item.rule, item.message) for item in findings]
    return findings[0]


class TestInYaml:
    def test_it_is_kept_as_written(self):
        assert parse_panel(f"{CAST}description: Alice waits.").description == "Alice waits."

    def test_without_one_there_is_none(self):
        assert parse_panel(CAST).description is None
        assert parse_panel(f"{CAST}description: null").description is None

    def test_whitespace_is_read_as_one_space(self):
        """A block scalar's line breaks are how it was typed, not part of what it says."""
        source = f"{CAST}description: |\n  Alice waits.\n\n  Bob   arrives,\tlate.\n"
        assert parse_panel(source).description == "Alice waits. Bob arrives, late."

    def test_a_word_processors_line_break_is_whitespace_too(self):
        """Word writes a manual line break as U+000B and a page break as U+000C."""
        source = f'{CAST}description: "Alice waits.\\vBob arrives.\\fThe end."'
        assert parse_panel(source).description == "Alice waits. Bob arrives. The end."

    @pytest.mark.parametrize("blank", ['""', '"   "', "|\n  \n"])
    def test_a_blank_one_is_refused(self, blank: str):
        with pytest.raises(PanelSyntaxError, match="leave it out to have one generated"):
            parse_panel(f"{CAST}description: {blank}")

    def test_a_blank_one_is_one_finding_at_the_key(self):
        finding = _only(diagnose_source(f'{CAST}description: "  "\n'))
        assert finding.rule == "invalid-field"
        assert finding.path == ("description",)
        assert finding.region is not None
        assert finding.region.start.line == 2

    def test_a_character_an_svg_cannot_hold_is_one_finding(self):
        finding = _only(diagnose_source(f'{CAST}description: "Alice \\a waits."\n'))
        assert finding.rule == "invalid-field"
        assert finding.path == ("description",)
        assert "U+0007" in finding.message

    @pytest.mark.parametrize("value", ["{text: Alice waits.}", "[Alice, waits]", "5"])
    def test_anything_but_text_is_one_finding(self, value: str):
        finding = _only(diagnose_source(f"{CAST}description: {value}\n"))
        assert finding.rule == "invalid-field"
        assert finding.path == ("description",)

    def test_prose_written_as_the_setting_points_at_it(self):
        """The one place the language refused prose now says where prose belongs."""
        with pytest.raises(PanelSyntaxError, match="description:"):
            parse_panel(f"{CAST}setting: a rainy street corner at midnight")


class TestInAScene:
    def test_each_panel_has_its_own(self):
        panels = parse_scene(SCENE.replace("    over: first\n", "    description: Later.\n"))
        assert panels["first"].description == "Alice waits in the rain."
        assert panels["second"].description == "Later."

    def test_a_panel_drawn_over_another_does_not_inherit_it(self):
        """A different picture: its parent's words would be wrong to the reader who
        cannot see that they are."""
        panels = parse_scene(SCENE)
        assert panels["first"].description == "Alice waits in the rain."
        assert panels["second"].description is None

    def test_one_over_one_over_one_inherits_none_either(self):
        source = SCENE + "  third:\n    over: second\n"
        assert parse_scene(source)["third"].description is None

    def test_it_writes_its_own_over_a_parent(self):
        source = SCENE + "    description: She gives up.\n"
        assert parse_scene(source)["second"].description == "She gives up."

    def test_checking_agrees(self):
        assert diagnose_source(SCENE) == []

    def test_beside_panels_it_is_refused(self):
        source = "description: Alice waits.\n" + SCENE
        with pytest.raises(PanelSyntaxError, match="describes one panel") as raised:
            parse_scene(source)
        assert raised.value.rule == "unknown-key"
        assert raised.value.loc == ("description",)

    def test_beside_panels_it_is_one_finding_where_it_is_written(self):
        source = "cast: {alice: {reference: alice}}\ndescription: Alice waits.\n" + "\n".join(
            SCENE.split("\n")[1:]
        )
        finding = _only(diagnose_source(source))
        assert finding.rule == "unknown-key"
        assert finding.path == ("description",)
        assert "describes one panel" in finding.message
        assert finding.region is not None
        assert finding.region.start.line == 2

    def test_the_scene_schema_does_not_offer_it_as_a_default(self):
        schema = scene_schema()
        assert "description" not in schema["properties"]
        member = schema["properties"]["panels"]["additionalProperties"]
        assert "description" in member["properties"]
        errors = list(Draft202012Validator(schema).iter_errors(yaml.safe_load("description: x\n")))
        assert errors

    def test_the_panel_schema_offers_it(self):
        description = panel_schema()["properties"]["description"]
        assert "reader who cannot see" in description["description"]
        validator = Draft202012Validator(panel_schema())
        assert not list(validator.iter_errors({"description": "Alice waits."}))


class TestInAComicScript:
    def test_the_prose_is_the_description(self):
        body = (
            "PANEL 1\nAlice and Bob face each other on a rainy street corner.\n"
            "She is exasperated.\n\nALICE\nYou forgot your umbrella!\n"
        )
        assert parse_script(_script(body))["1"].description == (
            "Alice and Bob face each other on a rainy street corner. She is exasperated."
        )

    def test_a_panel_with_no_prose_has_none(self):
        assert parse_script(_script("PANEL 1\nALICE\nHi.\n"))["1"].description is None

    def test_written_on_the_heading_line_as_dark_horse_does(self):
        body = "Panel 1. Alice on a corner.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == "Alice on a corner."

    def test_both_on_the_heading_and_under_it(self):
        body = "Panel 1. Alice on a corner.\nIt is raining.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == "Alice on a corner. It is raining."

    def test_in_french(self):
        body = "CASE 1 : Le port, la nuit.\n\nALICE\nSalut.\n"
        assert parse_script(_script(body))["1"].description == "Le port, la nuit."

    def test_markdown_emphasis_is_taken_off(self):
        """A screen reader would read the markers out: "star star Alice star star"."""
        body = "PANEL 1\n**Alice** looks _up_ at *Bob*, __slowly__.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == "Alice looks up at Bob, slowly."

    def test_an_underscore_inside_a_word_is_a_letter(self):
        body = "PANEL 1\nThe sign says snake_case_name and 2*3*4.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == (
            "The sign says snake_case_name and 2*3*4."
        )

    def test_a_note_to_the_artist_is_prose_too(self):
        """Everything the prose says is read; `@description:` is how to say something else."""
        body = "PANEL 1\nNOTE: redraw the rain.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == "NOTE: redraw the rain."

    def test_a_description_directive_wins_over_the_prose(self):
        body = "PANEL 1\n@description: Alice, alone.\nNOTE: redraw the rain.\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == "Alice, alone."

    @pytest.mark.parametrize(
        "written", ["9:14, and Alice waves.", "Alice: waves.", "yes", "#3 fan", "[draft]"]
    )
    def test_a_description_directive_is_kept_as_written(self, written: str):
        """Not read as YAML: `9:14` would be the number 554, `yes` true, `#3` nothing."""
        body = f"PANEL 1\n@description: {written}\n\nALICE\nHi.\n"
        assert parse_script(_script(body))["1"].description == written

    def test_a_panel_drawn_over_another_does_not_inherit_its_prose(self):
        body = "PANEL 1\nAlice waits.\n\nALICE\nHi.\n\nPANEL 2\n@over: 1\n\nALICE\nStill here.\n"
        panels = parse_script(_script(body))
        assert panels["1"].description == "Alice waits."
        assert panels["2"].description is None

    def test_a_character_an_svg_cannot_hold_is_one_finding_at_its_line(self):
        body = "PANEL 1\nAlice waits.\nIt rains \x07 hard.\n\nALICE\nHi.\n"
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script(_script(body))
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 6)
        finding = _only(diagnose_script(_script(body)))
        assert finding.rule == "invalid-field"
        assert finding.region is not None
        assert finding.region.start.line == 6

    def test_on_the_heading_line_too(self):
        body = "Panel 1. Alice \x07 waits.\n\nALICE\nHi.\n"
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script(_script(body))
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 4)

    def test_in_the_front_matter_it_is_refused_at_its_line(self):
        front = "---\ncast: {ALICE: {reference: alice}}\ndescription: Alice waits.\n---\n"
        body = "PANEL 1\nALICE\nHi.\n"
        with pytest.raises(ScriptSyntaxError, match="describes one panel") as raised:
            parse_script(_script(body, front))
        assert (raised.value.rule, raised.value.line) == ("unknown-key", 3)
        finding = _only(diagnose_script(_script(body, front)))
        assert finding.rule == "unknown-key"
        assert finding.region is not None
        assert finding.region.start.line == 3
