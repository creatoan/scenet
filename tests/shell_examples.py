"""Run the `bash` examples in the documentation, the `scenet` lines of them.

`docs/reference/cli.md` is the specification, and an example in it that stopped working
would misinform a reader without failing anything. So every documented `scenet build`,
`check`, `schema` and `--version` line is run, in-process through
:func:`scenet.cli.main`, inside a temporary copy of `examples/`, and must exit 0 without
a traceback.

- `scenet mcp` lines are parsed and not run: a server runs until its client leaves.
- `pip`, `pipx`, `uv`, `uvx`, `git`, `gh`, `cp`, `claude`, `wsl` and `ulimit` lines never
  run. They install, publish, reach the network or set limits on the reader's shell, and are
  about the reader's machine, not Scenet.
- A heredoc's body is skipped with its command.

A block that needs a file the reader creates along the way -- the tutorial's
`hello.panel.yaml` -- is marked `<!--- skip: next -->` in the Markdown.
"""

import contextlib
import io
import re
import shlex
import shutil
import tempfile
from pathlib import Path

from sybil import Example

from scenet.cli import build_parser, main

__all__ = ["run_bash_block"]

ROOT = Path(__file__).resolve().parents[1]

#: Programs whose lines are documentation for the reader's shell, never run here.
NEVER_RUN = frozenset({"pip", "pipx", "uv", "uvx", "git", "gh", "cp", "claude", "wsl", "ulimit"})

# `VAR=value command ...`: an environment assignment in front of a command.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
# `<<'END'` or `<<END`: the start of a heredoc, and the word that ends it.
_HEREDOC = re.compile(r"<<-?\s*'?(\w+)'?")


def _commands(source: str) -> list[list[str]]:
    """The `scenet` command lines of a block, split as a shell would, heredocs dropped."""
    commands: list[list[str]] = []
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
        commands.append(words[1:])
    return commands


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


def _run(argv: list[str], cwd: Path) -> None:
    if argv[:1] == ["mcp"]:
        build_parser().parse_args(argv)
        return
    argv, redirect = _expand(argv, cwd)
    stdout = io.StringIO()
    with contextlib.chdir(cwd), contextlib.redirect_stdout(stdout):
        try:
            status = main(argv)
        except SystemExit as exc:  # `--version` exits through argparse
            status = exc.code if isinstance(exc.code, int) else 1
    if redirect is not None:
        redirect.write_text(stdout.getvalue(), encoding="utf-8")
    assert status == 0, f"`scenet {shlex.join(argv)}` exited {status}"


def run_bash_block(example: Example) -> None:
    """Sybil evaluator: run each `scenet` line of a `bash` block in a copy of examples/."""
    commands = _commands(str(example.parsed))
    if not commands:
        return
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        # The reference names `examples/duel.panel.yaml`; a how-to, written as if from
        # the folder holding the reader's documents, names `duel.panel.yaml`. Both work.
        shutil.copytree(ROOT / "examples", cwd / "examples")
        for document in (ROOT / "examples").iterdir():
            if document.is_file():
                shutil.copy(document, cwd / document.name)
        for argv in commands:
            _run(argv, cwd)
