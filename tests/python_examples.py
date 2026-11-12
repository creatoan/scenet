"""Run the Python track's examples the way a reader runs them: as a script that prints (#322).

The developer's track, under `docs/tutorial/python/`, shows complete programs and what they
print. So each of its `python` blocks:

- **runs as a script of its own**, in a namespace that holds `__name__` and nothing else,
  as a file a reader saved would -- the rule #317 set for every block of the documentation;
- **runs in a folder that holds what the reader has made by then**: every file a block
  above it on the page showed under a file name, and the gallery's examples, pictures,
  fonts and puppets, as :func:`tests.shell_examples.workspace` lays them out for a `bash`
  block. What it writes goes there too, and is gone when it ends;
- **prints exactly what the page says it prints**: the `text` block right after it, or
  nothing when there is none.

:class:`TrackPythonCodeBlockParser` is the Python parser `conftest.py` gives Sybil: on a
page of the track it runs blocks so, and anywhere else it is
:class:`FreshPythonCodeBlockParser <tests.doc_examples.FreshPythonCodeBlockParser>`.
"""

import contextlib
import io
import tempfile
from collections.abc import Iterator
from pathlib import Path

from sybil import Document, Example, Region

from tests.doc_examples import FreshPythonCodeBlockParser, fences
from tests.shell_examples import Transcript, outputs, workspace

__all__ = [
    "TRACK",
    "TrackPythonCodeBlockParser",
    "in_the_track",
    "run_python",
    "run_python_block",
    "scripts",
]

ROOT = Path(__file__).resolve().parents[1]

#: The developer's track: a page of it is a chapter, or the track's index.
TRACK = ROOT / "docs" / "tutorial" / "python"


def in_the_track(path: Path) -> bool:
    """Whether a page is one of the track's."""
    return path.resolve().parent == TRACK


def scripts(page: Path) -> list[Transcript]:
    """Each `python` block of a page, with what it prints: the `text` block after it, or ``""``."""
    shown = {found.line: found for found in outputs(page, "python")}
    return [
        shown.get(fence.line, Transcript(page, fence.line, fence.text, ""))
        for fence in fences(page)
        if fence.language == "python"
    ]


def run_python(source: str, page: Path, line: int) -> str:
    """What a block prints, run as a script in a folder holding what the page made so far."""
    printed = io.StringIO()
    code = compile(source, f"{page.name}:{line}", "exec")
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        workspace(cwd, page, line)
        with contextlib.chdir(cwd), contextlib.redirect_stdout(printed):
            exec(code, {"__name__": "__main__"})  # noqa: S102 -- the documentation's own example
    return printed.getvalue()


def run_python_block(example: Example) -> None:
    """Sybil evaluator: run a block of the track and compare what it prints with its page."""
    page = Path(example.path)
    (shown,) = [found for found in scripts(page) if found.line == example.line]
    printed = run_python(str(example.parsed), page, example.line)
    assert printed == shown.output, f"{shown.where} printed:\n{printed}"


class TrackPythonCodeBlockParser(FreshPythonCodeBlockParser):
    """Python blocks: a page of the track's run as scripts, any other page's each alone."""

    def __call__(self, document: Document) -> Iterator[Region]:
        if not in_the_track(Path(document.path)):
            yield from super().__call__(document)
            return
        for region in self.codeblock_parser(document):
            region.evaluator = run_python_block
            yield region
