"""`scenet build --conditioning`, and the library call behind it (#72).

Five files beside each panel's SVG, named after it: `.pose.json`, `.boxes.json`, `.depth.svg`,
`.mask.svg`, `.semantics.json`. Text, JSON and SVG only -- nothing is rasterised -- and the same
bytes from any run and any working directory.
"""

import io
import zipfile
from pathlib import Path

import pytest

import scenet
from scenet import Conditioning, compile_source, render_conditioning
from scenet.cli import main
from scenet.emit.boxes import render_boxes
from scenet.emit.depth import render_depth
from scenet.emit.export import EXPORTS, conditioning_archive
from scenet.emit.mask import render_mask
from scenet.emit.pose import render_pose
from scenet.emit.semantics import render_semantics
from scenet.pipeline import compile_book, compile_book_file

ROOT = Path(__file__).resolve().parents[1]

PANEL = """\
cast:
  alice: {reference: alice, pose: pointing}
  bob: {reference: bob, facing: left}
staging: [alice left_of bob, alice looking_at bob]
script:
  - say: {by: alice, text: "You forgot your umbrella!"}
"""

SCENE = """\
cast:
  alice: {reference: alice}
  bob: {reference: bob}
panels:
  one: {staging: [alice left_of bob]}
  two: {camera: {shot: close_up}, staging: [bob left_of alice]}
pages: [{tiers: [{panels: [one, two]}]}]
"""

SCRIPT = """\
---
cast:
  ALICE: {reference: alice}
---
PAGE ONE

Panel 1

ALICE: Hello.

Panel 2

ALICE: Goodbye.
"""

SUFFIXES = [".pose.json", ".boxes.json", ".depth.svg", ".mask.svg", ".semantics.json"]


def _files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_bytes(text.encode("utf-8"))
    return path


class TestTheLibraryCall:
    def test_it_is_public(self):
        assert "render_conditioning" in scenet.__all__
        assert "Conditioning" in scenet.__all__

    def test_it_is_every_export_of_one_panel(self):
        core = compile_source(PANEL).core
        exports = render_conditioning(core)
        assert exports == Conditioning(
            pose=render_pose(core),
            boxes=render_boxes(core),
            depth=render_depth(core),
            mask=render_mask(core),
            semantics=render_semantics(core),
        )

    def test_its_files_are_named_by_suffix_in_a_fixed_order(self):
        exports = render_conditioning(compile_source(PANEL).core)
        assert [suffix for suffix, _ in exports.files()] == SUFFIXES
        assert dict(exports.files())[".depth.svg"] == exports.depth
        assert [suffix for suffix, _ in EXPORTS] == SUFFIXES


class TestBuild:
    def test_five_files_beside_a_panel(self, tmp_path: Path):
        source = _write(tmp_path, "duel.panel.yaml", PANEL)
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
        assert _files(tmp_path) == sorted(
            ["duel.panel.yaml", "duel.svg", *(f"duel{suffix}" for suffix in SUFFIXES)]
        )

    def test_each_holds_what_the_library_call_returns(self, tmp_path: Path):
        source = _write(tmp_path, "duel.panel.yaml", PANEL)
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
        exports = render_conditioning(compile_source(PANEL).core)
        for suffix, text in exports.files():
            assert (tmp_path / f"duel{suffix}").read_bytes() == text.encode("utf-8")

    def test_nothing_without_the_flag(self, tmp_path: Path):
        source = _write(tmp_path, "duel.panel.yaml", PANEL)
        assert main(["build", str(source), "--quiet"]) == 0
        assert _files(tmp_path) == ["duel.panel.yaml", "duel.svg"]

    def test_every_panel_of_a_scene_and_no_page(self, tmp_path: Path):
        """A page adds no layout to a panel; Page Core (`--core`) says where each frame is."""
        source = _write(tmp_path, "story.scene.yaml", SCENE)
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
        written = _files(tmp_path)
        for panel in ("one", "two"):
            for suffix in SUFFIXES:
                assert f"story.{panel}{suffix}" in written
        assert [name for name in written if ".page-" in name] == ["story.page-1.svg"]

    def test_every_panel_of_a_comic_script(self, tmp_path: Path):
        source = _write(tmp_path, "talk.script", SCRIPT)
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
        assert sum(name.endswith(".pose.json") for name in _files(tmp_path)) == 2

    def test_a_panel_named_like_an_export_is_refused_and_nothing_written(self, tmp_path: Path):
        source = _write(
            tmp_path,
            "x.scene.yaml",
            "cast: {a: {reference: alice}}\npanels:\n  p: {}\n  p.depth: {}\n",
        )
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 2
        assert _files(tmp_path) == ["x.scene.yaml"]

    def test_every_file_is_utf8_with_lf(self, tmp_path: Path):
        source = _write(tmp_path, "duel.panel.yaml", PANEL)
        assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
        for suffix in SUFFIXES:
            data = (tmp_path / f"duel{suffix}").read_bytes()
            assert b"\r" not in data
            assert data.endswith(b"\n")
            data.decode("utf-8")


class TestDeterminism:
    def test_the_same_bytes_from_any_working_directory(self, tmp_path: Path):
        """Built from a relative path, an absolute one, and the folder itself."""
        gallery = ROOT / "examples" / "gallery"
        source = "34-supplied-art.scene.yaml"
        builds: list[dict[str, bytes]] = []
        for index, (cwd, path) in enumerate(
            [
                (ROOT, str(Path("examples", "gallery", source))),
                (tmp_path, str(gallery / source)),
                (gallery, source),
            ]
        ):
            out = tmp_path / f"out{index}"
            with pytest.MonkeyPatch.context() as patch:
                patch.chdir(cwd)
                assert main(["build", path, "-o", f"{out}/", "--conditioning", "--quiet"]) == 0
            builds.append({p.name: p.read_bytes() for p in out.iterdir()})
        assert builds[0] == builds[1] == builds[2]
        for name, data in builds[0].items():
            text = data.decode("utf-8")
            for leak in (str(tmp_path), str(ROOT), ROOT.as_posix()):
                assert leak not in text, name

    def test_the_same_bytes_every_run(self):
        book = compile_book(SCENE)
        again = compile_book(SCENE)
        for name, result in book.panels.items():
            assert render_conditioning(result.core) == render_conditioning(again.panels[name].core)


def test_a_one_panel_scene_names_its_panel_and_a_panel_document_does_not(tmp_path: Path):
    """What the playground follows for a document of one panel."""
    source = _write(
        tmp_path, "story.scene.yaml", "cast: {a: {reference: alice}}\npanels:\n  one: {}\n"
    )
    assert main(["build", str(source), "--conditioning", "--quiet"]) == 0
    assert "story.one.pose.json" in _files(tmp_path)


class TestTheArchive:
    """Every panel's exports in one ZIP, which is how the playground offers a document's (#238).

    Under the names `build --conditioning` writes, holding what it writes, so a ZIP saved from
    the playground and unpacked is the command line's output.
    """

    @pytest.mark.parametrize(
        ("name", "text"),
        [("duel.panel.yaml", PANEL), ("story.scene.yaml", SCENE), ("talk.script", SCRIPT)],
    )
    def test_it_holds_what_build_writes_under_the_same_names(
        self, tmp_path: Path, name: str, text: str
    ):
        source = _write(tmp_path, name, text)
        assert main(["build", str(source), "-o", f"{tmp_path / 'out'}/", "--conditioning"]) == 0
        written = {
            path.name: path.read_bytes()
            for path in (tmp_path / "out").iterdir()
            if path.name.endswith(tuple(SUFFIXES))
        }
        book = compile_book_file(source)
        cores = {panel: result.core for panel, result in book.panels.items()}
        stem = name.split(".")[0]
        with zipfile.ZipFile(io.BytesIO(conditioning_archive(cores, stem))) as archive:
            held = {entry: archive.read(entry) for entry in archive.namelist()}
        assert held == written

    def test_in_build_s_order_panel_by_panel(self):
        cores = {panel: result.core for panel, result in compile_book(SCENE).panels.items()}
        with zipfile.ZipFile(io.BytesIO(conditioning_archive(cores, "story"))) as archive:
            names = archive.namelist()
        assert names == [f"story.{panel}{suffix}" for panel in ("one", "two") for suffix in SUFFIXES]

    def test_the_same_bytes_every_run_on_every_platform(self):
        """No clock, no file mode or system of the machine that made it."""
        cores = {panel: result.core for panel, result in compile_book(SCENE).panels.items()}
        data = conditioning_archive(cores, "story")
        assert data == conditioning_archive(cores, "story")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                assert entry.date_time == (1980, 1, 1, 0, 0, 0)
                assert entry.create_system == 3
                assert entry.external_attr == 0o100644 << 16
                assert entry.compress_type == zipfile.ZIP_STORED
