"""A tinted palette printed in colour (#280).

Every colour the compiler owns has a CMYK twin under one printing condition
(`scenet.emit.cmyk`), and print draws a tinted paint in it: the masses, the veil, the rain, the
`warm` caption. Lettering and every line stay on the black plate, overprinting; the paper
still knocks out; a grey still prints as black; and `mono` prints the greys a tinted panel was
chosen against.
"""

from functools import cache
from pathlib import Path

from scenet.core import PanelCore
from scenet.emit.cmyk import CMYK
from scenet.emit.marks import Mark, Paint, Role, marks
from scenet.emit.pdf import _cmyk, ink, panel_content, print_notes
from scenet.emit.svg import typeface_of
from scenet.pipeline import Book, compile_book, compile_book_file

GALLERY = Path(__file__).parent.parent / "examples" / "gallery"


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    depth = 0
    for line in lines:
        if line == "q":
            depth += 1
            if depth == 1:
                blocks.append([])
        if depth:
            blocks[-1].append(line)
        if line == "Q":
            depth -= 1
    return blocks


def _painted(core: PanelCore, book: Book) -> list[tuple[Mark, list[str]]]:
    drawn = marks(core, typeface_of(core, fonts=book.fonts))
    blocks = _blocks(panel_content(core, book.fonts))
    assert len(blocks) == len(drawn)
    return list(zip(drawn, blocks, strict=True))


def _twin(colour: str) -> str:
    cyan, magenta, yellow, black = CMYK[colour]
    return f"{_cmyk((cyan / 100, magenta / 100, yellow / 100, black / 100))} k"


def test_every_tinted_paint_prints_its_twin():
    book = _book("40-tinted-hours.scene.yaml")
    owners: set[str] = set()
    for result in book.panels.values():
        for mark, block in _painted(result.core, book):
            if mark.fill is not None and mark.fill.colour != mark.fill.grey:
                assert _twin(mark.fill.colour) in block
                owners.add(mark.owner.split("-")[0])
            if mark.stroke is not None and mark.stroke.colour != mark.stroke.grey:
                assert _twin(mark.stroke.colour)[:-1] + "K" in block
                owners.add(mark.owner.split("-")[0])
    assert {"mass", "veil", "weather"} <= owners


def test_the_warm_caption_prints_its_twin():
    book = compile_book(
        "palette: tinted\ncast: {a: {reference: alice}}\n"
        "panels: {one: {script: [{caption: {text: Meanwhile., tone: warm}}]}}\n"
    )
    core = book.panels["one"].core
    boxes = [
        block
        for mark, block in _painted(core, book)
        if mark.owner.startswith("caption-")
        and mark.fill is not None
        and mark.fill.colour == "#fef0a1"
    ]
    assert boxes
    assert all(_twin("#fef0a1") in block for block in boxes)


def test_lettering_and_lines_stay_on_the_black_plate_over_colour():
    book = _book("40-tinted-hours.scene.yaml")
    for result in book.panels.values():
        for mark, block in _painted(result.core, book):
            for paint in (mark.fill, mark.stroke):
                if paint is not None and paint.role in {Role.INK, Role.SOLID}:
                    assert any(line.endswith(" k") or line.endswith(" K") for line in block)
                    assert "0 0 0 1 k" in block or "0 0 0 1 K" in block


def test_a_colour_the_palette_does_not_own_prints_its_grey_and_is_said():
    book = _book("40-tinted-hours.scene.yaml")
    core = book.panels["dawn"].core
    assert core.backdrop is not None
    masses = list(core.backdrop.masses)
    masses[0] = masses[0].model_copy(update={"colour": "#123456"})
    edited = core.model_copy(
        update={"backdrop": core.backdrop.model_copy(update={"masses": tuple(masses)})}
    )
    (mass, block), *_ = [
        (mark, block)
        for mark, block in _painted(edited, book)
        if mark.fill is not None and mark.fill.colour == "#123456"
    ]
    assert mass.fill is not None
    grey = Paint(mass.fill.grey, Role.MASS, mass.fill.grey)
    assert f"{_cmyk(ink(grey))} k" in block
    notes = print_notes({"dawn": edited})
    assert any("#123456" in note for note in notes)
    assert print_notes({"dawn": core}) == []
