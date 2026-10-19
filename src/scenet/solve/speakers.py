"""What lettering needs to know about somebody in the panel, and nothing else.

Balloon, caption and sound-effect placement used to read posed puppets directly. They
need far less than a puppet carries: a face no box may cover, a point a tail aims at, a
silhouette that is costly to cover, and -- for a puppet -- where its eyes are and which
way it is looking. That is the whole interface, and this module is it.

It is what lets a figure that a supplied picture draws (#71) be lettered by the same
rules as a puppet Scenet posed: its contract declares a face, a mouth and a body in the
picture's pixels, and once those are mapped into the panel the placer cannot tell the
two apart. Nobody here ever sees artwork, the picture's or a puppet's.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon

from scenet.assets.kinematics import ResolvedPuppet
from scenet.geom import Circle, Point, Vector

#: Looking nowhere in particular: no line of sight for a balloon to block.
STILL = Vector(0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Speaker:
    """Somebody in the panel, as lettering placement sees them.

    Attributes:
        face: The disc no balloon, caption or sound effect may cover.
        mouth: Where a tail aims. Stopped on `face`'s outline when it lies inside it, as a
            letterer stops a tail at the head rather than stabbing into it.
        body: The silhouette a box pays to cover, as a polygon, or empty when none is
            known -- a figure whose contract declares only a face.
        eyes: Where a line of sight starts, if it is known.
        gaze: Which way they are looking. Zero for nobody in particular, and for a figure a
            picture draws, whose gaze nobody declared: the gaze term then costs nothing.
    """

    face: Circle
    mouth: Point
    body: tuple[Point, ...] = ()
    eyes: Point | None = None
    gaze: Vector = STILL

    @property
    def outline(self) -> tuple[Point, ...]:
        """The points that bound them: the body, or the corners of the face's square.

        What a sound they make is centred on and searched around.

        Example:
            >>> from scenet.geom import Circle, Point
            >>> Speaker(Circle(10.0, 10.0, 2.0), Point(10.0, 11.0)).outline[0]
            Point(x=8.0, y=8.0)
        """
        if self.body:
            return self.body
        square = self.face.as_bbox()
        return (
            Point(square.x, square.y),
            Point(square.right, square.y),
            Point(square.right, square.bottom),
            Point(square.x, square.bottom),
        )


def speaker_of(puppet: ResolvedPuppet) -> Speaker:
    """A posed puppet, reduced to what lettering reads.

    The mouth is the puppet's `mouth` anchor, or the face's centre for one that declares
    none -- where the tail of a balloon it speaks has always aimed.

    Args:
        puppet: The posed puppet.

    Returns:
        Its face, mouth, hull, eyes and gaze.
    """
    return Speaker(
        face=puppet.face,
        mouth=puppet.anchors.get("mouth", puppet.face.centre),
        body=puppet.hull,
        eyes=puppet.anchors.get("eyes"),
        gaze=puppet.gaze,
    )


@dataclass(frozen=True, slots=True)
class Bystanders:
    """Figures drawn in the panel who are not in its cast: always in the way, never heard.

    A picture can draw more people than a panel casts -- a crowd, of whom two speak. Each
    face it declares is still a face, so it is as forbidden to lettering as a speaker's;
    each body still costs, and nobody is forgiven covering it, since nobody speaks from it.

    Attributes:
        faces: Their faces, in the order the contract declares them.
        bodies: Their silhouettes, for those who have one, in the same order.
    """

    faces: tuple[Circle, ...] = ()
    bodies: tuple[Polygon, ...] = ()

    @classmethod
    def of(cls, figures: Sequence[Speaker]) -> "Bystanders":
        """Bystanders from the figures nobody cast.

        Args:
            figures: Each figure, as lettering sees them.

        Returns:
            Their faces, and the bodies of those that declare one.
        """
        return cls(
            faces=tuple(figure.face for figure in figures),
            bodies=tuple(
                Polygon([(point.x, point.y) for point in figure.body])
                for figure in figures
                if figure.body
            ),
        )


#: A panel with nobody in it but its cast.
NOBODY = Bystanders()
