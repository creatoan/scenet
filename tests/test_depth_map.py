"""The depth export: stepped grey planes in painter's order, white near and black far (#72).

Scenet is orthographic and has no metric depth. What it has is a painter's order, so the map
is flat grey planes in that order -- and honest about being nothing more. ControlNet's depth
maps run white near, black far: the reverse of the backdrop's own ladder, where aerial
perspective makes far planes paler. Reusing those tones would hand a model an inverted map.

A ground, a floor, a stretch of water and a ceiling are not walls: they recede (#227). Each is a
straight ramp from its own step at the horizon toward the reader, which is what a flat surface's
inverse depth is through a pinhole camera. Its paint names its step as the fallback, so reading
a region's fill reads its step, ramp or not.
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

#: A region's step: its flat fill, or the fallback a ramp's paint names.
FILL = re.compile(r'id="([^"]+)"[^>]*? fill="(?:url\(#ramp-\d+\) )?(#[0-9a-f]{6})"')

GRADIENT = re.compile(
    r'<linearGradient id="(ramp-\d+)" gradientUnits="userSpaceOnUse" '
    r'x1="0" y1="([^"]+)" x2="0" y2="([^"]+)">'
    r'<stop offset="0" stop-color="(#[0-9a-f]{6})"/>'
    r'<stop offset="1" stop-color="(#[0-9a-f]{6})"/></linearGradient>'
)

PAINT = re.compile(r'id="([^"]+)"[^>]*? fill="url\(#(ramp-\d+)\) (#[0-9a-f]{6})"')

#: The kinds that recede: three lie below the horizon, the ceiling above it.
RECEDING = {"ground", "floor", "water", "ceiling"}


def _fills(svg: str) -> dict[str, str]:
    return dict(FILL.findall(svg))


def _grey(fill: str) -> int:
    assert fill[1:3] == fill[3:5] == fill[5:7], fill
    return int(fill[1:3], 16)


def _ramps(svg: str) -> dict[str, tuple[float, float, int, int]]:
    """Each ramped region's `(y1, y2, grey at y1, grey at y2)`, checking its fallback is y1's."""
    gradients = {
        ramp: (float(y1), float(y2), _grey(start), _grey(end))
        for ramp, y1, y2, start, end in GRADIENT.findall(svg)
    }
    painted = PAINT.findall(svg)
    assert len(gradients) == len(painted) == svg.count("<linearGradient")
    for _, ramp, fallback in painted:
        assert gradients[ramp][2] == _grey(fallback)
    return {region: gradients[ramp] for region, ramp, _ in painted}


def _street() -> PanelCore:
    return compile_source(STREET).core


def _panel(setting: str) -> PanelCore:
    """A long shot of Alice, centre, in a 900 by 560 panel: the horizon is at 308."""
    return compile_source(
        "panel: {size: [900, 560]}\ncamera: {shot: long_shot}\n"
        f"setting: {setting}\ncast:\n  alice: {{reference: alice, at: center}}\n"
    ).core


DOCKS = "{place: docks}"
ROOM = "{place: room}"
ALLEY = "{place: alley}"
FOREGROUND_GROUND = (
    "{masses: [{kind: sky, plane: far}, {kind: ground, plane: near},"
    " {kind: ground, plane: foreground}]}"
)


def _horizon(core: PanelCore, horizon: float | None) -> PanelCore:
    assert core.backdrop is not None
    return core.model_copy(
        update={"backdrop": core.backdrop.model_copy(update={"horizon": horizon})}
    )


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


class TestARecedingSurface:
    """A ground, floor or water ramps from the horizon down, a ceiling from it up (#227)."""

    @pytest.mark.parametrize("setting", [DOCKS, ROOM, "{place: street}"])
    def test_a_ground_floor_or_water_ramps_from_its_step_at_the_horizon_to_the_bottom(
        self, setting: str
    ):
        core = _panel(setting)
        svg = render_depth(core)
        ramps, steps = _ramps(svg), _fills(svg)
        assert core.backdrop is not None
        lying = [m for m in core.backdrop.masses if m.kind in {"ground", "floor", "water"}]
        assert lying
        for mass in lying:
            region = f"mass-{mass.id}"
            assert ramps[region] == (308.0, 560.0, _grey(steps[region]), 255)
            assert ramps[region][2] < 255

    def test_a_ceiling_ramps_up_from_the_horizon_to_the_top_edge(self):
        core = _panel(ROOM)
        assert core.backdrop is not None
        ceiling = next(m for m in core.backdrop.masses if m.kind == "ceiling")
        assert _ramps(render_depth(core))[f"mass-{ceiling.id}"] == (308.0, 0.0, 128, 255)

    @pytest.mark.parametrize("setting", [DOCKS, ROOM, ALLEY, "{place: street}"])
    def test_nothing_else_ramps(self, setting: str):
        core = _panel(setting)
        svg = render_depth(core)
        assert core.backdrop is not None
        receding = {
            f"mass-{m.id}" for m in core.backdrop.masses if m.kind in RECEDING and m.depth < 0
        }
        assert set(_ramps(svg)) == receding
        flat = re.findall(r'id="([^"]+)"[^>]*? fill="#[0-9a-f]{6}"', svg)
        assert set(flat) == set(_fills(svg)) - receding

    def test_the_sky_stays_black(self):
        core = _panel(DOCKS)
        svg = render_depth(core)
        assert '<polygon id="mass-m0" ' in svg
        assert _fills(svg)["mass-m0"] == "#000000"
        assert "mass-m0" not in _ramps(svg)

    def test_over_a_picture_nothing_ramps(self):
        assert "linearGradient" not in render_depth(_picture("{ANA: {figure: ana}}"))

    def test_a_ramp_is_said_exactly_and_its_paint_falls_back_to_its_step(self):
        svg = render_depth(_panel(DOCKS))
        assert (
            '  <linearGradient id="ramp-2" gradientUnits="userSpaceOnUse" x1="0" y1="308" x2="0"'
            ' y2="560"><stop offset="0" stop-color="#808080"/>'
            '<stop offset="1" stop-color="#ffffff"/></linearGradient>\n'
        ) in svg
        assert re.search(
            r'<polygon id="mass-m2" points="[^"]+" fill="url\(#ramp-2\) #808080"/>', svg
        )

    def test_every_ramp_is_defined_after_the_paper_and_before_any_shape(self):
        core = _panel(DOCKS)
        outline = ((0.0, 0.0), (800.0, 0.0), (900.0, 560.0), (100.0, 560.0))
        for svg in (render_depth(core), render_depth(core.model_copy(update={"outline": outline}))):
            lines = svg.splitlines()
            assert lines[2].startswith("  <rect ")
            assert [line.startswith("  <linearGradient ") for line in lines[3:5]] == [True, True]
            assert not any("<linearGradient" in line for line in lines[5:])

    def test_a_ramp_ends_at_the_farthest_actor_s_step(self):
        """In the alley Alice is a step below the foreground wall: the ground stops at her grey,
        so it never comes out nearer than the feet standing on it."""
        svg = render_depth(_panel(ALLEY))
        steps = _fills(svg)
        assert _grey(steps["actor-alice"]) == 170
        assert steps["mass-m4"] == "#ffffff"
        assert _ramps(svg) == {"mass-m3": (308.0, 560.0, 85, 170)}

    def test_a_ground_in_the_foreground_stays_flat(self):
        """It is drawn over the cast, a step above every actor: a ramp would only darken."""
        svg = render_depth(_panel(FOREGROUND_GROUND))
        assert _fills(svg)["mass-m2"] == "#ffffff"
        assert _ramps(svg) == {"mass-m1": (308.0, 560.0, 85, 170)}

    def test_with_nobody_in_front_a_ramp_ends_white_and_the_nearest_ground_is_flat(self):
        core = _panel(DOCKS).model_copy(update={"actors": ()})
        svg = render_depth(core)
        assert _fills(svg)["mass-m4"] == "#ffffff"
        assert _ramps(svg) == {"mass-m2": (308.0, 560.0, 170, 255)}

    def test_without_a_horizon_a_surface_recedes_from_its_own_far_edge(self):
        """A hand-edited backdrop may set none: a ground starts at its top, a ceiling at its
        bottom."""
        docks = _ramps(render_depth(_horizon(_panel(DOCKS), None)))
        assert docks == {
            "mass-m2": (300.44, 560.0, 128, 255),
            "mass-m4": (408.8, 560.0, 191, 255),
        }
        room = _ramps(render_depth(_horizon(_panel(ROOM), None)))
        assert room["mass-m4"] == (64.06, 0.0, 128, 255)
        assert room["mass-m5"] == (308.0, 560.0, 191, 255)

    @pytest.mark.parametrize("horizon", [560.0, 600.0])
    def test_a_ground_with_no_room_to_recede_is_flat(self, horizon: float):
        svg = render_depth(_horizon(_panel(DOCKS), horizon))
        assert _ramps(svg) == {}
        assert _fills(svg)["mass-m4"] == "#bfbfbf"

    @pytest.mark.parametrize("horizon", [0.0, -10.0])
    def test_a_ceiling_with_no_room_to_recede_is_flat(self, horizon: float):
        svg = render_depth(_horizon(_panel(ROOM), horizon))
        assert "mass-m4" not in _ramps(svg)
        assert _fills(svg)["mass-m4"] == "#808080"
        assert _ramps(svg)["mass-m5"] == (horizon, 560.0, 191, 255)

    def test_a_ceiling_with_a_horizon_just_below_the_top_still_recedes(self):
        """Any room at all is room: the run is checked against the top edge, not a unit."""
        ramps = _ramps(render_depth(_horizon(_panel(ROOM), 0.5)))
        assert ramps["mass-m4"] == (0.5, 0.0, 128, 255)

    def test_a_ramp_is_named_by_its_place_never_by_the_mass(self):
        """A hand-edited id is escaped in its attribute, but nothing keeps it inside `url()`."""
        core = _panel(DOCKS)
        assert core.backdrop is not None
        masses = list(core.backdrop.masses)
        masses[2] = masses[2].model_copy(update={"id": "m2) x"})
        edited = core.model_copy(
            update={"backdrop": core.backdrop.model_copy(update={"masses": tuple(masses)})}
        )
        svg = render_depth(edited)
        assert re.findall(r"url\(#([^)]*)\)", svg) == ["ramp-2", "ramp-4"]


@pytest.mark.parametrize(
    "source",
    [
        STREET,
        "cast: {a: {reference: alice}}\n",
        "panel: {size: [900, 560]}\nsetting: {place: room}\ncast: {alice: {reference: alice}}\n",
    ],
)
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
