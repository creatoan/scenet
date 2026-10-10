"""Actor placement: ordering, anchors, grounding, facing and draw order.

Several of these assert on *priority resolution* rather than on exact coordinates --
that two actors asked to stand in the same place end up apart, that a crowded panel
loosens rather than fails. Those behaviours are the reason a constraint solver is here
at all, so they are what needs guarding.
"""

from itertools import pairwise
from pathlib import Path

import pytest
import yaml

from scenet.assets.contract import PuppetLibrary, PuppetSpec, default_library
from scenet.assets.kinematics import resolve
from scenet.frontends.yaml_front import parse_panel
from scenet.geom import BBox, Point
from scenet.ir import AnchorX
from scenet.solve.camera import CameraSolution, solve_camera
from scenet.solve.staging import (
    ANCHOR_FRACTIONS,
    LayoutError,
    Placement,
    _extent_of,
    _fit_cast_across_frame,
    depth_order,
    horizontal_order,
    solve_staging,
)

PANEL = 1000.0


@pytest.fixture(scope="module")
def library() -> PuppetLibrary:
    return default_library()


def bounds_of(placement: Placement, library: PuppetLibrary) -> BBox:
    return resolve(
        library.get(placement.reference),
        pose=placement.pose,
        facing_right=placement.facing_right,
        scale=placement.scale,
        origin=placement.origin,
    ).bounds


def solve(source: str, library: PuppetLibrary) -> dict[str, Placement]:
    placements, _ = solve_staging(parse_panel(source), library)
    return {placement.actor_id: placement for placement in placements}


TWO_ACTORS = """
camera: {shot: full_shot}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third}
"""


class TestHorizontalOrder:
    def test_declared_order_is_honoured(self, library: PuppetLibrary):
        panel = parse_panel("""
cast:
  a: {reference: alice, at: right_third}
  b: {reference: bob,   at: left_third}
staging:
  - a left_of b
""")
        assert horizontal_order(panel) == ("a", "b")

    def test_undeclared_order_falls_back_to_anchors(self, library: PuppetLibrary):
        panel = parse_panel("""
cast:
  a: {reference: alice, at: right_third}
  b: {reference: bob,   at: left_third}
""")
        assert horizontal_order(panel) == ("b", "a")

    def test_equal_anchors_break_by_id_for_determinism(self):
        panel = parse_panel("""
cast:
  zeta:  {reference: alice, at: center}
  alpha: {reference: bob,   at: center}
""")
        assert horizontal_order(panel) == ("alpha", "zeta")


class TestAnchors:
    def test_a_lone_actor_lands_on_its_anchor(self, library: PuppetLibrary):
        """With nothing to conflict with, the weak anchor preference is met exactly."""
        placements = solve(
            "camera: {shot: full_shot}\ncast:\n  a: {reference: alice, at: left_third}\n", library
        )
        centre = bounds_of(placements["a"], library).centre.x
        assert centre == pytest.approx(PANEL * ANCHOR_FRACTIONS[AnchorX.LEFT_THIRD], abs=1.0)

    @pytest.mark.parametrize("anchor", ["left_edge", "left_third", "center", "right_third"])
    def test_each_anchor_places_the_actor_where_it_says(self, library: PuppetLibrary, anchor: str):
        placements = solve(
            f"camera: {{shot: full_shot}}\ncast:\n  a: {{reference: alice, at: {anchor}}}\n",
            library,
        )
        centre = bounds_of(placements["a"], library).centre.x
        assert centre == pytest.approx(PANEL * ANCHOR_FRACTIONS[AnchorX(anchor)], abs=1.0)


class TestNonOverlap:
    def test_actors_never_overlap(self, library: PuppetLibrary):
        placements = solve(TWO_ACTORS, library)
        left = bounds_of(placements["alice"], library)
        right = bounds_of(placements["bob"], library)
        assert left.right < right.x

    def test_actors_sharing_an_anchor_are_pushed_apart(self, library: PuppetLibrary):
        """The reason for a constraint solver: a required non-overlap must beat a
        weak anchor preference without anyone writing a special case for it."""
        placements = solve(
            """
camera: {shot: full_shot}
cast:
  a: {reference: alice, at: center}
  b: {reference: bob,   at: center}
""",
            library,
        )
        left = bounds_of(placements["a"], library)
        right = bounds_of(placements["b"], library)
        assert left.right < right.x

    def test_a_crowded_panel_loosens_the_shot_rather_than_failing(self, library: PuppetLibrary):
        """Four actors at a close-up cannot fit; the camera must retreat."""
        source = "camera: {shot: close_up}\ncast:\n" + "\n".join(
            f"  a{i}: {{reference: alice}}" for i in range(4)
        )
        placements, camera = solve_staging(parse_panel(source), library)
        assert camera.was_pulled_back
        ordered = sorted(
            (bounds_of(placement, library) for placement in placements), key=lambda b: b.x
        )
        for earlier, later in pairwise(ordered):
            assert earlier.right < later.x


class TestGrounding:
    def test_shared_ground_aligns_feet(self, library: PuppetLibrary):
        placements = solve(
            """
camera: {shot: full_shot}
cast:
  alice: {reference: alice}
  bob:   {reference: bob}
staging:
  - alice ground_shared_with bob
""",
            library,
        )
        feet = [
            resolve(
                library.get(placement.reference),
                pose=placement.pose,
                facing_right=placement.facing_right,
                scale=placement.scale,
                origin=placement.origin,
            )
            .anchor("feet")
            .y
            for placement in placements.values()
        ]
        assert feet[0] == pytest.approx(feet[1], abs=0.5)

    def test_taller_actor_sits_higher_on_a_shared_ground(self, library: PuppetLibrary):
        placements = solve(
            """
camera: {shot: full_shot}
cast:
  alice: {reference: alice}
  bob:   {reference: bob}
staging:
  - alice ground_shared_with bob
""",
            library,
        )
        assert bounds_of(placements["bob"], library).y < bounds_of(placements["alice"], library).y


class TestFacing:
    def test_looking_at_turns_an_actor_toward_its_target(self, library: PuppetLibrary):
        placements = solve(
            """
cast:
  alice: {reference: alice, at: left_third, facing: left}
  bob:   {reference: bob,   at: right_third}
staging:
  - alice left_of bob
  - alice looking_at bob
""",
            library,
        )
        # `facing: left` is overridden: alice is left of her target, so she turns right.
        assert placements["alice"].facing_right is True

    def test_explicit_facing_is_used_when_no_gaze_target_exists(self, library: PuppetLibrary):
        placements = solve("cast:\n  a: {reference: alice, facing: left}\n", library)
        assert placements["a"].facing_right is False


class TestDepth:
    def test_unmentioned_actors_share_depth_zero(self):
        panel = parse_panel("cast:\n  a: {reference: alice}\n  b: {reference: bob}\n")
        assert depth_order(panel) == {"a": 0, "b": 0}

    def test_in_front_of_raises_depth(self):
        panel = parse_panel("""
cast:
  a: {reference: alice}
  b: {reference: bob}
staging:
  - a in_front_of b
""")
        depths = depth_order(panel)
        assert depths["a"] > depths["b"]

    def test_behind_is_the_same_relation_from_the_other_end(self):
        panel = parse_panel("""
cast:
  a: {reference: alice}
  b: {reference: bob}
staging:
  - b behind a
""")
        depths = depth_order(panel)
        assert depths["a"] > depths["b"]

    def test_chains_accumulate(self):
        panel = parse_panel("""
cast:
  a: {reference: alice}
  b: {reference: bob}
  c: {reference: alice}
staging:
  - a in_front_of b
  - b in_front_of c
""")
        depths = depth_order(panel)
        assert depths["a"] == 2
        assert depths["b"] == 1
        assert depths["c"] == 0

    def test_placements_come_out_in_draw_order(self, library: PuppetLibrary):
        placements, _ = solve_staging(
            parse_panel("""
cast:
  front: {reference: alice, at: left_third}
  back:  {reference: bob,   at: right_third}
staging:
  - front in_front_of back
"""),
            library,
        )
        assert [placement.actor_id for placement in placements] == ["back", "front"]


class TestErrors:
    def test_an_empty_cast_is_refused(self, library: PuppetLibrary):
        with pytest.raises(LayoutError, match="no cast"):
            solve_staging(parse_panel("panel: {size: [100, 100]}\ncast: {}\n"), library)


class TestDeterminism:
    def test_repeated_solves_are_identical(self, library: PuppetLibrary):
        panel = parse_panel(TWO_ACTORS)
        first, _ = solve_staging(panel, library)
        second, _ = solve_staging(panel, library)
        assert first == second

    # Found by the weekly Hypothesis exploration: two actors at the same anchor, whose
    # weak targets conflict. kiwisolver keys its internal maps by object address, so the
    # same system solved twice can come back a few ulps apart -- 352.33318181818186 one
    # time, 352.33318181818174 the next -- and a coordinate derived from it that lands on
    # a rounding boundary then prints differently.
    CONTESTED = """
panel: {size: [1399, 1196]}
camera: {shot: medium_shot}
cast:
  a: {reference: alice, facing: left}
  z: {reference: alice, facing: left}
"""

    def test_a_solved_position_carries_no_float_noise(self, library: PuppetLibrary):
        """Snapped to a millionth of a unit, far below anything the output shows and far
        above the noise, so the same system always yields the same number."""
        placements, _ = solve_staging(parse_panel(self.CONTESTED), library)
        for placement in placements:
            assert placement.x == round(placement.x, 6), placement.x

    def test_many_solves_give_bit_identical_positions(self, library: PuppetLibrary):
        panel = parse_panel(self.CONTESTED)
        solved = {
            tuple(repr(placement.x) for placement in solve_staging(panel, library)[0])
            for _ in range(40)
        }
        assert len(solved) == 1, solved

    def test_cast_declaration_order_does_not_change_geometry(self, library: PuppetLibrary):
        """Actors are keyed by name, so writing them in a different order must not
        move anybody. Only the framing reference depends on declaration order."""
        forward = solve(
            """
camera: {shot: full_shot}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: alice, at: right_third}
""",
            library,
        )
        backward = solve(
            """
camera: {shot: full_shot}
cast:
  bob:   {reference: alice, at: right_third}
  alice: {reference: alice, at: left_third}
""",
            library,
        )
        assert forward["alice"].x == pytest.approx(backward["alice"].x)
        assert forward["bob"].x == pytest.approx(backward["bob"].x)


# ---------------------------------------------------------------- mutation triage (#95)

LIBRARY_PATH = Path(__file__).parents[1] / "src" / "scenet" / "assets" / "library"


def _drawn_smaller(name: str, factor: float) -> PuppetSpec:
    """A shipped puppet with every length divided by `factor`: the same body, drawn in
    smaller units. Angles -- the poses -- do not scale."""
    data = yaml.safe_load((LIBRARY_PATH / f"{name}.puppet.yaml").read_text(encoding="utf-8"))

    def shrink(value: float) -> float:
        return value / factor

    def shrink_pair(pair: list[float]) -> list[float]:
        return [shrink(value) for value in pair]

    data["units_per_head"] = shrink(data["units_per_head"])
    data["landmarks"] = {key: shrink(value) for key, value in data["landmarks"].items()}
    for joint in data["joints"].values():
        joint["offset"] = shrink_pair(joint["offset"])
    for part in data["parts"]:
        for key in ("width", "radius"):
            if key in part:
                part[key] = shrink(part[key])
        if "offset" in part:
            part["offset"] = shrink_pair(part["offset"])
    for anchor in data["anchors"].values():
        anchor["offset"] = shrink_pair(anchor["offset"])
    data["face"]["radius"] = shrink(data["face"]["radius"])
    for feature in data["face"]["features"].values():
        feature["offset"] = shrink_pair(feature["offset"])
        feature["size"] = shrink(feature["size"])
    return PuppetSpec.model_validate(data)


CROWDED = """
panel: {size: [300, 400]}
camera: {shot: close_up}
cast:
  a: {reference: alice}
  b: {reference: alice}
"""


class TestAPuppetsUnitsAreItsOwn:
    def test_a_cast_drawn_five_hundred_times_smaller_is_composed_the_same(
        self, library: PuppetLibrary
    ):
        """The camera scales by the puppet's own height and the retreat by its own
        width, so the units it is drawn in cancel -- even when the whole cast is less
        than one unit wide."""
        tiny = PuppetLibrary({"alice": _drawn_smaller("alice", 500.0)})
        panel = parse_panel(CROWDED)
        normal_placements, normal_camera = solve_staging(panel, library)
        tiny_placements, tiny_camera = solve_staging(panel, tiny)
        assert normal_camera.was_pulled_back
        assert tiny_camera.pullback == pytest.approx(normal_camera.pullback)
        assert [p.x for p in tiny_placements] == pytest.approx([p.x for p in normal_placements])


class TestAnExtentIsMeasuredFromTheRoot:
    def test_it_does_not_depend_on_where_the_root_stands(self, library: PuppetLibrary):
        alice = library.get("alice")
        at_zero, elsewhere = Point(0.0, 500.0), Point(300.0, 500.0)
        here = _extent_of(
            resolve(alice, pose="pointing", facing_right=True, scale=1.0, origin=at_zero), at_zero
        )
        there = _extent_of(
            resolve(alice, pose="pointing", facing_right=True, scale=1.0, origin=elsewhere),
            elsewhere,
        )
        assert (there.left, there.right) == pytest.approx((here.left, here.right))
        assert here.left < 0 < here.right


class TestTheLeftToRightOrder:
    def test_an_actor_with_two_on_its_left_waits_for_both(self):
        order = horizontal_order(
            parse_panel(
                "cast:\n"
                "  a: {reference: alice, at: left_third}\n"
                "  b: {reference: bob, at: right_edge}\n"
                "  c: {reference: alice, at: left_edge}\n"
                "staging:\n"
                "  - a left_of c\n"
                "  - b left_of c\n"
            )
        )
        assert order.index("c") > order.index("a")
        assert order.index("c") > order.index("b")

    def test_an_actor_released_by_a_relation_is_placed_by_its_anchor_not_its_name(self):
        """`r` becomes free once `p` is placed, and stands left of `q` by anchor though
        `q` comes first by name."""
        order = horizontal_order(
            parse_panel(
                "cast:\n"
                "  p: {reference: alice, at: left_edge}\n"
                "  q: {reference: bob, at: right_edge}\n"
                "  r: {reference: alice, at: center}\n"
                "staging:\n"
                "  - p left_of r\n"
            )
        )
        assert order == ("p", "r", "q")


class TestDrawOrder:
    def test_placements_come_out_left_to_right_not_by_name(self, library: PuppetLibrary):
        placements, _ = solve_staging(
            parse_panel(
                "cast:\n  z: {reference: alice}\n  a: {reference: bob}\nstaging:\n  - z left_of a\n"
            ),
            library,
        )
        assert [placement.actor_id for placement in placements] == ["z", "a"]


class TestStagingErrorsSayWhatIsWrong:
    def test_an_empty_cast_is_named_as_such(self, library: PuppetLibrary):
        with pytest.raises(LayoutError, match=r"^panel has no cast; there is nothing to place$"):
            solve_staging(parse_panel("panel: {size: [600, 400]}\n"), library)

    def test_a_depth_cycle_names_an_actor_on_it(self):
        panel = parse_panel(
            "cast:\n  a: {reference: alice}\n  b: {reference: bob}\n"
            "staging:\n  - a in_front_of b\n  - b in_front_of a\n"
        )
        with pytest.raises(LayoutError, match="cyclic around 'a'"):
            depth_order(panel)


def _two_across(width: float, margin: float) -> str:
    return (
        f"panel: {{size: [{width}, {width}], margin: {margin}}}\n"
        "camera: {shot: close_up}\n"
        "cast:\n  a: {reference: alice}\n  b: {reference: alice}\n"
    )


def _fitted(source: str, library: PuppetLibrary) -> tuple[CameraSolution, CameraSolution]:
    panel = parse_panel(source)
    puppets = {actor: library.get(member.reference) for actor, member in panel.cast.items()}
    camera = solve_camera(
        puppets["a"],
        shot=panel.camera.shot,
        angle=panel.camera.angle,
        panel_height=panel.panel.height,
    )
    return camera, _fit_cast_across_frame(panel, puppets, camera)


class TestTheRoomTheCastIsFittedTo:
    """Two actors in a 200-unit panel: their one gap is 1.5% of the width, 3 units."""

    def test_the_margin_comes_out_of_the_room(self, library: PuppetLibrary):
        _, bare = _fitted(_two_across(600, 0), library)
        _, margined = _fitted(_two_across(600, 60), library)
        assert margined.scale / bare.scale == pytest.approx((600 - 120 - 9) / (600 - 9))

    @pytest.mark.parametrize("margin", [98.5, 99.0], ids=["no room", "less than none"])
    def test_with_no_room_left_the_camera_is_left_alone(
        self, library: PuppetLibrary, margin: float
    ):
        """A margin of 98.5 leaves 3 units, which the one gap takes exactly."""
        camera, fitted = _fitted(_two_across(200, margin), library)
        assert fitted is camera

    def test_half_a_unit_of_room_is_still_fitted_to(self, library: PuppetLibrary):
        camera, fitted = _fitted(_two_across(200, 98.25), library)
        assert fitted.scale < camera.scale
