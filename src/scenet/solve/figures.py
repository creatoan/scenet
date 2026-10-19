"""Figures a supplied picture draws, placed in the panel through the picture's fit (#71).

An artwork contract declares each figure in the picture's own pixels. The picture is fitted
to the panel -- centred, scaled, never stretched (:func:`fit_box
<scenet.solve.backdrop.fit_box>`) -- and every declared point goes through the same
transform, so a face lands exactly where the picture draws it, under `cover` and
`contain` alike. One scale serves both axes, because the picture keeps its proportions.

Nothing here moves anybody. The solver chooses no position for a figure: the artist did.
It only translates the contract into the panel's units, for lettering to work around.
"""

from dataclasses import dataclass

from scenet.assets.artwork import ArtworkContract
from scenet.geom import Circle, Point
from scenet.solve.backdrop import ResolvedImage
from scenet.solve.speakers import Speaker

__all__ = ["PlacedFigure", "PlacedPicture", "place_figures"]


@dataclass(frozen=True, slots=True)
class PlacedFigure:
    """One figure the picture draws, in panel units.

    Attributes:
        name: Its name in the contract.
        face: Its face, which no lettering may cover.
        mouth: Where a tail it speaks ends, if declared.
        body: Its silhouette, or empty when none is declared.
    """

    name: str
    face: Circle
    mouth: Point | None = None
    body: tuple[Point, ...] = ()

    @property
    def speaker(self) -> Speaker:
        """The figure as lettering sees it: no gaze, and the face's centre for a mouth."""
        return Speaker(face=self.face, mouth=self.mouth or self.face.centre, body=self.body)


@dataclass(frozen=True, slots=True)
class PlacedPicture:
    """What a picture's contract declares, placed.

    Attributes:
        figures: Each figure, in the order the contract declares them.
        keep_out: Each region lettering should stay off, in the same order.
    """

    figures: tuple[PlacedFigure, ...] = ()
    keep_out: tuple[tuple[Point, ...], ...] = ()


def place_figures(contract: ArtworkContract, image: ResolvedImage) -> PlacedPicture:
    """Map a contract from the picture's pixels into the panel.

    Args:
        contract: What the picture draws, in its pixels.
        image: Where the picture was placed.

    Returns:
        The figures and keep-out regions, in panel units.

    Example:
        >>> from scenet.assets.artwork import ArtworkContract
        >>> from scenet.geom import BBox
        >>> from scenet.ir import Fit
        >>> from scenet.solve.backdrop import ResolvedImage
        >>> contract = ArtworkContract.model_validate(
        ...     {
        ...         "size": [200, 100],
        ...         "figures": {"ana": {"face": {"center": [50, 40], "radius": 10}}},
        ...     }
        ... )
        >>> picture = ResolvedImage((200, 100), Fit.COVER, BBox(-50.0, 0.0, 400.0, 200.0))
        >>> place_figures(contract, picture).figures[0].face
        Circle(cx=50.0, cy=80.0, r=20.0)
    """
    box = image.box
    scale = box.width / image.pixels[0]

    def point(pixel: tuple[float, float]) -> Point:
        return Point(box.x + pixel[0] * scale, box.y + pixel[1] * scale)

    def face(center: tuple[float, float], radius: float) -> Circle:
        middle = point(center)
        return Circle(middle.x, middle.y, radius * scale)

    figures = tuple(
        PlacedFigure(
            name=name,
            face=face(figure.face.center, figure.face.radius),
            mouth=point(figure.mouth) if figure.mouth is not None else None,
            body=tuple(point(corner) for corner in figure.body or ()),
        )
        for name, figure in contract.figures.items()
    )
    keep_out = tuple(tuple(point(corner) for corner in region) for region in contract.keep_out)
    return PlacedPicture(figures=figures, keep_out=keep_out)
