"""`scenet build --pdf`: the print PDF from the command line (#80).

One PDF per document, beside the SVGs: a PDF page per page, or per panel when the document
has none. `--live-text` letters it in its embedded faces, as it letters the SVG in text
(#284); the other options that change how the SVG is written do not change the PDF, which
prints greys and carries its pictures. Everything is checked before anything is written, a
PDF included.
"""

import io
import struct
from collections.abc import Callable
from pathlib import Path

import pytest
from pypdf import PdfReader

from scenet import cli

PANEL = "cast: {a: {reference: alice}}\nscript:\n  - say: {by: a, text: Hello there.}\n"
FOGGY = (
    "cast: {a: {reference: alice}}\nsetting: {place: street, weather: fog}\n"
    "script:\n  - say: {by: a, text: Who is it}\n"
)
SCENE = (
    "cast: {a: {reference: alice}}\n"
    "page: {size: [1682.75, 2603.5], bleed: 31.75}\n"
    "pages: [{tiers: [{panels: [one, two]}]}]\n"
    "panels:\n"
    "  one: {script: [{say: {by: a, text: One.}}]}\n"
    "  two: {script: [{say: {by: a, text: Two.}}]}\n"
    "  aside: {script: [{say: {by: a, text: On no page.}}]}\n"
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    return source


def _pages(path: Path) -> int:
    return len(PdfReader(io.BytesIO(path.read_bytes())).pages)


class TestWhatItWrites:
    def test_a_panel_gets_a_pdf_beside_its_svg(self, tmp_path: Path, capsys):
        source = _write(tmp_path, "hello.panel.yaml", PANEL)
        assert cli.main(["build", str(source), "--pdf"]) == 0
        assert (tmp_path / "hello.svg").exists()
        assert _pages(tmp_path / "hello.pdf") == 1
        assert f"wrote {tmp_path / 'hello.pdf'}" in capsys.readouterr().out

    def test_a_document_with_pages_prints_its_pages_only(self, tmp_path: Path):
        source = _write(tmp_path, "book.scene.yaml", SCENE)
        assert cli.main(["build", str(source), "--pdf", "--quiet"]) == 0
        assert _pages(tmp_path / "book.pdf") == 1

    def test_a_document_without_pages_prints_each_panel(self, tmp_path: Path):
        text = SCENE.replace("pages: [{tiers: [{panels: [one, two]}]}]\n", "")
        source = _write(tmp_path, "loose.scene.yaml", text)
        assert cli.main(["build", str(source), "--pdf", "--quiet"]) == 0
        assert _pages(tmp_path / "loose.pdf") == 3

    def test_it_follows_the_output_name(self, tmp_path: Path):
        source = _write(tmp_path, "hello.panel.yaml", PANEL)
        out = tmp_path / "out"
        assert cli.main(["build", str(source), "--pdf", "-o", f"{out}/", "--quiet"]) == 0
        assert (out / "hello.pdf").exists()
        assert cli.main(["build", str(source), "--pdf", "-o", str(out / "x.svg"), "--quiet"]) == 0
        assert (out / "x.pdf").exists()

    def test_an_output_named_pdf_is_refused(self, tmp_path: Path, capsys):
        source = _write(tmp_path, "hello.panel.yaml", PANEL)
        target = tmp_path / "hello.pdf"
        assert cli.main(["build", str(source), "--pdf", "-o", str(target)]) == 2
        assert "-o" in capsys.readouterr().err
        assert not target.exists()

    def test_without_the_flag_there_is_no_pdf(self, tmp_path: Path):
        source = _write(tmp_path, "hello.panel.yaml", PANEL)
        assert cli.main(["build", str(source), "--quiet"]) == 0
        assert not (tmp_path / "hello.pdf").exists()


@pytest.mark.parametrize("flag", ["--mono", "--no-aria", "--embed-images", "--strip"])
def test_an_svg_option_does_not_change_the_pdf(tmp_path: Path, flag: str):
    source = _write(tmp_path, "book.scene.yaml", SCENE)
    assert cli.main(["build", str(source), "--pdf", "--quiet"]) == 0
    plain = (tmp_path / "book.pdf").read_bytes()
    assert cli.main(["build", str(source), "--pdf", "--quiet", flag]) == 0
    assert (tmp_path / "book.pdf").read_bytes() == plain


def test_live_text_letters_the_pdf_in_its_faces(tmp_path: Path):
    source = _write(tmp_path, "book.scene.yaml", SCENE)
    assert cli.main(["build", str(source), "--pdf", "--quiet"]) == 0
    outlined = (tmp_path / "book.pdf").read_bytes()
    assert cli.main(["build", str(source), "--pdf", "--quiet", "--live-text"]) == 0
    lettered = (tmp_path / "book.pdf").read_bytes()
    assert b"/FontFile2" not in outlined
    assert b"/FontFile2" in lettered
    assert "One." in PdfReader(io.BytesIO(lettered)).pages[0].extract_text()


class TestNotes:
    def test_the_fog_is_printed_and_so_not_said(self, tmp_path: Path, capsys):
        source = _write(tmp_path, "fog.panel.yaml", FOGGY)
        assert cli.main(["build", str(source), "--pdf"]) == 0
        assert "fog" not in capsys.readouterr().out

    def test_quiet_says_nothing(self, tmp_path: Path, capsys):
        source = _write(tmp_path, "fog.panel.yaml", FOGGY)
        assert cli.main(["build", str(source), "--pdf", "--quiet"]) == 0
        assert capsys.readouterr().out == ""

    def test_without_the_flag_print_says_nothing(self, tmp_path: Path, capsys):
        source = _write(tmp_path, "fog.panel.yaml", FOGGY)
        assert cli.main(["build", str(source)]) == 0
        assert "note:" not in capsys.readouterr().out


def test_a_picture_print_cannot_carry_fails_before_anything_is_written(tmp_path: Path, capsys):
    art = tmp_path / "art"
    art.mkdir()
    frame = struct.pack(">BHHB", 12, 300, 400, 3) + bytes(9)
    jpeg = bytes([0xFF, 0xD8, 0xFF, 0xC0]) + struct.pack(">H", len(frame) + 2) + frame
    (art / "p.jpg").write_bytes(jpeg + bytes([0xFF, 0xD9]))
    source = _write(
        tmp_path,
        "art.panel.yaml",
        "cast: {a: {reference: alice}}\nsetting: {image: art/p.jpg}\n"
        "script:\n  - say: {by: a, text: Look.}\n",
    )
    assert cli.main(["build", str(source), "--pdf"]) == 1
    error = capsys.readouterr().err
    assert "art/p.jpg" in error
    assert "Traceback" not in error
    assert error.count("\n") == 1
    assert not (tmp_path / "art.svg").exists()
    assert not (tmp_path / "art.pdf").exists()


def test_watch_rebuilds_the_pdf(tmp_path: Path, monkeypatch):
    source = _write(tmp_path, "hello.panel.yaml", PANEL)

    def once(_dependencies: set[Path], rebuild: Callable[[], object]) -> None:
        (tmp_path / "hello.pdf").unlink()
        rebuild()

    monkeypatch.setattr(cli, "watch_loop", once)
    assert cli.main(["build", str(source), "--pdf", "--watch", "--quiet"]) == 0
    assert (tmp_path / "hello.pdf").exists()
