"""A supplied picture as a PDF image, pixels unchanged (#80).

The compiler only ever reads a picture's size (`scenet.images`); print has to carry the
picture itself. The rule is to change nothing: no colour conversion -- an RGB picture
stays RGB, which the printer's RIP converts, and the PDF writer tags it as sRGB (#283) --
and, wherever PDF can read the file's own data, the file's own bytes:

- a JPEG Acrobat and every RIP decode (baseline, extended or progressive, 8-bit) goes in
  whole, as `DCTDecode`;
- a PNG that is not interlaced and has no alpha goes in as its image data, `FlateDecode`
  with the PNG predictors PDF shares with it -- a palette as `/Indexed`, a transparent
  colour as a colour-key `/Mask`;
- anything else -- interlaced, alpha, a palette with transparency -- is decoded and its
  samples stored uncompressed, alpha as a soft mask beside them. Never re-deflated: zlib
  implementations differ from one platform to the next, and so would the bytes.

`gAMA`, `iCCP` and `sRGB` chunks, and a JPEG's own profile, are not carried over: an RGB
picture is read as sRGB, as a browser reads an untagged one. A grey picture stays
`DeviceGray`, printing on black alone, and a CMYK JPEG `DeviceCMYK`.
"""

import struct
import zlib
from dataclasses import dataclass

from scenet.errors import RenderError

#: The PNG signature, and the colour types by their number.
SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
GREY, RGB, PALETTE, GREY_ALPHA, RGBA = 0, 2, 3, 4, 6
CHANNELS = {GREY: 1, RGB: 3, PALETTE: 1, GREY_ALPHA: 2, RGBA: 4}

#: JPEG start-of-frame markers PDF readers decode: baseline, extended and progressive.
READABLE_FRAMES = {0xC0, 0xC1, 0xC2}
#: Every start-of-frame marker, readable or not.
FRAMES = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})
SPACES = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}

#: Adam7's passes: where each starts in an 8 x 8 block, and its step, as (x, y, dx, dy).
ADAM7 = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)


@dataclass(frozen=True, slots=True)
class Embedded:
    """A picture ready to be written as an image XObject.

    Attributes:
        dictionary: The stream dictionary's entries, without `/Length`.
        data: The stream's bytes.
        mask: The soft mask -- alpha -- as entries and bytes, if the picture has one.
    """

    dictionary: str
    data: bytes
    mask: tuple[str, bytes] | None = None


def embed(data: bytes, media_type: str, name: str) -> Embedded:
    """A supplied picture's bytes as a PDF image.

    Args:
        data: The file.
        media_type: `image/png` or `image/jpeg`, as Panel Core records it.
        name: The path the document wrote, for an error message.

    Raises:
        RenderError: A JPEG no PDF reader decodes, or a file whose data is cut short.
    """
    if media_type == "image/jpeg":
        return _jpeg(data, name)
    return _png(data, name)


def _jpeg(data: bytes, name: str) -> Embedded:
    offset = 2
    adobe = False
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            break
        marker = data[offset + 1]
        if marker in STANDALONE or marker == 0xFF:
            offset += 1 if marker == 0xFF else 2
            continue
        (length,) = struct.unpack(">H", data[offset + 2 : offset + 4])
        body = data[offset + 4 : offset + 2 + length]
        if marker == 0xEE and body.startswith(b"Adobe"):
            adobe = True
        if marker in FRAMES:
            if marker not in READABLE_FRAMES or not body or body[0] != 8:
                raise RenderError(
                    f"{name} is a JPEG print cannot carry: only baseline, extended and "
                    "progressive 8-bit JPEGs are read by every PDF reader"
                )
            height, width = struct.unpack(">HH", body[1:5])
            components = body[5]
            space = SPACES.get(components)
            if space is None:
                raise RenderError(f"{name} is a JPEG with {components} colour components")
            decode = " /Decode [1 0 1 0 1 0 1 0]" if components == 4 and adobe else ""
            return Embedded(
                f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace {space} /BitsPerComponent 8 /Filter /DCTDecode{decode}",
                data,
            )
        offset += 2 + length
    raise RenderError(f"{name} is a JPEG whose data ends before its frame")


@dataclass(frozen=True, slots=True)
class _Png:
    width: int
    height: int
    depth: int
    kind: int
    interlaced: bool
    palette: bytes
    transparency: bytes | None
    data: bytes


def _chunks(data: bytes, name: str) -> _Png:
    if not data.startswith(SIGNATURE):
        raise RenderError(f"{name} is not a PNG")
    offset = len(SIGNATURE)
    header: tuple[int, ...] | None = None
    palette = b""
    transparency: bytes | None = None
    image = bytearray()
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        body = data[offset + 8 : offset + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            transparency = body
        elif kind == b"IDAT":
            image += body
        elif kind == b"IEND":
            break
        offset += 12 + length
    if header is None or not image:
        raise RenderError(f"{name} is a PNG with no image data in it")
    width, height, depth, colour, _, _, interlace = header
    return _Png(width, height, depth, colour, interlace == 1, palette, transparency, bytes(image))


def _png(data: bytes, name: str) -> Embedded:
    png = _chunks(data, name)
    if png.kind == PALETTE and not png.palette:
        raise RenderError(f"{name} is a palette PNG with no palette")
    alpha = png.kind in {GREY_ALPHA, RGBA} or (png.kind == PALETTE and png.transparency)
    if not png.interlaced and not alpha:
        return Embedded(_passed(png), png.data)
    return _decoded(png, name)


def _space(png: _Png) -> str:
    if png.kind == PALETTE:
        entries = len(png.palette) // 3
        return f"[/Indexed /DeviceRGB {entries - 1} <{png.palette.hex()}>]"
    return "/DeviceGray" if png.kind in {GREY, GREY_ALPHA} else "/DeviceRGB"


def _key(png: _Png) -> str:
    """A transparent colour, as the colour-key mask PDF shares with PNG's `tRNS`."""
    if png.transparency is None or png.kind == PALETTE:
        return ""
    values = struct.unpack(f">{len(png.transparency) // 2}H", png.transparency)
    return f" /Mask [{' '.join(f'{value} {value}' for value in values)}]"


def _passed(png: _Png) -> str:
    colours = CHANNELS[png.kind]
    return (
        f"/Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
        f"/ColorSpace {_space(png)} /BitsPerComponent {png.depth}{_key(png)} "
        f"/Filter /FlateDecode /DecodeParms << /Predictor 15 /Colors {colours} "
        f"/BitsPerComponent {png.depth} /Columns {png.width} >>"
    )


def _decoded(png: _Png, name: str) -> Embedded:
    """Decode a PNG, then store its samples uncompressed, alpha apart."""
    try:
        raw = zlib.decompress(png.data)
    except zlib.error as exc:
        raise RenderError(f"{name} is a PNG whose image data cannot be read: {exc}") from exc
    channels = CHANNELS[png.kind]
    rows = (
        _deinterlaced(raw, png, channels)
        if png.interlaced
        else _unfiltered(raw, png.width, png.height, channels, png.depth)
    )
    samples = [_samples(row, png.width * channels, png.depth) for row in rows]
    if png.kind == PALETTE:
        return _expanded(png, samples)
    depth = png.depth if png.depth in {8, 16} else 8
    if png.depth < 8:
        scale = 255 // ((1 << png.depth) - 1)
        samples = [[value * scale for value in row] for row in samples]
    colour = channels - 1 if png.kind in {GREY_ALPHA, RGBA} else channels
    colour_bytes = bytearray()
    alpha_bytes = bytearray()
    for row in samples:
        for pixel in range(png.width):
            values = row[pixel * channels : (pixel + 1) * channels]
            colour_bytes += _packed(values[:colour], depth)
            if colour < channels:
                alpha_bytes += _packed(values[colour:], depth)
    entries = (
        f"/Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
        f"/ColorSpace {_space(png)} /BitsPerComponent {depth}"
    )
    if colour == channels:
        return Embedded(entries + _key(png), bytes(colour_bytes))
    return Embedded(entries, bytes(colour_bytes), _mask(png, depth, bytes(alpha_bytes)))


def _expanded(png: _Png, samples: list[list[int]]) -> Embedded:
    """A palette picture with transparency, as RGB beside its alpha."""
    transparency = png.transparency or b""
    colour = bytearray()
    alpha = bytearray()
    for row in samples:
        for index in row[: png.width]:
            colour += png.palette[index * 3 : index * 3 + 3]
            alpha.append(transparency[index] if index < len(transparency) else 255)
    entries = (
        f"/Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8"
    )
    if png.transparency is None:
        return Embedded(entries, bytes(colour))
    return Embedded(entries, bytes(colour), _mask(png, 8, bytes(alpha)))


def _mask(png: _Png, depth: int, alpha: bytes) -> tuple[str, bytes]:
    return (
        f"/Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
        f"/ColorSpace /DeviceGray /BitsPerComponent {depth}",
        alpha,
    )


def _packed(values: list[int], depth: int) -> bytes:
    if depth == 16:
        return b"".join(value.to_bytes(2, "big") for value in values)
    return bytes(values)


def _samples(row: bytes, count: int, depth: int) -> list[int]:
    """A row's samples as integers, whatever their bit depth."""
    if depth == 8:
        return list(row[:count])
    if depth == 16:
        return [int.from_bytes(row[index : index + 2], "big") for index in range(0, count * 2, 2)]
    per_byte = 8 // depth
    mask = (1 << depth) - 1
    values: list[int] = []
    for byte in row:
        for slot in range(per_byte):
            values.append((byte >> (8 - depth * (slot + 1))) & mask)
    return values[:count]


def _unfiltered(raw: bytes, width: int, height: int, channels: int, depth: int) -> list[bytes]:
    """Undo PNG's per-row filters: each row's bytes, as they were before filtering."""
    stride = (width * channels * depth + 7) // 8
    distance = max(1, channels * depth // 8)
    rows: list[bytes] = []
    previous = bytes(stride)
    offset = 0
    for _ in range(height):
        kind = raw[offset]
        line = bytearray(raw[offset + 1 : offset + 1 + stride])
        offset += 1 + stride
        for index in range(stride):
            left = line[index - distance] if index >= distance else 0
            up = previous[index]
            corner = previous[index - distance] if index >= distance else 0
            if kind == 1:
                line[index] = (line[index] + left) & 0xFF
            elif kind == 2:
                line[index] = (line[index] + up) & 0xFF
            elif kind == 3:
                line[index] = (line[index] + (left + up) // 2) & 0xFF
            elif kind == 4:
                line[index] = (line[index] + _paeth(left, up, corner)) & 0xFF
        previous = bytes(line)
        rows.append(previous)
    return rows


def _paeth(left: int, up: int, corner: int) -> int:
    estimate = left + up - corner
    to_left, to_up, to_corner = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
    if to_left <= to_up and to_left <= to_corner:
        return left
    return up if to_up <= to_corner else corner


def _deinterlaced(raw: bytes, png: _Png, channels: int) -> list[bytes]:
    """Undo Adam7: the seven passes, each unfiltered, put back where their pixels belong.

    Returned as rows of whole bytes at the picture's own depth, as a plain PNG's are.
    """
    width, height, depth = png.width, png.height, png.depth
    grid = [[0] * (width * channels) for _ in range(height)]
    offset = 0
    for x0, y0, dx, dy in ADAM7:
        across = (width - x0 + dx - 1) // dx if width > x0 else 0
        down = (height - y0 + dy - 1) // dy if height > y0 else 0
        if not across or not down:
            continue
        stride = (across * channels * depth + 7) // 8
        size = down * (1 + stride)
        rows = _unfiltered(raw[offset : offset + size], across, down, channels, depth)
        offset += size
        for row_index, row in enumerate(rows):
            values = _samples(row, across * channels, depth)
            y = y0 + row_index * dy
            for column in range(across):
                x = x0 + column * dx
                grid[y][x * channels : (x + 1) * channels] = values[
                    column * channels : (column + 1) * channels
                ]
    return [_repacked(row, depth) for row in grid]


def _repacked(values: list[int], depth: int) -> bytes:
    if depth == 8:
        return bytes(values)
    if depth == 16:
        return b"".join(value.to_bytes(2, "big") for value in values)
    per_byte = 8 // depth
    packed = bytearray()
    for start in range(0, len(values), per_byte):
        byte = 0
        for slot, value in enumerate(values[start : start + per_byte]):
            byte |= value << (8 - depth * (slot + 1))
        packed.append(byte)
    return bytes(packed)
