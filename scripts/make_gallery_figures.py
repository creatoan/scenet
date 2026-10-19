"""Paint the picture the gallery's figures example is lettered over, and write its contract.

`examples/gallery/art/figures.png` is a station platform at night: three people under a
lamp and a timetable board. Two of them talk; the third waits. They are painted here, from
the constants below, rather than drawn by anyone or downloaded from anywhere, so the
picture's licence is the repository's -- 0BSD -- and its provenance is this file.

**Its artwork contract is written from the same constants**, to
`examples/gallery/art/figures.art.yaml`: each face's centre and radius, each mouth, each
body, and the board, which lettering should keep off. So the contract is right by
construction, and `tests/test_gallery_figures.py` checks it against the picture: the pixel
at every face's centre is a face, and the pixel at every mouth is a mouth. That is what a
contract measured by eye -- or proposed by a detector -- has to be checked against too, and
the debug overlay is how: `scenet build --debug` draws the contract over the panel.

As with `make_gallery_art.py`, running it again on another machine may give different PNG
bytes -- zlib's output is not promised across versions -- and the same pixels.

Run it with `uv run python scripts/make_gallery_figures.py`.
"""

import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICTURE = ROOT / "examples" / "gallery" / "art" / "figures.png"
CONTRACT = PICTURE.with_name("figures.art.yaml")

WIDTH, HEIGHT = 900, 600

Colour = tuple[int, int, int]

SKY: Colour = (22, 26, 48)
WALL: Colour = (52, 50, 66)
PLATFORM: Colour = (88, 84, 92)
EDGE: Colour = (214, 186, 64)
LAMP: Colour = (255, 228, 168)
BOARD: Colour = (18, 20, 24)
BOARD_TEXT: Colour = (240, 170, 40)
SKIN: Colour = (232, 190, 160)
EYE: Colour = (30, 24, 24)
MOUTH: Colour = (150, 40, 50)

#: Where the platform's floor starts, and where its yellow edge line runs.
FLOOR = 430
EDGE_Y = 520

#: The timetable board, which lettering should keep off: left, top, right, bottom.
BOARD_BOX = (560, 60, 860, 200)

#: The lamp's light, as a centre and a reach.
LAMP_AT = (450, 40)
LAMP_REACH = 260


@dataclass(frozen=True, slots=True)
class Person:
    """One person on the platform, by the measures the contract is written from.

    Attributes:
        name: Their name in the contract.
        head: The centre of their head, in pixels.
        radius: The head's radius.
        coat: Their coat's colour.
        shoulders: Half the coat's width at the shoulders.
        hem: Half its width at the hem, which reaches the bottom of the picture.
    """

    name: str
    head: tuple[int, int]
    radius: int
    coat: Colour
    shoulders: int
    hem: int

    @property
    def mouth(self) -> tuple[int, int]:
        """Where the mouth is drawn: below the centre of the head."""
        return self.head[0], self.head[1] + self.radius // 2

    @property
    def face(self) -> tuple[tuple[int, int], int]:
        """The disc the contract keeps lettering off: the head, with a margin."""
        return self.head, math.ceil(self.radius * 1.2)

    @property
    def body(self) -> list[tuple[int, int]]:
        """The coat, as a polygon: shoulders under the chin, hem at the picture's foot."""
        cx, cy = self.head
        top = cy + self.radius
        return [
            (cx - self.shoulders, top),
            (cx + self.shoulders, top),
            (cx + self.hem, HEIGHT),
            (cx - self.hem, HEIGHT),
        ]


PEOPLE = (
    Person("ana", head=(230, 250), radius=46, coat=(150, 60, 70), shoulders=62, hem=86),
    Person("ben", head=(410, 236), radius=50, coat=(60, 90, 140), shoulders=70, hem=92),
    Person("carl", head=(720, 300), radius=38, coat=(80, 110, 80), shoulders=52, hem=66),
)


def mix(one: Colour, other: Colour, t: float) -> Colour:
    """A blend of two colours, `t` of the way from the first to the second."""
    t = min(max(t, 0.0), 1.0)
    return (
        round(one[0] + (other[0] - one[0]) * t),
        round(one[1] + (other[1] - one[1]) * t),
        round(one[2] + (other[2] - one[2]) * t),
    )


def _inside(polygon: list[tuple[int, int]], x: float, y: float) -> bool:
    """Whether a point is inside a convex polygon listed clockwise."""
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) < 0:
            return False
    return True


def _person(person: Person, x: float, y: float) -> Colour | None:
    """The colour of one pixel of a person, or None where they are not."""
    cx, cy = person.head
    r = person.radius
    mx, my = person.mouth
    if (x - mx) ** 2 / (r * 0.28) ** 2 + (y - my) ** 2 / (r * 0.12) ** 2 <= 1:
        return MOUTH
    for side in (-1, 1):
        if math.hypot(x - (cx + side * r * 0.36), y - (cy - r * 0.18)) <= r * 0.1:
            return EYE
    if math.hypot(x - cx, y - cy) <= r:
        return SKIN
    if _inside(person.body, x, y):
        return person.coat
    return None


def pixel(x: int, y: int) -> Colour:
    """The colour of one pixel of the platform."""
    px, py = x + 0.5, y + 0.5
    if py < FLOOR:
        colour = mix(SKY, WALL, py / FLOOR) if py < 210 else WALL
    else:
        colour = EDGE if EDGE_Y <= py < EDGE_Y + 8 else mix(PLATFORM, WALL, (HEIGHT - py) / 400)
    glow = 1 - math.hypot(px - LAMP_AT[0], py - LAMP_AT[1]) / LAMP_REACH
    if glow > 0:
        colour = mix(colour, LAMP, glow**2 * 0.6)
    left, top, right, bottom = BOARD_BOX
    if left <= px < right and top <= py < bottom:
        row = int((py - top - 18) // 28)
        lit = 0 <= row < 4 and (py - top - 18) % 28 < 12 and (px - left - 20) % 40 < 30
        colour = BOARD_TEXT if lit and left + 20 <= px < right - 20 else BOARD
    # Back to front: the farther figure first, so the nearer one paints over it.
    for person in sorted(PEOPLE, key=lambda p: p.radius):
        painted = _person(person, px, py)
        if painted is not None:
            colour = painted
    return colour


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def encode(rows: list[bytes]) -> bytes:
    """An 8-bit RGB PNG of the rows, each filtered by "Up"."""
    stride = WIDTH * 3
    previous = bytes(stride)
    filtered = bytearray()
    for row in rows:
        filtered.append(2)
        filtered.extend((value - above) & 0xFF for value, above in zip(row, previous, strict=True))
        previous = row
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        bytes.fromhex("89504e470d0a1a0a")
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(filtered), 9))
        + _chunk(b"IEND", b"")
    )


def contract() -> str:
    """The picture's artwork contract, written from the constants it was painted from."""
    lines = [
        "# The artwork contract for figures.png, written by scripts/make_gallery_figures.py",
        "# from the same constants the picture is painted from. Pixels, from the top left.",
        f"size: [{WIDTH}, {HEIGHT}]",
        "figures:",
    ]
    for person in PEOPLE:
        (cx, cy), radius = person.face
        body = ", ".join(f"[{x}, {y}]" for x, y in person.body)
        lines += [
            f"  {person.name}:",
            f"    face: {{center: [{cx}, {cy}], radius: {radius}}}",
            f"    mouth: [{person.mouth[0]}, {person.mouth[1]}]",
            f"    body: [{body}]",
        ]
    left, top, right, bottom = BOARD_BOX
    lines += [
        "keep_out:",
        "  # The timetable board.",
        f"  - [[{left}, {top}], [{right}, {top}], [{right}, {bottom}], [{left}, {bottom}]]",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Paint the platform, and write it and its contract beside the gallery's documents."""
    rows = [bytes(channel for x in range(WIDTH) for channel in pixel(x, y)) for y in range(HEIGHT)]
    PICTURE.parent.mkdir(parents=True, exist_ok=True)
    PICTURE.write_bytes(encode(rows))
    CONTRACT.write_text(contract(), encoding="utf-8", newline="\n")
    for path in (PICTURE, CONTRACT):
        print(f"wrote {path.relative_to(ROOT).as_posix()}, {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
