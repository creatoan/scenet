"""Panel order is normative, and a list form makes it survive any tool (#356).

`panels:` is a mapping whose key order is the reading order, and `cast:` one whose first
member is the one the camera frames. A tool that sorts keys -- PyYAML's `dump` does by
default, `json.dumps(sort_keys=True)` on request -- reorders the comic without a word. So
both may also be written as a list: `panels: [{name: a, ...}]`, `cast: [{id: alice, ...}]`.

The list form is lowered to the mapping form as the document is read, before `over:` and a
scene's defaults are merged, so the two are one language and build one Core.
"""

import json
import random
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.forms import NAMING_KEYS, as_lists, lowered
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_scene_document
from scenet.pipeline import compile_book
from scenet.safe_yaml import load
from scenet.schema import panel_schema, scene_schema
from tests.strategies import dump

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
DOCUMENTS = sorted([*GALLERY.glob("*.panel.yaml"), *GALLERY.glob("*.scene.yaml")])


def cores(text: str, source: Path) -> list[tuple[str, str]]:
    """Every panel's Core and every page's, as JSON, in order."""
    book = compile_book(text, source=source)
    panels = [(name, result.core.model_dump_json()) for name, result in book.panels.items()]
    return panels + [
        (f"page {index}", page.model_dump_json()) for index, page in enumerate(book.pages)
    ]


def mapping(text: str) -> dict[str, Any]:
    """A document's text, read."""
    loaded = load(text)
    assert isinstance(loaded, dict)
    return loaded


def listed(text: str) -> str:
    """The document, with its panels and every cast written as lists."""
    return dump(as_lists(mapping(text)))


class TestTheGallery:
    @pytest.mark.parametrize("path", DOCUMENTS, ids=[path.name for path in DOCUMENTS])
    def test_the_list_form_builds_the_same_core(self, path: Path):
        text = path.read_text(encoding="utf-8")
        assert cores(listed(text), path) == cores(text, path)

    def test_the_gallery_has_lists_to_write(self):
        """Every scene's panels, and some cast, become lists: the test above tests something."""
        written = [as_lists(mapping(path.read_text(encoding="utf-8"))) for path in DOCUMENTS]
        assert all(
            isinstance(document["panels"], list) for document in written if "panels" in document
        )
        assert sum(isinstance(document.get("cast"), list) for document in written) > 10


def _shuffled(value: object, rng: random.Random) -> object:
    """The value with the keys of every mapping in it in another order."""
    if isinstance(value, dict):
        items = list(value.items())
        rng.shuffle(items)
        return {key: _shuffled(inner, rng) for key, inner in items}
    if isinstance(value, list):
        return [_shuffled(item, rng) for item in value]
    return value


#: Scenes small enough to compile many times over.
SMALL = [
    GALLERY / name
    for name in (
        "12-sequence.scene.yaml",
        "26-insets.scene.yaml",
        "49-leaving-someone-out.scene.yaml",
        "01-two-characters.panel.yaml",
    )
]


class TestKeyOrder:
    @settings(max_examples=12, deadline=None)
    @given(st.sampled_from(SMALL), st.randoms(use_true_random=False))
    def test_reordering_any_mapping_of_a_list_form_document_changes_nothing(
        self, path: Path, rng: random.Random
    ):
        text = path.read_text(encoding="utf-8")
        document = as_lists(mapping(text))
        assert cores(dump(_shuffled(document, rng)), path) == cores(dump(document), path)

    def test_a_sorted_mapping_reorders_the_comic(self):
        """Why the list form exists: in the mapping form, key order is reading order."""
        text = "cast: {a: {reference: alice}}\npanels: {zebra: {}, apple: {}}\n"
        assert list(parse_scene_document(text).panels) == ["zebra", "apple"]
        resorted = json.dumps(load(text), sort_keys=True)
        assert list(parse_scene_document(resorted).panels) == ["apple", "zebra"]

    def test_a_sorted_list_form_keeps_it(self):
        text = "cast: [{id: a, reference: alice}]\npanels: [{name: zebra}, {name: apple}]\n"
        resorted = json.dumps(load(text), sort_keys=True)
        assert list(parse_scene_document(resorted).panels) == ["zebra", "apple"]


class TestOneLanguage:
    def test_a_list_form_cast_is_the_mapping_form(self):
        mapping = parse_scene_document(
            "cast: {bob: {reference: bob}, alice: {reference: alice, pose: pointing}}"
        )
        listed_ = parse_scene_document(
            "cast: [{id: bob, reference: bob}, {id: alice, reference: alice, pose: pointing}]"
        )
        assert listed_.panels == mapping.panels
        assert list(listed_.panels["panel"].cast) == ["bob", "alice"]

    def test_the_order_written_is_the_order_read(self):
        document = parse_scene_document(
            "cast: [{id: a, reference: alice}]\npanels: [{name: two}, {name: one}]"
        )
        assert list(document.panels) == ["two", "one"]

    def test_both_forms_mix_across_keys(self):
        """A scene's defaults in one form, a panel's cast in the other: each key is whole."""
        document = parse_scene_document(
            "cast: {a: {reference: alice}}\n"
            "panels: [{name: one, cast: [{id: b, reference: bob}]}]\n"
        )
        assert list(document.panels["one"].cast) == ["a", "b"]

    def test_a_list_form_cast_merges_over_its_parent_per_actor(self):
        """Lowered before `over:` is resolved, so it merges exactly as the mapping form does."""

        def scene(cast: str) -> str:
            return (
                "panels:\n"
                "  - name: one\n"
                "    cast: [{id: a, reference: alice, at: left_third}, {id: b, reference: bob}]\n"
                "  - name: two\n"
                "    over: one\n"
                f"    cast: {cast}\n"
            )

        mapping = parse_scene_document(scene("{a: {pose: pointing}}"))
        listed_ = parse_scene_document(scene("[{id: a, pose: pointing}]"))
        assert listed_.panels == mapping.panels
        two = listed_.panels["two"].cast
        assert (two["a"].pose, two["a"].at.value, list(two)) == (
            "pointing",
            "left_third",
            ["a", "b"],
        )

    def test_a_scene_default_cast_in_list_form_is_inherited(self):
        document = parse_scene_document(
            "cast: [{id: a, reference: alice}]\npanels: [{name: one}, {name: two, over: one}]"
        )
        assert [list(panel.cast) for panel in document.panels.values()] == [["a"], ["a"]]

    def test_a_script_may_write_its_cast_as_a_list(self):
        mapping = parse_script("---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1\nALICE\nHi.\n")
        listed_ = parse_script(
            "---\ncast: [{id: ALICE, reference: alice}]\n---\nPANEL 1\nALICE\nHi.\n"
        )
        assert listed_ == mapping

    def test_a_script_directive_may_too(self):
        mapping = parse_script("PANEL 1\n@cast: {ALICE: {reference: alice}}\nALICE\nHi.\n")
        listed_ = parse_script("PANEL 1\n@cast: [{id: ALICE, reference: alice}]\nALICE\nHi.\n")
        assert listed_ == mapping

    def test_an_empty_list_is_an_empty_cast(self):
        assert lowered({"cast": []}) == ({"cast": {}}, ())


class TestMistakes:
    @pytest.mark.parametrize(
        ("source", "path", "line", "said"),
        [
            (
                "panels:\n  - {name: one, cast: [{id: a, reference: alice}]}\n  - {name: one}\n",
                ("panels", 1, "name"),
                3,
                "'one'",
            ),
            (
                "cast:\n  - {id: a, reference: alice}\n  - {id: a, reference: bob}\n",
                ("cast", 1, "id"),
                3,
                "'a'",
            ),
        ],
        ids=["panel", "actor"],
    )
    def test_a_name_written_twice_is_one_located_finding(
        self, source: str, path: tuple[str | int, ...], line: int, said: str
    ):
        (found,) = diagnose_source(source)
        assert (found.rule, found.path) == ("duplicate-key", path)
        assert said in found.message
        assert "item 1" in found.message
        assert found.region is not None
        assert found.region.start.line == line
        with pytest.raises(PanelSyntaxError) as caught:
            parse_scene_document(source)
        assert (caught.value.rule, caught.value.loc) == ("duplicate-key", path)

    def test_a_mapping_entry_in_a_list_says_so(self):
        """`- bob: {...}` is the mapping form's entry written as an item: the two forms mixed."""
        source = "cast:\n  - {id: a, reference: alice}\n  - bob: {reference: bob}\n"
        (found,) = diagnose_source(source)
        assert (found.rule, found.path) == ("missing-field", ("cast", 1))
        assert "{id: bob" in found.message
        assert found.region is not None
        assert found.region.start.line == 3

    def test_an_item_with_no_name_is_missing_it(self):
        (found,) = diagnose_source(
            "cast: [{id: a, reference: alice}]\npanels: [{camera: {shot: close_up}}]"
        )
        assert (found.rule, found.path) == ("missing-field", ("panels", 0))
        assert "`name`" in found.message

    def test_an_item_that_is_not_a_mapping_is_refused(self):
        (found,) = diagnose_source("cast: [alice]")
        assert (found.rule, found.path) == ("invalid-field", ("cast", 0))

    def test_a_name_that_is_a_number_is_quoted(self):
        (found,) = diagnose_source("cast: [{id: a, reference: alice}]\npanels: [{name: 1}]")
        assert (found.rule, found.path) == ("invalid-identifier", ("panels", 0, "name"))
        assert "quote" in found.message

    def test_a_bad_name_is_found_at_its_item(self):
        (found,) = diagnose_source("cast: [{id: a.b, reference: alice}]")
        assert found.rule == "invalid-identifier"
        assert found.region is not None
        assert (found.region.start.line, found.region.start.column) == (1, 13)

    def test_a_fault_inside_an_item_is_found_there(self):
        source = "cast:\n  - id: a\n    reference: alice\n    at: nowhere\n"
        (found,) = diagnose_source(source)
        assert found.path == ("cast", "a", "at")
        assert found.region is not None
        assert found.region.start.line == 4

    def test_a_script_cast_written_twice_is_found_at_its_line(self):
        script = (
            "---\ncast:\n  - {id: ALICE, reference: alice}\n  - {id: ALICE, reference: bob}\n"
            "---\nPANEL 1\nALICE\nHi.\n"
        )
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(script)
        assert (caught.value.rule, caught.value.line) == ("duplicate-key", 4)
        (found,) = diagnose_script(script)
        assert found.rule == "duplicate-key"
        assert found.region is not None
        assert found.region.start.line == 4


class TestTheConverter:
    def test_it_writes_the_naming_key_first(self):
        document = as_lists(
            {
                "cast": {"a": {"reference": "alice"}},
                "panels": {"one": {"cast": {"b": {"reference": "bob"}}}},
            }
        )
        assert document == {
            "cast": [{"id": "a", "reference": "alice"}],
            "panels": [{"name": "one", "cast": [{"id": "b", "reference": "bob"}]}],
        }
        assert list(document["panels"][0]) == ["name", "cast"]

    def test_a_cast_that_leaves_somebody_out_stays_a_mapping(self):
        """`bob: null` takes Bob out; the list form has no way to say so."""
        document = {
            "panels": {
                "one": {"cast": {"a": {"reference": "alice"}}},
                "two": {"over": "one", "cast": {"a": None}},
            }
        }
        assert as_lists(document)["panels"][1]["cast"] == {"a": None}

    def test_lowering_undoes_it(self):
        document = {
            "cast": {"a": {"reference": "alice"}},
            "panels": {"one": {}, "two": {"over": "one"}},
        }
        assert lowered(as_lists(document)) == (document, ())

    def test_the_naming_keys(self):
        assert NAMING_KEYS == {"panels": "name", "cast": "id"}


def _valid(schema: dict[str, Any], document: Any) -> bool:
    return not list(Draft202012Validator(schema).iter_errors(document))


class TestTheSchema:
    def test_a_panel_schema_takes_a_list_form_cast(self):
        assert _valid(panel_schema(), {"cast": [{"id": "a", "reference": "alice"}]})

    def test_a_scene_schema_takes_list_form_panels_with_partial_cast(self):
        document = {
            "cast": [{"id": "a", "reference": "alice"}],
            "panels": [
                {"name": "one"},
                {"name": "two", "over": "one", "cast": [{"id": "a", "pose": "pointing"}]},
            ],
        }
        assert _valid(scene_schema(), document)

    @pytest.mark.parametrize(
        "document",
        [
            {"cast": [{"reference": "alice"}]},
            {"cast": [{"id": "a.b", "reference": "alice"}]},
            {"cast": [{"id": 1, "reference": "alice"}]},
            {"cast": [{"a": {"reference": "alice"}}]},
            {"cast": ["alice"]},
        ],
    )
    def test_it_refuses_what_the_frontend_refuses(self, document: dict[str, Any]):
        assert not _valid(panel_schema(), document)

    def test_a_scene_item_still_needs_its_name(self):
        assert not _valid(scene_schema(), {"panels": [{"camera": {"shot": "close_up"}}]})
        assert not _valid(
            scene_schema(), {"panels": [{"name": "one", "cast": [{"pose": "pointing"}]}]}
        )

    def test_it_describes_both_forms(self):
        text = json.dumps(scene_schema())
        assert "list" in scene_schema()["properties"]["panels"]["description"]
        assert '"id"' in text
        assert '"name"' in text
