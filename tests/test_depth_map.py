"""The depth export: stepped grey planes in painter's order, white near and black far (#72).

Scenet is orthographic and has no metric depth. What it has is a painter's order, so the map
is flat grey planes in that order -- and honest about being nothing more. ControlNet's depth
maps run white near, black far: the reverse of the backdrop's own ladder, where aerial
perspective makes far planes paler. Reusing those tones would hand a model an inverted map.
"""

import re

import pytest

from scenet.core import PanelCore
from scenet.emit.depth import render_depth
from scenet.emit.mask import render_mask
from scenet.emit.svg import fmt, render
from scenet.pipeline import compile_source
from tests.images import contract, png

STREET = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot}
setting: {place: street, time: day}
cast:
  alice: {reference: alice, pose: pointing}
  bob: {reference: bob, facing: left}
  carol: {reference: alice}
staging:
  - alice left_of bob
  - bob left_of carol
  - bob in_front_of carol
"""

FILL = re.compile(r'id="([^"]+)"[^>]*? fill="(#[0-9a-f]{6})"')


def _fills(svg: str) -> dict[str, str]:
    return dict(FILL.findall(svg))


def _grey(fill: str) -> int:
    assert fill[1:3] == fill[3:5] == fill[5:7], fill
    return int(fill[1:3], 16)


def _street() -> PanelCore:
    return compile_source(STREET).core


class TestTheLadder:
    def test_the_frontmost_is_white(self):
        core = _street()
        fills = _fills(render_depth(core))
        front = max(core.actors, key=lambda actor: actor.depth)
        assert fills[f"actor-{front.id}"] == "#ffffff"

    def test_nothing_is_black(self):
        svg = render_depth(_street())
        assert re.search(r'<rect [^>]*fill="#000000"/>', svg)

    def test_nearer_is_paler_everywhere(self):
        """Grey rises with depth, actors and masses alike, and equal depths are equal."""
        core = _street()
        fills = _fills(render_depth(core))
        assert core.backdrop is not None
        depths = {f"actor-{actor.id}": actor.depth for actor in core.actors}
        depths |= {
            f"mass-{mass.id}": mass.depth for mass in core.backdrop.masses if mass.kind != "sky"
        }
        for one, depth in depths.items():
            for other, other_depth in depths.items():
                if depth < other_depth:
                    assert _grey(fills[one]) < _grey(fills[other]), (one, other)
                if depth == other_depth:
                    assert fills[one] == fills[other]

    def test_the_sky_is_at_infinity(self):
        core = _street()
        fills = _fills(render_depth(core))
        assert core.backdrop is not None
        skies = [mass for mass in core.backdrop.masses if mass.kind == "sky"]
        assert skies
        assert all(fills[f"mass-{mass.id}"] == "#000000" for mass in skies)

    def test_far_is_darker_the_reverse_of_the_backdrop_s_tones(self):
        core = _street()
        assert core.backdrop is not None
        far = next(m for m in core.backdrop.masses if m.plane == "far" and m.kind != "sky")
        near = next(m for m in core.backdrop.masses if m.plane == "near")
        fills = _fills(render_depth(core))
        assert _grey(fills[f"mass-{far.id}"]) < _grey(fills[f"mass-{near.id}"])
        assert _grey(far.tone) > _grey(near.tone)

    def test_the_steps_are_even(self):
        """Ranks, not distances: every plane one step nearer than the one behind it."""
        core = _street()
        greys = sorted({_grey(fill) for fill in _fills(render_depth(core)).values()} - {0})
        steps = len(greys)
        assert greys == [round(255 * (index + 1) / steps) for index in range(steps)]


class TestWhatIsDrawn:
    def test_in_the_panel_s_own_painter_s_order(self):
        core = _street()
        drawn = re.findall(r'id="((?:actor|mass)-[^"]+)"', render(core))
        assert list(_fills(render_depth(core))) == drawn

    def test_each_actor_is_its_hull(self):
        core = _street()
        svg = render_depth(core)
        alice = core.actor("alice")
        points = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in alice.hull)
        assert f'id="actor-alice" points="{points}"' in svg

    def test_marks_are_not_depth(self):
        plain = render_depth(_street())
        marked = render_depth(
            compile_source(STREET.replace("pose: pointing", "pose: pointing, marks: [plewds]")).core
        )
        assert marked == plain

    def test_a_slanted_panel_is_clipped_to_its_outline(self):
        core = _street()
        outline = ((0.0, 0.0), (900.0, 0.0), (1000.0, 800.0), (100.0, 800.0))
        svg = render_depth(core.model_copy(update={"outline": outline}))
        assert (
            '<clipPath id="outline"><polygon points="0,0 900,0 1000,800 100,800"/></clipPath>'
            in svg
        )
        assert "clip-path" not in render_depth(core)

    def test_the_document_is_the_panel_s_size(self):
        svg = render_depth(_street())
        assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<svg ')
        assert 'width="1000" height="800" viewBox="0 0 1000 800"' in svg
        assert svg.endswith("</svg>\n")


def _picture(cast: str) -> PanelCore:
    return compile_source(
        f"panel: {{size: [800, 600]}}\nsetting: {{image: art/p.png}}\ncast: {cast}\n",
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


class TestOverAPicture:
    def test_the_picture_is_the_far_plane(self):
        """Its content was never seen: nothing in it is said to be nearer than anything."""
        core = _picture("{alice: {reference: alice}}")
        svg = render_depth(core)
        assert "<image" not in svg
        assert _fills(svg) == {"actor-alice": "#ffffff"}

    def test_figures_it_draws_are_one_plane_in_front_of_it(self):
        """A silhouette is in front of what it is drawn against; nothing orders two of them."""
        svg = render_depth(_picture("{ANA: {figure: ana}}"))
        assert _fills(svg) == {"figure-ana": "#ffffff", "figure-ben": "#ffffff"}
        assert re.search(
            r'<g id="figure-ben" fill="#ffffff"><circle cx="600" cy="220" r="40"/></g>', svg
        )


@pytest.mark.parametrize("source", [STREET, "cast: {a: {reference: alice}}\n"])
def test_read_right_to_left_the_depth_is_the_same(source: str):
    source += "script:\n  - say: {by: alice, text: Hi.}\n" if "alice:" in source else ""
    ltr = compile_source(source).core
    rtl = compile_source("direction: rtl\n" + source).core
    assert render_depth(rtl) == render_depth(ltr)


def test_the_same_bytes_every_time():
    assert render_depth(_street()) == render_depth(_street())


class TestTheCanvas:
    """The maps are on the same pixel grid as the pose and the boxes: one unit, one pixel."""

    def test_a_panel_of_whole_units_is_its_own_size(self):
        svg = render_depth(_street())
        assert 'width="1000" height="800" viewBox="0 0 1000 800"' in svg

    def test_a_panel_of_part_units_is_drawn_on_the_canvas_rounded_up(self):
        core = _street().model_copy(update={"width": 999.5, "height": 799.25})
        for svg in (render_depth(core), render_mask(core)):
            assert 'width="1000" height="800" viewBox="0 0 1000 800"' in svg
            assert '<rect x="0" y="0" width="1000" height="800" fill="#000000"/>' in svg

    def test_nothing_moves_on_the_wider_canvas(self):
        core = _street()
        wider = core.model_copy(update={"width": 999.5, "height": 799.25})
        shapes = [line for line in render_depth(core).splitlines() if "points=" in line]
        assert shapes == [line for line in render_depth(wider).splitlines() if "points=" in line]


def test_a_hand_edited_core_with_figures_and_actors_puts_the_figures_in_front():
    """Panel Core is hand-editable, and a Core may hold both, though no document compiles to
    one: the figures' plane is in front of every actor, and the actors keep their steps."""
    actors = _street()
    figures = _picture("{ANA: {figure: ana}}")
    core = actors.model_copy(update={"figures": figures.figures, "backdrop": None})
    fills = _fills(render_depth(core))
    assert fills["figure-ana"] == fills["figure-ben"] == "#ffffff"
    assert all(_grey(fills[f"actor-{actor.id}"]) < 255 for actor in core.actors)
    depths = sorted({actor.depth for actor in core.actors})
    assert {_grey(fills[f"actor-{a.id}"]) for a in core.actors} == {
        round(255 * (rank + 1) / (len(depths) + 1)) for rank in range(len(depths))
    }
