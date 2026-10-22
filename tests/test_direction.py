"""Which way a comic is read (#68): `direction: ltr | rtl`, the whole document's.

Progression direction, not text direction: a manga translated into English still reads
right to left, while the words in each balloon read left to right. It is written once for
the whole document -- a single panel, a scene beside its `panels:`, a comic script in its
front matter -- and a panel may not have one of its own, because a page read right to left
holding a panel read left to right has no reading a reader could follow.
"""

import json
from pathlib import Path

import pytest

from scenet import (
    Direction,
    PageCore,
    PanelCore,
    compile_book,
    compile_source,
    parse_panel,
    parse_scene,
)
from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.frontends.script_front import ScriptSyntaxError, parse_script_document
from scenet.frontends.yaml_front import parse_scene_document

CAST = "cast: {alice: {reference: alice, at: left_third}, bob: {reference: bob, at: right_third}}\n"

SCENE = (
    "direction: rtl\n"
    + CAST
    + "pages: [{tiers: [{panels: [one, two]}]}]\n"
    + "panels:\n"
    + "  one: {script: [{say: {by: alice, text: Hello.}}]}\n"
    + "  two: {over: one}\n"
)

SCRIPT = """---
direction: rtl
cast:
  ALICE: {reference: alice, at: left_third}
---

PAGE ONE

PANEL 1

ALICE
Hello.

PANEL 2

ALICE
Again.
"""


class TestTheKey:
    def test_left_to_right_is_the_default(self):
        assert parse_panel(CAST).direction is Direction.LTR

    @pytest.mark.parametrize("written", ["ltr", "rtl"])
    def test_a_single_panel_writes_it_at_the_top(self, written: str):
        assert parse_panel(f"direction: {written}\n{CAST}").direction is Direction(written)

    def test_a_value_it_does_not_know_is_invalid_at_the_key(self):
        (found,) = diagnose_source(f"direction: sideways\n{CAST}")
        assert (found.rule, found.path) == ("invalid-field", ("direction",))

    def test_every_panel_of_a_scene_inherits_it(self):
        panels = parse_scene(SCENE)
        assert {name: panel.direction for name, panel in panels.items()} == {
            "one": Direction.RTL,
            "two": Direction.RTL,
        }

    def test_a_scene_document_reads_in_its_panels_direction(self):
        assert parse_scene_document(SCENE).direction is Direction.RTL
        assert parse_scene_document(CAST).direction is Direction.LTR

    def test_a_bad_value_beside_panels_is_one_finding_at_it(self):
        found = diagnose_source(SCENE.replace("direction: rtl", "direction: up"))
        assert [(item.rule, item.path) for item in found] == [("invalid-field", ("direction",))]


class TestAPanelHasNoDirectionOfItsOwn:
    @pytest.mark.parametrize("value", ["rtl", "ltr", "null"])
    def test_a_scene_panel_writing_it_is_refused(self, value: str):
        text = SCENE.replace("two: {over: one}", f"two: {{over: one, direction: {value}}}")
        with pytest.raises(PanelSyntaxError) as raised:
            parse_scene(text)
        assert raised.value.rule == "panel-direction"
        assert raised.value.loc == ("panels", "two", "direction")

    def test_check_reports_it_once_where_it_is_written(self):
        text = SCENE.replace("two: {over: one}", "two: {over: one, direction: ltr}")
        (found,) = diagnose_source(text, source=Path("x.scene.yaml"))
        assert (found.rule, found.path) == ("panel-direction", ("panels", "two", "direction"))
        assert found.region is not None
        assert found.region.start.line == 6

    def test_check_still_finds_a_fault_in_another_panel(self):
        text = SCENE.replace(
            "two: {over: one}", "two: {direction: ltr, script: [{say: {by: carol, text: Hi.}}]}"
        )
        rules = sorted(item.rule for item in diagnose_source(text))
        assert rules == ["panel-direction", "unknown-actor"]

    def test_a_script_directive_is_refused_at_its_line(self):
        text = SCRIPT.replace("PANEL 2\n", "PANEL 2\n@direction: ltr\n")
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text)
        assert (raised.value.rule, raised.value.line) == ("panel-direction", 15)
        (found,) = diagnose_script(text)
        assert found.rule == "panel-direction"
        assert found.region is not None
        assert found.region.start.line == 15


class TestAComicScript:
    def test_the_front_matter_sets_it_for_every_panel(self):
        document = parse_script_document(SCRIPT)
        assert {panel.direction for panel in document.panels.values()} == {Direction.RTL}
        assert document.direction is Direction.RTL

    def test_without_it_a_script_reads_left_to_right(self):
        document = parse_script_document(SCRIPT.replace("direction: rtl\n", ""))
        assert document.direction is Direction.LTR

    def test_a_bad_value_is_found_at_its_own_line(self):
        text = SCRIPT.replace("direction: rtl", "direction: backwards")
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text)
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 2)
        (found,) = diagnose_script(text)
        assert found.region is not None
        assert (found.rule, found.region.start.line) == ("invalid-field", 2)


class TestCore:
    def test_a_left_to_right_core_does_not_say_so(self):
        core = compile_source(CAST).core
        assert core.direction is Direction.LTR
        assert "direction" not in json.loads(core.to_json())

    def test_a_right_to_left_core_records_it(self):
        core = compile_source(f"direction: rtl\n{CAST}").core
        assert json.loads(core.to_json())["direction"] == "rtl"
        restored = PanelCore.from_json(core.to_json())
        assert restored == core
        assert restored.to_json() == core.to_json()

    def test_a_page_core_records_it_too(self):
        book = compile_book(SCENE)
        (page,) = book.pages
        assert json.loads(page.to_json())["direction"] == "rtl"
        assert PageCore.from_json(page.to_json()) == page
        assert {result.core.direction for result in book.panels.values()} == {Direction.RTL}
        (ltr,) = compile_book(SCENE.replace("direction: rtl\n", "")).pages
        assert "direction" not in json.loads(ltr.to_json())

    def test_a_core_written_before_it_reads_as_left_to_right(self):
        text = compile_source(CAST).core.to_json()
        assert PanelCore.from_json(text).direction is Direction.LTR
