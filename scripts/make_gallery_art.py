"""Paint the picture the gallery's supplied-art example is lettered over.

`examples/gallery/art/street.png` is a street at dusk: a sky going from blue to amber, a
row of buildings with lit windows, a road running away to a vanishing point, and two
lamps. It is painted here, pixel by pixel, rather than drawn by anyone or downloaded from
anywhere, so its licence is simply the repository's -- 0BSD -- and its provenance is this
file.

It has perspective on purpose. Scenet is an orthographic compiler and never draws a
vanishing point; a picture it is given may have one, which is the point of being able to
give it one. The picture is committed, and this script is how it was made: running it
again on another machine may give different bytes -- zlib's output is not promised to be
the same across versions -- and the same pixels.

Run it with `uv run python scripts/make_gallery_art.py`.
"""

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "examples" / "gallery" / "art" / "street.png"

WIDTH, HEIGHT = 720, 480
HORIZON = 0.58
VANISHING_X = 0.56

Colour = tuple[float, float, float]

SKY_TOP: Colour = (34, 46, 92)
SKY_LOW: Colour = (226, 146, 92)
BUILDING: Colour = (44, 38, 64)
BUILDING_NEAR: Colour = (30, 26, 44)
WINDOW: Colour = (250, 206, 120)
ROAD_FAR: Colour = (92, 80, 92)
ROAD_NEAR: Colour = (52, 46, 56)
PAVEMENT: Colour = (120, 104, 108)
LAMP: Colour = (255, 226, 160)

#: Building outlines as (left, right, top) fractions of the picture: two rows, far and near.
FAR_ROW = [
    (0.00, 0.09, 0.33),
    (0.09, 0.16, 0.41),
    (0.16, 0.27, 0.27),
    (0.27, 0.33, 0.37),
    (0.33, 0.45, 0.30),
    (0.45, 0.52, 0.43),
    (0.60, 0.68, 0.35),
    (0.68, 0.79, 0.25),
    (0.79, 0.88, 0.39),
    (0.88, 1.00, 0.31),
]
NEAR_ROW = [(0.00, 0.13, 0.12), (0.86, 1.00, 0.18)]
LAMPS = [(0.30, 0.40), (0.80, 0.36)]


def mix(one: Colour, other: Colour, t: float) -> Colour:
    """A blend of two colours, `t` of the way from the first to the second."""
    t = min(max(t, 0.0), 1.0)
    return (
        one[0] + (other[0] - one[0]) * t,
        one[1] + (other[1] - one[1]) * t,
        one[2] + (other[2] - one[2]) * t,
    )


def _windowed(fx: float, fy: float, left: float, right: float, top: float) -> bool:
    """Whether a point on a building's face is a lit window, by a fixed grid and a hash."""
    column = math.floor((fx - left) * 90)
    row = math.floor((fy - top) * 60)
    inside = 0.25 < (fx - left) * 90 % 1 < 0.75 and 0.2 < (fy - top) * 60 % 1 < 0.7
    lit = (column * 7 + row * 13 + int(left * 100)) % 5 < 2
    return inside and lit and fy < HORIZON - 0.02


def pixel(x: int, y: int) -> Colour:
    """The colour of one pixel of the street."""
    fx, fy = (x + 0.5) / WIDTH, (y + 0.5) / HEIGHT
    colour = mix(SKY_TOP, SKY_LOW, (fy / HORIZON) ** 1.6)

    for left, right, top in FAR_ROW:
        if left <= fx < right and top <= fy < HORIZON:
            lit = _windowed(fx, fy, left, right, top)
            colour = WINDOW if lit else mix(BUILDING, SKY_LOW, 0.18 * (fy - top) / HORIZON)

    if fy >= HORIZON:
        depth = (fy - HORIZON) / (1 - HORIZON)
        # The road's edges run from the bottom corners' quarters to the vanishing point.
        half = 0.02 + 0.46 * depth
        if abs(fx - VANISHING_X) < half:
            colour = mix(ROAD_FAR, ROAD_NEAR, depth)
            if abs(fx - VANISHING_X) < 0.004 + 0.01 * depth and (depth * 30) % 1 < 0.5:
                colour = mix(colour, WINDOW, 0.55)
        else:
            colour = mix(PAVEMENT, ROAD_NEAR, depth * 0.6)

    for left, right, top in NEAR_ROW:
        if left <= fx < right and fy >= top:
            colour = BUILDING_NEAR if not _windowed(fx, fy, left, right, top) else WINDOW

    for lamp_x, lamp_y in LAMPS:
        distance = math.hypot((fx - lamp_x) * WIDTH / HEIGHT, fy - lamp_y)
        colour = mix(colour, LAMP, max(0.0, 1 - distance / 0.12) ** 2 * 0.8)
        if abs(fx - lamp_x) < 0.003 and lamp_y < fy < HORIZON + 0.18:
            colour = BUILDING_NEAR
    return colour


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def encode(rows: list[bytes]) -> bytes:
    """An 8-bit RGB PNG of the rows, each filtered by "Up", which suits smooth gradients."""
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


def main() -> None:
    """Paint the street and write it beside the gallery's documents."""
    rows = [
        bytes(round(channel) for x in range(WIDTH) for channel in pixel(x, y))
        for y in range(HEIGHT)
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(encode(rows))
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}, {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
