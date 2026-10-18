"""A picture to letter over, read from a file the document names (#70).

`setting: {image: art/p01.png}` puts a picture drawn elsewhere behind the cast. The
solver never sees artwork, so what this module takes from the file is a fact about it,
not its content: **how many pixels across and how many down**, read from the header. The
pixels are never decoded.

Two formats, PNG and JPEG, because they are what SVG 2 requires every viewer to draw.
They are told apart by their first bytes, never by the file's name. Both headers take a
few lines to read, so no imaging library is involved: one would have to pass the licence
gate, and ship in the playground's Pyodide, to answer two questions.

One more fact is read, and refused rather than used: an **EXIF orientation** saying the
picture is to be shown turned. Renderers disagree on obeying it -- Chromium turns an SVG
`<image>` by it, gdk-pixbuf does not unless asked -- so a picture carrying one would be
upright in one viewer and on its side in the next. EXIF that cannot be read is ignored,
as every renderer ignores it.

Every failure -- the path, the file, the header, the orientation -- is rule
`image-file`, located where the image is named.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Final, Literal

from scenet.errors import PanelSyntaxError
from scenet.paths import Folder, read_relative

__all__ = ["IMAGE_RULE", "JPEG", "PNG", "MediaType", "SuppliedImage", "load_image", "measure"]

#: The rule every image fault is reported under.
IMAGE_RULE = "image-file"

#: The two media types, as a `data:` URI names them.
MediaType = Literal["image/png", "image/jpeg"]
PNG: Final = "image/png"
JPEG: Final = "image/jpeg"

_PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
_JPEG_START = bytes.fromhex("ffd8")

#: JPEG's start-of-frame markers: C0 to CF, less the three in that range that are not --
#: a Huffman table (C4), a reserved extension (C8) and arithmetic-coding conditions (CC).
_FRAMES = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}

#: Markers that stand alone, with no length after them: TEM, and the restart markers.
_STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})

#: EXIF's Orientation tag, and the one value that means "as stored".
_ORIENTATION = 0x0112
_UPRIGHT = 1


class _UnmeasurableError(ValueError):
    """Why a file is not a picture whose size can be read, finishing "image file 'x' …"."""


@dataclass(frozen=True, slots=True)
class SuppliedImage:
    """A picture a document names, read.

    Attributes:
        href: The path exactly as the document wrote it. A linked SVG points at it by this,
            so it reaches the output as written and nothing else about the file's
            location does.
        media_type: `image/png` or `image/jpeg`, from the file's own first bytes.
        sha256: The digest of its bytes, which is what it is known by -- as a font is.
        width: Pixels across.
        height: Pixels down.
        data: The bytes, for a renderer asked to embed them.
    """

    href: str
    media_type: MediaType
    sha256: str
    width: int
    height: int
    data: bytes = field(repr=False)


def load_image(declared: str, base: Folder | None, *, loc: tuple[str | int, ...]) -> SuppliedImage:
    """Read the picture a document names, and how big it is.

    Args:
        declared: The path as the document wrote it.
        base: The document's folder, the files sent with it, or `None` for text with
            neither.
        loc: Where in the document it was named, for the finding.

    Returns:
        The picture, with its size.

    Raises:
        PanelSyntaxError: Rule `image-file`, naming the path as written.

    Example:
        >>> from scenet.images import load_image
        >>> photo = bytes.fromhex("ffd8 ffc0000b080bb80fa001011100 ffd9")
        >>> image = load_image("art/photo.jpg", {"art/photo.jpg": photo}, loc=())
        >>> image.media_type, image.width, image.height
        ('image/jpeg', 4000, 3000)
    """
    data = read_relative(declared, base, what="image", rule=IMAGE_RULE, loc=loc)
    try:
        media_type, width, height = measure(data)
    except _UnmeasurableError as exc:
        raise PanelSyntaxError(f"image file {declared!r} {exc}", rule=IMAGE_RULE, loc=loc) from exc
    return SuppliedImage(
        href=declared,
        media_type=media_type,
        sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        data=data,
    )


def measure(data: bytes) -> tuple[MediaType, int, int]:
    """A picture's media type and size in pixels, from its header.

    Args:
        data: The file's bytes.

    Returns:
        `(media_type, width, height)`.

    Raises:
        ValueError: The bytes are not a PNG or JPEG whose size its header gives, or the
            picture is turned by its EXIF orientation. The message finishes a sentence
            that begins with the file's name.

    Example:
        >>> from scenet.images import measure
        >>> measure(bytes.fromhex("ffd8 ffc0000b080bb80fa001011100 ffd9"))
        ('image/jpeg', 4000, 3000)
    """
    if data.startswith(_PNG_SIGNATURE):
        return (PNG, *_png(data))
    if data.startswith(_JPEG_START):
        return (JPEG, *_jpeg(data))
    raise _UnmeasurableError(
        "is not a PNG or JPEG file, the two raster formats every SVG renderer must draw"
    )


def _png(data: bytes) -> tuple[int, int]:
    """Width and height from the IHDR chunk, which the PNG specification puts first."""
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise _UnmeasurableError("is a PNG whose header ends before it gives the picture's size")
    width, height = struct.unpack(">II", data[16:24])
    _sized(width, height)
    _upright(_png_exif(data))
    return width, height


def _png_exif(data: bytes) -> bytes | None:
    """The eXIf chunk, which comes before the image data if there is one."""
    offset = 8
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        if kind in (b"IDAT", b"IEND"):
            return None
        if kind == b"eXIf":
            return data[offset + 8 : offset + 8 + length]
        offset += 12 + length
    return None


def _jpeg(data: bytes) -> tuple[int, int]:
    """Width and height from the first start-of-frame segment.

    Segments are walked from the start: each marker but a few standalone ones carries
    its own length, and an APP1 segment before the frame may hold EXIF.
    """
    ended = "is a JPEG whose header ends before it gives the picture's size"
    offset = len(_JPEG_START)
    tiff: bytes | None = None
    while True:
        if offset >= len(data) or data[offset] != 0xFF:
            raise _UnmeasurableError(ended)
        # Any number of 0xFF fill bytes may come before a marker.
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise _UnmeasurableError(ended)
        marker = data[offset]
        offset += 1
        if marker in _STANDALONE:
            continue
        if offset + 2 > len(data):
            raise _UnmeasurableError(ended)
        (length,) = struct.unpack(">H", data[offset : offset + 2])
        body = data[offset + 2 : offset + length]
        if length < 2 or len(body) < length - 2:
            raise _UnmeasurableError(ended)
        if marker in _FRAMES:
            if len(body) < 5:
                raise _UnmeasurableError(ended)
            height, width = struct.unpack(">HH", body[1:5])
            _sized(width, height)
            _upright(tiff)
            return width, height
        if marker == 0xE1 and tiff is None and body.startswith(b"Exif" + bytes(2)):
            tiff = body[6:]
        if marker in (0xD9, 0xDA):
            # The end of the image, or the start of its data, with no frame before it.
            raise _UnmeasurableError(ended)
        offset += length


def _sized(width: int, height: int) -> None:
    """Refuse a picture with nothing across or down -- as JPEG says "given later"."""
    if width == 0 or height == 0:
        raise _UnmeasurableError(
            "has no width or height in its header -- a JPEG may give its height only after "
            "the image data, which this compiler does not read; save it again"
        )


def _upright(tiff: bytes | None) -> None:
    """Refuse a picture whose EXIF says to show it turned or mirrored."""
    orientation = _orientation(tiff) if tiff is not None else None
    if orientation is not None and orientation != _UPRIGHT:
        raise _UnmeasurableError(
            f"is turned by its EXIF orientation ({orientation}), which some SVG renderers "
            "obey and others ignore; save it with the pixels turned instead"
        )


def _orientation(tiff: bytes) -> int | None:
    """The Orientation tag of EXIF's first directory, or None when it cannot be read."""
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return None
    order = "<" if tiff[:2] == b"II" else ">"
    magic, directory = struct.unpack(order + "HI", tiff[2:8])
    if magic != 42 or directory + 2 > len(tiff):
        return None
    (count,) = struct.unpack(order + "H", tiff[directory : directory + 2])
    for index in range(count):
        entry = directory + 2 + 12 * index
        if entry + 12 > len(tiff):
            return None
        tag, kind, number = struct.unpack(order + "HHI", tiff[entry : entry + 8])
        if tag == _ORIENTATION:
            # A SHORT, one of them: anything else is not an Orientation anyone can read.
            if kind != 3 or number != 1:
                return None
            (value,) = struct.unpack(order + "H", tiff[entry + 8 : entry + 10])
            return value
    return None
