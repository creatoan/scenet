"""Tests for dependency tracking and watch mode."""

import os
import shutil
import sys
import types
from collections.abc import Callable, Generator
from pathlib import Path

import fonts.ttf
import pytest

from scenet import cli
from scenet.pipeline import compile_book_file
from scenet.watch import WatchSession, _nearest_existing_directory, snapshot, watch_loop
from tests.images import contract, png

SEMIBOLD = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[missing-attribute]  # pyright: ignore[reportAttributeAccessIssue]

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


# One watcher for the whole watch, and no rereading a file that has not moved (#266).
# `watchfiles` is replaced by a fake that counts the watchers opened and closed, and the
# session's reads, sleeps and wall clock by stand-ins: no test here waits on the real clock.

SECOND = 1_000_000_000
LONG_AGO = 1_700_000_000 * SECOND  # a whole number of NTFS's 100 ns ticks


class FakeWatchfiles(types.ModuleType):
    """Stands in for `watchfiles`, counting the watchers a watch opens and closes."""

    def __init__(self) -> None:
        super().__init__("watchfiles")
        self.opened = 0
        self.closed = 0
        self.calls: list[tuple[tuple[Path, ...], dict[str, object]]] = []
        self.on_next: Callable[[], None] = lambda: None
        self.fail: str | None = None

    def watch(
        self, *paths: Path | str, **options: object
    ) -> Generator[set[tuple[int, str]], None, None]:
        # Like the real one, the watcher opens on the first `next`, not on the call.
        self.calls.append((tuple(Path(path) for path in paths), options))
        self.opened += 1
        try:
            if self.fail == "missing":
                raise FileNotFoundError("Input watch path is neither a file nor a directory")
            if self.fail == "internal":
                raise RuntimeError("watcher error")
            if self.fail == "exhausted":
                return
            while True:
                self.on_next()
                yield set()
        finally:
            self.closed += 1


class CountedReads:
    """A session's file reader that remembers every file it read."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, path: Path) -> bytes:
        self.paths.append(path)
        return path.read_bytes()


@pytest.fixture
def fake_watchfiles(monkeypatch: pytest.MonkeyPatch) -> FakeWatchfiles:
    fake = FakeWatchfiles()
    monkeypatch.setitem(sys.modules, "watchfiles", fake)
    return fake


def pin(path: Path, mtime_ns: int = LONG_AGO) -> int:
    """Set a file's modification time, and return it as the file system stored it."""
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path.stat().st_mtime_ns


def old_font(tmp_path: Path) -> Path:
    font = tmp_path / "font.ttf"
    font.write_bytes(b"one")
    pin(font)
    return font


def test_one_watcher_serves_every_wait(tmp_path: Path, fake_watchfiles: FakeWatchfiles) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    sleeps: list[float] = []

    with WatchSession(sleep=sleeps.append) as session:
        for _ in range(3):
            session.wait(0.1, {source})
        assert fake_watchfiles.opened == 1
        assert fake_watchfiles.closed == 0
    assert fake_watchfiles.closed == 1

    [(paths, options)] = fake_watchfiles.calls
    assert paths == (tmp_path.resolve(),)
    assert options["recursive"] is False
    assert sleeps == []


def test_a_new_dependency_set_opens_a_new_watcher(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles
) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    font = tmp_path / "fonts" / "Lettering.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font")
    dependencies = {source}

    with WatchSession() as session:
        session.wait(0.1, dependencies)
        session.wait(0.1, dependencies)
        dependencies.add(font)
        session.wait(0.1, dependencies)
        session.wait(0.1, dependencies)
        assert fake_watchfiles.opened == 2
        assert fake_watchfiles.closed == 1

    assert fake_watchfiles.calls[1][0] == tuple(
        sorted({tmp_path.resolve(), font.parent.resolve()}, key=str)
    )


def test_a_folder_created_for_a_missing_file_moves_the_watcher(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles
) -> None:
    picture = tmp_path / "art" / "p.png"

    with WatchSession() as session:
        session.wait(0.1, {picture})
        picture.parent.mkdir()
        session.wait(0.1, {picture})

    assert [paths for paths, _options in fake_watchfiles.calls] == [
        (tmp_path.resolve(),),
        (picture.parent.resolve(),),
    ]


def test_the_watcher_wakes_only_for_what_the_snapshot_looks_at(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles
) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    library = tmp_path / "library"
    (library / "sub").mkdir(parents=True)
    picture = tmp_path / "art" / "p.png"

    with WatchSession() as session:
        session.wait(0.1, {source, library, picture})

    relevant = fake_watchfiles.calls[0][1]["watch_filter"]
    assert callable(relevant)
    for path in (source, library / "alice.puppet.yaml", tmp_path / "art"):
        assert relevant(1, str(path)) is True, path
    for path in (tmp_path / "notes.txt", library / "sub" / "deep.yaml"):
        assert relevant(1, str(path)) is False, path


def test_watch_loop_opens_a_watcher_again_only_when_a_rebuild_reads_new_files(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles
) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    font = tmp_path / "fonts" / "Lettering.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font")
    dependencies = {source}
    waits: list[int] = []
    rebuilds: list[int] = []

    def edit() -> None:
        waits.append(1)
        if len(waits) == 2:
            source.write_text("two", encoding="utf-8")

    def rebuild() -> None:
        rebuilds.append(len(waits))
        dependencies.add(font)

    fake_watchfiles.on_next = edit
    watch_loop(dependencies, rebuild, debounce=0, max_iterations=4)

    assert rebuilds == [2]
    assert fake_watchfiles.opened == 2
    assert fake_watchfiles.closed == 2


def test_ctrl_c_during_a_watch_leaves_no_watcher_open(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles
) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")

    def edit() -> None:
        source.write_text("two", encoding="utf-8")

    def rebuild() -> None:
        raise KeyboardInterrupt

    fake_watchfiles.on_next = edit
    with pytest.raises(KeyboardInterrupt):
        watch_loop({source}, rebuild, debounce=0, max_iterations=3)

    assert fake_watchfiles.opened == 1
    assert fake_watchfiles.closed == 1


def test_an_unchanged_file_is_read_once(tmp_path: Path) -> None:
    font = old_font(tmp_path)
    reads = CountedReads()
    session = WatchSession(now=lambda: LONG_AGO + 60 * SECOND, read=reads)

    first = session.snapshot({font})
    for _ in range(3):
        assert session.snapshot({font}) == first

    assert reads.paths == [font.resolve()]


def test_a_touched_file_is_read_again_and_is_no_change(tmp_path: Path) -> None:
    font = old_font(tmp_path)
    reads = CountedReads()
    session = WatchSession(now=lambda: LONG_AGO + 60 * SECOND, read=reads)

    first = session.snapshot({font})
    pin(font, LONG_AGO + SECOND)
    assert session.snapshot({font}) == first
    assert session.snapshot({font}) == first

    assert len(reads.paths) == 2


def test_a_file_rewritten_to_the_same_size_is_a_change(tmp_path: Path) -> None:
    font = old_font(tmp_path)
    reads = CountedReads()
    session = WatchSession(now=lambda: LONG_AGO + 60 * SECOND, read=reads)

    first = session.snapshot({font})
    font.write_bytes(b"two")
    pin(font, LONG_AGO + SECOND)

    assert session.snapshot({font}) != first
    assert len(reads.paths) == 2


def test_a_file_rewritten_within_one_timestamp_tick_is_read_again(tmp_path: Path) -> None:
    """Git's racy clean: a stat too close to the snapshot is not trusted yet."""
    font = tmp_path / "font.ttf"
    font.write_bytes(b"one")
    written = pin(font)
    clock = {"now": written}
    reads = CountedReads()
    session = WatchSession(now=lambda: clock["now"], read=reads)

    first = session.snapshot({font})
    # Same size and same timestamp, as on FAT or a network share: only the content says.
    font.write_bytes(b"two")
    pin(font, written)
    second = session.snapshot({font})
    assert second != first
    assert len(reads.paths) == 2

    clock["now"] = written + 3 * SECOND
    assert session.snapshot({font}) == second
    assert len(reads.paths) == 3
    assert session.snapshot({font}) == second
    assert len(reads.paths) == 3


def test_without_watchfiles_a_wait_sleeps_and_the_snapshot_still_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "watchfiles", None)
    font = old_font(tmp_path)
    sleeps: list[float] = []
    reads = CountedReads()

    with WatchSession(
        now=lambda: LONG_AGO + 60 * SECOND, sleep=sleeps.append, read=reads
    ) as session:
        first = session.snapshot({font})
        for _ in range(3):
            session.wait(0.1, {font})
            assert session.snapshot({font}) == first

    assert sleeps == [0.1, 0.1, 0.1]
    assert reads.paths == [font.resolve()]


@pytest.mark.parametrize("failure", ["missing", "internal", "exhausted"])
def test_a_failed_watcher_falls_back_to_polling_until_the_dependencies_change(
    tmp_path: Path, fake_watchfiles: FakeWatchfiles, failure: str
) -> None:
    source = tmp_path / "source.panel.yaml"
    source.write_text("one", encoding="utf-8")
    font = tmp_path / "fonts" / "Lettering.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font")
    sleeps: list[float] = []
    fake_watchfiles.fail = failure

    with WatchSession(sleep=sleeps.append) as session:
        session.wait(0.1, {source})
        session.wait(0.1, {source})
        assert fake_watchfiles.opened == 1
        assert sleeps == [0.1, 0.1]

        fake_watchfiles.fail = None
        session.wait(0.1, {source, font})
        assert fake_watchfiles.opened == 2
        assert sleeps == [0.1, 0.1]
