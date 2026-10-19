"""What lettering knows about somebody in the panel: `scenet.solve.speakers`."""

import math

import pytest
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from scenet.assets.kinematics import ResolvedPuppet
from scenet.geom import BBox, Circle, Point, Vector
from scenet.ir import SfxEvent
from scenet.solve.sfx import _source_point, place_effects
from scenet.solve.speakers import NOBODY, Bystanders, Speaker, speaker_of
from scenet.solve.text import Typeface

FACE = Circle(100.0, 50.0, 10.0)
HULL = (Point(80.0, 30.0), Point(120.0, 30.0), Point(120.0, 200.0), Point(80.0, 200.0))


def _puppet(anchors: dict[str, Point]) -> ResolvedPuppet:
    return ResolvedPuppet(
        name="alice",
        pose="stand",
        facing_right=True,
        scale=1.0,
        joints={},
        anchors=anchors,
        landmarks={},
        capsules=(),
        blobs=(),
        face=FACE,
        gaze=Vector(1.0, 0.0),
        hull=HULL,
    )


class TestAPuppetAsLetteringSeesIt:
    def test_it_keeps_the_face_hull_eyes_and_gaze(self):
        eyes, mouth = Point(100.0, 45.0), Point(100.0, 55.0)
        speaker = speaker_of(_puppet({"eyes": eyes, "mouth": mouth}))
        assert speaker == Speaker(
            face=FACE, mouth=mouth, body=HULL, eyes=eyes, gaze=Vector(1.0, 0.0)
        )

    def test_a_puppet_without_a_mouth_is_spoken_from_its_face(self):
        speaker = speaker_of(_puppet({}))
        assert speaker.mouth == FACE.centre
        assert speaker.eyes is None


class TestTheOutline:
    def test_is_the_body_when_there_is_one(self):
        assert Speaker(face=FACE, mouth=FACE.centre, body=HULL).outline == HULL

    def test_is_the_faces_square_when_there_is_none(self):
        outline = Speaker(face=FACE, mouth=FACE.centre).outline
        assert outline == (
            Point(90.0, 40.0),
            Point(110.0, 40.0),
            Point(110.0, 60.0),
            Point(90.0, 60.0),
        )

    def test_a_sound_from_a_figure_with_no_body_comes_from_its_face(self):
        centre, reach = _source_point(Speaker(face=FACE, mouth=FACE.centre))
        assert centre == FACE.centre
        assert reach == pytest.approx(math.hypot(20.0, 20.0) / 2)


class TestASoundAndABystander:
    PANEL = BBox(0.0, 0.0, 600.0, 400.0)

    def _place(self, bystanders: Bystanders = NOBODY) -> Polygon:
        (effect,) = place_effects(
            [(0, SfxEvent(text="KRAK"))],
            actors={},
            hulls={},
            panel=self.PANEL,
            dialogue_size=20.0,
            typeface=Typeface(),
            bystanders=bystanders,
        )
        return effect.zone

    def test_a_sound_never_covers_a_bystanders_face(self):
        natural = self._place().centroid
        face = Circle(natural.x, natural.y, 40.0)
        zone = self._place(Bystanders(faces=(face,)))
        assert zone.distance(ShapelyPoint(face.cx, face.cy)) >= face.r

    def test_a_sound_pays_to_cover_a_bystanders_body(self):
        natural = self._place()
        moved = self._place(Bystanders(bodies=(natural,)))
        assert moved.intersection(natural).area < natural.area


class TestBystanders:
    def test_every_face_and_every_body_there_is(self):
        bodied = Speaker(face=FACE, mouth=FACE.centre, body=HULL)
        bare = Speaker(face=Circle(300.0, 50.0, 12.0), mouth=Point(300.0, 50.0))
        bystanders = Bystanders.of([bodied, bare])
        assert bystanders.faces == (FACE, bare.face)
        assert len(bystanders.bodies) == 1
        assert bystanders.bodies[0].area == pytest.approx(40.0 * 170.0)

    def test_nobody_is_nobody(self):
        assert Bystanders.of([]) == NOBODY
        assert NOBODY.faces == ()
        assert NOBODY.bodies == ()
