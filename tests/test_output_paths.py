"""Where `scenet build` writes (#460).

`-o PATH` is a folder when it is one already, when it ends with a separator, or when it has
no extension at all; it is the SVG when it ends in `.svg`; and anything else is a usage
error, since every SVG written ends in `.svg`. `outT` used to be written as a file called
`outT`, beside `outT.pdf`, and a scene's panels as `outT.whole` and `outT.page-1`.

A picture a panel links is copied beside the SVG, at the path the SVG links it by, so the
SVG shows it wherever it was written. A file already there that is not the picture is
replaced, and the build says so.
"""

import os
import re
from pathlib import Path

import pytest

import scenet.cli
from scenet.cli import main
from tests.images import tiny_png

PANEL = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
SCENE = (
    "cast: {alice: {reference: alice}}\n"
    "pages: [{tiers: [{panels: [one, two]}]}]\n"
    "panels: {one: {}, two: {}}\n"
)
PICTURE = tiny_png(3, 2)
OTHER = tiny_png(5, 4)


def _written(root: Path, *, leave: frozenset[str] = frozenset()) -> list[str]:
    """Every file under `root`, by its path from it, but the ones a test put there."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in leave
    )


@pytest.fixture
def panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "duel.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    return source


@pytest.fixture
def scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "story.scene.yaml"
    source.write_text(SCENE, encoding="utf-8")
    return source


class TestAPanel:
    """For a panel, with `--core` and `--pdf`: every name written, for each form of `-o`."""

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            (None, ["duel.core.json", "duel.pdf", "duel.svg"]),
            ("out.svg", ["out.core.json", "out.pdf", "out.svg"]),
            ("OUT.SVG", ["OUT.SVG", "OUT.core.json", "OUT.pdf"]),
            ("nested/out.svg", ["nested/out.core.json", "nested/out.pdf", "nested/out.svg"]),
            ("outT", ["outT/duel.core.json", "outT/duel.pdf", "outT/duel.svg"]),
            ("outT/", ["outT/duel.core.json", "outT/duel.pdf", "outT/duel.svg"]),
            (f"outT{os.sep}", ["outT/duel.core.json", "outT/duel.pdf", "outT/duel.svg"]),
            ("a/b/c", ["a/b/c/duel.core.json", "a/b/c/duel.pdf", "a/b/c/duel.svg"]),
            (".", ["duel.core.json", "duel.pdf", "duel.svg"]),
        ],
    )
    def test_every_name_written(
        self, panel: Path, tmp_path: Path, written: str | None, expected: list[str]
    ):
        output = [] if written is None else ["-o", written]
        assert main(["build", str(panel), *output, "--core", "--pdf", "--quiet"]) == 0
        assert _written(tmp_path, leave=frozenset({panel.name})) == sorted(expected)

    @pytest.mark.parametrize("folder", ["out", "v1.2", "out.svg"])
    def test_a_folder_that_is_there_is_a_folder(self, panel: Path, tmp_path: Path, folder: str):
        """Whatever its name: one that looks like a file is still the folder it is."""
        (tmp_path / folder).mkdir()
        assert main(["build", str(panel), "-o", folder, "--quiet"]) == 0
        assert _written(tmp_path, leave=frozenset({panel.name})) == [f"{folder}/duel.svg"]

    @pytest.mark.parametrize("written", ["out.pdf", "out.png", "out.txt", "v1.2", "out.svg.bak"])
    def test_another_extension_is_a_usage_error_and_nothing_is_written(
        self, panel: Path, tmp_path: Path, written: str, capsys: pytest.CaptureFixture[str]
    ):
        assert main(["build", str(panel), "-o", written, "--pdf"]) == 2
        assert _written(tmp_path) == [panel.name]
        (line,) = capsys.readouterr().err.splitlines()
        assert line == (
            f"scenet: -o names the SVG, which ends in .svg, or a folder; {written} is neither: "
            f"write {Path(written).with_suffix('.svg')} for the file, or {written}/ for a folder"
        )

    def test_every_svg_written_ends_in_svg(
        self, panel: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        argv = ["build", str(panel), "-o", "plain", "--debug", "--conditioning", "--core"]
        assert main(argv) == 0
        wrote = [
            line.removeprefix("wrote ")
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("wrote ")
        ]
        assert sorted(Path(path).relative_to("plain").as_posix() for path in wrote) == [
            "duel.boxes.json",
            "duel.core.json",
            "duel.debug.svg",
            "duel.depth.svg",
            "duel.mask.svg",
            "duel.pose.json",
            "duel.semantics.json",
            "duel.svg",
        ]
        assert _written(tmp_path, leave=frozenset({panel.name})) == sorted(
            f"plain/{Path(path).name}" for path in wrote
        )

    def test_a_watch_writes_where_a_build_does(
        self, panel: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def watched(*_args: object, **_kwargs: object) -> None:
            """The watcher, stopped at once: only the first build runs."""

        monkeypatch.setattr(scenet.cli, "watch_loop", watched)
        assert main(["build", str(panel), "-o", "outW", "--watch", "--quiet"]) == 0
        assert _written(tmp_path, leave=frozenset({panel.name})) == ["outW/duel.svg"]


class TestAScene:
    """For a scene of two panels on a page, with `--strip`."""

    @pytest.mark.parametrize(
        ("written", "folder", "stem"),
        [
            (None, "", "story"),
            ("outTS", "outTS/", "story"),
            ("outTS/", "outTS/", "story"),
            ("outTS.svg", "", "outTS"),
            ("into/outTS.svg", "into/", "outTS"),
        ],
    )
    def test_every_name_written(
        self, scene: Path, tmp_path: Path, written: str | None, folder: str, stem: str
    ):
        output = [] if written is None else ["-o", written]
        assert main(["build", str(scene), *output, "--strip", "--core", "--quiet"]) == 0
        assert _written(tmp_path, leave=frozenset({scene.name})) == sorted(
            f"{folder}{stem}.{name}"
            for name in (
                "one.svg",
                "one.core.json",
                "two.svg",
                "two.core.json",
                "strip.svg",
                "page-1.svg",
                "page-1.core.json",
            )
        )


@pytest.fixture
def comic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A document lettered over a picture of its own, in a folder of its own."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "comic"
    (folder / "art").mkdir(parents=True)
    (folder / "art" / "street.png").write_bytes(PICTURE)
    (folder / "p1.panel.yaml").write_text(
        f"{PANEL}setting: {{image: ./art/street.png}}\n", encoding="utf-8"
    )
    return folder


def _links(svg: Path) -> list[str]:
    return re.findall(r'xlink:href="([^"#][^"]*)"', svg.read_text(encoding="utf-8"))


class TestALinkedPicture:
    def test_built_into_an_empty_folder_the_svg_finds_it(
        self, comic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Opened from that folder, every link the SVG holds is to the picture."""
        assert main(["build", str(comic / "p1.panel.yaml"), "-o", "out/"]) == 0
        svg = tmp_path / "out" / "p1.svg"
        (link,) = _links(svg)
        assert (svg.parent / link).read_bytes() == PICTURE
        assert _written(tmp_path / "out") == ["art/street.png", "p1.svg"]
        out = capsys.readouterr().out
        assert f"wrote {Path('out/art/street.png')}" in out
        assert (
            f"note: ./art/street.png is linked, so it was copied beside the SVG, to "
            f"{Path('out/art/street.png')}; build with --embed-images for an SVG that stands alone"
        ) in out.splitlines()

    def test_a_page_and_a_strip_find_it_too(self, comic: Path, tmp_path: Path):
        (comic / "s.scene.yaml").write_text(
            "cast: {alice: {reference: alice}}\npages: [{tiers: [{panels: [one, two]}]}]\n"
            "panels:\n  one: {setting: {image: art/street.png}}\n  two: {}\n",
            encoding="utf-8",
        )
        assert main(["build", str(comic / "s.scene.yaml"), "-o", "out", "--strip", "--quiet"]) == 0
        for name in ("s.one.svg", "s.page-1.svg", "s.strip.svg"):
            svg = tmp_path / "out" / name
            assert [(svg.parent / link).read_bytes() for link in _links(svg)] == [PICTURE]

    def test_beside_the_document_nothing_is_copied(
        self, comic: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert main(["build", str(comic / "p1.panel.yaml")]) == 0
        assert _written(comic) == ["art/street.png", "p1.panel.yaml", "p1.svg"]
        out = capsys.readouterr().out
        assert "copied" not in out
        assert "street.png" not in out

    def test_embedded_nothing_is_copied(self, comic: Path, tmp_path: Path):
        argv = ["build", str(comic / "p1.panel.yaml"), "-o", "out/", "--embed-images", "--quiet"]
        assert main(argv) == 0
        assert _written(tmp_path / "out") == ["p1.svg"]

    def test_the_same_picture_already_there_is_left_alone(
        self, comic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert main(["build", str(comic / "p1.panel.yaml"), "-o", "out/", "--quiet"]) == 0
        copy = tmp_path / "out" / "art" / "street.png"
        earlier = copy.stat().st_mtime_ns - 10**9
        os.utime(copy, ns=(earlier, earlier))
        assert main(["build", str(comic / "p1.panel.yaml"), "-o", "out/"]) == 0
        assert copy.stat().st_mtime_ns == earlier
        captured = capsys.readouterr()
        assert f"wrote {Path('out/art/street.png')}" not in captured.out
        assert captured.err == ""

    def test_another_file_there_is_replaced_and_the_build_says_so(
        self, comic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Even under `--quiet`: losing a file is never silent."""
        copy = tmp_path / "out" / "art" / "street.png"
        copy.parent.mkdir(parents=True)
        copy.write_bytes(OTHER)
        assert main(["build", str(comic / "p1.panel.yaml"), "-o", "out/", "--quiet"]) == 0
        assert copy.read_bytes() == PICTURE
        assert capsys.readouterr().err == (
            f"scenet: replaced {Path('out/art/street.png')}, which was not the picture "
            "./art/street.png the document links\n"
        )

    def test_a_picture_above_the_document_is_not_copied_out_of_the_folder(
        self, comic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Copied at the path it is linked by, it would land outside the output folder."""
        (tmp_path / "shared").mkdir()
        (tmp_path / "shared" / "sky.png").write_bytes(PICTURE)
        document = comic / "p2.panel.yaml"
        document.write_text(f"{PANEL}setting: {{image: ../shared/sky.png}}\n", encoding="utf-8")
        assert main(["build", str(document), "-o", "out/sub/"]) == 0
        assert _written(tmp_path / "out") == ["sub/p2.svg"]
        assert (
            "note: ../shared/sky.png is linked, and is outside the document's folder, so it was "
            f"not copied beside the SVG, in {Path('out/sub')}; build with --embed-images, or "
            "beside the document"
        ) in capsys.readouterr().out.splitlines()

    def test_a_copy_that_would_be_an_output_is_refused(
        self, comic: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """A picture is known by its bytes, not its name, so it may be called anything."""
        (comic / "p1.svg").write_bytes(PICTURE)
        document = comic / "p1.panel.yaml"
        document.write_text(f"{PANEL}setting: {{image: p1.svg}}\n", encoding="utf-8")
        assert main(["build", str(document), "-o", "out/"]) == 2
        assert "two outputs would both be written to" in capsys.readouterr().err
        assert not (tmp_path / "out").exists()


class TestEveryLinkedPicture:
    """Each picture is looked at on its own: one skipped does not stop the next."""

    @pytest.fixture
    def scene(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        folder = tmp_path / "comic"
        (folder / "art").mkdir(parents=True)
        (folder / "art" / "a.png").write_bytes(PICTURE)
        (folder / "art" / "b.png").write_bytes(OTHER)
        (tmp_path / "shared.png").write_bytes(PICTURE)
        (tmp_path / "scenet.toml").write_text("", encoding="utf-8")
        source = folder / "s.scene.yaml"
        say = "script: [{say: {by: alice, text: Hello.}}]"
        panels = {
            "one": "../shared.png",
            "two": "art/a.png",
            "three": "art/b.png",
        }
        source.write_text(
            "cast: {alice: {reference: alice}}\npanels:\n"
            + "".join(
                f"  {name}: {{setting: {{image: {image}}}, {say}}}\n"
                for name, image in panels.items()
            ),
            encoding="utf-8",
        )
        return source

    def test_one_reached_with_dots_does_not_stop_the_next(self, scene: Path, tmp_path: Path):
        assert main(["build", str(scene), "-o", "out/", "--quiet"]) == 0
        assert _written(tmp_path / "out") == sorted(
            ["art/a.png", "art/b.png", "s.one.svg", "s.three.svg", "s.two.svg"]
        )

    def test_one_already_there_does_not_stop_the_next(self, scene: Path, tmp_path: Path):
        (tmp_path / "out" / "art").mkdir(parents=True)
        (tmp_path / "out" / "art" / "a.png").write_bytes(PICTURE)
        assert main(["build", str(scene), "-o", "out/", "--quiet"]) == 0
        assert (tmp_path / "out" / "art" / "b.png").read_bytes() == OTHER

    def test_beside_the_document_none_is_copied_and_each_still_links(self, scene: Path):
        assert main(["build", str(scene), "--quiet"]) == 0
        assert sorted(p.name for p in (scene.parent / "art").iterdir()) == ["a.png", "b.png"]
