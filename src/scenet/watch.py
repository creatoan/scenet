"""Dependency-aware watch mode for the build command."""

import hashlib
import importlib
import time
from collections.abc import Callable
from pathlib import Path


def snapshot(paths: set[Path]) -> tuple[tuple[str, object], ...]:
    """Return a stable fingerprint of tracked files and directories."""
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
                digest = hashlib.sha256(path.read_bytes()).digest()
                result.append((str(path), ("file", digest)))
        except OSError:
            result.append((str(path), ("missing",)))
    return tuple(result)


def _nearest_existing_directory(path: Path) -> Path:
    """Find the nearest existing ancestor directory for a possibly missing path."""
    candidate = path if path.is_dir() else path.parent
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.resolve()


def _wait(interval: float, dependencies: set[Path]) -> None:
    """Wait for a filesystem event, lazily using watchfiles when installed."""
    paths = {path.resolve() for path in dependencies}
    directories = {_nearest_existing_directory(path) for path in paths}
    if not directories:
        time.sleep(interval)
        return

    try:
        watch = importlib.import_module("watchfiles").watch
    except ImportError:
        time.sleep(interval)
        return

    def relevant(_change: object, raw_path: str) -> bool:
        path = Path(raw_path).resolve()
        return path in paths or any(
            path == directory or directory in path.parents for directory in directories
        )

    events = watch(
        *sorted(directories, key=str),
        watch_filter=relevant,
        debounce=100,
        step=50,
        rust_timeout=max(50, int(interval * 1000)),
        yield_on_timeout=True,
    )
    next(events, None)
    events.close()


def watch_loop(
    dependencies: set[Path],
    rebuild: Callable[[], object],
    *,
    interval: float = 0.1,
    debounce: float = 0.3,
    wait: Callable[[float, set[Path]], None] = _wait,
    take_snapshot: Callable[[set[Path]], object] = snapshot,
    clock: Callable[[], float] = time.monotonic,
    max_iterations: int | None = None,
) -> None:
    """Rebuild once dependencies have remained unchanged for the debounce window."""
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
