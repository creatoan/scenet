"""Paint the photograph the gallery's JPEG example is lettered over.

`examples/gallery/art/harbour.jpg` is a harbour at dawn: a sky going from night blue to
peach, a low sun, a line of hills, the sea with the sun's path on it, and a quay in the
foreground. Like `make_gallery_art.py`'s street, it is painted here rather than drawn by
anyone or downloaded from anywhere, so its licence is the repository's -- 0BSD -- and its
provenance is this file.

It is a JPEG because a supplied picture may be one: the compiler reads PNG and JPEG, told
apart by their first bytes. Nothing the project depends on encodes JPEG, so this file does,
in the plainest form there is: baseline JFIF, every component at full resolution, and the
example tables of the standard (ITU-T T.81, Annex K) -- the luminance Huffman tables for all
three components, which is allowed and leaves fewer tables to get wrong.

Run it with `uv run python scripts/make_gallery_photo.py`.
"""

import math
import struct
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "examples" / "gallery" / "art" / "harbour.jpg"

WIDTH, HEIGHT = 720, 480
HORIZON = 0.56
SUN = (0.68, 0.46)
QUALITY = 90

Image = NDArray[np.float64]

#: Annex K's example quantisation tables, row by row.
LUMINANCE_QUANTISATION = [
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
]  # fmt: skip
CHROMINANCE_QUANTISATION = [
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    *[99] * 32,
]  # fmt: skip

#: Annex K's luminance Huffman tables: how many codes of each length, then the symbols.
DC_COUNTS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
DC_SYMBOLS = list(range(12))
AC_COUNTS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D]
AC_SYMBOLS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51,
    0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1,
    0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57,
    0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x92,
    0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3,
    0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
    0xD9, 0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2,
    0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
]  # fmt: skip

#: End of block, and a run of sixteen zeros.
EOB, ZRL = 0x00, 0xF0

#: The order coefficients are written in: along the anti-diagonals, alternately.
ZIGZAG = sorted(
    range(64), key=lambda k: (k // 8 + k % 8, k // 8 if (k // 8 + k % 8) % 2 else -(k // 8))
)


def mix(one: Image, other: Image, t: Image) -> Image:
    """A blend of two colours per pixel, `t` of the way from the first to the second."""
    t = np.clip(t, 0.0, 1.0)[..., None]
    return one * (1 - t) + other * t


def colour(red: float, green: float, blue: float) -> Image:
    """One colour, as the painting functions take it."""
    return np.array([red, green, blue], dtype=np.float64)


def paint() -> Image:
    """The harbour, as rows of RGB values from 0 to 255."""
    fy, fx = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float64)
    fx, fy = (fx + 0.5) / WIDTH, (fy + 0.5) / HEIGHT
    sun_x, sun_y = SUN

    # The sky, night blue at the top to peach at the horizon, warmer round the sun.
    picture = mix(colour(38, 54, 104), colour(250, 192, 146), (fy / HORIZON) ** 1.6)
    # Distances in the picture's own proportions, so the sun is round.
    across, down = (fx - sun_x) * WIDTH / HEIGHT, fy - sun_y
    glow = np.exp(-(across**2 + down**2) / 0.02)
    picture = mix(picture, colour(255, 226, 170), glow * 0.8)
    picture = mix(picture, colour(255, 246, 220), (np.hypot(across, down) < 0.045) * 1.0)

    # Hills along the left of the horizon, one value.
    height = 0.05 + 0.025 * np.sin(fx * 9.0) + 0.015 * np.sin(fx * 23.0 + 1.0)
    ridge = HORIZON - height * np.clip((0.62 - fx) / 0.2, 0.0, 1.0)
    hills = (fy > ridge) & (fy < HORIZON)
    picture = mix(picture, colour(96, 82, 112), hills * 1.0)

    # The sea, darker towards the reader, with the sun's path broken into ripples.
    below = fy >= HORIZON
    depth = (fy - HORIZON) / (1 - HORIZON)
    sea = mix(np.broadcast_to(colour(92, 112, 140), picture.shape), colour(24, 42, 72), depth)
    path = np.abs(fx - sun_x) < 0.02 + 0.10 * depth
    ripple = np.sin(fy * 260.0 + np.sin(fx * 40.0) * 2.0) > 0.35
    sea = mix(sea, colour(250, 204, 150), (path & ripple) * (0.85 - 0.5 * depth))
    picture = np.where(below[..., None], sea, picture)

    # The quay across the bottom left, and three bollards on it.
    edge = 0.80 + 0.12 * fx
    quay = (fy > edge) & (fx < 0.75)
    picture = mix(picture, colour(46, 40, 50), quay * 1.0)
    for x in (0.12, 0.30, 0.48):
        post = (np.abs(fx - x) < 0.008) & (fy > 0.80 + 0.12 * x - 0.035) & (fy <= 0.80 + 0.12 * x)
        picture = mix(picture, colour(30, 26, 34), post * 1.0)
    return picture


def scaled(table: list[int]) -> list[int]:
    """A quantisation table at `QUALITY`, scaled as the Independent JPEG Group scales it."""
    scale = 200 - 2 * QUALITY if QUALITY >= 50 else 5000 // QUALITY
    return [min(max((value * scale + 50) // 100, 1), 255) for value in table]


def codes(counts: list[int], symbols: list[int]) -> dict[int, tuple[int, int]]:
    """Each symbol's canonical Huffman code, as `(code, length)`."""
    table: dict[int, tuple[int, int]] = {}
    code, index = 0, 0
    for length, count in enumerate(counts, start=1):
        for _ in range(count):
            table[symbols[index]] = (code, length)
            code += 1
            index += 1
        code <<= 1
    return table


class Bits:
    """Entropy-coded data: bits packed into bytes, every 0xFF followed by a stuffed 0x00."""

    def __init__(self) -> None:
        """No bits yet."""
        self.data = bytearray()
        self.buffer = 0
        self.count = 0

    def write(self, value: int, length: int) -> None:
        """Append the low `length` bits of `value`, most significant first."""
        self.buffer = (self.buffer << length) | (value & ((1 << length) - 1))
        self.count += length
        while self.count >= 8:
            self.count -= 8
            byte = (self.buffer >> self.count) & 0xFF
            self.data.append(byte)
            if byte == 0xFF:
                self.data.append(0x00)
        self.buffer &= (1 << self.count) - 1

    def finish(self) -> bytes:
        """The bytes, the last one padded with ones as the standard asks."""
        if self.count:
            self.write((1 << (8 - self.count)) - 1, 8 - self.count)
        return bytes(self.data)


def magnitude(value: int) -> tuple[int, int]:
    """A coefficient as the standard writes it: its size in bits, and those bits."""
    size = abs(value).bit_length()
    return size, value if value >= 0 else value + (1 << size) - 1


def blocks(plane: Image, table: list[int]) -> NDArray[np.int64]:
    """Every 8x8 block of a plane, transformed, quantised and in zigzag order."""
    n = np.arange(8)
    basis = np.cos((2 * n[None, :] + 1) * n[:, None] * math.pi / 16)
    basis *= np.where(n == 0, math.sqrt(1 / 8), math.sqrt(2 / 8))[:, None]
    tiles = (plane - 128.0).reshape(HEIGHT // 8, 8, WIDTH // 8, 8).transpose(0, 2, 1, 3)
    transformed = np.einsum("ux,abxy,vy->abuv", basis, tiles, basis).reshape(-1, 64)
    quantised = np.rint(transformed / np.array(table, dtype=np.float64)).astype(np.int64)
    return quantised[:, ZIGZAG]


def encode(picture: Image) -> bytes:
    """The picture as a baseline JFIF file."""
    red, green, blue = picture[..., 0], picture[..., 1], picture[..., 2]
    planes = [
        0.299 * red + 0.587 * green + 0.114 * blue,
        -0.168736 * red - 0.331264 * green + 0.5 * blue + 128,
        0.5 * red - 0.418688 * green - 0.081312 * blue + 128,
    ]
    tables = [scaled(LUMINANCE_QUANTISATION), scaled(CHROMINANCE_QUANTISATION)]
    coded = [blocks(plane, tables[0 if index == 0 else 1]) for index, plane in enumerate(planes)]
    dc, ac = codes(DC_COUNTS, DC_SYMBOLS), codes(AC_COUNTS, AC_SYMBOLS)

    bits = Bits()
    previous = [0, 0, 0]
    for block in range(coded[0].shape[0]):
        for component in range(3):
            coefficients = [int(value) for value in coded[component][block]]
            size, value = magnitude(coefficients[0] - previous[component])
            previous[component] = coefficients[0]
            bits.write(*dc[size])
            bits.write(value, size)
            run = 0
            for coefficient in coefficients[1:]:
                if coefficient == 0:
                    run += 1
                    continue
                while run > 15:
                    bits.write(*ac[ZRL])
                    run -= 16
                size, value = magnitude(coefficient)
                bits.write(*ac[(run << 4) | size])
                bits.write(value, size)
                run = 0
            if run:
                bits.write(*ac[EOB])

    def segment(marker: int, payload: bytes) -> bytes:
        return struct.pack(">HH", marker, len(payload) + 2) + payload

    quantisation = b"".join(
        bytes([index]) + bytes(table[k] for k in ZIGZAG) for index, table in enumerate(tables)
    )
    frame = struct.pack(">BHHB", 8, HEIGHT, WIDTH, 3) + bytes([1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1])
    huffman = bytes([0x00, *DC_COUNTS, *DC_SYMBOLS]) + bytes([0x10, *AC_COUNTS, *AC_SYMBOLS])
    scan = bytes([3, 1, 0x00, 2, 0x00, 3, 0x00, 0, 63, 0])
    return b"".join(
        [
            b"\xff\xd8",
            segment(0xFFE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"),
            segment(0xFFDB, quantisation),
            segment(0xFFC0, frame),
            segment(0xFFC4, huffman),
            segment(0xFFDA, scan),
            bits.finish(),
            b"\xff\xd9",
        ]
    )


def main() -> None:
    """Paint the harbour and write it beside the gallery's other picture."""
    symbols = sorted([EOB, ZRL, *((run << 4) | size for run in range(16) for size in range(1, 11))])
    if sorted(AC_SYMBOLS) != symbols:
        raise SystemExit("the AC table must code every run and size once")
    OUTPUT.write_bytes(encode(np.clip(paint(), 0, 255)))
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
