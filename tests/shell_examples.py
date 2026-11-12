"""Run the `bash` examples in the documentation, the `scenet` lines of them.

`docs/reference/cli.md` is the specification, and an example in it that stopped working
would misinform a reader without failing anything. So every documented `scenet build`,
`check`, `schema` and `--version` line is run, in-process through
:func:`scenet.cli.main`, inside a temporary copy of `examples/`, and must exit 0 without
a traceback.

- `scenet mcp` lines are parsed and not run: a server runs until its client leaves.
- A `scenet build --watch` line runs its first build, which must succeed, and then stops
  watching at once: watching runs until the reader presses Ctrl-C.
- `pip`, `pipx`, `uv`, `uvx`, `git`, `gh`, `cp`, `claude`, `wsl` and `ulimit` lines never
  run. They install, publish, reach the network or set limits on the reader's shell, and are
  about the reader's machine, not Scenet.
- A heredoc's body is skipped with its command.
- A line that ends on `# exits 1` must exit 1 instead: a chapter of the tour shows
  `scenet check` failing on a mistake, as a reader's terminal would.

A block that names a file the reader creates along the way -- the tutorial's
`hello.panel.yaml` -- finds it: every block above it on the page whose caption is a file
name is written there first, the latest one of each name winning, as a reader saving each
version in turn would have it. The gallery's pictures, fonts and puppets are there too, as
the playground writes them beside every document it opens.
"""

import contextlib
import io
import itertools
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple
from unittest import mock

from markdown_it import MarkdownIt
from sybil import Example

from scenet.cli import build_parser, main
from tests.doc_examples import fences, file_named

__all__ = [
    "Transcript",
    "commands",
    "outputs",
    "run_bash_block",
    "run_transcript",
    "transcripts",
    "workspace",
]

ROOT = Path(__file__).resolve().parents[1]

#: Programs whose lines are documentation for the reader's shell, never run here.
NEVER_RUN = frozenset({"pip", "pipx", "uv", "uvx", "git", "gh", "cp", "claude", "wsl", "ulimit"})

# `VAR=value command ...`: an environment assignment in front of a command.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
# `<<'END'` or `<<END`: the start of a heredoc, and the word that ends it.
_HEREDOC = re.compile(r"<<-?\s*'?(\w+)'?")
# `# exits 1` at the end of a line: the status the command is shown exiting with.
_EXITS = re.compile(r"#\s*exits (\d+)\s*$")


class Command(NamedTuple):
    """A documented `scenet` line: its arguments, and the status it is shown exiting with."""

    words: list[str]
    status: int


def commands(source: str) -> list[Command]:
    """The `scenet` command lines of a block, split as a shell would, heredocs dropped."""
    found: list[Command] = []
    lines = iter(source.splitlines())
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        heredoc = _HEREDOC.search(line)
        if heredoc:
            for body in lines:
                if body.strip() == heredoc.group(1):
                    break
        words = shlex.split(line, comments=True)
        while words and _ASSIGNMENT.match(words[0]):
            words = words[1:]
        if not words or words[0] in NEVER_RUN:
            continue
        assert words[0] == "scenet", f"a documented command this suite cannot run: {line!r}"
        exits = _EXITS.search(line)
        found.append(Command(words[1:], int(exits.group(1)) if exits else 0))
    return found


def _expand(words: list[str], cwd: Path) -> tuple[list[str], Path | None]:
    """Expand globs as a shell would, and take a trailing `> file` as a redirect."""
    redirect: Path | None = None
    if len(words) >= 2 and words[-2] == ">":
        redirect = cwd / words[-1]
        words = words[:-2]
    expanded: list[str] = []
    for word in words:
        if any(mark in word for mark in "*?["):
            matches = sorted(path.relative_to(cwd).as_posix() for path in cwd.glob(word))
            assert matches, f"{word!r} matches no file in examples/"
            expanded.extend(matches)
        else:
            expanded.append(word)
    return expanded, redirect


def _stop_watching(*_args: object, **_kwargs: object) -> None:
    """A watch loop that returns at once, as if Ctrl-C came right after the first build."""


def _run(argv: list[str], cwd: Path, expected: int = 0) -> None:
    if argv[:1] == ["mcp"]:
        build_parser().parse_args(argv)
        return
    argv, redirect = _expand(argv, cwd)
    stdout = io.StringIO()
    # Watching runs until Ctrl-C; the first build is what the example shows working.
    watching = mock.patch("scenet.cli.watch_loop", _stop_watching) if "--watch" in argv else None
    with (
        contextlib.chdir(cwd),
        contextlib.redirect_stdout(stdout),
        watching or contextlib.nullcontext(),
    ):
        try:
            status = main(argv)
        except SystemExit as exc:  # `--version` exits through argparse
            status = exc.code if isinstance(exc.code, int) else 1
    if redirect is not None:
        redirect.write_text(stdout.getvalue(), encoding="utf-8")
    assert status == expected, f"`scenet {shlex.join(argv)}` exited {status}, not {expected}"


def workspace(cwd: Path, page: Path, line: int) -> None:
    """Fill `cwd` with what a command on line `line` of `page` may name.

    - `examples/`, and each document beside it: the reference names
      `examples/duel.panel.yaml`, and a how-to, written as if from the folder holding the
      reader's documents, names `duel.panel.yaml`. Both work.
    - The gallery's folders of pictures, fonts and puppets, which its documents name.
    - Every file the page has shown so far, by the file name its block's caption gives.
    """
    shutil.copytree(ROOT / "examples", cwd / "examples")
    for document in (ROOT / "examples").iterdir():
        if document.is_file():
            shutil.copy(document, cwd / document.name)
    gallery = ROOT / "examples" / "gallery"
    for folder in sorted(gallery.iterdir()):
        if folder.is_dir():
            shutil.copytree(folder, cwd / folder.name, dirs_exist_ok=True)
    for fence in fences(page):
        name = file_named(fence)
        if fence.line < line and name is not None:
            path = cwd / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fence.text, encoding="utf-8", newline="\n")


def run_bash_block(example: Example) -> None:
    """Sybil evaluator: run each `scenet` line of a `bash` block where its page's files are."""
    found = commands(str(example.parsed))
    if not found:
        return
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        workspace(cwd, Path(example.path), example.line)
        for command in found:
            _run(command.words, cwd, command.status)


class Transcript(NamedTuple):
    """A block of a page followed by the `text` block that shows what it prints."""

    page: Path
    #: The line its fence opens on, counted from 1.
    line: int
    source: str
    output: str

    @property
    def where(self) -> str:
        """`page:line`, for a test id."""
        return f"{self.page.stem}:{self.line}"


def outputs(page: Path, language: str) -> list[Transcript]:
    """Each `language` block of a page that a `text` block follows, with nothing between.

    That `text` block is what the first one prints: a page shows a command, or a script, and
    then its output, as a reader's terminal would.
    """
    text = page.read_text(encoding="utf-8")
    lines = text.splitlines()
    tokens = [
        token
        for token in MarkdownIt("commonmark").parse(text)
        if token.type == "fence" and token.map is not None
    ]
    found: list[Transcript] = []
    for before, after in itertools.pairwise(tokens):
        assert before.map is not None
        assert after.map is not None
        if before.info.strip() == language and after.info.strip() == "text":
            between = lines[before.map[1] : after.map[0]]
            if all(not line.strip() for line in between):
                found.append(Transcript(page, before.map[0] + 1, before.content, after.content))
    return found


def transcripts(pages: list[Path]) -> list[Transcript]:
    """Each `bash` block of the pages that a `text` block, its output, follows."""
    return [found for page in pages for found in outputs(page, "bash")]


def run_transcript(transcript: Transcript) -> str:
    """What a transcript's `scenet` lines print, run where its page's files are.

    Each line must exit with the status it is shown exiting with.
    """
    printed = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        workspace(cwd, transcript.page, transcript.line)
        for command in commands(transcript.source):
            with (
                contextlib.chdir(cwd),
                contextlib.redirect_stdout(printed),
                contextlib.redirect_stderr(printed),
            ):
                status = main(command.words)
            assert status == command.status, shlex.join(command.words)
    return printed.getvalue()
