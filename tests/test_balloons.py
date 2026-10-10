"""Balloon placement rules that are easy to get subtly wrong."""

from collections.abc import Sequence

import pytest
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from scenet.assets.kinematics import ResolvedPuppet
from scenet.errors import BalloonPlacementError
from scenet.geom import BBox, Circle, Point, Vector
from scenet.ir import CaptionEvent, CaptionKind, PlacementZone, SayEvent
from scenet.solve.balloons import (
    READING_EPSILON,
    W_CAPTION_EDGE,
    W_EMANATA_OCCLUSION,
    W_GAZE_BLOCKING,
    W_MASS_OCCLUSION,
    W_OCCLUSION,
    W_PREFERRED_ZONE,
    _blocks_gaze,
    _candidate_positions,
    _curve_hits,
    _edge_slack,
    _emanata_cost,
    _Limits,
    _mass_cost,
    _occlusion_cost,
    _reading_order_allows,
    _rim_point,
    _score,
    _score_caption,
    _segment_hits_box,
    _stop_at_face,
    caption_text,
    place_script,
    route_tail,
)
from scenet.solve.text import ITALIC_FONT_PATH, layout_text, load_metrics


def _actor(
    name: str = "a",
    face: Circle | None = None,
    *,
    mouth: Point | None = None,
    eyes: Point | None = None,
    gaze: Vector | None = None,
) -> ResolvedPuppet:
    """A character reduced to what placement looks at: a face, two anchors and a gaze.

    The silhouette is the face's own square, so a box clear of the face is clear of the
    body too, and no occlusion cost creeps into a test about something else.
    """
    face = face or Circle(200.0, 200.0, 20.0)
    anchors = {key: point for key, point in (("mouth", mouth), ("eyes", eyes)) if point is not None}
    left, top = face.cx - face.r, face.cy - face.r
    right, bottom = face.cx + face.r, face.cy + face.r
    return ResolvedPuppet(
        name=name,
        pose="stand",
        facing_right=True,
        scale=1.0,
        joints={},
        anchors=anchors,
        landmarks={},
        capsules=(),
        blobs=(),
        face=face,
        gaze=gaze or Vector(0.0, 0.0),
        hull=(Point(left, top), Point(right, top), Point(right, bottom), Point(left, bottom)),
    )


def _square(left: float, top: float, right: float, bottom: float) -> Polygon:
    return box(left, top, right, bottom)


class TestReadingOrder:
    """A balloon may never sit above *and* left of one that precedes it."""

    def test_below_is_allowed(self):
        first = BBox(100, 100, 80, 40)
        assert _reading_order_allows([first], BBox(0, 200, 80, 40))

    def test_right_of_is_allowed(self):
        first = BBox(100, 100, 80, 40)
        assert _reading_order_allows([first], BBox(200, 0, 80, 40))

    def test_above_and_left_is_refused(self):
        first = BBox(100, 100, 80, 40)
        assert not _reading_order_allows([first], BBox(0, 0, 80, 40))

    def test_nothing_placed_yet_allows_anything(self):
        assert _reading_order_allows([], BBox(0, 0, 80, 40))

    def test_checked_against_every_predecessor_not_just_the_last(self):
        # "Readable after" is not a transitive relation, which is the whole point of
        # this test. Balloon 1 is legal after balloon 0 because it is far to its right;
        # the candidate is legal after balloon 1 because it is below it -- and yet the
        # candidate sits above *and* left of balloon 0, so reading 0, 1, candidate takes
        # the page in the wrong order. Comparing only against the last one misses it.
        first = BBox(0, 300, 100, 60)
        second = BBox(400, 100, 100, 60)
        candidate = BBox(0, 200, 100, 60)

        assert _reading_order_allows([first], second), "second follows first legally"
        assert _reading_order_allows([second], candidate), "legal against the last alone"
        assert not _reading_order_allows([first, second], candidate), (
            "must be refused: it is above and left of the first balloon"
        )

    @pytest.mark.parametrize("rise", [READING_EPSILON, READING_EPSILON / 2])
    def test_level_within_the_tolerance_counts_as_below(self, rise: float):
        # Two balloons side by side whose tops differ by less than READING_EPSILON read
        # as one row, whichever is a hair higher -- up to and including the tolerance.
        first = BBox(100, 100, 80, 40)
        assert _reading_order_allows([first], BBox(0, first.y - rise, 40, 40))

    @pytest.mark.parametrize("reach", [READING_EPSILON, READING_EPSILON / 2])
    def test_touching_within_the_tolerance_counts_as_right_of(self, reach: float):
        first = BBox(100, 100, 80, 40)
        assert _reading_order_allows([first], BBox(first.right - reach, 0, 40, 40))


class TestTailTermination:
    """A tail stops on the face outline, not at the mouth anchor buried inside it."""

    def test_tail_stops_on_the_outline(self):
        face = Circle(cx=100.0, cy=100.0, r=30.0)
        mouth = Point(100.0, 110.0)  # inside the head
        tip = _stop_at_face(Point(100.0, 300.0), mouth, face)

        distance = ((tip.x - face.cx) ** 2 + (tip.y - face.cy) ** 2) ** 0.5
        assert distance == pytest.approx(face.r, abs=1e-6)

    def test_a_mouth_outside_the_face_is_left_alone(self):
        face = Circle(cx=100.0, cy=100.0, r=10.0)
        mouth = Point(100.0, 200.0)
        assert _stop_at_face(Point(100.0, 300.0), mouth, face) == mouth

    # Coordinates are panel units, and nothing fixes what one is worth: the same
    # geometry at a thousandth of the size must stop on the outline just the same.
    @pytest.mark.parametrize(
        ("start_y", "radius"), [(0.3, 0.1), (1.0, 0.5), (30.0, 10.0), (3000.0, 1000.0)]
    )
    def test_the_tip_is_on_the_outline_at_any_scale(self, start_y: float, radius: float):
        face = Circle(0.0, 0.0, radius)
        tip = _stop_at_face(Point(0.0, start_y), face.centre, face)
        assert tip.x == pytest.approx(0.0, abs=1e-12)
        assert tip.y == pytest.approx(radius, rel=1e-9)

    def test_a_tail_starting_on_the_outline_ends_where_it_starts(self):
        # A balloon may touch a face -- only overlapping one is illegal -- so a tail can
        # begin exactly on the outline. Its tip is then that same point.
        face = Circle(0.0, 0.0, 10.0)
        start = Point(0.0, 10.0)
        assert _stop_at_face(start, face.centre, face) == start

    def test_a_clear_run_produces_a_straight_tail(self):
        route = route_tail(BBox(0, 0, 60, 40), Point(200.0, 200.0), obstacles=[])
        assert not route.is_curved

    def test_an_obstructing_face_bends_the_tail(self):
        balloon = BBox(0, 0, 60, 40)
        mouth = Point(400.0, 400.0)
        blocker = Circle(cx=200.0, cy=200.0, r=40.0)
        assert route_tail(balloon, mouth, obstacles=[blocker]).is_curved


class TestTheRimPoint:
    """Where a tail leaves the balloon: on its outline, in the mouth's direction."""

    BALLOON = BBox(0.0, 0.0, 60.0, 40.0)  # centre (30, 20)

    @pytest.mark.parametrize(
        ("toward", "rim"),
        [
            (Point(500.0, 20.0), Point(60.0, 20.0)),  # level, to the right
            (Point(-500.0, 20.0), Point(0.0, 20.0)),  # level, to the left
            (Point(30.0, 500.0), Point(30.0, 40.0)),  # straight down
            (Point(31.0, 20.0), Point(60.0, 20.0)),  # one unit right of centre
            (Point(30.0, 21.0), Point(30.0, 40.0)),  # one unit below centre
        ],
    )
    def test_the_tail_leaves_from_the_edge_facing_the_mouth(self, toward: Point, rim: Point):
        assert _rim_point(self.BALLOON, toward) == rim

    def test_a_mouth_at_the_centre_has_no_direction(self):
        assert _rim_point(self.BALLOON, self.BALLOON.centre) == self.BALLOON.centre


class TestBentTails:
    """When a face is in the way, the tail bends by the smallest offset that clears it.

    A chord of length 200 runs from (50, 30) to (250, 30); its normal points down the
    page. A bend of `m` puts the control point `m * 200` off the chord's midpoint, and
    the curve's apex halfway there. Faces placed on those apexes block the bends one at
    a time, so each test pins which bend, on which side, the router settles on.
    """

    BALLOON = BBox(10.0, 10.0, 40.0, 40.0)  # its rim, toward the mouth, is (50, 30)
    MOUTH = Point(250.0, 30.0)
    CHORD = Circle(150.0, 30.0, 10.0)  # what makes the straight tail fail

    @staticmethod
    def _apex_blockers(*offsets: float) -> list[Circle]:
        return [Circle(150.0, 30.0 + offset, 10.0) for offset in offsets]

    def _route(self, blockers: list[Circle]):
        return route_tail(self.BALLOON, self.MOUTH, obstacles=[self.CHORD, *blockers])

    @pytest.mark.parametrize(
        ("blocked", "control_y"),
        [
            ((), 30.0 + 70.0),  # the gentlest bend, below the chord
            ((35.0,), 30.0 - 70.0),  # below is blocked, so above
            ((35.0, -35.0), 30.0 + 140.0),  # both sides blocked: the next bend
            ((35.0, -35.0, 70.0, -70.0), 30.0 + 220.0),
            ((35.0, -35.0, 70.0, -70.0, 110.0, -110.0), 30.0 + 320.0),
        ],
    )
    def test_the_smallest_clearing_bend_is_chosen(
        self, blocked: tuple[float, ...], control_y: float
    ):
        route = self._route(self._apex_blockers(*blocked))
        assert route.start == Point(50.0, 30.0)
        assert route.end == self.MOUTH
        assert route.control is not None
        assert route.control.x == pytest.approx(150.0)
        assert route.control.y == pytest.approx(control_y)

    def test_when_nothing_clears_the_tail_goes_straight(self):
        offsets = (35.0, 70.0, 110.0, 160.0)
        route = self._route(self._apex_blockers(*offsets, *(-o for o in offsets)))
        assert route.control is None
        assert route.end == self.MOUTH


class TestCurveSampling:
    """`_curve_hits` follows the quadratic curve the tail will be drawn as."""

    START, CONTROL, END = Point(10.0, 20.0), Point(60.0, 140.0), Point(130.0, 30.0)

    def _on_curve(self, t: float) -> Point:
        inverse = 1 - t
        return Point(
            inverse * inverse * self.START.x
            + 2 * inverse * t * self.CONTROL.x
            + t * t * self.END.x,
            inverse * inverse * self.START.y
            + 2 * inverse * t * self.CONTROL.y
            + t * t * self.END.y,
        )

    @pytest.mark.parametrize("t", [0.25, 0.5, 0.75, 0.97])
    def test_a_face_on_the_curve_is_hit(self, t: float):
        point = self._on_curve(t)
        face = Circle(point.x, point.y, 1.5)
        assert _curve_hits(self.START, self.CONTROL, self.END, [face])

    def test_a_face_on_the_chord_but_off_the_curve_is_missed(self):
        midpoint = Point((self.START.x + self.END.x) / 2, (self.START.y + self.END.y) / 2)
        assert not _curve_hits(
            self.START, self.CONTROL, self.END, [Circle(midpoint.x, midpoint.y, 5.0)]
        )

    def test_the_curve_stops_at_its_end(self):
        # Where the curve would go if it carried on for one more sample past its end.
        beyond = self._on_curve(17 / 16)
        assert not _curve_hits(
            self.START, self.CONTROL, self.END, [Circle(beyond.x, beyond.y, 2.0)]
        )


class TestSegmentAgainstBox:
    """The gaze test: a segment hits a box that it reaches, edges included."""

    TARGET = BBox(10.0, 10.0, 10.0, 10.0)

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (Point(0.0, 15.0), Point(10.0, 15.0)),  # stops on the left edge
            (Point(30.0, 15.0), Point(20.0, 15.0)),  # stops on the right edge
            (Point(15.0, 0.0), Point(15.0, 10.0)),  # stops on the top edge
            (Point(15.0, 30.0), Point(15.0, 20.0)),  # stops on the bottom edge
        ],
    )
    def test_a_segment_reaching_an_edge_hits(self, start: Point, end: Point):
        assert _segment_hits_box(start, end, self.TARGET)

    def test_a_segment_stopping_short_misses(self):
        assert not _segment_hits_box(Point(0.0, 15.0), Point(9.0, 15.0), self.TARGET)


class TestGaze:
    def test_a_gaze_reaches_as_far_as_its_reach(self):
        # Looking straight down, with a box ninety units below the eyes.
        actor = _actor(eyes=Point(100.0, 100.0), gaze=Vector(0.0, 1.0))
        assert _blocks_gaze(BBox(80.0, 170.0, 40.0, 20.0), actor, reach=90.0)

    def test_the_first_candidate_is_straight_above_the_head(self):
        # Ties resolve upward because "above the speaker" is tried first.
        speaker = _actor(face=Circle(200.0, 200.0, 20.0))
        first = _candidate_positions(speaker, (60.0, 30.0), BBox(0.0, 0.0, 400.0, 400.0))[0]
        assert first.centre.x == pytest.approx(200.0)
        assert first.centre.y < 200.0 - 20.0


class TestLimits:
    def test_the_least_overlap_with_an_inset_is_refused(self):
        limits = _Limits(blocked=(BBox(0.0, 0.0, 10.0, 10.0),))
        assert not limits.allow(BBox(9.5, 0.0, 10.0, 1.0))  # half a square unit


class TestCostsAreNormalisedByTheBoxArea:
    """A box lying wholly over something costs exactly that thing's weight, at any size."""

    @pytest.mark.parametrize("size", [(1.5, 1.0), (40.0, 25.0)])
    def test_covering_a_silhouette(self, size: tuple[float, float]):
        hull = _square(-1000.0, -1000.0, 1000.0, 1000.0)
        assert _occlusion_cost(BBox(0.0, 0.0, *size), {"x": hull}, None) == pytest.approx(
            W_OCCLUSION
        )

    @pytest.mark.parametrize("size", [(1.5, 1.0), (40.0, 25.0)])
    def test_covering_a_mass(self, size: tuple[float, float]):
        mass = (_square(-1000.0, -1000.0, 1000.0, 1000.0), 1.0)
        assert _mass_cost(BBox(0.0, 0.0, *size), [mass]) == pytest.approx(W_MASS_OCCLUSION)

    def test_no_masses_cost_nothing(self):
        assert _mass_cost(BBox(0.0, 0.0, 10.0, 10.0), []) == 0.0

    @pytest.mark.parametrize("size", [(1.5, 1.0), (40.0, 25.0)])
    def test_covering_emanata(self, size: tuple[float, float]):
        zone = _square(-1000.0, -1000.0, 1000.0, 1000.0)
        assert _emanata_cost(BBox(0.0, 0.0, *size), [zone]) == pytest.approx(W_EMANATA_OCCLUSION)

    def test_every_actors_emanata_counts(self):
        # Half the box over one actor's marks and half over another's: all of it is
        # covered, so it costs the full weight, not the last actor's half.
        candidate = BBox(0.0, 0.0, 10.0, 10.0)
        halves = [_square(0.0, 0.0, 5.0, 10.0), _square(5.0, 0.0, 10.0, 10.0)]
        assert _emanata_cost(candidate, halves) == pytest.approx(W_EMANATA_OCCLUSION)


class TestEdgeSlack:
    """Distance to the nearest edge, for a panel that does not start at the origin."""

    PANEL = BBox(100.0, 50.0, 400.0, 300.0)

    @pytest.mark.parametrize(
        "candidate",
        [
            BBox(110.0, 200.0, 50.0, 50.0),  # 10 from the left
            BBox(250.0, 60.0, 50.0, 50.0),  # 10 from the top
            BBox(440.0, 200.0, 50.0, 50.0),  # 10 from the right
            BBox(250.0, 290.0, 50.0, 50.0),  # 10 from the bottom
        ],
    )
    def test_the_nearest_edge_decides(self, candidate: BBox):
        assert _edge_slack(candidate, self.PANEL) == pytest.approx(10.0)


class TestCaptionText:
    def test_a_run_of_spoken_captions_closes_once(self):
        run = (
            CaptionEvent(text="Get down!", kind=CaptionKind.SPOKEN),
            CaptionEvent(text="All of you!", kind=CaptionKind.SPOKEN),
        )
        assert caption_text(run, 0) == "“Get down!"
        assert caption_text(run, 1) == "“All of you!”"


class TestBalloonScore:
    PANEL = BBox(0.0, 0.0, 400.0, 400.0)

    def _score(self, speaker: ResolvedPuppet, candidate: BBox, limits: _Limits | None = None):
        return _score(
            candidate,
            speaker=speaker,
            actors={speaker.name: speaker},
            hulls={},
            panel=self.PANEL,
            prefer=None,
            placed=[],
            masses=[],
            limits=limits or _Limits(),
        )

    def test_a_balloon_under_an_inset_is_illegal(self):
        candidate = BBox(20.0, 20.0, 60.0, 30.0)
        limits = _Limits(blocked=(BBox(0.0, 0.0, 50.0, 50.0),))
        assert self._score(_actor(), candidate) < float("inf")
        assert self._score(_actor(), candidate, limits) == float("inf")

    def test_a_speaker_without_a_mouth_is_spoken_from_the_face(self):
        face = Circle(200.0, 200.0, 20.0)
        candidate = BBox(20.0, 20.0, 60.0, 30.0)
        mouthless = self._score(_actor(face=face), candidate)
        assert mouthless == pytest.approx(
            self._score(_actor(face=face, mouth=face.centre), candidate)
        )


class TestCaptionScore:
    # Wider than tall, so the diagonal is neither side.
    PANEL = BBox(0.0, 0.0, 400.0, 200.0)
    DIAGONAL = (400.0**2 + 200.0**2) ** 0.5

    def _score(
        self,
        candidate: BBox,
        *,
        actors: dict[str, ResolvedPuppet] | None = None,
        hulls: dict[str, Polygon] | None = None,
        emanata: Sequence[BaseGeometry] = (),
    ) -> float:
        return _score_caption(
            candidate,
            actors=actors or {},
            hulls=hulls or {},
            panel=self.PANEL,
            prefer=PlacementZone.TOP_LEFT,
            placed=[],
            masses=[],
            emanata=emanata,
        )

    @pytest.mark.parametrize(
        "candidate",
        [
            BBox(2.0, 3.0, 60.0, 20.0),  # hugging the corner
            BBox(150.0, 80.0, 60.0, 20.0),  # far from every edge
        ],
    )
    def test_an_empty_panel_costs_the_zone_and_the_edge(self, candidate: BBox):
        # The two soft terms a caption pays with nobody in the panel: distance from the
        # zone it prefers, and distance from the edge it wants to tuck into.
        target = Point(400.0 * 0.25, 200.0 * 0.2)
        zone = W_PREFERRED_ZONE * candidate.centre.distance_to(target) / self.DIAGONAL
        edge = W_CAPTION_EDGE * min(
            1.0, _edge_slack(candidate, self.PANEL) / (self.DIAGONAL * 0.05)
        )
        assert self._score(candidate) == pytest.approx(zone + edge)

    def test_covering_emanata_costs_a_caption_too(self):
        candidate = BBox(150.0, 80.0, 60.0, 20.0)
        marks = [_square(150.0, 80.0, 180.0, 100.0)]
        extra = self._score(candidate, emanata=marks) - self._score(candidate)
        assert extra == pytest.approx(_emanata_cost(candidate, marks))
        assert extra > 0

    def test_standing_in_a_sight_line_costs_a_caption_too(self):
        # A sight line reaches three face radii: 60 here, so it reaches a box 35 away.
        face = Circle(100.0, 100.0, 20.0)
        looking = _actor(face=face, eyes=face.centre, gaze=Vector(1.0, 0.0))
        idle = _actor(face=face, eyes=face.centre)
        candidate = BBox(135.0, 90.0, 20.0, 20.0)
        hulls = {"a": _square(80.0, 80.0, 120.0, 120.0)}
        blocked = self._score(candidate, actors={"a": looking}, hulls=hulls)
        clear = self._score(candidate, actors={"a": idle}, hulls=hulls)
        assert blocked - clear == pytest.approx(W_GAZE_BLOCKING)


class TestPlaceScript:
    """The arguments `place_script` is handed reach every box it places."""

    PANEL = BBox(0.0, 0.0, 600.0, 400.0)
    FACE = Circle(450.0, 280.0, 25.0)

    def _speaker(self) -> dict[str, ResolvedPuppet]:
        return {"a": _actor(face=self.FACE)}

    def _say(self, text: str = "Over here!", prefer: PlacementZone | None = None) -> SayEvent:
        return SayEvent(by="a", text=text, prefer=prefer)

    def test_a_font_size_override_sets_balloons_and_captions(self):
        layout = place_script(
            [CaptionEvent(text="Later."), self._say()],
            self._speaker(),
            self.PANEL,
            font_size=9.0,
        )
        assert layout.captions[0].block.font_size == 9.0
        assert layout.balloons[0].block.font_size == 9.0

    def test_dialogue_and_roman_captions_are_measured_in_the_face_given(self):
        # Hand the italic file in as the roman one: every roman box must be measured
        # with it, which it would not be if the argument fell back to the default.
        italic = load_metrics(str(ITALIC_FONT_PATH))
        layout = place_script(
            [CaptionEvent(text="Get down!", kind=CaptionKind.SPOKEN), self._say()],
            self._speaker(),
            self.PANEL,
            metrics=italic,
            font_size=12.0,
        )
        assert layout.balloons[0].block == layout_text("Over here!", font_size=12.0, metrics=italic)
        assert layout.captions[0].block == layout_text(
            "“Get down!”", font_size=12.0, metrics=italic
        )
        assert layout.balloons[0].block != layout_text("Over here!", font_size=12.0)

    def test_italic_captions_are_measured_in_the_italic_face_given(self):
        roman = load_metrics()
        layout = place_script(
            [CaptionEvent(text="Meanwhile.")],
            {},
            self.PANEL,
            italic_metrics=roman,
            font_size=12.0,
        )
        assert layout.captions[0].block == layout_text("Meanwhile.", font_size=12.0, metrics=roman)

    def test_a_caption_stays_inside_a_shaped_panel(self):
        # The top-left corner is cut away, which is where the caption would otherwise go.
        inside = [(150.0, 0.0), (600.0, 0.0), (600.0, 400.0), (0.0, 400.0), (0.0, 150.0)]
        layout = place_script([CaptionEvent(text="Later.")], {}, self.PANEL, inside=inside)
        caption = layout.captions[0].box
        assert Polygon(inside).contains(box(caption.x, caption.y, caption.right, caption.bottom))

    def test_a_caption_keeps_off_emanata(self):
        unmarked = place_script([CaptionEvent(text="Later.")], {}, self.PANEL).captions[0].box
        zone = [
            Point(unmarked.x, unmarked.y),
            Point(unmarked.right, unmarked.y),
            Point(unmarked.right, unmarked.bottom),
            Point(unmarked.x, unmarked.bottom),
        ]
        marked = (
            place_script([CaptionEvent(text="Later.")], {}, self.PANEL, emanata={"a": [zone]})
            .captions[0]
            .box
        )
        assert marked.overlap_area(unmarked) == 0

    def test_a_balloon_keeps_out_from_under_an_inset(self):
        natural = place_script([self._say()], self._speaker(), self.PANEL).balloons[0].box
        moved = (
            place_script([self._say()], self._speaker(), self.PANEL, exclusions=[natural])
            .balloons[0]
            .box
        )
        assert moved.overlap_area(natural) == 0

    def test_a_speaker_without_a_mouth_is_pointed_at_from_the_face(self):
        balloon = place_script([self._say()], self._speaker(), self.PANEL).balloons[0]
        assert balloon.tail.end.distance_to(self.FACE.centre) == pytest.approx(self.FACE.r)

    def test_no_room_names_the_balloon_and_its_speaker(self):
        cramped = BBox(0.0, 0.0, 60.0, 60.0)
        actors = {"a": _actor(face=Circle(30.0, 30.0, 20.0))}
        with pytest.raises(BalloonPlacementError, match="balloon 0 spoken by 'a'"):
            place_script([self._say("Far too much to say.")], actors, cramped, font_size=12.0)

    def test_a_tail_bends_around_somebody_elses_face(self):
        # The speaker asks for the top left, and a bystander's face sits up and to the
        # left of theirs, on the line between. The tail must bend around the bystander --
        # and not around the speaker, whose face it is meant to arrive at.
        bystander = Circle(380.0, 250.0, 30.0)
        actors = {
            "a": _actor("a", self.FACE, mouth=Point(450.0, 290.0)),
            "b": _actor("b", bystander),
        }
        balloon = place_script(
            [self._say(prefer=PlacementZone.TOP_LEFT)], actors, self.PANEL
        ).balloons[0]
        assert balloon.tail.control is not None
        assert not _curve_hits(
            balloon.tail.start, balloon.tail.control, balloon.tail.end, [bystander]
        )
