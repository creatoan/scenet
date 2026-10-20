"""A contract's pixels, mapped into the panel through the picture's fit (#71).

The property that matters: a point the contract declares lands exactly where the SVG
draws that pixel of the picture. The renderer draws the picture into Core's `box`, so pixel
`(px, py)` of a `w` by `h` picture is drawn at `box.x + px * box.width / w` across and
`box.y + py * box.height / h` down -- each axis on its own, which is how a renderer does
it. The solver uses one scale for both, since the picture is never stretched; these tests
hold the two to each other, under `cover` and `contain`, for any picture and any panel.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scenet.assets.artwork import ArtworkContract
from scenet.geom import BBox, Circle, Point
from scenet.ir import Fit
from scenet.solve.backdrop import ResolvedImage, fit_box
from scenet.solve.figures import PlacedFigure, place_figures


def _placed(pixels: tuple[int, int], panel: BBox, fit: Fit) -> ResolvedImage:
    return ResolvedImage(pixels=pixels, fit=fit, box=fit_box(pixels, panel, fit))


def _drawn_at(image: ResolvedImage, pixel: tuple[float, float]) -> tuple[float, float]:
    """Where the SVG draws a pixel of the picture: each axis scaled on its own."""
    box, (width, height) = image.box, image.pixels
    return box.x + pixel[0] * box.width / width, box.y + pixel[1] * box.height / height


@st.composite
def _cases(draw: st.DrawFn) -> tuple[ResolvedImage, tuple[float, float]]:
    width = draw(st.integers(1, 6000))
    height = draw(st.integers(1, 6000))
    panel = BBox(
        draw(st.floats(-500, 500)),
        draw(st.floats(-500, 500)),
        draw(st.floats(10, 3000)),
        draw(st.floats(10, 3000)),
    )
    image = _placed((width, height), panel, draw(st.sampled_from(list(Fit))))
    pixel = (draw(st.floats(0, width)), draw(st.floats(0, height)))
    return image, pixel


@given(_cases())
def test_every_point_lands_where_the_picture_is_drawn(
    case: tuple[ResolvedImage, tuple[float, float]],
):
    image, pixel = case
    width, height = image.pixels
    contract = ArtworkContract.model_validate(
        {
            "size": [width, height],
            "figures": {
                "ana": {
                    "face": {"center": list(pixel), "radius": 1},
                    "mouth": list(pixel),
                    "body": [[0, 0], [width, 0], list(pixel)] if pixel[1] > 0 else None,
                }
            },
            "keep_out": [[[0, 0], [width, 0], [width, height]]],
        }
    )
    placed = place_figures(contract, image)
    (ana,) = placed.figures
    expected = _drawn_at(image, pixel)
    tolerance = 1e-9 * max(1.0, abs(image.box.width), abs(image.box.height), *map(abs, expected))
    assert ana.face.cx == pytest.approx(expected[0], abs=tolerance)
    assert ana.face.cy == pytest.approx(expected[1], abs=tolerance)
    assert ana.mouth is not None
    assert (ana.mouth.x, ana.mouth.y) == (ana.face.cx, ana.face.cy)
    corner = placed.keep_out[0][2]
    far = _drawn_at(image, (width, height))
    assert corner.x == pytest.approx(far[0], abs=tolerance)
    assert corner.y == pytest.approx(far[1], abs=tolerance)


@given(_cases())
def test_a_radius_scales_as_the_picture_does(case: tuple[ResolvedImage, tuple[float, float]]):
    image, pixel = case
    contract = ArtworkContract.model_validate(
        {
            "size": list(image.pixels),
            "figures": {"ana": {"face": {"center": list(pixel), "radius": 7}}},
        }
    )
    (ana,) = place_figures(contract, image).figures
    assert ana.face.r == pytest.approx(7 * image.box.width / image.pixels[0])
    assert ana.face.r == pytest.approx(7 * image.box.height / image.pixels[1])


class TestCoverAndContain:
    PANEL = BBox(0.0, 0.0, 1200.0, 600.0)
    #: A 3:2 picture: wider than tall, but less so than the 2:1 panel.
    CONTRACT = ArtworkContract.model_validate(
        {
            "size": [900, 600],
            "figures": {
                "top": {"face": {"center": [450, 0], "radius": 30}},
                "middle": {"face": {"center": [450, 300], "radius": 30}},
            },
        }
    )

    def _faces(self, fit: Fit) -> dict[str, Circle]:
        placed = place_figures(self.CONTRACT, _placed((900, 600), self.PANEL, fit))
        return {figure.name: figure.face for figure in placed.figures}

    def test_cover_crops_top_and_bottom_and_keeps_the_middle_centred(self):
        faces = self._faces(Fit.COVER)
        # Scaled by 4/3 to fill 1200 across, 800 tall, overhanging 100 above and below.
        assert faces["middle"] == Circle(600.0, 300.0, 40.0)
        assert faces["top"].cy == pytest.approx(-100.0)

    def test_contain_shows_it_all_with_bands_at_the_sides(self):
        faces = self._faces(Fit.CONTAIN)
        # Scaled by 1 to fit 600 down, 900 across, with 150 either side.
        assert faces["middle"] == Circle(600.0, 300.0, 30.0)
        assert faces["top"] == Circle(600.0, 0.0, 30.0)


class TestAFigureAsLetteringSeesIt:
    def test_speaks_from_its_mouth(self):
        figure = PlacedFigure("ana", Circle(10.0, 10.0, 5.0), Point(12.0, 14.0))
        assert figure.speaker.mouth == Point(12.0, 14.0)
        assert figure.speaker.gaze.length == 0
        assert figure.speaker.eyes is None

    def test_speaks_from_its_face_with_no_mouth(self):
        figure = PlacedFigure("ana", Circle(10.0, 10.0, 5.0))
        assert figure.speaker.mouth == Point(10.0, 10.0)

    def test_keeps_its_body(self):
        body = (Point(0.0, 0.0), Point(4.0, 0.0), Point(4.0, 4.0))
        assert PlacedFigure("ana", Circle(1.0, 1.0, 1.0), body=body).speaker.body == body

    def test_order_is_the_contracts(self):
        contract = ArtworkContract.model_validate(
            {
                "size": [10, 10],
                "figures": {
                    name: {"face": {"center": [5, 5], "radius": 1}} for name in ("zed", "ana")
                },
            }
        )
        placed = place_figures(contract, _placed((10, 10), BBox(0, 0, 10, 10), Fit.COVER))
        assert [figure.name for figure in placed.figures] == ["zed", "ana"]
        assert math.isclose(placed.figures[0].face.r, 1.0)
