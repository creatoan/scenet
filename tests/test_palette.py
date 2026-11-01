"""The palette a panel is drawn in (#244): `palette: mono | tinted`.

Colour is a twin of value, never a replacement for it. Every value the compiler resolves
keeps its grey in Panel Core, under the key it always had, and a palette adds the colour
beside it as `colour`, left out of the JSON when there is none. Two rules follow, and both
are checked here:

- **Every decision is made on the grey.** A palette moves nothing and changes no choice, so
  a tinted Core with its colours taken out *is* the mono Core, byte for byte.
- **The image-model exports never see colour.** Pose, boxes, depth and mask are the same
  in every palette; the semantics names the palette, and only when it is not `mono`.

`palette` is written where `lettering` is: at the top of a panel, beside `panels:` as a
default every panel inherits, on one panel for that panel alone, and in a comic script's
front matter or as `@palette:`. Unlike `direction`, a panel may have its own: a flashback
in grey on a page in colour is a convention, where a page read two ways is not.
"""

import json
import re
from typing import Any

import pytest

from scenet import Palette, PanelCore, compile_source, parse_panel, parse_scene, render
from scenet.diagnostics import diagnose_source
from scenet.emit.export import render_conditioning
from scenet.frontends.script_front import parse_script_document
from scenet.ir import TimeOfDay, Weather
from scenet.places import Place
from scenet.solve.backdrop import LADDER, SNOW_TONE, TINTED
from tests.images import png

CAST = "cast: {alice: {reference: alice, pose: standing_neutral}}\n"
FRAME = "panel: {size: [900, 600]}\ncamera: {shot: long_shot}\n"

SCENE = (
    "palette: tinted\n"
    + FRAME
    + CAST
    + "setting: {place: street, time: dusk}\n"
    + "panels:\n"
    + "  one: {}\n"
    + "  two: {palette: mono}\n"
    + "  three: {over: two}\n"
)

SCRIPT = """---
palette: tinted
setting: {place: street, time: dusk}
cast:
  ALICE: {reference: alice}
---

PAGE ONE

PANEL 1

ALICE
Now.

PANEL 2
@palette: mono

ALICE
Then.
"""

#: Every place at every hour, and every weather at every hour over a place with all four
#: planes: what the contact sheet shows, and so what the policy has to hold for.
SETTINGS = [
    f"place: {place.value}, time: {time.value}" for place in Place for time in TimeOfDay
] + [
    f"place: docks, time: {time.value}, weather: {weather.value}"
    for weather in Weather
    for time in TimeOfDay
]

FILES = {"art/street.png": png(960, 640)}


def source(setting: str, palette: str | None = None) -> str:
    """A long shot of one figure in a setting, in a palette or in none."""
    head = f"palette: {palette}\n" if palette is not None else ""
    return f"{head}{FRAME}{CAST}setting: {{{setting}}}\n"


def core(setting: str, palette: str | None = None) -> PanelCore:
    return compile_source(source(setting, palette), base=FILES).core


def without_colour(panel: PanelCore) -> str:
    """A Core's JSON with everything a palette adds taken back out."""
    payload: dict[str, Any] = json.loads(panel.to_json())
    payload.pop("palette", None)
    backdrop = payload.get("backdrop") or {}
    for mass in backdrop.get("masses", []):
        mass.pop("colour", None)
    air = backdrop.get("atmosphere") or {}
    air.pop("colour", None)
    air.pop("fall_colour", None)
    (air.get("veil") or {}).pop("colour", None)
    for caption in payload["captions"]:
        caption.pop("colour", None)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def twin(time: TimeOfDay, grey: str) -> str:
    """The colour on the same rung of the same hour."""
    return TINTED[time][LADDER[time].index(grey)]


class TestTheKey:
    def test_mono_is_the_default(self):
        assert parse_panel(CAST).palette is Palette.MONO

    @pytest.mark.parametrize("written", ["mono", "tinted"])
    def test_a_panel_writes_it_at_the_top(self, written: str):
        assert parse_panel(f"palette: {written}\n{CAST}").palette is Palette(written)

    @pytest.mark.parametrize("written", ["sepia", "'#ff0000'", "colour", "true"])
    def test_anything_else_is_invalid_at_the_key(self, written: str):
        """A closed set of names. A free colour is exactly what the policy refuses."""
        (found,) = diagnose_source(f"palette: {written}\n{CAST}")
        assert (found.rule, found.path) == ("invalid-field", ("palette",))

    def test_having_no_effect_is_not_a_finding(self):
        """A panel with nothing on the ladder has nothing to tint, which is fine: a palette is
        a choice for the whole document, and changing it must never make one invalid."""
        assert diagnose_source(f"palette: tinted\n{CAST}") == []


class TestWhereItIsWritten:
    def test_every_panel_of_a_scene_inherits_it(self):
        assert parse_scene(SCENE)["one"].palette is Palette.TINTED

    def test_a_panel_may_have_its_own(self):
        """The flashback in grey on a page in colour."""
        assert parse_scene(SCENE)["two"].palette is Palette.MONO

    def test_a_panel_over_another_takes_its_palette(self):
        assert parse_scene(SCENE)["three"].palette is Palette.MONO

    def test_a_comic_script_sets_it_in_its_front_matter(self):
        panels = parse_script_document(SCRIPT).panels
        assert [panel.palette for panel in panels.values()] == [Palette.TINTED, Palette.MONO]


class TestCore:
    def test_a_mono_core_does_not_say_so(self):
        """So every Core written before palettes existed is still exactly what it was."""
        text = core("place: docks, time: dusk, weather: rain").to_json()
        assert "palette" not in json.loads(text)
        assert '"colour"' not in text
        assert '"fall_colour"' not in text

    def test_a_tinted_core_records_it(self):
        panel = core("place: docks, time: dusk, weather: rain", "tinted")
        assert json.loads(panel.to_json())["palette"] == "tinted"
        restored = PanelCore.from_json(panel.to_json())
        assert restored == panel
        assert restored.to_json() == panel.to_json()

    def test_a_core_written_before_it_is_mono(self):
        text = core("place: street, time: day").to_json()
        assert PanelCore.from_json(text).palette is Palette.MONO

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_every_mass_is_the_twin_of_its_grey(self, time: TimeOfDay):
        backdrop = core(f"place: mountain, time: {time.value}", "tinted").backdrop
        assert backdrop is not None
        assert backdrop.masses
        for mass in backdrop.masses:
            assert mass.colour == twin(time, mass.tone)

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_the_air_is_the_twin_of_its_grey(self, time: TimeOfDay):
        backdrop = core(f"place: docks, time: {time.value}, weather: rain", "tinted").backdrop
        assert backdrop is not None
        air = backdrop.atmosphere
        assert air is not None
        assert air.veil is not None
        assert air.colour == twin(time, air.tone)
        assert air.veil.colour == twin(time, air.veil.tone)
        assert air.fall_colour == twin(time, air.fall_tone)

    def test_snow_stays_white(self):
        """White snow is a convention, not a rung of the ladder, so it has no twin."""
        backdrop = core("place: docks, time: night, weather: snow", "tinted").backdrop
        assert backdrop is not None
        assert backdrop.atmosphere is not None
        assert backdrop.atmosphere.fall_tone == SNOW_TONE
        assert backdrop.atmosphere.fall_colour == ""

    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_the_air_it_falls_through_is_tinted(self, time: TimeOfDay):
        """Only the flakes stay white: the sky they fall from and its cloud are rungs."""
        backdrop = core(f"place: docks, time: {time.value}, weather: snow", "tinted").backdrop
        assert backdrop is not None
        air = backdrop.atmosphere
        assert air is not None
        assert air.veil is not None
        assert air.colour == twin(time, air.tone)
        assert air.veil.colour == twin(time, air.veil.tone)

    def test_the_weather_over_a_picture_is_tinted_too(self):
        """A supplied picture has no masses to tint, but the air over it is the setting's."""
        backdrop = core("image: art/street.png, time: dusk, weather: fog", "tinted").backdrop
        assert backdrop is not None
        assert backdrop.atmosphere is not None
        assert backdrop.atmosphere.veil is not None
        veil = backdrop.atmosphere.veil
        assert veil.colour == twin(TimeOfDay.DUSK, veil.tone)

    def test_with_nothing_on_the_ladder_there_is_nothing_to_tint(self):
        text = compile_source(f"palette: tinted\n{CAST}").core.to_json()
        assert '"colour"' not in text
        assert json.loads(text)["palette"] == "tinted"

    @pytest.mark.parametrize("setting", SETTINGS)
    def test_taking_the_colour_out_gives_the_mono_core(self, setting: str):
        """Rule 2: every decision is made on the grey. A palette that moved one mass, or
        flipped the rain from ink to paper, would show up here."""
        assert without_colour(core(setting, "tinted")) == core(setting).to_json()


class TestDrawn:
    @pytest.mark.parametrize("time", list(TimeOfDay))
    def test_every_mass_is_filled_with_its_colour(self, time: TimeOfDay):
        svg = render(core(f"place: street, time: {time.value}", "tinted"))
        fills = set(re.findall(r'id="mass-m\d+" points="[^"]*" fill="(#[0-9a-f]{6})"', svg))
        assert fills
        assert fills <= set(TINTED[time])

    def test_the_veil_and_the_rain_are_drawn_in_colour(self):
        panel = core("place: docks, time: dusk, weather: rain", "tinted")
        air = panel.backdrop.atmosphere if panel.backdrop is not None else None
        assert air is not None
        assert air.veil is not None
        svg = render(panel)
        assert f'fill="{air.veil.colour}" filter=' in svg
        assert f'fill="{air.fall_colour}" stroke="{air.fall_colour}"' in svg

    def test_the_veil_takes_its_tint_from_the_colour(self):
        """The noise is flattened to one colour by a matrix, and that colour is the twin."""
        setting = "place: docks, time: dusk, weather: fog"
        matrix = re.compile(r'<feColorMatrix [^>]*values="([^"]*)"')
        tinted = matrix.findall(render(core(setting, "tinted")))
        mono = matrix.findall(render(core(setting)))
        assert tinted
        assert tinted != mono

    def test_a_mono_panel_draws_no_colour(self):
        svg = render(core("place: docks, time: dusk, weather: rain"))
        colours = {colour for rungs in TINTED.values() for colour in rungs}
        assert not set(re.findall(r"#[0-9a-f]{6}", svg)) & colours


class TestTheExportsNeverSeeColour:
    @pytest.mark.parametrize("weather", list(Weather))
    def test_pose_boxes_depth_and_mask_are_the_same(self, weather: Weather):
        setting = f"place: docks, time: dusk, weather: {weather.value}"
        tinted = render_conditioning(core(setting, "tinted"))
        mono = render_conditioning(core(setting))
        assert (tinted.pose, tinted.boxes, tinted.depth, tinted.mask) == (
            mono.pose,
            mono.boxes,
            mono.depth,
            mono.mask,
        )

    def test_the_semantics_names_the_palette_and_nothing_else_moves(self):
        setting = "place: docks, time: dusk, weather: rain"
        tinted = json.loads(render_conditioning(core(setting, "tinted")).semantics)
        mono = json.loads(render_conditioning(core(setting)).semantics)
        assert "palette" not in mono
        assert tinted.pop("palette") == "tinted"
        assert tinted == mono
