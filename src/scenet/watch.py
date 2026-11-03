"""Dependency-aware watch mode for the build command."""

import hashlib
import importlib
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, TracebackType

# A file's stat is trusted only once it is this much older than the snapshot that read it.
# Two seconds is FAT's timestamp resolution, the coarsest in common use: a file rewritten to
# the same size within one tick keeps its stat, so it is hashed again until that tick is
# surely over, as git does for a "racy clean" entry. A network share whose clock runs more
# than this behind ours can still hide such a rewrite.
_RACY_NS = 2_000_000_000

_EXHAUSTED = object()


@dataclass(frozen=True, slots=True)
class _Stamp:
    """What a snapshot learnt about a file: its stat, and the hash of the content it read."""

    mtime_ns: int
    size: int
    digest: bytes
    racy: bool


class WatchSession:
    """What one watch keeps between polls: a file watcher, and each file's stat and hash."""

    def __init__(
        self,
        *,
        now: Callable[[], int] = time.time_ns,
        sleep: Callable[[float], None] = time.sleep,
        read: Callable[[Path], bytes] = Path.read_bytes,
    ) -> None:
        """Start a session with no watcher open and nothing hashed yet.

        Args:
            now: The wall clock in nanoseconds, compared with modification times to decide
                whether a file's stat can be trusted yet. It decides a reread, nothing else.
            sleep: How a wait without a file watcher passes the time.
            read: How a file is read to be hashed.
        """
        self._now = now
        self._sleep = sleep
        self._read = read
        self._stamps: dict[Path, _Stamp] = {}
        self._imported = False
        self._watchfiles: ModuleType | None = None
        self._events: Generator[object, None, None] | None = None
        self._key: tuple[frozenset[Path], frozenset[Path], int] | None = None
        self._failed: tuple[frozenset[Path], frozenset[Path], int] | None = None

    def __enter__(self) -> "WatchSession":
        """Return the session itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the watcher, however the watch ended."""
        self.close()

    def snapshot(self, paths: set[Path]) -> tuple[tuple[str, object], ...]:
        """Return a stable fingerprint of tracked files and directories.

        A file is hashed again only when its size or modification time moved since the
        previous snapshot, or when its stat was then too recent to trust. The fingerprint
        holds the hash alone, so touching a file without changing it changes nothing.
        """
        now = self._now()
        stamps: dict[Path, _Stamp] = {}
        result: list[tuple[str, object]] = []
        for path in sorted((item.resolve() for item in paths), key=str):
            try:
                if path.is_dir():
                    children = []
                    for child in sorted(path.iterdir(), key=lambda item: item.name):
                        try:
                            stat = child.stat()
                            children.append(
                                (child.name, child.is_dir(), stat.st_mtime_ns, stat.st_size)
                            )
                        except OSError:
                            children.append((child.name, "unavailable"))
                    result.append((str(path), ("directory", tuple(children))))
                else:
                    stamp = self._stamp(path, now)
                    stamps[path] = stamp
                    result.append((str(path), ("file", stamp.digest)))
            except OSError:
                result.append((str(path), ("missing",)))
        self._stamps = stamps
        return tuple(result)

    def _stamp(self, path: Path, now: int) -> _Stamp:
        stat = path.stat()
        known = self._stamps.get(path)
        if (
            known is not None
            and not known.racy
            and (known.mtime_ns, known.size) == (stat.st_mtime_ns, stat.st_size)
        ):
            return known
        digest = hashlib.sha256(self._read(path)).digest()
        racy = now - stat.st_mtime_ns < _RACY_NS
        return _Stamp(stat.st_mtime_ns, stat.st_size, digest, racy)

    def wait(self, interval: float, dependencies: set[Path]) -> None:
        """Wait for a filesystem event, or for `interval` seconds at most.

        With `watchfiles` installed, one watcher serves every wait until the dependencies,
        or the folders they are watched from, change. It watches each folder without its
        subfolders, as the snapshot looks no deeper. Without `watchfiles`, or once a watcher
        failed for these dependencies, a wait sleeps and the next snapshot decides.
        """
        paths = frozenset(path.resolve() for path in dependencies)
        roots = frozenset(_nearest_existing_directory(path) for path in paths)
        timeout = max(50, int(interval * 1000))
        key = (paths, roots, timeout)
        watchfiles = self._import_watchfiles() if roots else None
        if watchfiles is None or key == self._failed:
            self._sleep(interval)
            return

        events = self._events
        if events is None or key != self._key:
            self.close()
            opened: Generator[object, None, None] = watchfiles.watch(
                *sorted(roots, key=str),
                watch_filter=_relevant_to(paths),
                debounce=100,
                step=50,
                rust_timeout=timeout,
                yield_on_timeout=True,
                recursive=False,
            )
            self._events = events = opened
            self._key = key
        try:
            event = next(events, _EXHAUSTED)
        except (OSError, RuntimeError):
            # A folder removed before the watcher opened, or the watcher itself failing.
            event = _EXHAUSTED
        if event is _EXHAUSTED:
            self.close()
            self._failed = key
            self._sleep(interval)

    def close(self) -> None:
        """Close the file watcher, if one is open."""
        if self._events is not None:
            self._events.close()
        self._events = None
        self._key = None

    def _import_watchfiles(self) -> ModuleType | None:
        # Imported on the first wait, so that no other command pays for it.
        if not self._imported:
            self._imported = True
            try:
                self._watchfiles = importlib.import_module("watchfiles")
            except ImportError:
                self._watchfiles = None
        return self._watchfiles


def snapshot(paths: set[Path]) -> tuple[tuple[str, object], ...]:
    """Return a stable fingerprint of tracked files and directories, hashing every file."""
    return WatchSession().snapshot(paths)


def _nearest_existing_directory(path: Path) -> Path:
    """Find the nearest existing ancestor directory for a possibly missing path."""
    candidate = path if path.is_dir() else path.parent
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.resolve()


def _relevant_to(paths: frozenset[Path]) -> Callable[[object, str], bool]:
    """Keep the events a snapshot of `paths` can see.

    That is a dependency itself, a direct child of a dependency folder, or a folder on the
    way to a dependency, which may be the missing one a missing file waits for.
    """
    on_the_way = frozenset(parent for path in paths for parent in path.parents)

    def relevant(_change: object, raw_path: str) -> bool:
        path = Path(raw_path).resolve()
        return path in paths or path in on_the_way or path.parent in paths

    return relevant


def watch_loop(
    dependencies: set[Path],
    rebuild: Callable[[], object],
    *,
    interval: float = 0.1,
    debounce: float = 0.3,
    wait: Callable[[float, set[Path]], None] | None = None,
    take_snapshot: Callable[[set[Path]], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
    max_iterations: int | None = None,
) -> None:
    """Rebuild once dependencies have remained unchanged for the debounce window.

    `wait` and `take_snapshot` default to those of a :class:`WatchSession` made for this
    watch, which is closed when the watch ends, Ctrl-C included.
    """
    with WatchSession() as session:
        wait = session.wait if wait is None else wait
        take_snapshot = session.snapshot if take_snapshot is None else take_snapshot
        previous = take_snapshot(dependencies)
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            wait(interval, dependencies)
            current = take_snapshot(dependencies)
            if current != previous:
                previous = current
                stable_since = clock()
                while clock() - stable_since < debounce:
                    wait(interval, dependencies)
                    current = take_snapshot(dependencies)
                    if current != previous:
                        previous = current
                        stable_since = clock()
                rebuild()
                previous = take_snapshot(dependencies)
            iterations += 1
