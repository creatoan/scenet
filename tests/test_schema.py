"""The JSON Schema the editor uses for completion and validation.

The schema is generated from the pydantic models rather than hand-written, so what an
editor suggests is derived from the compiler's own definition of the language. These
tests guard the property that makes that worth doing: that the two cannot disagree --
and, since the models describe the language *after* the frontend has normalised it,
that the schema describes what people actually write.
"""

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from scenet.cli import main
from scenet.frontends.common import KNOWN_VERBS
from scenet.ir import (
    AnchorX,
    BalloonKind,
    CaptionTone,
    Fit,
    Horizon,
    Mark,
    MassKind,
    PanelIR,
    PlacementZone,
    Plane,
    Predicate,
    SfxSize,
    ShotType,
    Spans,
    TimeOfDay,
    Weather,
)
from scenet.places import Place
from scenet.schema import artwork_schema, panel_schema, scene_schema

REPO = Path(__file__).resolve().parents[1]
SHIPPED = {
    "panel": REPO / "editor" / "schemas" / "panel.schema.json",
    "scene": REPO / "editor" / "schemas" / "scene.schema.json",
    "artwork": REPO / "editor" / "schemas" / "artwork.schema.json",
}

EXAMPLES = sorted(
    path
    for path in (REPO / "examples").rglob("*.yaml")
    if path.name.endswith((".panel.yaml", ".scene.yaml"))
)


def generated(kind: str) -> str:
    schema = {"panel": panel_schema, "scene": scene_schema, "artwork": artwork_schema}[kind]()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def problems(schema: dict[str, Any], source: str) -> list[str]:
    """Every validation error for a YAML document, as `path: message` lines."""
    document = yaml.safe_load(source)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(document)
    ]


class TestPanelSchema:
    def test_top_level_keys_match_the_language(self):
        properties = panel_schema()["properties"]
        assert set(properties) == {
            "panel",
            "camera",
            "setting",
            "cast",
            "staging",
            "script",
            "lettering",
            "description",
        }

    def test_it_is_a_valid_schema(self):
        Draft202012Validator.check_schema(panel_schema())
        Draft202012Validator.check_schema(scene_schema())

    @pytest.mark.parametrize(
        "enum",
        [
            ShotType,
            AnchorX,
            Predicate,
            BalloonKind,
            CaptionTone,
            Mark,
            PlacementZone,
            MassKind,
            Plane,
            Spans,
            Horizon,
            TimeOfDay,
            Weather,
            Fit,
            SfxSize,
        ],
    )
    def test_every_enum_member_reaches_the_schema(self, enum: type[StrEnum]):
        """Completion is only useful if it offers everything the compiler accepts."""
        document = json.dumps(panel_schema())
        for member in enum:
            assert f'"{member.value}"' in document, f"{enum.__name__}.{member.name} is missing"

    def test_every_place_is_offered(self):
        assert set(panel_schema()["$defs"]["Place"]["enum"]) == {place.value for place in Place}

    def test_every_script_verb_is_offered(self):
        """One wrapper per verb the frontend accepts, so neither side can add one alone."""
        branches = panel_schema()["properties"]["script"]["items"]["anyOf"]
        assert {verb for branch in branches for verb in branch["required"]} == KNOWN_VERBS

    def test_the_ir_schema_is_not_what_is_published(self):
        """`PanelIR.model_json_schema()` describes the language after normalisation.

        Publishing it flagged every staging sentence and every `- say:` in the gallery.
        """
        assert panel_schema() != PanelIR.model_json_schema()


class TestTheSchemaDescribesWhatIsWritten:
    """Every document the project ships must pass the schema the editor ships.

    Until this existed, the only check was that the shipped schema equalled the generated
    one -- which held perfectly while the schema rejected 21 of the 22 gallery documents,
    because it described the IR rather than the surface syntax. Each case below is one
    convenience `normalise()` removes, and the schema has to know about.
    """

    def test_examples_were_found(self):
        """Guards the glob: an empty parametrisation would pass vacuously."""
        assert len(EXAMPLES) >= 20

    @pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
    def test_every_example_passes_the_shipped_schema(self, path: Path):
        kind = "scene" if path.name.endswith(".scene.yaml") else "panel"
        shipped = json.loads(SHIPPED[kind].read_text(encoding="utf-8"))
        assert problems(shipped, path.read_text(encoding="utf-8")) == []

    @pytest.mark.parametrize(
        "source",
        [
            "staging: [alice left_of bob]",
            "staging: ['  alice   in_front_of   bob  ']",
            # The mapping form is still accepted by the frontend, so it must be here too.
            "staging: [{subject: alice, predicate: left_of, object: bob}]",
            "script: [{say: {by: alice, text: Hi}}, {caption: {text: Later.}}]",
            "setting: {place: docks, time: night}",
            "setting: {image: art/a.png, fit: contain, time: night, weather: rain}",
            # Merge Patch: a null takes away what a panel would otherwise inherit.
            "setting: {place: null, image: art/a.png}",
        ],
    )
    def test_panel_conveniences_are_accepted(self, source: str):
        assert problems(panel_schema(), source) == []

    @pytest.mark.parametrize(
        "source",
        [
            "colour: red",
            "staging: [alice beside bob]",
            "staging: [alice left_of]",
            "script: [{shout: {by: alice, text: Hi}}]",
            "script: [{say: {by: alice, text: Hi}, caption: {text: Two verbs.}}]",
            "script: [{say: {by: alice}}]",
            "setting: {place: nowhere}",
            "setting: {place: docks, masses: []}",
            "setting: {image: art/a.png, place: docks}",
            "setting: {image: art/a.png, masses: []}",
            "setting: {image: art/a.png, horizon: low}",
            "setting: {fit: cover}",
            "setting: {image: art/a.png, fit: stretch}",
        ],
    )
    def test_panel_mistakes_are_still_rejected(self, source: str):
        assert problems(panel_schema(), source) != []

    @pytest.mark.parametrize(
        "source",
        [
            "setting: {place: street}\n"
            "panels:\n  painted: {setting: {place: null, image: art/a.png}}\n",
            # The image may be the scene's, and a panel only say how it fits.
            "setting: {image: art/a.png}\npanels:\n  close: {setting: {fit: contain}}\n",
        ],
    )
    def test_a_scene_panel_may_change_its_backdrop(self, source: str):
        assert problems(scene_schema(), source) == []

    def test_a_scene_panel_still_cannot_write_two_backdrops(self):
        source = "panels:\n  one: {setting: {image: art/a.png, place: docks}}\n"
        assert problems(scene_schema(), source) != []

    def test_a_scene_panel_may_override_part_of_an_inherited_actor(self):
        source = (
            "cast: {alice: {reference: alice}}\n"
            "panels:\n"
            "  one: {}\n"
            "  two: {over: one, cast: {alice: {pose: pointing}}}\n"
        )
        assert problems(scene_schema(), source) == []

    @pytest.mark.parametrize(
        "source",
        [
            "panels:\n  one: {colour: red}\n",
            "panels:\n  one: {cast: {alice: {reference: alice, mood: sad}}}\n",
            # Lists replace rather than merge, so a script entry is always whole.
            "panels:\n  one: {script: [{say: {by: alice}}]}\n",
        ],
    )
    def test_scene_mistakes_are_still_rejected(self, source: str):
        assert problems(scene_schema(), source) != []


class TestSceneSchema:
    def test_it_allows_panels_alongside_defaults(self):
        schema = scene_schema()
        assert "panels" in schema["properties"]
        # Document-level keys act as defaults every panel inherits.
        assert "camera" in schema["properties"]

    def test_panel_members_may_declare_over(self):
        member = scene_schema()["properties"]["panels"]["additionalProperties"]
        assert "over" in member["properties"]

    def test_definitions_are_carried_across(self):
        """The member schema references $defs, so dropping them would leave every
        reference dangling and the editor silently unable to validate anything."""
        schema = scene_schema()
        assert schema["$defs"]
        assert "ShotType" in schema["$defs"]

    def test_both_schemas_describe_the_same_language(self):
        panel = panel_schema()["properties"]
        scene = scene_schema()["properties"]
        member = scene["panels"]["additionalProperties"]["properties"]
        assert set(panel) <= set(member)
        # A description says what one panel shows: a panel's, never a scene's default.
        assert set(panel) - set(scene) == {"description"}


class TestShippedSchemasAreCurrent:
    """The editor ships generated files, and a stale one is worse than none.

    A language change with no regeneration leaves the editor confidently offering
    completions that no longer compile. CI runs these, so that cannot ship.
    """

    @pytest.mark.parametrize("kind", ["panel", "scene", "artwork"])
    def test_shipped_schema_is_up_to_date(self, kind: str):
        path = SHIPPED[kind]
        assert path.exists(), f"{path} is missing; run `npm run schemas` in editor/"
        assert path.read_text(encoding="utf-8") == generated(kind), (
            f"{path} is stale; run `npm run schemas` in editor/"
        )


class TestArtworkSchema:
    """The schema an editor checks a `*.art.yaml` against, beside its picture (#71)."""

    CONTRACT = """
size: [3000, 2000]
figures:
  ana:
    face: {center: [1240, 610], radius: 150}
    mouth: [1270, 700]
    body: [[1050, 520], [1450, 520], [1500, 2000], [1000, 2000]]
  ben:
    face: {center: [2210, 580], radius: 140}
keep_out:
  - [[400, 1200], [900, 1200], [900, 1700], [400, 1700]]
"""

    def test_a_contract_as_the_issue_writes_it_is_valid(self):
        assert problems(artwork_schema(), self.CONTRACT) == []

    @pytest.mark.parametrize(
        ("broken", "where"),
        [
            ("mouth: [1270, 700]", "mouht: [1270, 700]"),
            ("radius: 150", "radius: 0"),
            ("size: [3000, 2000]", "size: [3000]"),
            ("  - [[400, 1200], [900, 1200], [900, 1700], [400, 1700]]", "  - [[400, 1200]]"),
        ],
    )
    def test_a_slip_is_flagged(self, broken: str, where: str):
        assert problems(artwork_schema(), self.CONTRACT.replace(broken, where))

    def test_the_command_writes_it(self, tmp_path: Path):
        target = tmp_path / "artwork.schema.json"
        assert main(["schema", "--artwork", "-o", str(target)]) == 0
        assert target.read_text(encoding="utf-8") == generated("artwork")

    def test_the_editor_checks_contracts_against_it(self):
        manifest = json.loads((REPO / "editor" / "package.json").read_text(encoding="utf-8"))
        associations = {
            entry["fileMatch"]: entry["url"] for entry in manifest["contributes"]["yamlValidation"]
        }
        assert associations["*.art.yaml"] == "./schemas/artwork.schema.json"
        assert "--artwork -o editor/schemas/artwork.schema.json" in manifest["scripts"]["schemas"]


class TestSchemaCommand:
    def test_it_writes_to_a_file(self, tmp_path: Path, capsys):
        target = tmp_path / "nested" / "panel.schema.json"
        assert main(["schema", "-o", str(target)]) == 0
        assert json.loads(target.read_text(encoding="utf-8"))["properties"]

    def test_it_prints_to_stdout_by_default(self, capsys):
        assert main(["schema"]) == 0
        assert json.loads(capsys.readouterr().out)["properties"]

    def test_the_scene_flag_selects_the_scene_schema(self, capsys):
        assert main(["schema", "--scene"]) == 0
        assert "panels" in json.loads(capsys.readouterr().out)["properties"]

    def test_output_is_deterministic(self, capsys):
        """Keys are sorted so regenerating produces no spurious diff."""
        main(["schema"])
        first = capsys.readouterr().out
        main(["schema"])
        assert capsys.readouterr().out == first


class TestAFigureInTheCast:
    """`figure:` in place of `reference:` (#71), as the frontend and the model hold it."""

    @pytest.mark.parametrize(
        "member",
        [
            "{figure: ana}",
            "{reference: alice}",
            "{figure: ana, reference: null}",
            "{figure: ana, pose: null, facing: null}",
        ],
    )
    def test_accepted(self, member: str):
        assert problems(panel_schema(), f"cast: {{a: {member}}}") == []

    @pytest.mark.parametrize(
        "member",
        [
            "{figure: ana, reference: alice}",
            "{figure: ana, pose: pointing}",
            "{figure: ana, marks: [plewds]}",
            "{figure: ana, at: center}",
            "{pose: pointing}",
        ],
    )
    def test_refused(self, member: str):
        assert problems(panel_schema(), f"cast: {{a: {member}}}")

    def test_a_scene_panel_may_override_one_key_of_an_inherited_figure(self):
        scene = "cast: {a: {figure: ana}}\npanels: {one: {cast: {a: {figure: ben}}}}\n"
        assert problems(scene_schema(), scene) == []

    def test_a_scene_panel_may_not_pose_a_figure(self):
        scene = "panels: {one: {cast: {a: {figure: ben, pose: pointing}}}}\n"
        assert problems(scene_schema(), scene)
