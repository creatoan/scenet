"""Supplied pictures in the print PDF (#80): carried over, pixels unchanged.

The fixtures are built here from their bytes, as `tests/images.py` builds the compiler's,
so a test never trusts an imaging library's writer. Each PNG kind PDF can read in place goes
in as the file's own image data; every other is decoded and compared, pixel by pixel, with
what was encoded.
"""

import hashlib
import io
import struct
import zlib
from collections.abc import Sequence
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from scenet.emit.pdf import print_notes, printed_panels, render_pdf
from scenet.emit.pdf_images import _paeth as paeth_predictor
from scenet.emit.pdf_images import embed
from scenet.pipeline import compile_book_file
from tests.images import PNG_SIGNATURE, chunk, jpeg

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
    pixels: Sequence[Sequence[tuple[int, ...]]],
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

    def encoded(rows: Sequence[Sequence[tuple[int, ...]]]) -> bytes:
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
    assert isinstance(resources, DictionaryObject)
    assert "/XObject" in resources
    assert data == render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)


@pytest.mark.parametrize(
    ("picture", "data"),
    [
        ("art/street.png", (GALLERY / "art" / "street.png").read_bytes()),
        # A lossless JPEG: the SVG draws it, and no PDF reader decodes it.
        ("art/lossless.jpg", jpeg(400, 300, frame=0xC3)),
    ],
    ids=["printable", "unprintable"],
)
def test_a_picture_on_no_page_is_not_carried(tmp_path: Path, picture: str, data: bytes):
    """Only the panels a page places are printed, so only their pictures are carried.

    The playground hands `render_pdf` every panel, and `scenet build --pdf` only the
    printed ones: both must write the same PDF, and neither may refuse a picture it does
    not print.
    """
    folder = tmp_path / "comic"
    (folder / "art").mkdir(parents=True)
    (folder / picture).write_bytes(data)
    source = folder / "page.scene.yaml"
    source.write_text(
        "cast: {a: {reference: alice}}\n"
        "pages: [{tiers: [{panels: [shown]}]}]\n"
        "panels:\n"
        "  shown: {}\n"
        f"  spare: {{setting: {{image: {picture}}}}}\n",
        encoding="utf-8",
    )
    book = compile_book_file(source)
    cores = {key: result.core for key, result in book.panels.items()}
    printed = printed_panels(book.pages, cores)
    assert list(printed) == ["shown"]
    every = render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)
    assert every == render_pdf(book.pages, printed, fonts=book.fonts, images=book.images)
    assert b"/XObject" not in every


def test_a_picture_not_handed_over_is_refused():
    book = compile_book_file(GALLERY / "52-a-jpeg.panel.yaml")
    cores = {key: result.core for key, result in book.panels.items()}
    with pytest.raises(ValueError, match="not handed over"):
        render_pdf(book.pages, cores, fonts=book.fonts)


def test_a_picture_printing_below_300_dpi_is_said():
    book = compile_book_file(GALLERY / "34-supplied-art.scene.yaml")
    cores = {key: result.core for key, result in book.panels.items()}
    notes = print_notes(cores)
    assert any("dpi" in note and "300" in note for note in notes)


def _noise(
    width: int, height: int, channels: int, *, seed: str, depth: int = 8
) -> list[list[tuple[int, ...]]]:
    """Pixels of deterministic noise, so every filter meets ties and carries."""
    limit = (1 << depth) - 1
    stream = hashlib.sha256(seed.encode()).digest()
    while len(stream) < width * height * channels * 2:
        stream += hashlib.sha256(stream).digest()
    values = [
        int.from_bytes(stream[i : i + 2], "big") % (limit + 1) for i in range(0, len(stream), 2)
    ]
    return [
        [
            tuple(values[(y * width + x) * channels + c] for c in range(channels))
            for x in range(width)
        ]
        for y in range(height)
    ]


def _flat(pixels: Sequence[Sequence[tuple[int, ...]]], take: slice, depth: int = 8) -> bytes:
    values = [value for row in pixels for pixel in row for value in pixel[take]]
    if depth == 16:
        return b"".join(value.to_bytes(2, "big") for value in values)
    return bytes(values)


class TestWhatMutationTestingFound:
    """Decoding and parsing the mutation run (#80) showed nothing checked."""

    @pytest.mark.parametrize("interlaced", [False, True])
    def test_noise_through_every_filter_comes_back_as_it_went_in(self, interlaced: bool):
        pixels = _noise(23, 19, 4, seed=f"rgba-{interlaced}")
        picture = embed(_png(pixels, kind=6, interlaced=interlaced), "image/png", "p.png")
        assert picture.data == _flat(pixels, slice(0, 3))
        assert picture.mask is not None
        assert picture.mask[1] == _flat(pixels, slice(3, 4))

    def test_sixteen_bit_rgba_is_decoded_whole(self):
        pixels = _noise(9, 7, 4, seed="rgba16", depth=16)
        picture = embed(_png(pixels, kind=6, depth=16), "image/png", "p.png")
        assert picture.data == _flat(pixels, slice(0, 3), 16)
        assert picture.mask is not None
        assert picture.mask[1] == _flat(pixels, slice(3, 4), 16)

    def test_an_interlaced_sixteen_bit_grey_is_put_back_together(self):
        pixels = _noise(10, 9, 1, seed="grey16", depth=16)
        picture = embed(_png(pixels, kind=0, depth=16, interlaced=True), "image/png", "p.png")
        assert picture.data == _flat(pixels, slice(0, 1), 16)
        assert picture.dictionary == (
            "/Type /XObject /Subtype /Image /Width 10 /Height 9 "
            "/ColorSpace /DeviceGray /BitsPerComponent 16"
        )

    @pytest.mark.parametrize(("width", "height"), [(1, 1), (2, 3), (3, 2), (5, 1), (1, 6)])
    def test_a_tiny_interlaced_picture_has_empty_passes(self, width: int, height: int):
        pixels = _noise(width, height, 3, seed=f"tiny-{width}-{height}")
        picture = embed(_png(pixels, kind=2, interlaced=True), "image/png", "p.png")
        assert picture.data == _flat(pixels, slice(0, 3))

    @pytest.mark.parametrize("depth", [2, 4])
    def test_an_interlaced_grey_below_eight_bits_is_widened(self, depth: int):
        pixels = _noise(9, 9, 1, seed=f"grey-{depth}", depth=depth)
        picture = embed(_png(pixels, kind=0, depth=depth, interlaced=True), "image/png", "p.png")
        scale = 255 // ((1 << depth) - 1)
        assert picture.data == bytes(p[0] * scale for row in pixels for p in row)

    def test_a_palette_with_transparency_takes_each_entry_whole(self):
        palette = bytes(range(12))
        data = _png(
            [[(index,) for index in (0, 1, 2, 3)]],
            kind=3,
            extra=chunk(b"PLTE", palette) + chunk(b"tRNS", bytes([10, 20])),
        )
        picture = embed(data, "image/png", "p.png")
        assert picture.data == palette
        assert picture.dictionary == (
            "/Type /XObject /Subtype /Image /Width 4 /Height 1 "
            "/ColorSpace /DeviceRGB /BitsPerComponent 8"
        )
        assert picture.mask == (
            "/Type /XObject /Subtype /Image /Width 4 /Height 1 "
            "/ColorSpace /DeviceGray /BitsPerComponent 8",
            bytes([10, 20, 255, 255]),
        )

    def test_a_transparent_rgb_colour_is_a_three_part_key(self):
        key = struct.pack(">HHH", 1, 2, 3)
        data = _png([[(1, 2, 3), (4, 5, 6)]], kind=2, extra=chunk(b"tRNS", key))
        assert "/Mask [1 1 2 2 3 3] " in embed(data, "image/png", "p.png").dictionary

    def test_a_grey_png_is_device_grey(self):
        data = _png([[(10,), (20,)]], kind=0)
        assert embed(data, "image/png", "p.png").dictionary.startswith(
            "/Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceGray "
        )

    def test_ancillary_chunks_and_anything_after_iend_are_ignored(self):
        plain = _png(RGB_PIXELS, kind=2)
        gamma = chunk(b"gAMA", struct.pack(">I", 45455))
        with_gamma = _png(RGB_PIXELS, kind=2, extra=gamma)
        trailing = plain + chunk(b"IDAT", b"not image data")
        assert embed(with_gamma, "image/png", "p.png").data == _idat(plain)
        assert embed(trailing, "image/png", "p.png").data == _idat(plain)

    def test_a_png_cut_off_before_iend_still_embeds(self):
        plain = _png(RGB_PIXELS, kind=2)
        cut = plain[: -len(chunk(b"IEND", b""))]
        assert embed(cut, "image/png", "p.png").data == _idat(plain)

    def test_a_png_with_no_header_or_palette_says_which_file(self):
        no_header = PNG_SIGNATURE + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")
        with pytest.raises(ValueError, match=r"art/q\.png is a PNG with no image data"):
            embed(no_header, "image/png", "art/q.png")
        no_palette = _png([[(0,)]], kind=3)
        with pytest.raises(ValueError, match=r"art/q\.png is a palette PNG with no palette"):
            embed(no_palette, "image/png", "art/q.png")

    def test_a_png_whose_data_cannot_be_read_says_which_file(self):
        header = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
        broken = (
            PNG_SIGNATURE
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", b"not zlib")
            + chunk(b"IEND", b"")
        )
        with pytest.raises(
            ValueError, match=r"art/q\.png is a PNG whose image data cannot be read"
        ):
            embed(broken, "image/png", "art/q.png")


class TestJpegHeaders:
    def test_fill_bytes_before_a_marker_are_skipped(self):
        data = _jpeg()
        filled = data[:2] + bytes([0xFF]) + data[2:]
        assert "/Width 3 /Height 2 " in embed(filled, "image/jpeg", "p.jpg").dictionary

    def test_a_long_segment_is_read_as_unsigned(self):
        icc = bytes([0xFF, 0xE2]) + struct.pack(">H", 40002) + bytes(40000)
        data = _jpeg()
        assert "/Width 3 " in embed(data[:2] + icc + data[2:], "image/jpeg", "p.jpg").dictionary

    def test_a_wide_picture_is_read_as_unsigned(self):
        frame = struct.pack(">BHHB", 8, 40000, 50000, 3) + bytes(9)
        data = bytes([0xFF, 0xD8, 0xFF, 0xC0]) + struct.pack(">H", len(frame) + 2) + frame
        dictionary = embed(data + bytes([0xFF, 0xD9]), "image/jpeg", "p.jpg").dictionary
        assert "/Width 50000 /Height 40000 " in dictionary

    def test_an_app14_that_is_not_adobe_inverts_nothing(self):
        body = b"Other" + bytes(7)
        other = bytes([0xFF, 0xEE]) + struct.pack(">H", len(body) + 2) + body
        data = _jpeg(components=4)
        assert "/Decode" not in embed(data[:2] + other + data[2:], "image/jpeg", "p.jpg").dictionary

    def test_an_adobe_jpeg_is_written_exactly(self):
        assert embed(_jpeg(components=4, adobe=True), "image/jpeg", "p.jpg").dictionary == (
            "/Type /XObject /Subtype /Image /Width 3 /Height 2 /ColorSpace /DeviceCMYK "
            "/BitsPerComponent 8 /Filter /DCTDecode /Decode [1 0 1 0 1 0 1 0]"
        )

    def test_a_jpeg_with_no_frame_is_refused(self):
        app = bytes([0xFF, 0xE0]) + struct.pack(">H", 4) + bytes(2)
        with pytest.raises(ValueError, match=r"p\.jpg is a JPEG whose data ends before its frame"):
            embed(bytes([0xFF, 0xD8]) + app, "image/jpeg", "p.jpg")


class TestPaeth:
    """PNG's Paeth predictor, at each of the ties its specification breaks in order."""

    def test_left_wins_a_tie_with_the_corner(self):
        assert paeth_predictor(10, 25, 20) == 10

    def test_up_wins_a_tie_with_the_corner(self):
        assert paeth_predictor(25, 10, 20) == 10

    def test_the_nearest_of_the_three_wins(self):
        assert paeth_predictor(30, 40, 50) == 30
        assert paeth_predictor(10, 12, 30) == 10
        assert paeth_predictor(20, 22, 21) == 21
