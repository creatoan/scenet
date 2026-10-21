"""The gallery's figures, checked against the picture they are declared in (#71).

`scripts/make_gallery_figures.py` paints `art/figures.png` and writes its artwork contract
from the same constants. These tests hold the committed files to that: the contract is what
the script writes, and the picture, decoded here, has a face where every face is declared and
a mouth where every mouth is. It is the check a contract measured by eye needs too, done by a
machine because this one was made by one.
"""

import importlib.util
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from scenet.assets.artwork import ArtworkContract
from scenet.images import measure

REPO = Path(__file__).resolve().parent.parent
ART = REPO / "examples" / "gallery" / "art"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "make_gallery_figures", REPO / "scripts" / "make_gallery_figures.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _script()


def _decoded(data: bytes) -> tuple[int, int, list[bytes]]:
    """An 8-bit RGB PNG's rows, every one filtered by "Up" as the script writes them."""
    assert data[:8] == bytes.fromhex("89504e470d0a1a0a")
    offset, idat, width, height = 8, b"", 0, 0
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", payload[:10])
            assert (depth, colour) == (8, 2)
        elif kind == b"IDAT":
            idat += payload
        offset += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 3
    rows: list[bytes] = []
    previous = bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 2, "every row is filtered by Up"
        line = raw[start + 1 : start + 1 + stride]
        row = bytes((value + above) & 0xFF for value, above in zip(line, previous, strict=True))
        rows.append(row)
        previous = row
    return width, height, rows


@pytest.fixture(scope="module")
def picture() -> tuple[int, int, list[bytes]]:
    return _decoded((ART / "figures.png").read_bytes())


@pytest.fixture(scope="module")
def contract() -> ArtworkContract:
    return ArtworkContract.model_validate(
        yaml.safe_load((ART / "figures.art.yaml").read_text(encoding="utf-8"))
    )


def _at(picture: tuple[int, int, list[bytes]], x: float, y: float) -> tuple[int, int, int]:
    _, _, rows = picture
    row = rows[int(y)]
    column = int(x) * 3
    return row[column], row[column + 1], row[column + 2]


class TestTheContractIsTheScripts:
    def test_the_committed_contract_is_what_the_script_writes(self):
        assert (ART / "figures.art.yaml").read_text(encoding="utf-8") == SCRIPT.contract()

    def test_its_size_is_the_pictures(self, contract: ArtworkContract):
        assert measure((ART / "figures.png").read_bytes()) == ("image/png", *contract.size)


class TestTheContractMatchesThePicture:
    def test_every_face_centre_is_a_face(self, picture, contract: ArtworkContract):
        for name, figure in contract.figures.items():
            assert _at(picture, *figure.face.center) == SCRIPT.SKIN, name

    def test_every_mouth_is_a_mouth(self, picture, contract: ArtworkContract):
        for name, figure in contract.figures.items():
            assert figure.mouth is not None
            assert _at(picture, *figure.mouth) == SCRIPT.MOUTH, name

    def test_every_face_disc_covers_its_head(self, contract: ArtworkContract):
        for person in SCRIPT.PEOPLE:
            face = contract.figures[person.name].face
            assert face.center == person.head
            assert face.radius >= person.radius

    def test_the_keep_out_is_the_board(self, picture, contract: ArtworkContract):
        (board,) = contract.keep_out
        left, top = board[0]
        right, _ = board[2]
        assert _at(picture, (left + right) / 2, top + 4) == SCRIPT.BOARD

    def test_the_picture_is_the_scripts_on_a_sample_of_pixels(self, picture):
        width, height, _ = picture
        for y in range(0, height, 37):
            for x in range(0, width, 41):
                assert _at(picture, x, y) == SCRIPT.pixel(x, y), (x, y)
