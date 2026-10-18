"""The words a panel is read in: its description, and each line of its lettering.

Built in the pipeline and carried in Panel Core, so the emitter copies them and decides
nothing. A description is the author's when there is one -- written, or a comic script's
prose -- and otherwise generated from what the panel holds, covering what AccessComics
found blind readers wanted: the shot, the place and the hour, who is where, facing whom,
with what face and what marks. Generated text is templated English, and deterministic.
"""

import json

import pytest
from pydantic import ValidationError

from scenet import compile_script, compile_source
from scenet.core import PanelCore
from scenet.frontends.yaml_front import parse_panel
from scenet.ir import CameraAngle, Mark, MassKind, ShotType, TimeOfDay, Weather
from scenet.places import PLACES, Place
from scenet.solve.describe import (
    ANGLES,
    EXPRESSIONS,
    INDOOR,
    MARKS,
    PLACE_NAMES,
    SHOTS,
    TIMES,
    WEATHERS,
    describe,
    label,
    labels,
    name,
    sentence,
)

TWO = """\
camera: {shot: medium_shot}
setting: {place: street, time: night, weather: rain}
cast:
  alice: {reference: alice, pose: pointing, expression: angry}
  bob: {reference: bob, pose: arms_crossed, marks: [plewds]}
staging:
  - alice left_of bob
  - alice looking_at bob
"""


def _described(source: str, faces: dict[str, float], width: float = 1000.0) -> str:
    return describe(parse_panel(source), faces, width)


class TestTheTables:
    """Every word the generator can say is in a table, and every value has one."""

    def test_every_shot_has_a_name(self):
        assert set(SHOTS) == set(ShotType)

    def test_wide_is_a_long_shot(self):
        assert SHOTS[ShotType.WIDE] == SHOTS[ShotType.LONG_SHOT] == "Long shot"

    def test_the_shots(self):
        assert [SHOTS[shot] for shot in ShotType] == [
            "Long shot",
            "Long shot",
            "Full shot",
            "Medium full shot",
            "Cowboy shot",
            "Medium shot",
            "Medium close-up",
            "Close-up",
            "Big close-up",
            "Extreme close-up",
        ]

    def test_every_angle(self):
        assert ANGLES == {
            CameraAngle.LOW: "from a low angle",
            CameraAngle.EYE_LEVEL: "",
            CameraAngle.HIGH: "from a high angle",
        }

    def test_every_time(self):
        assert TIMES == {
            TimeOfDay.DAWN: "at dawn",
            TimeOfDay.DAY: "by day",
            TimeOfDay.DUSK: "at dusk",
            TimeOfDay.NIGHT: "at night",
        }

    def test_every_weather(self):
        assert WEATHERS == {
            Weather.CLEAR: "",
            Weather.RAIN: "in the rain",
            Weather.FOG: "in fog",
            Weather.SNOW: "in the snow",
        }

    def test_every_mark_says_what_it_means(self):
        """Walker's terms, read as what they say: `Mark`'s own table."""
        assert MARKS == {
            Mark.PLEWDS: "sweating",
            Mark.SQUEANS: "dizzy",
            Mark.GRAWLIXES: "swearing",
            Mark.BRIFFITS: "dashing off",
        }

    def test_every_place(self):
        assert PLACE_NAMES == {
            Place.ALLEY: "An alley",
            Place.DESERT: "A desert",
            Place.DOCKS: "The docks",
            Place.FIELD: "A field",
            Place.FOREST: "A forest",
            Place.MOUNTAIN: "A mountainside",
            Place.OFFICE: "An office",
            Place.ROOM: "A room",
            Place.SHORE: "A shore",
            Place.STREET: "A street",
        }

    def test_no_two_places_are_the_same_masses(self):
        """A place is recognised by its masses, so each must be its own."""
        lists = [PLACES[place] for place in Place]
        assert len(set(lists)) == len(lists)

    def test_the_indoor_kinds_are_coco_stuffs(self):
        assert {
            MassKind.CEILING,
            MassKind.FLOOR,
            MassKind.FURNITURE,
            MassKind.WALL,
            MassKind.WINDOW,
        } == INDOOR

    def test_an_expression_that_is_a_noun_is_read_as_an_adjective(self):
        assert EXPRESSIONS == {"surprise": "surprised"}


class TestNames:
    @pytest.mark.parametrize(
        ("actor", "said"),
        [("alice", "Alice"), ("guard_left", "Guard left"), ("ALICE", "ALICE"), ("McCoy", "McCoy")],
    )
    def test_an_id_is_read_as_a_name(self, actor: str, said: str):
        assert name(actor) == said


class TestSentences:
    @pytest.mark.parametrize(
        ("text", "said"),
        [
            ("Hi", "Hi."),
            ("Hi.", "Hi."),
            ("You what?!", "You what?!"),
            ("Wait…", "Wait…"),
            ("Wait—", "Wait—"),
            ("I was go-", "I was go-"),
            ('"Run!"', '"Run!"'),
            ("“Get down”", "“Get down”."),
            ("“Get down!”", "“Get down!”"),
            ("  two   spaces ", "two spaces."),
        ],
    )
    def test_each_line_is_heard_as_a_sentence(self, text: str, said: str):
        assert sentence(text) == said


class TestGenerated:
    def test_the_issues_example(self):
        assert _described(TWO, {"alice": 250.0, "bob": 750.0}) == (
            "Medium shot. A street at night, in the rain. "
            "Alice, left, pointing, angry, looking at Bob; Bob, right, arms crossed, sweating."
        )

    def test_the_cast_is_read_left_to_right(self):
        said = _described(TWO, {"alice": 750.0, "bob": 250.0})
        assert said.index("Bob, left") < said.index("Alice, right")

    def test_a_tie_is_broken_by_id(self):
        said = _described(TWO, {"alice": 500.0, "bob": 500.0})
        assert said.index("Alice, centre") < said.index("Bob, centre")

    @pytest.mark.parametrize(
        ("x", "where"),
        [(0.0, "left"), (333.0, "left"), (334.0, "centre"), (666.0, "centre"), (667.0, "right")],
    )
    def test_where_is_by_thirds_of_the_panel(self, x: float, where: str):
        assert f"Alice, {where}" in _described(TWO, {"alice": x, "bob": 1000.0})

    def test_the_angle_follows_the_shot(self):
        source = TWO.replace("{shot: medium_shot}", "{shot: close_up, angle: low}")
        said = _described(source, {"alice": 250.0, "bob": 750.0})
        assert said.startswith("Close-up, from a low angle. ")

    def test_a_standing_figure_with_a_plain_face_is_just_where_they_are(self):
        said = _described("cast: {alice: {reference: alice}}\n", {"alice": 500.0})
        assert said == "Medium shot. Alice, centre."

    def test_a_noun_expression(self):
        source = "cast: {alice: {reference: alice, expression: surprise}}\n"
        assert _described(source, {"alice": 500.0}) == "Medium shot. Alice, centre, surprised."

    def test_marks_in_their_order(self):
        source = "cast: {alice: {reference: alice, marks: [squeans, plewds]}}\n"
        said = _described(source, {"alice": 500.0})
        assert said == "Medium shot. Alice, centre, sweating, dizzy."

    def test_in_front_and_behind(self):
        source = TWO + "  - bob behind alice\n"
        said = _described(source, {"alice": 250.0, "bob": 750.0})
        assert "Bob, right, arms crossed, sweating, behind Alice." in said
        source = TWO + "  - alice in_front_of bob\n"
        said = _described(source, {"alice": 250.0, "bob": 750.0})
        assert "looking at Bob, in front of Bob;" in said

    def test_looking_at_somebody_off_panel(self):
        source = (
            "cast: {alice: {reference: alice}}\n"
            "staging: [alice looking_at carol]\n"
            "script: [{say: {by: carol, text: Hi., off_panel: left}}]\n"
        )
        assert _described(source, {"alice": 500.0}).endswith(
            "Alice, centre, looking off panel at Carol."
        )

    def test_masses_that_are_no_place_are_indoors_or_out(self):
        indoors = "setting: {masses: [{kind: wall}, {kind: floor}]}\n"
        outdoors = "setting: {masses: [{kind: sky}]}\n"
        assert _described(indoors, {}) == "Indoors by day."
        assert _described(outdoors, {}) == "Outdoors by day."

    def test_weather_with_nothing_else_is_outdoors(self):
        assert _described("setting: {weather: snow, time: dusk}\n", {}) == (
            "Outdoors at dusk, in the snow."
        )

    def test_a_place_written_out_as_its_masses_is_that_place(self):
        """A preset is the mass list an author could have typed; typed, it is the place."""
        masses = [
            {"kind": mass.kind.value, "plane": mass.plane.value, "spans": mass.spans.value}
            for mass in PLACES[Place.DOCKS]
        ]
        source = f"setting: {json.dumps({'masses': masses})}\n"
        assert _described(source, {}) == "The docks by day."

    def test_a_place_with_no_cast_has_no_shot(self):
        assert _described("setting: {place: docks, time: night}\n", {}) == "The docks at night."

    def test_nothing_at_all(self):
        assert _described("{}\n", {}) == "An empty panel."

    def test_the_authors_wins(self):
        source = TWO + "description: Alice tells Bob off in the rain.\n"
        said = _described(source, {"alice": 250.0, "bob": 750.0})
        assert said == "Alice tells Bob off in the rain."


class TestLabels:
    def _labels(self, script: str, cast: str = "cast: {alice: {reference: alice}}\n") -> list[str]:
        return list(labels(parse_panel(f"{cast}script:\n{script}").script))

    def test_one_per_entry_in_reading_order(self):
        said = self._labels(
            "  - caption: {text: Midnight. The docks.}\n"
            "  - say: {by: alice, text: You forgot your umbrella!}\n"
            "  - sfx: {text: BLAM, from: alice}\n"
        )
        assert said == [
            "Caption: Midnight. The docks.",
            "Alice: You forgot your umbrella!",
            "Sound effect, from Alice: BLAM.",
        ]

    @pytest.mark.parametrize(
        ("kind", "said"),
        [
            ("speech", "Alice: I know."),
            ("whisper", "Alice, whispering: I know."),
            ("shout", "Alice, shouting: I know."),
            ("thought", "Alice, thinking: I know."),
        ],
    )
    def test_how_a_line_is_said(self, kind: str, said: str):
        assert self._labels(f"  - say: {{by: alice, text: I know., kind: {kind}}}\n") == [said]

    def test_small_type_is_said_quietly(self):
        said = self._labels("  - say: {by: alice, text: Sorry., kind: whisper, size: small}\n")
        assert said == ["Alice, whispering, quietly: Sorry."]

    def test_from_off_panel(self):
        said = self._labels("  - say: {by: carol, text: Over here!, off_panel: left}\n")
        assert said == ["Carol, off panel: Over here!"]

    def test_emphasis_is_read_as_the_words(self):
        assert self._labels("  - say: {by: alice, text: I _told_ you}\n") == [
            "Alice: I told you."
        ]

    @pytest.mark.parametrize(
        ("caption", "said"),
        [
            ("{text: Midnight}", "Caption: Midnight."),
            ("{text: Not again, kind: monologue}", "Caption, inner voice: Not again."),
            ("{text: See issue 3, kind: editorial}", "Editor's note: See issue 3."),
            ("{text: Get down!, kind: spoken, by: carol}", "Carol, off panel: Get down!"),
            ("{text: Get down!, kind: spoken}", "Off panel: Get down!"),
        ],
    )
    def test_captions(self, caption: str, said: str):
        assert self._labels(f"  - caption: {caption}\n") == [said]

    def test_a_spoken_captions_quotation_marks_are_not_read(self):
        """The marks are lettering, added to the drawn lines, not to what is said."""
        core = compile_source(
            "script:\n  - caption: {text: Get down!, kind: spoken, by: carol}\n"
        ).core
        assert core.captions[0].lines[0].startswith("“")
        assert core.captions[0].label == "Carol, off panel: Get down!"

    def test_an_effect_with_no_source(self):
        assert self._labels("  - sfx: {text: KRAK}\n") == ["Sound effect: KRAK."]

    def test_an_effects_underscore_is_a_letter(self):
        assert self._labels("  - sfx: {text: _BZZT_}\n") == ["Sound effect: _BZZT_."]

    def test_one_label_alone(self):
        source = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hi}}]"
        event = parse_panel(source).script
        assert label(event[0]) == "Alice: Hi."


class TestInPanelCore:
    SOURCE = (
        TWO
        + "script:\n"
        + "  - caption: {text: Midnight.}\n"
        + "  - say: {by: alice, text: You forgot your umbrella!}\n"
        + "  - sfx: {text: BLAM, from: bob}\n"
        + "  - say: {by: bob, text: I know., kind: whisper}\n"
    )

    @pytest.fixture(scope="class")
    def core(self) -> PanelCore:
        return compile_source(self.SOURCE).core

    def test_the_description_is_generated_from_where_everyone_landed(self, core: PanelCore):
        assert core.description == (
            "Medium shot. A street at night, in the rain. "
            "Alice, left, pointing, angry, looking at Bob; Bob, right, arms crossed, sweating."
        )

    def test_each_item_carries_its_words(self, core: PanelCore):
        assert [caption.label for caption in core.captions] == ["Caption: Midnight."]
        assert [balloon.label for balloon in core.balloons] == [
            "Alice: You forgot your umbrella!",
            "Bob, whispering: I know.",
        ]
        assert [effect.label for effect in core.sfx] == ["Sound effect, from Bob: BLAM."]

    def test_in_reading_order(self, core: PanelCore):
        items = sorted([*core.balloons, *core.captions, *core.sfx], key=lambda item: item.order)
        assert [item.label for item in items] == [
            "Caption: Midnight.",
            "Alice: You forgot your umbrella!",
            "Sound effect, from Bob: BLAM.",
            "Bob, whispering: I know.",
        ]

    def test_the_document_says_them(self, core: PanelCore):
        written = json.loads(core.to_json())
        assert written["description"] == core.description
        assert [balloon["label"] for balloon in written["balloons"]] == [
            balloon.label for balloon in core.balloons
        ]
        assert written["sfx"][0]["label"] == "Sound effect, from Bob: BLAM."

    def test_it_reads_back(self, core: PanelCore):
        assert PanelCore.from_json(core.to_json()) == core

    def test_a_core_written_before_them_reads_and_writes_as_it_did(self, core: PanelCore):
        written = json.loads(core.to_json())
        del written["description"]
        for item in (*written["balloons"], *written["captions"], *written["sfx"]):
            del item["label"]
        old = json.dumps(written, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        again = PanelCore.from_json(old)
        assert again.description is None
        assert all(item.label is None for item in (*again.balloons, *again.sfx))
        assert again.to_json() == old

    def test_a_hand_edited_core_may_not_hold_what_an_svg_cannot(self, core: PanelCore):
        written = json.loads(core.to_json())
        written["description"] = "Alice \u0007 waits."
        with pytest.raises(ValidationError, match="U\\+0007"):
            PanelCore.model_validate(written)
        written = json.loads(core.to_json())
        written["balloons"][0]["label"] = "Alice: \u0001"
        with pytest.raises(ValidationError, match="U\\+0001"):
            PanelCore.model_validate(written)

    def test_the_authors_description_reaches_core(self):
        core = compile_source(TWO + "description: Alice tells Bob off.\n").core
        assert core.description == "Alice tells Bob off."

    def test_a_scripts_prose_reaches_core(self):
        book = compile_script(
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PANEL 1\nAlice waits in the rain.\n\nALICE\nHi.\n"
        )
        core = book.panels["1"].core
        assert core.description == "Alice waits in the rain."
        assert core.balloons[0].label == "ALICE: Hi."
