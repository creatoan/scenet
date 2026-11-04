"""Supplied pictures in the print PDF (#80): carried over, pixels unchanged.

The fixtures are built here from their bytes, as `tests/images.py` builds the compiler's,
so a test never trusts an imaging library's writer. Each PNG kind PDF can read in place goes
in as the file's own image data; every other is decoded and compared, pixel by pixel, with
what was encoded.
"""

import io
import struct
import zlib
from pathlib import Path

import pytest
from pypdf import PdfReader

from scenet.emit.pdf import render_pdf
from scenet.emit.pdf_images import embed
from scenet.pipeline import compile_book_file
from tests.images import PNG_SIGNATURE, chunk

GALLERY = Path(__file__).parent.parent / "examples" / "gallery"

#: Adam7: where each pass starts in an 8 x 8 block, and its step.
ADAM7 = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)


def _paeth(left: int, up: int, corner: int) -> int:
    estimate = left + up - corner
    to_left, to_up, to_corner = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
    if to_left <= to_up and to_left <= to_corner:
        return left
    return up if to_up <= to_corner else corner


def _filtered(rows: list[bytes], distance: int) -> bytes:
    """Rows filtered with each of PNG's five filters in turn, as an encoder would."""
    out = bytearray()
    previous = bytes(len(rows[0]))
    for number, row in enumerate(rows):
        kind = number % 5
        line = bytearray()
        for index, value in enumerate(row):
            left = row[index - distance] if index >= distance else 0
            up = previous[index]
            corner = previous[index - distance] if index >= distance else 0
            predicted = (0, left, up, (left + up) // 2, _paeth(left, up, corner))[kind]
            line.append((value - predicted) & 0xFF)
        out += bytes([kind]) + line
        previous = row
    return bytes(out)


def _pack(values: list[int], depth: int) -> bytes:
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


def _png(
    pixels: list[list[tuple[int, ...]]],
    *,
    kind: int,
    depth: int = 8,
    interlaced: bool = False,
    extra: bytes = b"",
) -> bytes:
    """A PNG of `pixels` (rows of per-pixel sample tuples), filtered, maybe interlaced."""
    height, width = len(pixels), len(pixels[0])
    channels = len(pixels[0][0])
    distance = max(1, channels * depth // 8)

    def encoded(rows: list[list[tuple[int, ...]]]) -> bytes:
        packed = [_pack([value for pixel in row for value in pixel], depth) for row in rows]
        return _filtered(packed, distance)

    if interlaced:
        data = b""
        for x0, y0, dx, dy in ADAM7:
            sub = [row[x0::dx] for row in pixels[y0::dy]]
            if sub and sub[0]:
                data += encoded(sub)
    else:
        data = encoded(pixels)
    header = struct.pack(">IIBBBBB", width, height, depth, kind, 0, 0, int(interlaced))
    image = zlib.compress(data)
    # Two IDAT chunks, as encoders split them: PDF needs them joined.
    middle = len(image) // 2
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + extra
        + chunk(b"IDAT", image[:middle])
        + chunk(b"IDAT", image[middle:])
        + chunk(b"IEND", b"")
    )


RGB_PIXELS = [
    [((x * 40) % 256, (y * 70) % 256, (x * y * 13) % 256) for x in range(6)] for y in range(5)
]


def _idat(data: bytes) -> bytes:
    offset, out = 8, b""
    while offset < len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        if kind == b"IDAT":
            out += data[offset + 8 : offset + 8 + length]
        offset += 12 + length
    return out


class TestPassedThrough:
    def test_an_rgb_png_goes_in_as_its_own_image_data(self):
        data = _png(RGB_PIXELS, kind=2)
        picture = embed(data, "image/png", "art/p.png")
        assert picture.data == _idat(data)
        assert "/Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns 6" in picture.dictionary
        assert "/ColorSpace /DeviceRGB" in picture.dictionary
        assert picture.mask is None

    def test_a_palette_png_keeps_its_palette(self):
        palette = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])
        data = _png(
            [[(x % 3,) for x in range(8)] for _ in range(3)],
            kind=3,
            depth=2,
            extra=chunk(b"PLTE", palette),
        )
        picture = embed(data, "image/png", "p.png")
        assert f"[/Indexed /DeviceRGB 2 <{palette.hex()}>]" in picture.dictionary
        assert "/Colors 1 /BitsPerComponent 2" in picture.dictionary

    def test_a_transparent_grey_is_a_colour_key(self):
        data = _png(
            [[(x * 30,) for x in range(5)]], kind=0, extra=chunk(b"tRNS", struct.pack(">H", 60))
        )
        assert "/Mask [60 60]" in embed(data, "image/png", "p.png").dictionary

    def test_sixteen_bits_stay_sixteen(self):
        data = _png([[(x * 4000, 1, 2) for x in range(4)]], kind=2, depth=16)
        assert "/BitsPerComponent 16" in embed(data, "image/png", "p.png").dictionary


class TestDecoded:
    def test_alpha_becomes_a_soft_mask(self):
        pixels = [[(x * 20, y * 30, 7, (x + y) * 25) for x in range(5)] for y in range(4)]
        picture = embed(_png(pixels, kind=6), "image/png", "p.png")
        assert "/Filter" not in picture.dictionary
        assert picture.data == bytes(v for row in pixels for p in row for v in p[:3])
        assert picture.mask is not None
        assert picture.mask[1] == bytes(p[3] for row in pixels for p in row)

    def test_grey_and_alpha_at_sixteen_bits(self):
        pixels = [[(x * 9000, 65535 - x * 9000) for x in range(4)] for _ in range(3)]
        picture = embed(_png(pixels, kind=4, depth=16), "image/png", "p.png")
        assert picture.data == b"".join(p[0].to_bytes(2, "big") for row in pixels for p in row)
        assert picture.mask is not None
        assert "/BitsPerComponent 16" in picture.mask[0]

    def test_an_interlaced_picture_is_put_back_together(self):
        pixels = [
            [((x * 31 + y) % 256, (y * 17) % 256, x % 256) for x in range(11)] for y in range(9)
        ]
        picture = embed(_png(pixels, kind=2, interlaced=True), "image/png", "p.png")
        assert picture.data == bytes(v for row in pixels for p in row for v in p)

    def test_an_interlaced_one_bit_grey_is_widened_to_eight(self):
        pixels = [[((x + y) % 2,) for x in range(10)] for y in range(10)]
        picture = embed(_png(pixels, kind=0, depth=1, interlaced=True), "image/png", "p.png")
        assert picture.data == bytes(255 * p[0] for row in pixels for p in row)
        assert "/BitsPerComponent 8" in picture.dictionary

    def test_a_palette_with_transparency_is_rgb_beside_its_alpha(self):
        palette = bytes([10, 20, 30, 40, 50, 60])
        data = _png(
            [[(x % 2,) for x in range(4)]],
            kind=3,
            extra=chunk(b"PLTE", palette) + chunk(b"tRNS", bytes([0])),
        )
        picture = embed(data, "image/png", "p.png")
        assert picture.data == bytes([10, 20, 30, 40, 50, 60] * 2)
        assert picture.mask is not None
        assert picture.mask[1] == bytes([0, 255, 0, 255])


def _jpeg(
    *, marker: int = 0xC0, precision: int = 8, components: int = 3, adobe: bool = False
) -> bytes:
    frame = struct.pack(">BHHB", precision, 2, 3, components) + bytes(3 * components)
    segments = b""
    if adobe:
        body = b"Adobe" + bytes(7)
        segments += bytes([0xFF, 0xEE]) + struct.pack(">H", len(body) + 2) + body
    segments += bytes([0xFF, marker]) + struct.pack(">H", len(frame) + 2) + frame
    return bytes([0xFF, 0xD8]) + segments + bytes([0xFF, 0xDA, 0, 2]) + bytes([0xFF, 0xD9])


class TestJpeg:
    @pytest.mark.parametrize(
        ("components", "space"), [(1, "DeviceGray"), (3, "DeviceRGB"), (4, "DeviceCMYK")]
    )
    def test_it_goes_in_whole(self, components: int, space: str):
        data = _jpeg(components=components)
        picture = embed(data, "image/jpeg", "p.jpg")
        assert picture.data == data
        assert f"/ColorSpace /{space}" in picture.dictionary
        assert "/DCTDecode" in picture.dictionary
        assert "/Decode" not in picture.dictionary

    def test_an_adobe_cmyk_jpeg_is_inverted_back(self):
        picture = embed(_jpeg(components=4, adobe=True), "image/jpeg", "p.jpg")
        assert "/Decode [1 0 1 0 1 0 1 0]" in picture.dictionary

    def test_a_progressive_one_is_read(self):
        assert "/DCTDecode" in embed(_jpeg(marker=0xC2), "image/jpeg", "p.jpg").dictionary

    @pytest.mark.parametrize(("marker", "precision"), [(0xC3, 8), (0xC9, 8), (0xC0, 12)])
    def test_one_no_pdf_reader_decodes_is_refused(self, marker: int, precision: int):
        with pytest.raises(ValueError, match=r"p\.jpg"):
            embed(_jpeg(marker=marker, precision=precision), "image/jpeg", "p.jpg")


def test_a_png_with_no_image_data_is_refused():
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    data = PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IEND", b"")
    with pytest.raises(ValueError, match="no image data"):
        embed(data, "image/png", "p.png")


@pytest.mark.parametrize(
    "name", ["34-supplied-art.scene.yaml", "35-figures.scene.yaml", "52-a-jpeg.panel.yaml"]
)
def test_a_gallery_picture_prints(name: str):
    book = compile_book_file(GALLERY / name)
    cores = {key: result.core for key, result in book.panels.items()}
    data = render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)
    reader = PdfReader(io.BytesIO(data))
    resources = reader.pages[0]["/Resources"]
    assert "/XObject" in resources
    assert data == render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)


def test_a_picture_not_handed_over_is_refused():
    book = compile_book_file(GALLERY / "52-a-jpeg.panel.yaml")
    cores = {key: result.core for key, result in book.panels.items()}
    with pytest.raises(ValueError, match="not handed over"):
        render_pdf(book.pages, cores, fonts=book.fonts)
