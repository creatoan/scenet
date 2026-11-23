"""The fuzzing oracle: for any bytes, Scenet answers with findings or a `ScenetError` (#378).

One oracle, shared by every engine that feeds it: the short Hypothesis run on every pull
request (`fuzz/test_fuzz.py`), the weekly coverage-guided run (`fuzz/atheris_fuzz.py`), and
the replay of every input either ever found, in the ordinary suite
(`tests/test_fuzz_regressions.py`). An input fails the oracle when an entry point:

- raises anything but a :exc:`ScenetError <scenet.errors.ScenetError>`, the documented
  error of every entry point -- a `KeyError`, a `RecursionError`, a `MemoryError` alike;
- prints a traceback, or exits other than 0, 1 or 2, on the command line;
- takes longer than :data:`SECONDS`, or allocates more than :data:`MEMORY` at its peak.

Each entry point is one kind of input, read the way Scenet reads it: a panel or a scene, a
comic script, a puppet file and an artwork contract a document names, a Panel Core, a PNG or
JPEG picture and a font. The files a document names go in a mapping, as the MCP server and
the playground send them, so nothing here reads beyond the input.
"""

import contextlib
import io
import tempfile
import time
import tracemalloc
from collections.abc import Callable, Iterator
from pathlib import Path

from scenet.assets.contract import DEFAULT_LIBRARY_PATH
from scenet.cli import main
from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.pdf import printed_panels, render_pdf
from scenet.emit.svg import render
from scenet.errors import ScenetError
from scenet.pipeline import Book, compile_book, compile_script

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "examples" / "gallery"
#: Every input either engine found, replayed by the ordinary suite: one folder per entry point.
REGRESSIONS = Path(__file__).resolve().parent / "fuzz_regressions"

#: The most one input may take, generous for a slow runner: a real document takes well under
#: a second. Longer is a finding of its own, whatever the answer.
SECONDS = 30.0
#: The most memory one input may allocate at its peak.
MEMORY = 1024 * 2**20

#: A cast and a line, for the inputs that are a file a document names.
_CAST = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"


class OracleError(AssertionError):
    """An input the oracle refuses: what Scenet did that it may not."""


def _built(book: Book, *, pdf: bool = False, live_text: bool = False) -> None:
    """Draw everything a compiled document draws: each panel, and its print when asked."""
    for result in book.panels.values():
        render(result.core, fonts=result.fonts, embed=book.images, live_text=live_text)
    if pdf:
        render_pdf(
            book.pages,
            printed_panels(book.pages, {name: result.core for name, result in book.panels.items()}),
            fonts=book.fonts,
            images=book.images,
            live_text=live_text,
        )


def _on_the_command_line(data: bytes, suffix: str) -> int:
    """`scenet check` on the bytes as a file: no traceback, and a documented status."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"fuzz{suffix}"
        path.write_bytes(data)
        said = io.StringIO()
        with contextlib.redirect_stderr(said), contextlib.redirect_stdout(io.StringIO()):
            status = main(["check", "--quiet", str(path)])
    if "Traceback" in said.getvalue() or status not in (0, 1, 2):
        raise OracleError(f"`scenet check` exited {status}:\n{said.getvalue()}")
    return status


def _document(data: bytes, suffix: str) -> None:
    """A panel, a scene or a script: checked, and compiled and drawn when it checks clean."""
    if _on_the_command_line(data, suffix) != 0:
        return
    text = data.decode("utf-8")
    book = compile_script(text) if suffix == ".script" else compile_book(text)
    _built(book)


def _named(
    document: str, files: dict[str, bytes], *, pdf: bool = False, live_text: bool = False
) -> None:
    """A document naming a file it is sent with: checked, then compiled if it checks clean."""
    found = diagnose_source(document, base=files)
    if any(item.level == "error" for item in found):
        return
    _built(compile_book(document, base=files), pdf=pdf, live_text=live_text)


def panel(data: bytes) -> None:
    """A `*.panel.yaml` or `*.scene.yaml` document: YAML, or JSON, which YAML reads."""
    _document(data, ".panel.yaml")


def script(data: bytes) -> None:
    """A `*.script` comic script."""
    _document(data, ".script")


def puppet(data: bytes) -> None:
    """A puppet file a cast member names."""
    _named(
        "cast: {pip: {reference: puppets/p.puppet.yaml}}\nscript: [{say: {by: pip, text: Hi.}}]\n",
        {"puppets/p.puppet.yaml": data},
    )


def contract(data: bytes) -> None:
    """An artwork contract, beside the gallery's picture of three figures."""
    _named(
        "setting: {image: art/figures.png}\ncast: {ana: {figure: ana}}\n"
        "script: [{say: {by: ana, text: Hi.}}]\n",
        {
            "art/figures.png": (GALLERY / "art" / "figures.png").read_bytes(),
            "art/figures.art.yaml": data,
        },
    )


def core(data: bytes) -> None:
    """A Panel Core, read back and drawn, as a hand-edited `.core.json` is."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    render(PanelCore.from_json(text))


def picture(data: bytes) -> None:
    """A picture to letter over, drawn into the SVG and the print PDF."""
    _named(f"setting: {{image: art/a.png}}\n{_CAST}", {"art/a.png": data}, pdf=True)


def font(data: bytes) -> None:
    """A lettering face, in print as live text too, which subsets it to embed it."""
    _named(
        f"lettering: {{font: fonts/a.ttf}}\n{_CAST}",
        {"fonts/a.ttf": data},
        pdf=True,
        live_text=True,
    )


#: Each entry point by name: the name of its folder of regressions, and of its seeds.
ENTRY_POINTS: dict[str, Callable[[bytes], None]] = {
    "panel": panel,
    "script": script,
    "puppet": puppet,
    "contract": contract,
    "core": core,
    "picture": picture,
    "font": font,
}


def check(entry: str, data: bytes) -> None:
    """Feed one input to one entry point, and refuse anything the oracle does not allow.

    Args:
        entry: The entry point's name, a key of :data:`ENTRY_POINTS`.
        data: The input.

    Raises:
        OracleError: Scenet raised something other than a `ScenetError`, printed a
            traceback, took longer than :data:`SECONDS` or allocated more than
            :data:`MEMORY`. Its cause is what was raised, if anything.
    """
    started = time.monotonic()
    tracing = not tracemalloc.is_tracing()
    if tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        ENTRY_POINTS[entry](data)
    except ScenetError:
        pass
    except OracleError:
        raise
    except Exception as exc:
        raise OracleError(f"{entry}: {type(exc).__name__}: {exc}") from exc
    finally:
        _, peak = tracemalloc.get_traced_memory()
        if tracing:
            tracemalloc.stop()
    seconds = time.monotonic() - started
    if seconds > SECONDS:
        raise OracleError(f"{entry}: took {seconds:.1f} s, past the {SECONDS:g} s budget")
    if peak > MEMORY:
        raise OracleError(f"{entry}: allocated {peak / 2**20:.0f} MiB, past the budget")


#: What each entry point is seeded with: real inputs of its kind, which a mutation bends.
_SEEDS: dict[str, Callable[[], Iterator[Path]]] = {
    "panel": lambda: (
        path
        for path in sorted(GALLERY.iterdir())
        if path.name.endswith((".panel.yaml", ".scene.yaml"))
    ),
    "script": lambda: (path for path in sorted(GALLERY.iterdir()) if path.suffix == ".script"),
    "puppet": lambda: iter(
        [
            GALLERY / "puppets" / "pip.puppet.yaml",
            *sorted(DEFAULT_LIBRARY_PATH.glob("*.puppet.yaml")),
        ]
    ),
    "contract": lambda: iter([GALLERY / "art" / "figures.art.yaml"]),
    "core": lambda: iter(sorted((ROOT / "tests" / "golden" / "core").glob("*.core.json"))[:12]),
    "picture": lambda: iter(
        [
            GALLERY / "art" / "street.png",
            GALLERY / "art" / "harbour.jpg",
            GALLERY / "art" / "figures.png",
        ]
    ),
    "font": lambda: iter([GALLERY / "fonts" / "ComicNeue-Regular.ttf"]),
}


def seeds(entry: str) -> list[bytes]:
    """The real inputs an entry point is seeded with, as bytes."""
    return [path.read_bytes() for path in _SEEDS[entry]()]


def regressions() -> list[tuple[str, Path]]:
    """Every input kept in :data:`REGRESSIONS`, by its entry point."""
    return sorted(
        (folder.name, path)
        for folder in REGRESSIONS.iterdir()
        if folder.is_dir()
        for path in folder.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
