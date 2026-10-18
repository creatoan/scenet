"""An author's lettering face: font files the document declares, read beside it.

The rule is CLAUDE.md's: a font is a **declared file, never a system lookup**, so the
same document letters the same way on every machine. Until now only a library caller
could swap the face; an author could not, captions always used the shipped italic, and
`--live-text` named Source Sans Pro whatever was measured.

`lettering: {font: ...}` names the files, relative to the document -- a path written as
it would be in a link, never an absolute one, so a document carries its fonts with it
and a server compiling documents it was sent cannot be steered at its own files. The
fonts the letterers use are mostly commercial: an author can declare one; the project
can never ship one.

Two promises are checked here beyond "the face is used". Nothing about where the file
was reaches the output: Panel Core records each face by its family, style and a digest
of its bytes, and `tests/test_golden.py` holds the output to being the same from any
directory. And a Core can only be drawn in the font it was measured in: a renderer
handed a different file, or none, refuses rather than drawing text that does not fit.
"""

import hashlib
import json
import shutil
from pathlib import Path

import fonts.ttf
import pytest

from scenet.core import CoreFont, PanelCore
from scenet.diagnostics import diagnose_file, diagnose_source
from scenet.emit.page import render_page, render_pages
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.errors import PanelSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_panel
from scenet.ir import Face
from scenet.paths import resolve_relative
from scenet.pipeline import (
    compile_book,
    compile_book_file,
    compile_file,
    compile_ir,
    compile_source,
)
from scenet.solve.text import FontMetrics, load_metrics
from tests.invariants import assert_svg_is_sound

#: Faces of the shipped family that are not the ones it letters in, standing in for an
#: author's own: real files, measurably different, and nothing new to commit.
SEMIBOLD = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
SEMIBOLD_ITALIC = Path(fonts.ttf.SourceSansProSemiboldIt)  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]

CAST = "cast: {alice: {reference: alice}}\n"
SAY = "script:\n  - say: {by: alice, text: I _told_ you so.}\n"
CAPTION = "  - caption: {text: The next day., kind: locale}\n"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A document folder with a `fonts/` beside it, as an author would keep one."""
    fonts_dir = tmp_path / "comic" / "fonts"
    fonts_dir.mkdir(parents=True)
    shutil.copy(SEMIBOLD, fonts_dir / "Lettering-Regular.ttf")
    shutil.copy(SEMIBOLD_ITALIC, fonts_dir / "Lettering-Italic.ttf")
    return tmp_path / "comic"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(folder: Path, body: str, name: str = "page.panel.yaml") -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


class TestDeclaringIt:
    def test_a_path_names_the_regular_face(self):
        panel = parse_panel("lettering: {font: fonts/Lettering-Regular.ttf}")
        assert panel.lettering.font is not None
        assert panel.lettering.font.regular == "fonts/Lettering-Regular.ttf"
        assert panel.lettering.font.italic is None

    def test_a_mapping_names_each_face(self):
        panel = parse_panel(
            "lettering: {font: {regular: a.ttf, italic: b.ttf, bold_italic: c.ttf}}"
        )
        assert panel.lettering.font is not None
        assert (panel.lettering.font.italic, panel.lettering.font.bold_italic) == ("b.ttf", "c.ttf")

    def test_a_mapping_needs_a_regular_face(self):
        with pytest.raises(PanelSyntaxError, match="regular"):
            parse_panel("lettering: {font: {italic: b.ttf}}")


class TestTheFaceIsUsed:
    def test_dialogue_is_measured_and_drawn_in_it(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        declared = compile_file(path)
        shipped = compile_source(CAST + SAY)
        assert declared.core.balloons[0].box.width != shipped.core.balloons[0].box.width
        svg = render(declared.core, fonts=declared.fonts)
        semibold = FontMetrics(SEMIBOLD)
        assert semibold.glyph_outlines("y")[0][0] in svg

    def test_core_names_the_face_by_family_style_and_digest(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        core = compile_file(path).core
        assert core.fonts[Face.REGULAR] == CoreFont(
            family="Source Sans Pro Semibold",
            style="Regular",
            sha256=_digest(folder / "fonts" / "Lettering-Regular.ttf"),
        )

    def test_a_declared_italic_sets_the_italic_captions(self, folder: Path):
        fonts_key = "{regular: fonts/Lettering-Regular.ttf, italic: fonts/Lettering-Italic.ttf}"
        path = _write(folder, f"lettering: {{font: {fonts_key}}}\n{CAST}{SAY}{CAPTION}")
        result = compile_file(path)
        assert result.core.fonts[Face.ITALIC].sha256 == _digest(SEMIBOLD_ITALIC)
        assert not any("no italic face" in note for note in result.notes)

    def test_an_undeclared_face_falls_back_to_the_regular_and_says_so(self, folder: Path):
        path = _write(
            folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}{CAPTION}"
        )
        result = compile_file(path)
        regular = _digest(SEMIBOLD)
        assert result.core.fonts[Face.ITALIC].sha256 == regular
        assert result.core.fonts[Face.BOLD_ITALIC].sha256 == regular
        assert any("no italic face" in note for note in result.notes)
        assert any("no bold italic face" in note for note in result.notes)

    def test_every_face_can_be_named(self, folder: Path):
        faces = (
            "{regular: fonts/Lettering-Regular.ttf, italic: fonts/Lettering-Italic.ttf,"
            " bold_italic: fonts/Lettering-Italic.ttf}"
        )
        path = _write(folder, f"lettering: {{font: {faces}}}\n{CAST}{SAY}{CAPTION}")
        result = compile_file(path)
        assert result.core.fonts[Face.BOLD_ITALIC].sha256 == _digest(SEMIBOLD_ITALIC)
        assert result.notes == ()

    def test_no_note_for_a_face_nothing_uses(self, folder: Path):
        plain = "script:\n  - say: {by: alice, text: Hello.}\n"
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{plain}")
        assert compile_file(path).notes == ()

    def test_a_panel_without_a_font_records_none(self):
        assert '"fonts"' not in compile_source(CAST + SAY).core.to_json()

    def test_the_scene_default_letters_every_panel(self, folder: Path):
        body = (
            "lettering: {font: fonts/Lettering-Regular.ttf}\n"
            "cast: {alice: {reference: alice}}\n"
            "panels:\n"
            "  one: {script: [{say: {by: alice, text: Hi.}}]}\n"
            "  two: {script: [{say: {by: alice, text: Bye.}}]}\n"
        )
        book = compile_book_file(_write(folder, body, "story.scene.yaml"))
        digests = {result.core.fonts[Face.REGULAR].sha256 for result in book.panels.values()}
        assert digests == {_digest(SEMIBOLD)}
        assert set(book.fonts) == digests

    def test_a_comic_script_declares_it_in_the_front_matter(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n"
            "lettering: {font: fonts/Lettering-Regular.ttf}\n---\n"
            "PANEL 1\n\nALICE\nHello.\n"
        )
        path = _write(folder, script, "story.script")
        book = compile_book_file(path)
        assert book.panels["1"].core.fonts[Face.REGULAR].sha256 == _digest(SEMIBOLD)

    def test_live_text_names_the_declared_family(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        result = compile_file(path)
        svg = render(result.core, fonts=result.fonts, live_text=True)
        assert 'font-family="Source Sans Pro Semibold, sans-serif"' in svg

    def test_live_text_without_a_font_names_the_shipped_family(self):
        svg = render(compile_source(CAST + SAY).core, live_text=True)
        assert 'font-family="Source Sans Pro, sans-serif"' in svg

    def test_the_drawing_is_at_the_size_measured(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        result = compile_file(path)
        core = result.core
        assert_svg_is_sound(
            render(core, fonts=result.fonts),
            size=(core.width, core.height),
            font_sizes=[balloon.font_size for balloon in core.balloons],
        )


class TestWhereTheFileIs:
    def test_it_is_read_beside_the_document_not_the_working_directory(
        self, folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        assert compile_file(path).core.fonts[Face.REGULAR].sha256 == _digest(SEMIBOLD)

    def test_text_can_be_given_the_folder_it_belongs_to(self, folder: Path):
        source = f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}"
        assert compile_source(source, base=folder).core.fonts[Face.REGULAR].sha256 == _digest(
            SEMIBOLD
        )

    def test_text_with_no_folder_cannot_declare_a_font(self):
        source = f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}"
        with pytest.raises(PanelSyntaxError, match="no folder") as raised:
            compile_source(source)
        assert raised.value.rule == "font-file"

    @pytest.mark.parametrize(
        "declared", ["/etc/fonts/x.ttf", "C:/Windows/Fonts/arial.ttf", "C:x.ttf"]
    )
    def test_an_absolute_path_is_refused(self, declared: str, folder: Path):
        with pytest.raises(PanelSyntaxError, match="relative") as raised:
            resolve_relative(declared, folder, what="font", rule="font-file")
        assert raised.value.rule == "font-file"

    @pytest.mark.parametrize("declared", ["fonts\\Lettering-Regular.ttf", "fonts/a\\b.ttf"])
    def test_a_backslash_is_refused_on_every_platform(self, declared: str, folder: Path):
        """A backslash separates folders on Windows and is part of a file name elsewhere,
        so a document that wrote one found its font on one machine and not another."""
        with pytest.raises(PanelSyntaxError, match="/ between folders") as raised:
            resolve_relative(declared, folder, what="font", rule="font-file")
        assert raised.value.rule == "font-file"

    def test_a_backslash_is_refused_where_the_file_would_open(self, folder: Path):
        path = _write(folder, f"lettering: {{font: 'fonts\\Lettering-Regular.ttf'}}\n{CAST}{SAY}")
        with pytest.raises(PanelSyntaxError, match="/ between folders") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"

    def test_check_locates_a_backslash(self, folder: Path):
        path = _write(folder, f"{CAST}lettering: {{font: 'fonts\\Lettering-Regular.ttf'}}\n{SAY}")
        found = diagnose_file(path)
        assert [(item.rule, item.path) for item in found] == [("font-file", ("lettering", "font"))]
        assert found[0].region is not None
        assert found[0].region.start.line == 2

    def test_a_path_may_climb_out_of_the_document_folder(self, folder: Path):
        (folder / "chapter").mkdir()
        path = _write(
            folder / "chapter",
            f"lettering: {{font: ../fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}",
        )
        assert compile_file(path).core.fonts[Face.REGULAR].sha256 == _digest(SEMIBOLD)

    def test_no_path_reaches_the_output(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        result = compile_file(path)
        outputs = [
            result.core.to_json(),
            render(result.core, fonts=result.fonts),
            render(result.core, fonts=result.fonts, live_text=True),
        ]
        for text in outputs:
            assert str(folder) not in text
            assert "fonts/Lettering" not in text
            assert "Lettering-Regular" not in text

    def test_it_is_byte_identical_across_runs(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        first, second = compile_file(path), compile_file(path)
        assert first.core.to_json() == second.core.to_json()
        assert render(first.core, fonts=first.fonts) == render(second.core, fonts=second.fonts)

    def test_a_changed_file_is_read_again(self, folder: Path):
        """Fonts are cached by what is in them, not by where they are, so replacing the
        file -- as the playground does on every upload -- is never answered from memory."""
        font = folder / "fonts" / "Lettering-Regular.ttf"
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        before = compile_file(path).core.fonts[Face.REGULAR].sha256
        shutil.copy(SEMIBOLD_ITALIC, font)
        assert compile_file(path).core.fonts[Face.REGULAR].sha256 != before


class TestMistakes:
    def test_a_missing_file_is_named_as_written(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Missing.ttf}}\n{CAST}{SAY}")
        with pytest.raises(PanelSyntaxError, match=r"fonts/Missing\.ttf") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"
        assert str(folder) not in str(raised.value).replace(str(path), "")

    def test_a_file_that_is_not_a_font_is_refused(self, folder: Path):
        (folder / "fonts" / "notes.ttf").write_text("not a font", encoding="utf-8")
        path = _write(folder, f"lettering: {{font: fonts/notes.ttf}}\n{CAST}{SAY}")
        with pytest.raises(PanelSyntaxError, match="not a font") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"

    def test_check_locates_a_missing_font(self, folder: Path):
        path = _write(folder, f"{CAST}lettering:\n  font: fonts/Missing.ttf\n{SAY}")
        (found,) = diagnose_file(path)
        assert found.rule == "font-file"
        assert found.path == ("lettering", "font")
        assert found.region is not None
        assert found.region.start.line == 3

    def test_check_locates_the_face_in_a_mapping(self, folder: Path):
        body = (
            f"{CAST}lettering:\n  font:\n    regular: fonts/Lettering-Regular.ttf\n"
            f"    italic: fonts/Missing.ttf\n{SAY}"
        )
        (found,) = diagnose_file(_write(folder, body))
        assert found.path == ("lettering", "font", "italic")
        assert found.region is not None
        assert found.region.start.line == 5

    def test_check_reports_a_scene_default_once(self, folder: Path):
        body = (
            "lettering: {font: fonts/Missing.ttf}\n"
            "cast: {alice: {reference: alice}}\n"
            "panels:\n  one: {}\n  two: {}\n"
        )
        found = diagnose_file(_write(folder, body, "story.scene.yaml"))
        assert [(item.rule, item.path) for item in found] == [("font-file", ("lettering", "font"))]

    def test_check_of_text_with_no_folder_reports_it(self):
        (found,) = diagnose_source(f"lettering: {{font: fonts/x.ttf}}\n{CAST}")
        assert found.rule == "font-file"

    def test_check_of_a_script_finds_it_in_the_front_matter(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n"
            "lettering: {font: fonts/Missing.ttf}\n---\nPANEL 1\n\nALICE\nHello.\n"
        )
        (found,) = diagnose_file(_write(folder, script, "story.script"))
        assert found.rule == "font-file"
        assert found.path == ("lettering", "font")
        assert found.region is not None
        assert found.region.start.line == 3

    def test_a_folder_named_as_a_font_cannot_be_read(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts}}\n{CAST}{SAY}")
        with pytest.raises(PanelSyntaxError, match="cannot be read") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"

    def test_an_empty_path_is_refused(self, folder: Path):
        path = _write(folder, f"lettering: {{font: ''}}\n{CAST}{SAY}")
        with pytest.raises(PanelSyntaxError, match="empty") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"

    @pytest.mark.parametrize("control", ["\\0", "\\x01", "\\x1f", "\\x7f"])
    def test_a_control_character_is_refused_not_a_crash(self, control: str, folder: Path):
        """A NUL reached the file system, which raises `ValueError` -- not an error the
        compiler reports, so `build` and `check` both ended in a traceback."""
        path = _write(folder, f'lettering: {{font: "fonts/a{control}b.ttf"}}\n{CAST}{SAY}')
        with pytest.raises(PanelSyntaxError, match="control character") as raised:
            compile_file(path)
        assert raised.value.rule == "font-file"

    def test_check_locates_a_control_character(self, folder: Path):
        path = _write(folder, f'{CAST}lettering: {{font: "fonts/a\\0b.ttf"}}\n{SAY}')
        found = diagnose_file(path)
        assert [(item.rule, item.path) for item in found] == [("font-file", ("lettering", "font"))]
        assert "U+0000" in found[0].message

    def test_a_font_a_script_panel_names_is_reported_against_that_panel(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PANEL 1\n@lettering: {font: fonts/Missing.ttf}\n\nALICE\nHello.\n"
        )
        (found,) = diagnose_file(_write(folder, script, "story.script"))
        assert found.rule == "font-file"
        assert found.path == ("1", "lettering", "font")

    def test_check_takes_the_folder_for_text(self, folder: Path):
        source = f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}"
        assert diagnose_source(source, base=folder) == []

    def test_a_good_font_is_not_a_finding(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        assert diagnose_file(path) == []


class TestRenderingNeedsTheFont:
    def test_a_core_is_never_drawn_in_a_font_it_was_not_measured_in(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        core = compile_file(path).core
        with pytest.raises(ValueError, match="Source Sans Pro Semibold"):
            render(core)

    def test_a_hand_edited_core_can_be_drawn_given_its_font(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        core = PanelCore.from_json(compile_file(path).core.to_json())
        font = FontMetrics(folder / "fonts" / "Lettering-Regular.ttf")
        assert render(core, fonts={font.sha256: font}) == render(
            compile_file(path).core, fonts=compile_file(path).fonts
        )

    def test_a_strip_and_a_page_are_drawn_from_the_same_fonts(self, folder: Path):
        body = (
            "lettering: {font: fonts/Lettering-Regular.ttf}\n"
            "cast: {alice: {reference: alice}}\n"
            "pages: [{tiers: [{panels: [one, two]}]}]\n"
            "panels:\n"
            "  one: {script: [{say: {by: alice, text: Hi.}}]}\n"
            "  two: {script: [{say: {by: alice, text: Bye.}}]}\n"
        )
        book = compile_book_file(_write(folder, body, "story.scene.yaml"))
        cores = {name: result.core for name, result in book.panels.items()}
        assert render_page(book.pages[0], cores, fonts=book.fonts)
        assert render_pages(book.pages, cores, fonts=book.fonts)
        assert render_strip(list(cores.items()), fonts=book.fonts)
        with pytest.raises(ValueError, match="Semibold"):
            render_page(book.pages[0], cores)

    def test_the_refusal_names_the_font_by_the_start_of_its_digest(self, folder: Path):
        path = _write(folder, f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        digest = _digest(folder / "fonts" / "Lettering-Regular.ttf")
        with pytest.raises(ValueError, match=rf"\(sha256 {digest[:12]}\), and that font"):
            render(compile_file(path).core)

    def test_a_library_caller_can_still_replace_the_regular_face(self):
        semibold = FontMetrics(SEMIBOLD)
        result = compile_source(CAST + SAY, metrics=semibold)
        assert result.core.fonts[Face.REGULAR].sha256 == semibold.sha256
        assert render(result.core, metrics=semibold) == render(result.core, fonts=result.fonts)

    def test_the_shipped_regular_passed_by_hand_records_nothing(self):
        result = compile_source(CAST + SAY, metrics=load_metrics())
        assert result.core.fonts == {}

    def test_compile_ir_takes_the_folder_too(self, folder: Path):
        panel = parse_panel(f"lettering: {{font: fonts/Lettering-Regular.ttf}}\n{CAST}{SAY}")
        assert compile_ir(panel, base=folder).core.fonts[Face.REGULAR].sha256 == _digest(SEMIBOLD)

    def test_the_book_of_a_scene_given_as_text_uses_its_folder(self, folder: Path):
        body = "lettering: {font: fonts/Lettering-Regular.ttf}\n" + CAST + SAY
        book = compile_book(body, base=folder)
        assert (
            json.loads(book.panels["panel"].core.to_json())["fonts"]["regular"]["style"]
            == "Regular"
        )

    def test_a_script_parsed_alone_can_be_compiled_against_its_folder(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n"
            "lettering: {font: fonts/Lettering-Regular.ttf}\n---\nPANEL 1\n\nALICE\nHello.\n"
        )
        (panel,) = parse_script(script).values()
        assert compile_ir(panel, base=folder).core.fonts[Face.REGULAR].sha256 == _digest(SEMIBOLD)
