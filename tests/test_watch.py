"""Tests for dependency tracking and watch mode."""

import shutil
from collections.abc import Callable
from pathlib import Path

import fonts.ttf

from scenet import cli
from scenet.pipeline import compile_book_file
from scenet.watch import _nearest_existing_directory, snapshot, watch_loop
from tests.images import contract, png

SEMIBOLD = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]

PANEL = """cast:
  alice: {reference: alice}
script:
  - say: {by: alice, text: Hello}
"""


def test_compiler_reports_files_it_reads(tmp_path: Path) -> None:
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    dependencies: set[Path] = set()

    compile_book_file(source, dependencies=dependencies)

    assert source.resolve() in dependencies
    assert any(path.name == "alice.puppet.yaml" for path in dependencies)
    assert any(path.is_dir() and path.name == "library" for path in dependencies)


def test_watch_loop_rebuilds_again_after_a_failed_build() -> None:
    dependencies = {Path("source.panel.yaml")}
    state = {"revision": 0}
    calls: list[int] = []

    def wait(_interval: float, _dependencies: set[Path]) -> None:
        state["revision"] += 1

    def rebuild() -> int:
        calls.append(state["revision"])
        return 1 if len(calls) == 1 else 0

    watch_loop(
        dependencies,
        rebuild,
        wait=wait,
        take_snapshot=lambda _paths: state["revision"],
        debounce=0,
        max_iterations=2,
    )

    assert calls == [1, 2]


def test_watch_build_matches_regular_build(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    assert cli.main(["build", str(source), "--quiet"]) == 0
    regular = source.with_name("watch.svg").read_bytes()

    source.with_name("watch.svg").unlink()

    def no_watch(_dependencies: set[Path], _rebuild: Callable[[], object]) -> None:
        return None

    monkeypatch.setattr(cli, "watch_loop", no_watch)
    assert cli.main(["build", str(source), "--watch", "--quiet"]) == 0
    assert source.with_name("watch.svg").read_bytes() == regular


def test_snapshot_detects_content_and_directory_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    dependencies = {source, tmp_path}
    before = snapshot(dependencies)
    source.write_text("two", encoding="utf-8")
    assert snapshot(dependencies) != before


def test_watch_loop_debounces_quick_writes() -> None:
    dependencies = {Path("source.panel.yaml")}
    state = {"revision": 0, "ticks": 0}
    calls: list[int] = []

    def wait(_interval: float, _dependencies: set[Path]) -> None:
        state["ticks"] += 1
        if state["ticks"] in (1, 3):
            state["revision"] += 1

    def clock() -> float:
        return state["ticks"] * 0.1

    watch_loop(
        dependencies,
        lambda: calls.append(state["revision"]),
        wait=wait,
        take_snapshot=lambda _paths: state["revision"],
        clock=clock,
        debounce=0.3,
        interval=0.1,
        max_iterations=1,
    )

    assert calls == [2]


def test_watch_loop_does_not_rebuild_without_changes() -> None:
    calls: list[int] = []
    watch_loop(
        {Path("source.panel.yaml")},
        lambda: calls.append(1),
        wait=lambda _interval, _dependencies: None,
        take_snapshot=lambda _paths: "constant-snapshot",
        debounce=0,
        max_iterations=3,
    )
    assert calls == []


def test_watch_loop_keeps_watching_dependencies_after_rebuild() -> None:
    dependencies = {Path("source.panel.yaml"), Path("font.ttf")}
    state = {"revision": 0}
    calls: list[int] = []

    def wait(_interval: float, _dependencies: set[Path]) -> None:
        state["revision"] += 1

    watch_loop(
        dependencies,
        lambda: calls.append(state["revision"]),
        wait=wait,
        take_snapshot=lambda _paths: state["revision"],
        clock=lambda: state["revision"] * 1.0,
        debounce=0,
        max_iterations=2,
    )

    assert calls == [1, 2]
    assert Path("font.ttf") in dependencies


def test_nearest_existing_directory_handles_missing_parent(tmp_path: Path) -> None:
    missing = tmp_path / "art" / "x.png"
    assert _nearest_existing_directory(missing) == tmp_path.resolve()


def test_watch_survives_broken_then_fixed_document(tmp_path: Path, monkeypatch) -> None:
    """A failed build does not end the watch; a fixed document produces a fresh SVG."""
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    assert cli.main(["build", str(source), "--quiet"]) == 0
    good_svg = source.with_name("watch.svg").read_bytes()
    source.with_name("watch.svg").unlink()

    def fake_watch_loop(
        dependencies: set[Path],
        rebuild: Callable[[], object],
    ) -> None:
        source.write_text("not: valid: yaml: {", encoding="utf-8")
        rebuild()
        # Delete the SVG just before the last rebuild so the check proves a fresh write
        source.with_name("watch.svg").unlink()
        source.write_text(PANEL, encoding="utf-8")
        rebuild()
        assert source.with_name("watch.svg").read_bytes() == good_svg

    monkeypatch.setattr(cli, "watch_loop", fake_watch_loop)
    result = cli.main(["build", str(source), "--watch", "--quiet"])
    assert result == 0


def test_watch_survives_non_scenet_exception(tmp_path: Path, monkeypatch) -> None:
    """An OSError during a rebuild does not end the watch."""
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")

    calls: list[int] = []

    def fake_watch_loop(
        dependencies: set[Path],
        rebuild: Callable[[], object],
    ) -> None:
        for _ in range(2):
            calls.append(1)
            rebuild()

    original_compile = cli.compile_book_file

    call_count = 0

    def patched_compile(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # second call (first rebuild) raises OSError
            raise OSError("disk full")
        return original_compile(*args, **kwargs)

    monkeypatch.setattr(cli, "watch_loop", fake_watch_loop)
    monkeypatch.setattr("scenet.cli.compile_book_file", patched_compile)

    # Should not raise; the watch continues
    result = cli.main(["build", str(source), "--watch", "--quiet"])
    assert result == 0
    assert len(calls) == 2


def test_watch_keeps_dependencies_after_failed_build(tmp_path: Path, monkeypatch) -> None:
    """After a failed build, the old dependency set is retained."""
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")

    captured_deps: list[set[Path]] = []
    original_compile = cli.compile_book_file
    call_count = 0

    def patched_compile(*args, dependencies=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("write failed")
        return original_compile(*args, dependencies=dependencies, **kwargs)

    def fake_watch_loop(
        dependencies: set[Path],
        rebuild: Callable[[], object],
    ) -> None:
        # Record deps before first rebuild
        captured_deps.append(set(dependencies))
        rebuild()  # fails with OSError
        # Deps should still contain what the initial build found
        captured_deps.append(set(dependencies))

    monkeypatch.setattr(cli, "watch_loop", fake_watch_loop)
    monkeypatch.setattr("scenet.cli.compile_book_file", patched_compile)

    cli.main(["build", str(source), "--watch", "--quiet"])

    # The dependency set passed to watch_loop initially has the source and puppets
    assert source.resolve() in captured_deps[0]
    assert any(p.name == "alice.puppet.yaml" for p in captured_deps[0])
    # After the failed rebuild, it still includes those same dependencies
    assert captured_deps[0] <= captured_deps[1]


def test_watch_triggers_on_right_files(tmp_path: Path) -> None:
    """The compiler records a font, a picture and an artwork contract that a document names."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    font_file = fonts_dir / "Lettering-Regular.ttf"
    shutil.copy(SEMIBOLD, font_file)

    art_dir = tmp_path / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    img_file = art_dir / "p.png"
    img_file.write_bytes(png(900, 600))
    contract_file = art_dir / "p.art.yaml"
    contract_file.write_bytes(
        contract(
            (900, 600),
            figures={"ana": {"face": {"center": [250, 180], "radius": 50}, "mouth": [255, 210]}},
        )
    )

    doc = (
        "panel: {size: [1200, 600]}\n"
        "lettering: {font: fonts/Lettering-Regular.ttf}\n"
        "cast: {ANA: {figure: ana}}\n"
        "setting: {image: art/p.png}\n"
        "script: [{say: {by: ANA, text: Hello}}]\n"
    )
    source = tmp_path / "source.panel.yaml"
    source.write_text(doc, encoding="utf-8")

    deps: set[Path] = set()
    compile_book_file(source, dependencies=deps)

    assert source.resolve() in deps
    assert font_file.resolve() in deps
    assert img_file.resolve() in deps
    assert contract_file.resolve() in deps


def test_watch_deleted_then_restored_source_rebuilds(tmp_path: Path, monkeypatch) -> None:
    """A deleted then restored source file triggers a rebuild."""
    source = tmp_path / "watch.panel.yaml"
    source.write_text(PANEL, encoding="utf-8")
    assert cli.main(["build", str(source), "--quiet"]) == 0
    good_svg = source.with_name("watch.svg").read_bytes()
    source.with_name("watch.svg").unlink()

    def fake_watch_loop(
        dependencies: set[Path],
        rebuild: Callable[[], object],
    ) -> None:
        source.unlink()
        rebuild()
        assert source.resolve() in dependencies
        source.with_name("watch.svg").unlink()
        source.write_text(PANEL, encoding="utf-8")
        rebuild()
        assert source.with_name("watch.svg").read_bytes() == good_svg

    monkeypatch.setattr(cli, "watch_loop", fake_watch_loop)
    result = cli.main(["build", str(source), "--watch", "--quiet"])
    assert result == 0
