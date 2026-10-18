"""Pictures for tests, built from their bytes: the headers a size is read from, and EXIF.

Most need no pixels at all -- the compiler reads a picture's header and nothing else --
so `png` writes a signature, an IHDR chunk and an IEND, and `jpeg` the markers before
the image data. `tiny_png` is a real one, which any viewer opens, for the tests that
check a picture survives into the SVG.

Built with `struct` and `zlib` only, as the compiler reads them: a test that needed an
imaging library to make its fixtures would be testing that library's writer too.
"""

import struct
import zlib

PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
SOI = bytes([0xFF, 0xD8])
EOI = bytes([0xFF, 0xD9])

#: Baseline and progressive start-of-frame markers: the two a camera or an editor writes.
BASELINE = 0xC0
PROGRESSIVE = 0xC2


def chunk(kind: bytes, payload: bytes) -> bytes:
    """One PNG chunk: length, type, payload, and the CRC of type and payload."""
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def exif(orientation: int, *, big_endian: bool = False) -> bytes:
    """A TIFF structure holding one tag, Orientation, as EXIF stores it."""
    order, mark = (">", b"MM") if big_endian else ("<", b"II")
    header = mark + struct.pack(order + "HI", 42, 8)
    entry = struct.pack(order + "HHIHH", 0x0112, 3, 1, orientation, 0)
    return header + struct.pack(order + "H", 1) + entry + struct.pack(order + "I", 0)


def png(width: int, height: int, *, orientation: int | None = None) -> bytes:
    """A PNG's header and nothing to draw: enough to be measured."""
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunks = chunk(b"IHDR", header)
    if orientation is not None:
        chunks += chunk(b"eXIf", exif(orientation, big_endian=True))
    return PNG_SIGNATURE + chunks + chunk(b"IEND", b"")


def tiny_png(width: int = 3, height: int = 2) -> bytes:
    """A real PNG, every pixel a mid grey, that any viewer can open."""
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    rows = b"".join(bytes([0]) + bytes([128] * width) for _ in range(height))
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def segment(marker: int, payload: bytes) -> bytes:
    """One JPEG marker segment; its length counts itself and the payload."""
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg(
    width: int,
    height: int,
    *,
    frame: int = BASELINE,
    orientation: int | None = None,
    before: bytes = b"",
) -> bytes:
    """A JPEG's markers up to its frame header, then the end of the image.

    Args:
        width: Written into the frame header.
        height: Likewise; zero is how a DNL marker defers it.
        frame: Which start-of-frame marker.
        orientation: An EXIF Orientation to put in an APP1 segment, if any.
        before: Segments to put ahead of the frame header, as encoders do with tables.
    """
    app0 = segment(0xE0, b"JFIF" + bytes([0, 1, 1, 0, 0, 1, 0, 1, 0, 0]))
    app1 = b"" if orientation is None else segment(0xE1, b"Exif" + bytes(2) + exif(orientation))
    sof = segment(frame, struct.pack(">BHHB", 8, height, width, 1) + bytes([1, 0x11, 0]))
    return SOI + app0 + app1 + before + sof + EOI
