"""The semantics export: what a panel holds, as structure, not as a prompt (#72).

A prompt is a model's dialect, and changes with every model; turning structure into prose is
the language step prior art leaves to whatever is in the loop. So this hands over the
structure, cleanly -- and where Panel Core already has words for something, the description
and every label from accessible output (#76), it copies them rather than phrasing anything
twice.
"""

import json
import re
from typing import Any

from scenet.core import PanelCore
from scenet.emit.mask import character_colour, render_mask, slot_of
from scenet.emit.semantics import render_semantics
from scenet.pipeline import compile_source
from tests.images import contract, png

STREET = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot, angle: high}
setting: {place: street, time: night, weather: rain}
cast:
  alice: {reference: alice, pose: pointing, expression: angry, marks: [plewds]}
  bob: {reference: bob, facing: left}
staging:
  - alice left_of bob
  - alice looking_at bob
script:
  - caption: {text: Midnight.}
  - say: {by: alice, text: "You forgot your umbrella!"}
  - sfx: {text: CRASH, from: bob}
  - say: {by: bob, text: I know., kind: whisper}
"""


def _semantics(core: PanelCore) -> dict[str, Any]:
    return json.loads(render_semantics(core))


def _street() -> PanelCore:
    return compile_source(STREET).core


class TestWhatTheCompilerAlreadySaid:
    def test_the_description_is_panel_core_s(self):
        core = _street()
        assert _semantics(core)["description"] == core.description

    def test_every_label_is_panel_core_s_in_reading_order(self):
        core = _street()
        lettering = _semantics(core)["lettering"]
        items = sorted((*core.balloons, *core.captions, *core.sfx), key=lambda item: item.order)
        assert [entry["id"] for entry in lettering] == [item.id for item in items]
        assert [entry["label"] for entry in lettering] == [item.label for item in items]
        assert [entry["order"] for entry in lettering] == [0, 1, 2, 3]

    def test_there_is_no_prompt(self):
        text = render_semantics(_street())
        assert "prompt" not in text


class TestTheCamera:
    def test_the_shot_and_angle_asked_for_and_how_far_it_retreated(self):
        assert _semantics(_street())["camera"] == {
            "angle": "high",
            "pullback": 1.0,
            "shot": "full_shot",
        }

    def test_a_cast_a_picture_draws_has_none(self):
        assert _semantics(_figures())["camera"] is None


class TestTheSetting:
    def test_place_hour_weather_and_masses(self):
        core = _street()
        setting = _semantics(core)["setting"]
        assert setting["place"] == "street"
        assert setting["time"] == "night"
        assert setting["weather"] == "rain"
        assert setting["image"] is None
        assert core.backdrop is not None
        assert setting["masses"] == [
            {"depth": mass.depth, "id": mass.id, "kind": mass.kind.value, "plane": mass.plane.value}
            for mass in core.backdrop.masses
        ]

    def test_clear_weather_is_said(self):
        """The atmosphere is None in clear weather; the backdrop still has an hour."""
        setting = _semantics(compile_source(STREET.replace(", weather: rain", "")).core)["setting"]
        assert setting["weather"] == "clear"
        assert setting["time"] == "night"

    def test_a_panel_set_nowhere_has_no_setting(self):
        core = compile_source("{cast: {a: {reference: alice}}}").core
        assert _semantics(core)["setting"] is None

    def test_over_a_picture_only_what_the_compiler_knows(self):
        setting = _semantics(_figures())["setting"]
        assert setting == {
            "image": {"fit": "cover", "href": "art/p.png"},
            "masses": [],
            "place": None,
            "time": None,
            "weather": "clear",
        }


class TestTheCast:
    def test_each_actor_in_panel_core_s_order(self):
        core = _street()
        actors = _semantics(core)["actors"]
        assert [actor["id"] for actor in actors] == [actor.id for actor in core.actors]
        alice = next(actor for actor in actors if actor["id"] == "alice")
        assert alice == {
            "depth": core.actor("alice").depth,
            "expression": "angry",
            "facing": "right",
            "id": "alice",
            "looking_at": "bob",
            "mask": TestTheMaskColours._fills(core)["actor-alice"],
            "marks": ["plewds"],
            "pose": "pointing",
            "reference": "alice",
        }

    def test_facing_is_read_from_the_mirror(self):
        bob = next(actor for actor in _semantics(_street())["actors"] if actor["id"] == "bob")
        assert bob["facing"] == "left"
        assert bob["looking_at"] is None

    def test_figures_a_picture_draws(self):
        payload = _semantics(_figures())
        assert payload["actors"] == []
        assert payload["figures"] == [
            {"actor": "ANA", "figure": "ana", "mask": character_colour(slot_of("ANA"))}
        ]


class TestTheLettering:
    def test_each_entry_says_what_it_is_and_who(self):
        lettering = _semantics(_street())["lettering"]
        assert [(entry["type"], entry["kind"], entry["by"]) for entry in lettering] == [
            ("caption", "locale", None),
            ("balloon", "speech", "alice"),
            ("sfx", None, "bob"),
            ("balloon", "whisper", "bob"),
        ]

    def test_each_box_is_a_fraction_of_the_panel(self):
        core = _street()
        lettering = _semantics(core)["lettering"]
        balloon = core.balloons[0]
        entry = next(entry for entry in lettering if entry["id"] == balloon.id)
        box = balloon.box
        assert entry["box"] == [
            round(box.x / core.width, 4),
            round(box.y / core.height, 4),
            round(box.right / core.width, 4),
            round(box.bottom / core.height, 4),
        ]
        effect = core.sfx[0]
        sound = next(entry for entry in lettering if entry["id"] == effect.id)
        xs = [x for x, _ in effect.zone]
        assert sound["box"][0] == round(max(min(xs), 0.0) / core.width, 4)


class TestTheDocument:
    def test_its_keys(self):
        payload = _semantics(_street())
        assert sorted(payload) == [
            "actors",
            "camera",
            "canvas_height",
            "canvas_width",
            "description",
            "direction",
            "figures",
            "lettering",
            "setting",
        ]
        assert (payload["canvas_width"], payload["canvas_height"]) == (1000, 800)

    def test_it_is_written_as_panel_core_is(self):
        text = render_semantics(_street())
        assert (
            text
            == json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )

    def test_read_right_to_left_only_reading_changes(self):
        """The direction, the description (which names the cast from the right), and where the
        lettering went. Nothing about the scene."""
        ltr = _semantics(_street())
        rtl = _semantics(compile_source("direction: rtl\n" + STREET).core)
        assert rtl["direction"] == "rtl"
        assert ltr["direction"] == "ltr"
        for key in ("actors", "camera", "canvas_height", "canvas_width", "figures", "setting"):
            assert rtl[key] == ltr[key], key
        strip = ("box",)
        assert [
            {k: v for k, v in entry.items() if k not in strip} for entry in rtl["lettering"]
        ] == [{k: v for k, v in entry.items() if k not in strip} for entry in ltr["lettering"]]


def _figures() -> PanelCore:
    return compile_source(
        "setting: {image: art/p.png}\ncast: {ANA: {figure: ana}}\n"
        "script:\n  - say: {by: ANA, text: Hi.}\n",
        base={
            "art/p.png": png(800, 600),
            "art/p.art.yaml": contract(
                (800, 600), {"ana": {"face": {"center": [400, 200], "radius": 60}}}
            ),
        },
    ).core


class TestTheMaskColours:
    """Each character's mask colour, so a tool maps colour to character without the SVG."""

    @staticmethod
    def _fills(core: PanelCore) -> dict[str, str]:
        return dict(re.findall(r'id="([^"]+)"[^>]*? fill="(#[0-9a-f]{6})"', render_mask(core)))

    def test_each_actor_s_is_the_mask_s(self):
        core = _street()
        fills = self._fills(core)
        for actor in _semantics(core)["actors"]:
            assert actor["mask"] == fills[f"actor-{actor['id']}"]

    def test_each_figure_s_is_the_mask_s(self):
        core = _figures()
        fills = self._fills(core)
        figures = _semantics(core)["figures"]
        assert figures
        for figure in figures:
            assert figure["mask"] == fills[f"figure-{figure['figure']}"]

    def test_a_figure_cast_as_an_actor_has_that_actor_s_colour(self):
        puppet = compile_source("cast: {ANA: {reference: alice}}\n").core
        figure = _figures()
        assert _semantics(figure)["figures"][0]["mask"] == _semantics(puppet)["actors"][0]["mask"]

    def test_a_character_keeps_it_from_panel_to_panel(self):
        """The street has masses; a bare panel has none."""
        bare = compile_source(
            "cast: {alice: {reference: alice}, bob: {reference: bob}}\n"
            "staging: [alice left_of bob]\n"
        ).core
        street = {actor["id"]: actor["mask"] for actor in _semantics(_street())["actors"]}
        alone = {actor["id"]: actor["mask"] for actor in _semantics(bare)["actors"]}
        assert street == alone

    def test_masses_have_none(self):
        setting = _semantics(_street())["setting"]
        assert all("mask" not in mass for mass in setting["masses"])
