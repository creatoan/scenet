"""The mask export: one flat fill per actor, figure and mass, ids as in Core (#72).

A segmentation with stable labels: every region the panel's geometric contract names --
an actor's hull, a figure's body and face, a mass's polygon -- in its own colour, under the
id the panel's SVG gives it, drawn in the panel's own painter's order so that what covers
what is what the panel draws.
"""

import re

from scenet.core import PanelCore
from scenet.emit.mask import colour, render_mask
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

    def test_the_first_two_hundred_and_fifty_six_are_distinct_and_never_dark(self):
        colours = [colour(index) for index in range(256)]
        assert len(set(colours)) == 256
        for each in colours:
            assert re.fullmatch(r"#[0-9a-f]{6}", each)
            assert max(int(each[i : i + 2], 16) for i in (1, 3, 5)) >= 150

    def test_colours_go_in_drawing_order(self):
        fills = _fills(render_mask(_street()))
        assert list(fills.values()) == [colour(index) for index in range(len(fills))]


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
