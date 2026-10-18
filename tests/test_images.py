"""Reading a supplied picture: its size, from its header, and nothing else (#70).

The solver never sees artwork. What it is given of a picture is a fact about the file --
how many pixels across and down -- read from the PNG or JPEG header, the two formats SVG
2 requires every viewer to draw. The pixels are never decoded, and no imaging library is
involved: the playground could not ship one, and the licence gate would have to pass it
for two headers.

A picture is read as a font is, relative to the folder the document is in, and every way
of failing to read one is `image-file`, found by `scenet check` without the solver.
"""

import hashlib
from pathlib import Path

import pytest

from scenet.diagnostics import diagnose_file, diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.images import IMAGE_RULE, load_image, measure
from scenet.paths import read_relative
from scenet.pipeline import compile_book, compile_file, compile_script, compile_source
from tests.images import PROGRESSIVE, jpeg, png, segment, tiny_png

CAST = "cast: {alice: {reference: alice}}\n"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A document folder with an `art/` beside it, as an author would keep one."""
    art = tmp_path / "comic" / "art"
    art.mkdir(parents=True)
    (art / "street.png").write_bytes(png(960, 640))
    (art / "photo.jpg").write_bytes(jpeg(4000, 3000))
    return tmp_path / "comic"


def _write(folder: Path, body: str, name: str = "page.panel.yaml") -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def _refusal(data: bytes) -> str:
    """Why a picture is refused, as the author is told."""
    with pytest.raises(PanelSyntaxError) as raised:
        load_image("art/x", {"art/x": data}, loc=("setting", "image"))
    assert raised.value.rule == IMAGE_RULE
    return str(raised.value)


class TestTheSizeIsReadFromTheHeader:
    @pytest.mark.parametrize(("width", "height"), [(1, 1), (960, 640), (640, 960), (65535, 3)])
    def test_a_png(self, width: int, height: int):
        assert measure(png(width, height)) == ("image/png", width, height)

    @pytest.mark.parametrize("frame", [0xC0, 0xC1, PROGRESSIVE, 0xC3, 0xC9, 0xCF])
    def test_a_jpeg_of_any_frame_kind(self, frame: int):
        assert measure(jpeg(4000, 3000, frame=frame)) == ("image/jpeg", 4000, 3000)

    def test_tables_before_the_frame_are_skipped(self):
        """A Huffman table's marker, C4, sits among the frame markers and is not one."""
        tables = (
            segment(0xC4, bytes(20)) + segment(0xDB, bytes(65)) + segment(0xFE, b"made by hand")
        )
        assert measure(jpeg(800, 600, before=tables)) == ("image/jpeg", 800, 600)

    def test_fill_bytes_between_markers_are_skipped(self):
        assert measure(jpeg(10, 20, before=bytes([0xFF, 0xFF]))) == ("image/jpeg", 10, 20)

    def test_the_format_is_read_from_the_bytes_not_the_name(self, folder: Path):
        (folder / "art" / "mislabelled.jpg").write_bytes(png(30, 20))
        image = load_image("art/mislabelled.jpg", folder, loc=())
        assert (image.media_type, image.width, image.height) == ("image/png", 30, 20)

    def test_a_real_png_is_read_the_same_as_a_bare_header(self):
        assert measure(tiny_png(3, 2)) == ("image/png", 3, 2)


class TestWhatIsKept:
    def test_the_path_as_written_its_digest_and_its_bytes(self, folder: Path):
        data = (folder / "art" / "street.png").read_bytes()
        image = load_image("./art/street.png", folder, loc=())
        assert image.href == "./art/street.png"
        assert image.sha256 == hashlib.sha256(data).hexdigest()
        assert image.data == data

    def test_the_bytes_are_not_in_its_repr(self, folder: Path):
        assert "data" not in repr(load_image("art/street.png", folder, loc=()))


class TestRefused:
    def test_a_format_other_than_png_or_jpeg(self):
        assert "PNG or JPEG" in _refusal(b"GIF89a" + bytes(20))

    def test_text(self):
        assert "PNG or JPEG" in _refusal(b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    def test_an_empty_file(self):
        assert "PNG or JPEG" in _refusal(b"")

    @pytest.mark.parametrize("cut", [8, 16, 23])
    def test_a_png_cut_short(self, cut: int):
        assert "size" in _refusal(png(10, 10)[:cut])

    def test_a_png_whose_first_chunk_is_not_its_header(self):
        data = png(10, 10)
        assert "size" in _refusal(data[:12] + b"IHDX" + data[16:])

    @pytest.mark.parametrize("cut", [2, 3, 10, 30])
    def test_a_jpeg_cut_short(self, cut: int):
        assert "size" in _refusal(jpeg(10, 10)[:cut])

    def test_a_jpeg_with_no_frame_before_its_data(self):
        assert "size" in _refusal(bytes([0xFF, 0xD8]) + segment(0xDA, bytes(4)))

    def test_a_jpeg_whose_height_comes_after_its_data(self):
        """A height of zero means a DNL marker gives it after the scan: not a header."""
        assert "width or height" in _refusal(jpeg(10, 0))

    @pytest.mark.parametrize("size", [(0, 10), (10, 0)])
    def test_a_png_with_nothing_across_or_down(self, size: tuple[int, int]):
        assert "width or height" in _refusal(png(*size))


class TestOrientation:
    """EXIF can say a picture is to be shown turned, and renderers disagree on obeying it:
    Chromium turns an SVG `<image>`, gdk-pixbuf does not unless asked, and Inkscape's own
    tracker says both. A picture that turns depending on the viewer is refused instead."""

    @pytest.mark.parametrize("orientation", [2, 3, 5, 6, 7, 8])
    def test_a_turned_jpeg_is_refused(self, orientation: int):
        assert f"orientation ({orientation})" in _refusal(jpeg(10, 20, orientation=orientation))

    @pytest.mark.parametrize("orientation", [3, 6])
    def test_a_turned_png_is_refused(self, orientation: int):
        assert "orientation" in _refusal(png(10, 20, orientation=orientation))

    def test_upright_is_fine(self):
        assert measure(jpeg(10, 20, orientation=1)) == ("image/jpeg", 10, 20)
        assert measure(png(10, 20, orientation=1)) == ("image/png", 10, 20)

    def test_exif_nobody_can_read_is_ignored_as_every_renderer_ignores_it(self):
        broken = segment(0xE1, b"Exif" + bytes(2) + b"XX*" + bytes(9))
        assert measure(jpeg(10, 20, before=broken)) == ("image/jpeg", 10, 20)


class TestWhereTheFileIs:
    def test_it_is_read_beside_the_document_not_the_working_directory(
        self, folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        path = _write(folder, f"{CAST}setting: {{image: art/street.png}}\n")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        result = compile_file(path)
        assert set(result.images.values()) == {(folder / "art" / "street.png").read_bytes()}

    @pytest.mark.parametrize(
        ("declared", "why"),
        [
            ("/srv/art/x.png", "absolute"),
            ("C:/art/x.png", "absolute"),
            ("art\\x.png", "backslash"),
            ("", "empty"),
            ("art/missing.png", "not found"),
            ("art", "cannot be read"),
        ],
    )
    def test_every_fault_is_image_file(self, declared: str, why: str, folder: Path):
        with pytest.raises(PanelSyntaxError, match=why) as raised:
            load_image(declared, folder, loc=("setting", "image"))
        assert (raised.value.rule, raised.value.loc) == (IMAGE_RULE, ("setting", "image"))

    def test_text_with_no_folder_cannot_name_one(self):
        with pytest.raises(PanelSyntaxError, match="no folder") as raised:
            compile_source(f"{CAST}setting: {{image: art/street.png}}\n")
        assert raised.value.rule == IMAGE_RULE

    def test_the_message_names_the_path_as_written(self, folder: Path):
        with pytest.raises(PanelSyntaxError) as raised:
            load_image("art/missing.png", folder, loc=())
        assert "'art/missing.png'" in str(raised.value)
        assert str(folder) not in str(raised.value)


class TestTheFilesThemselvesMayStandInForTheFolder:
    """A server is sent the text, and the files beside it, never a path of its own."""

    def test_a_mapping_by_the_path_the_document_writes(self):
        result = compile_source(
            f"{CAST}setting: {{image: art/street.png}}\n", base={"art/street.png": png(9, 6)}
        )
        assert list(result.images.values()) == [png(9, 6)]

    @pytest.mark.parametrize(
        "declared", ["./art/street.png", "art//street.png", "x/../art/street.png"]
    )
    def test_the_path_is_read_as_a_folder_would_read_it(self, declared: str):
        assert (
            read_relative(declared, {"art/street.png": b"bytes"}, what="image", rule=IMAGE_RULE)
            == b"bytes"
        )

    def test_the_keys_are_read_so_too(self):
        assert (
            read_relative("art/a.png", {"./art/a.png": b"x"}, what="image", rule=IMAGE_RULE) == b"x"
        )

    def test_a_file_not_given_is_not_found(self):
        with pytest.raises(PanelSyntaxError, match="not found beside the document"):
            read_relative("art/a.png", {"art/b.png": b"x"}, what="image", rule=IMAGE_RULE)

    def test_the_same_checks_apply(self):
        with pytest.raises(PanelSyntaxError, match="absolute"):
            read_relative("/art/a.png", {"/art/a.png": b"x"}, what="image", rule=IMAGE_RULE)

    def test_a_font_too_letters_the_same_from_memory_as_from_a_file(
        self, folder: Path, tmp_path: Path
    ):
        import fonts.ttf  # noqa: PLC0415 -- only this test needs the shipped family's files

        face = Path(fonts.ttf.SourceSansProSemibold).read_bytes()  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
        (folder / "fonts").mkdir()
        (folder / "fonts" / "Comic.ttf").write_bytes(face)
        source = (
            f"{CAST}lettering: {{font: fonts/Comic.ttf}}\n"
            "script: [{say: {by: alice, text: Hi}}]\n"
        )
        from_disk = compile_source(source, base=folder)
        from_memory = compile_source(source, base={"fonts/Comic.ttf": face})
        assert from_memory.core.to_json() == from_disk.core.to_json()


class TestCheckFindsIt:
    def test_a_missing_picture_is_one_finding_where_it_is_named(self, folder: Path):
        path = _write(folder, f"{CAST}setting:\n  time: dusk\n  image: art/missing.png\n")
        found = diagnose_file(path)
        assert [(item.rule, item.path) for item in found] == [(IMAGE_RULE, ("setting", "image"))]
        assert found[0].region is not None
        assert found[0].region.start.line == 4

    def test_a_good_picture_is_not_a_finding(self, folder: Path):
        assert diagnose_file(_write(folder, f"{CAST}setting: {{image: art/street.png}}\n")) == []

    def test_text_is_checked_against_the_folder_it_is_given(self, folder: Path):
        source = f"{CAST}setting: {{image: art/street.png}}\n"
        assert diagnose_source(source, base=folder) == []
        assert [item.rule for item in diagnose_source(source)] == [IMAGE_RULE]

    def test_a_scene_default_is_reported_once(self, folder: Path):
        path = _write(
            folder,
            f"{CAST}setting: {{image: art/missing.png}}\npanels:\n  one: {{}}\n  two: {{}}\n",
            "page.scene.yaml",
        )
        found = diagnose_file(path)
        assert [(item.rule, item.path) for item in found] == [(IMAGE_RULE, ("setting", "image"))]

    def test_a_scene_panel_of_its_own_is_reported_against_it(self, folder: Path):
        path = _write(
            folder,
            f"{CAST}panels:\n  one: {{}}\n  two: {{setting: {{image: art/missing.png}}}}\n",
            "page.scene.yaml",
        )
        found = diagnose_file(path)
        assert [item.path for item in found] == [("panels", "two", "setting", "image")]

    def test_a_script_directive_is_reported_at_its_line(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PANEL 1\n@shot: wide\n@setting: {image: art/missing.png}\nALICE\nHi.\n"
        )
        found = diagnose_script(script, base=folder)
        assert [(item.rule, item.path) for item in found] == [
            (IMAGE_RULE, ("1", "setting", "image"))
        ]
        assert found[0].region is not None
        assert found[0].region.start.line == 6

    def test_a_script_front_matter_picture_is_reported_once(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\nsetting: {image: art/missing.png}\n---\n"
            "PANEL 1\nALICE\nHi.\nPANEL 2\nALICE\nBye.\n"
        )
        found = diagnose_script(script, base=folder)
        assert [(item.rule, item.path) for item in found] == [(IMAGE_RULE, ("setting", "image"))]


class TestCheckAndBuildAgree:
    @pytest.mark.parametrize(
        "image",
        ["art/missing.png", "/art/x.png", "art\\x.png", "art", "art/turned.jpg", "art/note.txt"],
    )
    def test_build_refuses_what_check_reports(self, image: str, folder: Path):
        (folder / "art" / "turned.jpg").write_bytes(jpeg(10, 20, orientation=6))
        (folder / "art" / "note.txt").write_text("not a picture", encoding="utf-8")
        source = f"{CAST}setting: {{image: '{image}'}}\n"
        assert [item.rule for item in diagnose_source(source, base=folder)] == [IMAGE_RULE]
        with pytest.raises(PanelSyntaxError) as raised:
            compile_source(source, base=folder)
        assert raised.value.rule == IMAGE_RULE

    def test_a_book_holds_every_panel_s_picture_once(self, folder: Path):
        book = compile_book(
            f"{CAST}setting: {{image: art/street.png}}\n"
            "panels:\n  one: {}\n  two: {setting: {image: art/photo.jpg}}\n  three: {}\n",
            base=folder,
        )
        assert sorted(book.images.values(), key=len) == sorted(
            [(folder / "art" / name).read_bytes() for name in ("street.png", "photo.jpg")], key=len
        )

    def test_a_script_reads_its_pictures(self, folder: Path):
        script = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PANEL 1\n@setting: {image: art/street.png}\nALICE\nHi.\n"
        )
        assert len(compile_script(script, base=folder).images) == 1

    def test_a_panel_without_a_picture_holds_none(self):
        assert compile_source(CAST).images == {}
