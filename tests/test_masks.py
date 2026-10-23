"""The mask export: one flat fill per actor, figure and mass, ids as in Core (#72).

A segmentation with stable labels: every region the panel's geometric contract names --
an actor's hull, a figure's body and face, a mass's polygon -- in its own colour, under the
id the panel's SVG gives it, drawn in the panel's own painter's order so that what covers
what is what the panel draws.
"""

import re

from scenet.core import PanelCore
from scenet.emit.depth import render_depth
from scenet.emit.mask import (
    CHARACTER_SLOTS,
    character_colour,
    mass_colour,
    render_mask,
    slot_of,
)
from scenet.emit.svg import render
from scenet.pipeline import compile_source
from tests.images import contract, png

STREET = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot}
setting: {place: alley, time: night}
cast:
  alice: {reference: alice, pose: pointing, marks: [plewds]}
  bob: {reference: bob, facing: left}
staging: [alice left_of bob]
"""

FILL = re.compile(r'id="([^"]+)"[^>]*? fill="(#[0-9a-f]{6})"')


def _fills(svg: str) -> dict[str, str]:
    return dict(FILL.findall(svg))


def _channels(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _street() -> PanelCore:
    return compile_source(STREET).core


class TestRegions:
    def test_one_per_actor_and_mass_under_the_panel_s_ids_in_its_order(self):
        core = _street()
        drawn = re.findall(r'id="((?:actor|mass)-[^"]+)"', render(core))
        assert list(_fills(render_mask(core))) == drawn
        assert core.backdrop is not None
        assert len(drawn) == len(core.actors) + len(core.backdrop.masses)

    def test_a_foreground_mass_covers_the_cast(self):
        """The alley's foreground is drawn over everyone, in the mask as in the panel."""
        core = _street()
        ids = list(_fills(render_mask(core)))
        assert core.backdrop is not None
        front = max(core.backdrop.masses, key=lambda mass: mass.depth)
        assert front.plane == "foreground"
        assert ids[-1] == f"mass-{front.id}"

    def test_figures_a_picture_draws(self):
        core = compile_source(
            "panel: {size: [800, 600]}\nsetting: {image: art/p.png}\ncast: {ANA: {figure: ana}}\n",
            base={
                "art/p.png": png(800, 600),
                "art/p.art.yaml": contract(
                    (800, 600),
                    {
                        "ana": {
                            "face": {"center": [300, 200], "radius": 50},
                            "body": [[250, 150], [350, 150], [360, 600], [240, 600]],
                        },
                        "ben": {"face": {"center": [600, 220], "radius": 40}},
                    },
                ),
            },
        ).core
        fills = _fills(render_mask(core))
        assert list(fills) == ["figure-ana", "figure-ben"]
        assert fills["figure-ana"] != fills["figure-ben"]


class TestColours:
    def test_every_region_its_own_and_none_black(self):
        fills = _fills(render_mask(_street()))
        assert len(set(fills.values())) == len(fills)
        assert "#000000" not in fills.values()

    def test_nothing_is_black(self):
        assert re.search(r'<rect [^>]*fill="#000000"/>', render_mask(_street()))

    def test_masses_are_distinct_and_never_dark(self):
        colours = [mass_colour(index) for index in range(256)]
        assert len(set(colours)) == 256
        for each in colours:
            assert re.fullmatch(r"#[0-9a-f]{6}", each)
            assert max(_channels(each)) >= 150

    def test_every_character_slot_is_distinct(self):
        colours = [character_colour(slot) for slot in range(CHARACTER_SLOTS)]
        assert len(set(colours)) == CHARACTER_SLOTS

    def test_a_mass_never_takes_a_character_s_colour(self):
        """Two bands: a character is saturated, a mass is not, so a wall is never Alice."""
        characters = {character_colour(slot) for slot in range(CHARACTER_SLOTS)}
        masses = {mass_colour(index) for index in range(1024)}
        assert not characters & masses
        assert all(min(_channels(each)) < 60 for each in characters)
        assert all(min(_channels(each)) > 80 for each in masses)

    def test_masses_are_coloured_in_drawing_order(self):
        core = _street()
        assert core.backdrop is not None
        fills = _fills(render_mask(core))
        masses = [name for name in fills if name.startswith("mass-")]
        assert [fills[name] for name in masses] == [
            mass_colour(index) for index in range(len(masses))
        ]


class TestACharacterKeepsItsColour:
    """A character is the same colour in every panel, so regional prompts follow them."""

    def test_from_panel_to_panel(self):
        alone = compile_source("cast: {alice: {reference: alice}}\n").core
        crowded = _street()
        assert (
            _fills(render_mask(alone))["actor-alice"] == _fills(render_mask(crowded))["actor-alice"]
        )
        assert _fills(render_mask(alone))["actor-alice"] == character_colour(slot_of("alice"))

    def test_a_figure_takes_the_colour_of_the_part_it_plays(self):
        figures = compile_source(
            "panel: {size: [800, 600]}\nsetting: {image: art/p.png}\n"
            "cast: {alice: {figure: ana}}\n",
            base={
                "art/p.png": png(800, 600),
                "art/p.art.yaml": contract(
                    (800, 600),
                    {
                        "ana": {"face": {"center": [300, 200], "radius": 50}},
                        "ben": {"face": {"center": [600, 220], "radius": 40}},
                    },
                ),
            },
        ).core
        fills = _fills(render_mask(figures))
        assert fills["figure-ana"] == character_colour(slot_of("alice"))
        assert fills["figure-ben"] == character_colour(slot_of("ben"))

    def test_two_characters_on_one_slot_the_later_name_steps_to_the_next_free_one(self):
        names = [f"x{index}" for index in range(400)]
        first = names[0]
        second = next(name for name in names[1:] if slot_of(name) == slot_of(first))
        a, b = sorted((first, second))
        core = compile_source(
            f"cast: {{{a}: {{reference: alice}}, {b}: {{reference: bob}}}}\n"
            f"staging: [{a} left_of {b}]\n"
        ).core
        fills = _fills(render_mask(core))
        assert fills[f"actor-{a}"] == character_colour(slot_of(a))
        assert fills[f"actor-{b}"] == character_colour((slot_of(a) + 1) % CHARACTER_SLOTS)

    def test_whatever_order_they_are_drawn_in(self):
        """Which one steps aside is decided by name, never by who is in front."""
        names = [f"x{index}" for index in range(400)]
        first = names[0]
        second = next(name for name in names[1:] if slot_of(name) == slot_of(first))
        a, b = sorted((first, second))
        source = f"cast: {{{a}: {{reference: alice}}, {b}: {{reference: bob}}}}\n"
        front = compile_source(source + f"staging: [{a} left_of {b}, {a} in_front_of {b}]\n").core
        back = compile_source(source + f"staging: [{a} left_of {b}, {b} in_front_of {a}]\n").core
        assert _fills(render_mask(front))[f"actor-{a}"] == _fills(render_mask(back))[f"actor-{a}"]


class TestTheDocument:
    def test_marks_are_not_masked(self):
        plain = render_mask(compile_source(STREET.replace(", marks: [plewds]", "")).core)
        assert render_mask(_street()) == plain

    def test_a_slanted_panel_is_clipped_to_its_outline(self):
        core = _street()
        outline = ((0.0, 0.0), (900.0, 0.0), (1000.0, 800.0), (100.0, 800.0))
        svg = render_mask(core.model_copy(update={"outline": outline}))
        assert 'clip-path="url(#outline)"' in svg
        assert "clip-path" not in render_mask(core)

    def test_read_right_to_left_the_mask_is_the_same(self):
        source = (
            STREET + "script:\n  - say: {by: alice, text: Hi.}\n  - say: {by: bob, text: Yes.}\n"
        )
        ltr = compile_source(source).core
        rtl = compile_source("direction: rtl\n" + source).core
        assert render_mask(rtl) == render_mask(ltr)

    def test_the_same_bytes_every_time(self):
        assert render_mask(_street()) == render_mask(_street())
        assert render_mask(_street()).endswith("</svg>\n")


def test_both_maps_are_rasterised_without_antialiasing():
    """An antialiased edge blends two regions' colours into one that belongs to neither id,
    and two planes' greys into a depth no plane has."""
    core = _street()
    for svg in (render_mask(core), render_depth(core)):
        root = next(line for line in svg.splitlines() if line.startswith("<svg "))
        assert 'shape-rendering="crispEdges"' in root


def test_a_character_stepping_aside_never_lands_on_a_colour_already_taken():
    """Three names: `a` and `c` on one slot, and `b`, between them by name, on the next. `c`
    steps past both, to the slot after."""
    names = sorted(f"x{index}" for index in range(2000))
    found = None
    for a in names:
        b = next(
            (n for n in names if n > a and slot_of(n) == (slot_of(a) + 1) % CHARACTER_SLOTS), None
        )
        c = next((n for n in names if b is not None and n > b and slot_of(n) == slot_of(a)), None)
        if b is not None and c is not None:
            found = (a, b, c)
            break
    assert found is not None
    a, b, c = found
    core = compile_source(
        f"cast: {{{a}: {{reference: alice}}, {b}: {{reference: bob}}, {c}: {{reference: alice}}}}\n"
        f"staging: [{a} left_of {b}, {b} left_of {c}]\n"
    ).core
    fills = _fills(render_mask(core))
    assert fills[f"actor-{c}"] == character_colour((slot_of(a) + 2) % CHARACTER_SLOTS)
    assert len({fills[f"actor-{name}"] for name in (a, b, c)}) == 3
