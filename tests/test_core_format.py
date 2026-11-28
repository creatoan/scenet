"""Panel Core format 2: one deliberate shape that can evolve forwards (#433).

The reading policy is a table. A document names its format and its version, as `major.minor`:
a major this reader does not know is refused, naming both; a newer minor of a known major
reads, with what it does not know reported as a newer Scenet's, not as a typo; `extras` and
`extensions` carry what Scenet does not interpret; and the informational fields are open
strings, which the language checks and the reader does not.
"""

import json
import warnings
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import scenet.core as core_module
from scenet.core import CORE_FORMAT_VERSION, CoreMannequin, PageCore, PanelCore
from scenet.emit.svg import render
from scenet.errors import CoreSyntaxError
from scenet.pipeline import compile_book, compile_source
from scenet.schema import core_schema, page_core_schema

ROOT = Path(__file__).resolve().parents[1]
OLD = sorted((ROOT / "tests" / "data" / "core-0.11.1").glob("*.core.json"))
SITE = "https://creatoan.github.io/scenet/schemas/core"
_DRAWING = {"capsules", "blobs", "face_marks", "emanata"}

SOURCE = """\
setting: {place: street}
camera: {shot: medium_shot}
cast:
  alice: {reference: alice, marks: [plewds]}
  bob: {reference: bob, pose: arms_crossed, facing: left}
staging:
  - alice left_of bob
script:
  - say: {by: alice, text: "You forgot your umbrella!"}
  - caption: {text: "Dusk."}
"""


def _core() -> PanelCore:
    return compile_source(SOURCE).core


def _payload() -> dict[str, Any]:
    return json.loads(_core().to_json())


def _text(payload: dict[str, Any]) -> str:
    """A payload written as a Core is: sorted, indented, with its newline."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _read(payload: dict[str, Any]) -> PanelCore:
    return PanelCore.from_json(json.dumps(payload))


class TestTheHeader:
    def test_a_panel_says_what_it_is(self):
        payload = _payload()
        assert payload["$schema"] == f"{SITE}/2.0/panel.schema.json"
        assert payload["format"] == "scenet.panel"
        assert payload["format_version"] == "2.0"
        assert payload["units"] == "0.1mm"

    def test_a_page_says_what_it_is(self):
        book = compile_book(
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [one]}]}]\npanels: {one: {}}"
        )
        payload = json.loads(book.pages[0].to_json())
        assert payload["$schema"] == f"{SITE}/2.0/page.schema.json"
        assert payload["format"] == "scenet.page"
        assert payload["format_version"] == "2.0"
        assert payload["units"] == "0.1mm"

    def test_the_version_is_a_major_and_a_minor(self):
        assert CORE_FORMAT_VERSION == "2.0"

    def test_the_schema_is_the_address_the_document_names(self):
        assert core_schema()["$id"] == f"{SITE}/2.0/panel.schema.json"
        assert page_core_schema()["$id"] == f"{SITE}/2.0/page.schema.json"

    def test_the_header_is_written_first(self):
        assert _core().to_json().startswith('{\n  "$schema"')


class TestReadingPolicy:
    """What a reader does with each version a document can name."""

    @pytest.mark.parametrize("version", ["3.0", "3.7", "10.0", "1.0", 3, 99, "99"])
    def test_an_unknown_major_is_refused_naming_both(self, version: object):
        payload = _payload()
        payload["format_version"] = version
        with pytest.raises(CoreSyntaxError) as caught:
            _read(payload)
        message = str(caught.value)
        assert str(version) in message
        assert "2.0" in message
        assert "format" in message

    @pytest.mark.parametrize("version", ["2", "2.x", "2.0.1", "", None, True, 2.5, [2, 0]])
    def test_a_version_that_is_not_major_dot_minor_is_refused(self, version: object):
        payload = _payload()
        payload["format_version"] = version
        with pytest.raises(CoreSyntaxError, match="format_version"):
            _read(payload)

    def test_the_same_version_reads(self):
        assert _read(_payload()) == _core()

    def test_a_newer_minor_reads_and_says_nothing_when_it_knows_everything(self):
        payload = _payload()
        payload["format_version"] = "2.3"
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert _read(payload) == _core()

    def test_a_newer_minor_with_a_key_it_does_not_know_reads_and_says_so(self):
        payload = _payload()
        payload["format_version"] = "2.3"
        payload["flair"] = 3
        payload["balloons"][0]["swirl"] = {"turns": 2}
        with pytest.warns(UserWarning, match="newer Scenet") as caught:
            core = _read(payload)
        message = str(caught.list[0].message)
        assert "written by a newer Scenet (2.3); this reads 2.0" in message
        assert "flair" in message
        assert "swirl" in message
        assert "typo" not in message
        assert core == _core()

    def test_it_still_renders(self):
        payload = _payload()
        payload["format_version"] = "2.9"
        payload["actors"][0]["halo"] = True
        with pytest.warns(UserWarning, match="newer Scenet"):
            core = _read(payload)
        assert "<svg" in render(core)

    def test_what_a_newer_minor_wrote_is_written_back_as_what_this_reads(self):
        payload = _payload()
        payload["format_version"] = "2.3"
        payload["flair"] = 3
        with pytest.warns(UserWarning, match="newer Scenet"):
            core = _read(payload)
        assert core.to_json() == _core().to_json()

    def test_the_same_minor_with_a_key_it_does_not_know_is_a_typo(self):
        payload = _payload()
        payload["flair"] = 3
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(CoreSyntaxError) as caught:
                _read(payload)
        assert "flair" in str(caught.value)
        assert "newer" not in str(caught.value)

    def test_an_older_minor_is_not_a_thing_to_say(self):
        """2.0 is the first, so a lower minor cannot be written: it is not a version."""
        payload = _payload()
        payload["format_version"] = "2.-1"
        with pytest.raises(CoreSyntaxError, match="format_version"):
            _read(payload)

    def test_a_newer_minor_still_refuses_what_is_wrong(self):
        payload = _payload()
        payload["format_version"] = "2.3"
        payload["width"] = "wide"
        with pytest.raises(CoreSyntaxError, match="width"):
            _read(payload)

    def test_a_page_has_the_same_policy(self):
        book = compile_book(
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [one]}]}]\npanels: {one: {}}"
        )
        payload = json.loads(book.pages[0].to_json())
        payload["format_version"] = "3.0"
        with pytest.raises(CoreSyntaxError, match=r"3\.0"):
            PageCore.from_json(json.dumps(payload))
        payload["format_version"] = "2.2"
        payload["flair"] = 1
        with pytest.warns(UserWarning, match="newer Scenet"):
            assert PageCore.from_json(json.dumps(payload)) == book.pages[0]

    @pytest.mark.parametrize(
        ("name", "what"),
        [("scenet.page", "Page Core"), ("scenet.book", "Book Core"), ("scenet.panels", "")],
    )
    def test_a_document_that_is_another_format_is_refused_naming_both(self, name: str, what: str):
        payload = _payload()
        payload["format"] = name
        with pytest.raises(CoreSyntaxError) as caught:
            _read(payload)
        assert name in str(caught.value)
        assert "scenet.panel" in str(caught.value)


class TestExtras:
    """`extras` is the one place a Core carries what Scenet does not interpret."""

    def _with_extras(self) -> dict[str, Any]:
        payload = _payload()
        note = {"by": "an annotator", "weights": [0.25, 3, 1e-7], "nested": {"ok": True, "n": None}}
        payload["extras"] = note
        payload["actors"][0]["extras"] = {"tag": "hero"}
        payload["actors"][0]["transform"]["extras"] = {"rotation": 12.5}
        payload["balloons"][0]["box"]["extras"] = {"locked": True}
        payload["balloons"][0]["tail"]["extras"] = {"curl": [1, 2]}
        payload["backdrop"]["masses"][0]["extras"] = {"material": "brick"}
        return payload

    def test_it_round_trips_byte_for_byte(self):
        payload = self._with_extras()
        text = _text(payload)
        assert _read(payload).to_json() == text

    def test_it_is_not_interpreted(self):
        assert _read(self._with_extras()).actors[0].extras == {"tag": "hero"}

    def test_it_is_left_out_when_empty(self):
        assert '"extras"' not in _core().to_json()

    def test_it_is_for_values_json_can_hold(self):
        payload = _payload()
        payload["extras"] = {"bad": "x"}
        _read(payload)
        payload["extras"] = ["not", "an", "object"]
        with pytest.raises(CoreSyntaxError, match="extras"):
            _read(payload)

    def test_a_misspelt_key_is_still_refused(self):
        payload = _payload()
        payload["actors"][0]["extra"] = {}
        with pytest.raises(CoreSyntaxError, match="extra"):
            _read(payload)

    def test_every_object_of_the_schema_offers_it(self):
        definitions = core_schema()["$defs"]
        missing = [
            name
            for name, node in definitions.items()
            if "properties" in node
            and "extras" not in node["properties"]
            and node.get("additionalProperties") is not True
        ]
        assert missing == []
        assert "extras" in core_schema()["properties"]


class TestExtensions:
    NAME = "com.example.lighting"

    def test_data_for_a_renderer_round_trips(self):
        payload = _payload()
        payload["extensions"] = {self.NAME: {"intensity": 0.5, "rays": [1, 2, 3]}}
        payload["actors"][0]["extensions"] = {self.NAME: {"rim": True}}
        core = _read(payload)
        assert core.extensions[self.NAME] == {"intensity": 0.5, "rays": [1, 2, 3]}
        assert core.to_json() == _text(payload)

    def test_an_extension_a_reader_does_not_know_is_ignored_unless_required(self):
        payload = _payload()
        payload["extensions"] = {self.NAME: {}}
        assert "<svg" in render(_read(payload))

    def test_an_unknown_required_extension_is_refused_by_name(self):
        payload = _payload()
        payload["extensions"] = {self.NAME: {}}
        payload["extensions_required"] = [self.NAME]
        with pytest.raises(CoreSyntaxError) as caught:
            _read(payload)
        assert self.NAME in str(caught.value)
        assert "requires" in str(caught.value)

    def test_a_required_extension_is_refused_even_from_a_newer_minor(self):
        payload = _payload()
        payload["format_version"] = "2.4"
        payload["extensions_required"] = [self.NAME]
        with pytest.raises(CoreSyntaxError, match=self.NAME):
            _read(payload)

    def test_none_required_is_the_default_and_is_not_written(self):
        assert "extensions_required" not in _core().to_json()
        payload = _payload()
        payload["extensions_required"] = []
        assert _read(payload).to_json() == _core().to_json()

    @pytest.mark.parametrize(
        "name", ["lighting", "Com.Example", "com..example", "com.example.", "a b.c", ""]
    )
    def test_a_name_is_reverse_dns(self, name: str):
        payload = _payload()
        payload["extensions"] = {name: {}}
        with pytest.raises(CoreSyntaxError):
            _read(payload)


class TestOpenStrings:
    """The language says which places, shots and hours there are. A Core only says which one."""

    def _edited(self, *edits: tuple[tuple[str | int, ...], object]) -> dict[str, Any]:
        payload = _payload()
        for path, value in edits:
            node: Any = payload
            for part in path[:-1]:
                node = node[part]
            node[path[-1]] = value
        return payload

    def test_a_place_the_reader_does_not_know_renders(self):
        payload = self._edited((("backdrop", "place"), "harbour"))
        core = _read(payload)
        assert core.backdrop is not None
        assert core.backdrop.place == "harbour"
        assert "<svg" in render(core)
        assert core.to_json() == _text(payload)

    @pytest.mark.parametrize(
        "edit",
        [
            (("backdrop", "masses", 0, "kind"), "lagoon"),
            (("camera", "shot"), "dutch_roll"),
            (("camera", "angle"), "worm"),
            (("backdrop", "time"), "twilight"),
            (("actors", 0, "marks"), ["sparkles", "plewds"]),
        ],
        ids=["mass.kind", "camera.shot", "camera.angle", "backdrop.time", "actor.marks"],
    )
    def test_an_informational_field_is_any_string(self, edit: tuple[tuple[str | int, ...], object]):
        payload = self._edited(edit)
        core = _read(payload)
        assert "<svg" in render(core)
        assert core.to_json() == _text(payload)

    def test_the_hour_of_the_air_too(self):
        core = compile_source(
            "setting: {place: street, time: night, weather: rain}\ncast: {a: {reference: alice}}\n"
        ).core
        payload = json.loads(core.to_json())
        payload["backdrop"]["atmosphere"]["time"] = "twilight"
        assert "<svg" in render(_read(payload))

    def test_the_schema_offers_what_the_language_has_without_requiring_it(self):
        schema = core_schema()
        place = schema["$defs"]["CoreBackdrop"]["properties"]["place"]
        assert "enum" not in json.dumps(place)
        assert "street" in json.dumps(place)
        validator = Draft202012Validator(schema)
        assert validator.is_valid(self._edited((("backdrop", "place"), "harbour")))

    def test_a_string_is_still_a_string(self):
        with pytest.raises(CoreSyntaxError, match="place"):
            _read(self._edited((("backdrop", "place"), 7)))


class TestTheActor:
    def test_the_contract_is_at_the_top_and_the_drawing_is_under_drawing(self):
        actor = _payload()["actors"][0]
        for key in ("transform", "anchors", "joints", "features", "hull", "face_exclusion", "gaze"):
            assert key in actor
        for key in ("capsules", "blobs", "face_marks", "emanata"):
            assert key not in actor
        assert actor["drawing"]["kind"] == "mannequin"
        assert actor["drawing"]["capsules"]
        assert actor["drawing"]["blobs"]
        assert actor["drawing"]["face_marks"]

    def test_the_marks_and_their_zones_stay_with_the_contract(self):
        actor = _payload()["actors"][0]
        assert actor["marks"] == ["plewds"]
        assert actor["emanata_zones"]
        assert actor["drawing"]["emanata"]

    def test_it_reads_back(self):
        core = _core()
        drawing = core.actors[0].drawing
        assert drawing is not None
        assert drawing.kind == "mannequin"
        assert PanelCore.from_json(core.to_json()) == core

    def test_a_drawing_of_a_kind_nobody_knows_reads_and_draws_nothing(self):
        payload = _payload()
        payload["actors"][0]["drawing"] = {"kind": "paper_doll", "layers": [1, 2], "cutout": "x"}
        core = _read(payload)
        assert core.to_json() == _text(payload)
        drawn = render(core)
        assert 'id="actor-bob"' in drawn
        assert 'id="actor-alice"' not in drawn
        assert "paper_doll" not in drawn

    def test_an_actor_with_no_drawing_is_a_contract(self):
        payload = _payload()
        del payload["actors"][0]["drawing"]
        core = _read(payload)
        assert core.actors[0].drawing is None
        assert "<svg" in render(core)
        assert "drawing" not in json.loads(core.to_json())["actors"][0]

    def test_the_contract_does_not_move_with_the_drawing(self):
        payload = _payload()
        payload["actors"][0]["drawing"] = {"kind": "paper_doll"}
        assert _read(payload).actors[0].hull == _core().actors[0].hull


class TestDefaultsAreLeftOut:
    def test_the_hand_kept_list_is_gone(self):
        assert not hasattr(core_module, "_drop_unused")

    def test_a_field_at_its_default_is_not_written(self):
        payload = _payload()
        actor = payload["actors"][1]
        assert "expression" not in actor or actor["expression"] != "neutral"
        assert all(key != "extras" for key in actor)
        assert "direction" not in payload
        assert "palette" not in payload
        assert "fonts" not in payload

    def test_a_field_set_away_from_its_default_is_written(self):
        payload = _payload()
        assert payload["actors"][1]["transform"]["mirrored"] is True

    def test_it_is_the_models_default_that_decides(self):
        """An actor's `depth` defaults to 0, so a document naming 0 writes back without it."""
        payload = _payload()
        payload["actors"][0]["depth"] = 0
        payload["actors"][0]["expression"] = "neutral"
        written = json.loads(_read(payload).to_json())["actors"][0]
        assert "depth" not in written
        assert "expression" not in written

    def test_a_tag_is_always_written(self):
        written = _core().to_json()
        assert '"mark": "' in written
        assert '"kind": "mannequin"' in written

    def test_every_golden_writes_back_as_it_was_read(self):
        for path in sorted((ROOT / "tests" / "golden" / "core").glob("*.core.json")):
            text = path.read_text(encoding="utf-8")
            if '"frames"' in text:
                assert PageCore.from_json(text).to_json() == text, path.name
            else:
                assert PanelCore.from_json(text).to_json() == text, path.name


class TestVersionOne:
    """A Core of format 1, which every release before this wrote, reads as format 2."""

    def test_there_are_documents_to_upgrade(self):
        assert len(OLD) >= 5

    @pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
    def test_it_loads_and_writes_back_as_format_two(self, path: Path):
        old = json.loads(path.read_text(encoding="utf-8"))
        assert old["format_version"] == 1
        core = PanelCore.from_json(path.read_text(encoding="utf-8"))
        written = json.loads(core.to_json())
        assert written["format_version"] == "2.0"
        assert written["format"] == "scenet.panel"
        assert written["units"] == "0.1mm"
        assert len(core.actors) == len(old["actors"])
        for before, after, actor in zip(
            old["actors"], written.get("actors", []), core.actors, strict=True
        ):
            moved = {key: before[key] for key in _DRAWING if key in before}
            assert actor.drawing == CoreMannequin.model_validate({"kind": "mannequin", **moved})
            assert not _DRAWING & set(after)
            assert after["drawing"]["kind"] == "mannequin"
            assert after["hull"] == before["hull"]
            assert after["transform"] == before["transform"]
        assert [b["id"] for b in written.get("balloons", [])] == [
            b["id"] for b in old.get("balloons", [])
        ]

    @pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
    def test_it_is_deterministic_and_a_fixed_point(self, path: Path):
        text = path.read_text(encoding="utf-8")
        once = PanelCore.from_json(text).to_json()
        assert PanelCore.from_json(text).to_json() == once
        assert PanelCore.from_json(once).to_json() == once

    @pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
    def test_it_validates_against_the_schema(self, path: Path):
        written = json.loads(PanelCore.from_json(path.read_text(encoding="utf-8")).to_json())
        assert Draft202012Validator(core_schema()).is_valid(written)

    @pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
    def test_it_still_draws_what_it_drew(self, path: Path):
        text = path.read_text(encoding="utf-8")
        assert render(PanelCore.from_json(text)) == render(
            PanelCore.from_json(PanelCore.from_json(text).to_json())
        )

    @pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
    def test_its_lettering_is_set_where_the_emitters_used_to_set_it(self, path: Path):
        core = PanelCore.from_json(path.read_text(encoding="utf-8"))
        for lettered in (*core.balloons, *core.captions):
            assert len(lettered.setting) == len(lettered.lines)

    def test_a_format_one_document_in_a_font_of_its_own_is_refused_and_says_why(self):
        old = json.loads(OLD[0].read_text(encoding="utf-8"))
        old["fonts"] = {"regular": {"family": "X", "style": "Regular", "sha256": "0" * 64}}
        if not old.get("balloons"):
            pytest.skip("no balloon to set")
        with pytest.raises(CoreSyntaxError, match="font of its own"):
            PanelCore.from_json(json.dumps(old))

    def test_a_page_of_format_one_upgrades_too(self):
        book = compile_book(
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [one]}]}]\npanels: {one: {}}"
        )
        payload = json.loads(book.pages[0].to_json())
        for key in ("$schema", "format", "units"):
            del payload[key]
        payload["format_version"] = 1
        assert PageCore.from_json(json.dumps(payload)) == book.pages[0]

    def test_a_document_that_names_no_version_is_format_one(self):
        old = json.loads(OLD[0].read_text(encoding="utf-8"))
        del old["format_version"]
        assert (
            PanelCore.from_json(json.dumps(old)).to_json()
            == PanelCore.from_json(OLD[0].read_text(encoding="utf-8")).to_json()
        )

    def test_a_format_one_document_with_a_typo_is_still_refused(self):
        old = json.loads(OLD[0].read_text(encoding="utf-8"))
        old["actors"][0]["capsule"] = []
        with pytest.raises(CoreSyntaxError, match="capsule"):
            PanelCore.from_json(json.dumps(old))

    def test_a_document_that_names_format_two_without_a_version_is_refused(self):
        payload = _payload()
        del payload["format_version"]
        with pytest.raises(CoreSyntaxError, match="format_version"):
            _read(payload)
