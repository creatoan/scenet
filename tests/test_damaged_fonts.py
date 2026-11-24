"""A font that opens and is damaged further in: what fuzzing found, held part by part (#378).

`tests/fuzz_regressions/font/` keeps the fonts themselves, which the oracle replays. This file
says what each part of Scenet makes of them: the probe at load names the part it could not
read, a later read is refused the same way, and print refuses a face it cannot embed in one
line that names it.
"""

import io
from pathlib import Path
from typing import Any

import fonts.ttf
import pytest
from fontTools.ttLib import TTFont

import scenet.emit.pdf_fonts
from scenet.diagnostics import diagnose_source
from scenet.emit.pdf_fonts import pdf_font
from scenet.errors import MalformedAssetError, RenderError
from scenet.solve.text import _PROBED, FontMetrics

REGRESSIONS = Path(__file__).resolve().parent / "fuzz_regressions" / "font"
#: Opens, and fails when its kerning is first read.
KERNING = REGRESSIONS / "kerned-or-drawn-after-opening-font-3.ttf"
#: Opens, and fails when an outline is first drawn.
OUTLINES = REGRESSIONS / "kerned-or-drawn-after-opening-font-1.ttf"
SOUND = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[missing-attribute]  # pyright: ignore[reportAttributeAccessIssue]


def _opened(path: Path) -> FontMetrics:
    return FontMetrics(Path("fonts/a.ttf"), data=path.read_bytes())


@pytest.mark.parametrize(("path", "part"), [(KERNING, "kerning"), (OUTLINES, "outlines")])
def test_the_probe_names_the_part_it_could_not_read(path: Path, part: str):
    with pytest.raises(MalformedAssetError) as raised:
        _opened(path).probe()
    assert raised.value.source == Path("fonts/a.ttf")
    assert str(raised.value).endswith(
        f"not a TrueType or OpenType font that can be drawn: its {part} cannot be read"
    )


def test_a_sound_face_passes_the_probe():
    FontMetrics(SOUND).probe()


@pytest.mark.parametrize("path", [KERNING, OUTLINES])
def test_a_document_naming_one_has_the_font_file_finding_at_it(path: Path):
    (finding,) = diagnose_source(
        "lettering: {font: fonts/a.ttf}\ncast: {alice: {reference: alice}}\n"
        "script: [{say: {by: alice, text: Hello.}}]\n",
        base={"fonts/a.ttf": path.read_bytes()},
    )
    assert (finding.rule, finding.path) == ("font-file", ("lettering", "font"))


def _broken_character(metrics: FontMetrics) -> str:
    for character in _PROBED:
        try:
            metrics.glyph_outlines(character)
        except MalformedAssetError:
            return character
    pytest.fail("no character of the probe is drawn broken")


@pytest.mark.parametrize("read", ["glyph_outlines", "glyph_pdf_path"])
def test_a_later_read_of_a_broken_outline_is_refused_alike(read: str):
    """Each on a face opened afresh: fontTools reads a table once, failing or not."""
    character = _broken_character(_opened(OUTLINES))
    with pytest.raises(MalformedAssetError, match=r"its outlines cannot be read$"):
        getattr(_opened(OUTLINES), read)(character)


def test_a_later_read_of_broken_kerning_is_refused_alike():
    metrics = _opened(KERNING)
    with pytest.raises(MalformedAssetError, match=r"its kerning cannot be read$"):
        metrics.measure("AV", 20)


def test_print_refuses_a_face_it_cannot_embed_in_one_line(monkeypatch: pytest.MonkeyPatch):
    def damaged(*_args: object) -> None:
        raise ValueError("fontTools failed somewhere")

    monkeypatch.setattr(scenet.emit.pdf_fonts, "_embedded", damaged)
    metrics = FontMetrics(Path("fonts/a.ttf"), data=SOUND.read_bytes())
    with pytest.raises(RenderError) as raised:
        pdf_font(metrics, "Hi")
    assert str(raised.value) == (
        "fonts/a.ttf cannot be embedded in print: it is a damaged font; build without "
        "--live-text to letter it in outlines"
    )


def _with_fs_type(bits: int) -> FontMetrics:
    font = TTFont(io.BytesIO(SOUND.read_bytes()))
    table: Any = font["OS/2"]  # fontTools builds its tables at run time
    table.fsType = bits
    out = io.BytesIO()
    font.save(out)
    return FontMetrics(Path("a.ttf"), data=out.getvalue())


def test_a_face_embedded_whole_keeps_its_own_name():
    """A face that may not be subset goes in whole, under its own name; a subset is tagged."""
    whole = pdf_font(_with_fs_type(0x0100), "Hi")
    subset = pdf_font(_with_fs_type(0), "Hi")
    assert "+" not in whole.name
    assert subset.name.endswith("+" + whole.name)
