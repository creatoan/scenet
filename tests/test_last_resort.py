"""No traceback ever reaches a user (#377).

A document that will not compile is the author's to fix, and says why in one line. A file
that cannot be read or written is the system's say, and says which file and why in one
line. Ctrl-C stops the command and exits 130, as a shell expects. Anything else is a bug in
Scenet: one line saying so, where to report it, and the exception's type and message, with
exit 70 -- the traceback only when asked for, with `--traceback` or `SCENET_DEBUG=1`.
"""

import errno
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

import scenet.cli
import scenet.mcp
from scenet.cli import (
    EXIT_INTERNAL,
    EXIT_INTERRUPTED,
    ISSUES,
    _silence_stdout,
    describe_failure,
    main,
)
from scenet.errors import LayoutError, UnknownActorError
from scenet.mcp import build_server

PANEL = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"


@pytest.fixture
def panel(tmp_path: Path) -> Path:
    path = tmp_path / "duel.panel.yaml"
    path.write_text(PANEL, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's own `SCENET_DEBUG` must not change what these tests see."""
    monkeypatch.delenv("SCENET_DEBUG", raising=False)


def _raise(error: BaseException) -> Callable[..., Any]:
    def fail(*_args: object, **_kwargs: object) -> Any:
        raise error

    return fail


#: For each command, the function it calls into that a fault can be injected in, and the
#: arguments that reach it.
_ENTRY: dict[str, tuple[str, Callable[[Path, Path], list[str]]]] = {
    "build": ("compile_book_file", lambda source, _tmp: ["build", str(source)]),
    "check": ("diagnose_file", lambda source, _tmp: ["check", str(source)]),
    "schema": ("panel_schema", lambda _source, tmp: ["schema", "-o", str(tmp / "s.json")]),
}


def _inject(monkeypatch: pytest.MonkeyPatch, command: str, error: BaseException) -> None:
    if command == "mcp":
        monkeypatch.setattr(scenet.mcp, "serve", _raise(error))
    else:
        monkeypatch.setattr(scenet.cli, _ENTRY[command][0], _raise(error))


def _argv(command: str, source: Path, tmp_path: Path) -> list[str]:
    return ["mcp"] if command == "mcp" else _ENTRY[command][1](source, tmp_path)


COMMANDS = ("build", "check", "schema", "mcp")


class TestAnUnexpectedException:
    @pytest.mark.parametrize("command", COMMANDS)
    def test_is_one_line_naming_the_bug_and_exits_70(
        self,
        command: str,
        panel: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        _inject(monkeypatch, command, RuntimeError("the frobnicator\nfell over"))
        assert main(_argv(command, panel, tmp_path)) == EXIT_INTERNAL == 70
        err = capsys.readouterr().err
        assert "Traceback" not in err
        (line, hint) = err.splitlines()
        assert line == (
            "scenet: internal error (RuntimeError: the frobnicator fell over) -- this is a bug; "
            f"please report it at {ISSUES}"
        )
        assert "--traceback" in hint
        assert "SCENET_DEBUG=1" in hint

    @pytest.mark.parametrize(
        "error", [MemoryError(), RecursionError("maximum recursion depth exceeded"), KeyError("x")]
    )
    def test_even_running_out_of_memory_or_stack(
        self,
        error: BaseException,
        panel: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        _inject(monkeypatch, "build", error)
        assert main(["build", str(panel)]) == 70
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert f"internal error ({type(error).__name__}" in err

    def test_a_message_less_exception_is_named_by_its_type(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        _inject(monkeypatch, "build", MemoryError())
        main(["build", str(panel)])
        assert "internal error (MemoryError) -- this is a bug" in capsys.readouterr().err

    @pytest.mark.parametrize("command", COMMANDS)
    def test_the_traceback_is_there_with_the_flag(
        self,
        command: str,
        panel: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        _inject(monkeypatch, command, RuntimeError("boom"))
        assert main(["--traceback", *_argv(command, panel, tmp_path)]) == 70
        err = capsys.readouterr().err
        assert "Traceback (most recent call last)" in err
        assert "RuntimeError: boom" in err
        assert "internal error (RuntimeError: boom)" in err

    @pytest.mark.parametrize("value", ["1", "yes"])
    def test_the_traceback_is_there_with_the_variable(
        self,
        value: str,
        panel: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        monkeypatch.setenv("SCENET_DEBUG", value)
        _inject(monkeypatch, "build", RuntimeError("boom"))
        assert main(["build", str(panel)]) == 70
        assert "Traceback (most recent call last)" in capsys.readouterr().err

    @pytest.mark.parametrize("value", ["", "0"])
    def test_debug_off_is_off(
        self,
        value: str,
        panel: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        monkeypatch.setenv("SCENET_DEBUG", value)
        _inject(monkeypatch, "build", RuntimeError("boom"))
        assert main(["build", str(panel)]) == 70
        assert "Traceback" not in capsys.readouterr().err


class TestCtrlC:
    @pytest.mark.parametrize("command", COMMANDS)
    def test_exits_130_with_no_traceback(
        self,
        command: str,
        panel: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        _inject(monkeypatch, command, KeyboardInterrupt())
        assert main(_argv(command, panel, tmp_path)) == EXIT_INTERRUPTED == 130
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert captured.out == ""

    def test_while_writing_leaves_no_traceback_either(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(scenet.cli, "_write", _raise(KeyboardInterrupt()))
        assert main(["build", str(panel)]) == 130
        assert "Traceback" not in capsys.readouterr().err

    def test_ends_a_watch_with_zero_as_before(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        """Ctrl-C is how a watch is meant to end, so it is not an interruption."""
        monkeypatch.setattr(scenet.cli, "watch_loop", _raise(KeyboardInterrupt()))
        assert main(["build", str(panel), "--watch", "--quiet"]) == 0
        assert "Traceback" not in capsys.readouterr().err


class TestAFileTheSystemWillNotTouch:
    """An `OSError` reading or writing: the path and the system's reason, exit 1."""

    def test_an_output_path_that_is_a_directory(
        self, panel: Path, capsys: pytest.CaptureFixture[str]
    ):
        (panel.parent / "duel.svg").mkdir()
        assert main(["build", str(panel)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        (line,) = err.splitlines()
        assert line.startswith("scenet: ")
        assert str(panel.parent / "duel.svg") in line
        assert line.endswith(("Is a directory", "Permission denied"))

    def test_an_output_folder_under_a_file(
        self, panel: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        (tmp_path / "taken").write_text("a file, not a folder", encoding="utf-8")
        target = tmp_path / "taken" / "out" / "duel.svg"
        assert main(["build", str(panel), "-o", str(target)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        (line,) = err.splitlines()
        assert str(tmp_path / "taken") in line

    @pytest.mark.skipif(
        sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        reason="needs POSIX permissions, which root ignores",
    )
    def test_a_read_only_folder(
        self, panel: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        try:
            assert main(["build", str(panel), "-o", str(locked / "duel.svg")]) == 1
        finally:
            locked.chmod(0o700)
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert err == f"scenet: {locked / 'duel.svg'}: Permission denied\n"

    @pytest.mark.parametrize(
        "writer", [("build", "_write"), ("check", "_write_report"), ("schema", "_write_document")]
    )
    def test_a_full_disk(
        self,
        writer: tuple[str, str],
        panel: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        command, function = writer
        target = tmp_path / "out.txt"
        full = OSError(errno.ENOSPC, "No space left on device", str(target))
        monkeypatch.setattr(scenet.cli, function, _raise(full))
        argv = {
            "build": ["build", str(panel), "--quiet"],
            "check": ["check", str(panel), "-o", str(target)],
            "schema": ["schema", "-o", str(target)],
        }[command]
        assert main(argv) == 1
        assert capsys.readouterr().err == f"scenet: {target}: No space left on device\n"

    def test_a_reason_with_no_path(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(
            scenet.mcp, "serve", _raise(OSError(errno.EADDRINUSE, "Address already in use"))
        )
        assert main(["mcp", "--transport", "streamable-http"]) == 1
        assert capsys.readouterr().err == "scenet: Address already in use\n"

    def test_a_rename_names_both_paths(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        moved = OSError(errno.EXDEV, "Invalid cross-device link", "a.svg", None, "b.svg")
        monkeypatch.setattr(scenet.cli, "_write", _raise(moved))
        assert main(["build", str(panel), "--quiet"]) == 1
        assert capsys.readouterr().err == "scenet: a.svg -> b.svg: Invalid cross-device link\n"

    def test_a_source_that_vanishes_before_build_reads_it(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        compile_book_file = scenet.cli.compile_book_file

        def vanish_then_compile(source: Path, **options: Any) -> Any:
            source.unlink()
            return compile_book_file(source, **options)

        monkeypatch.setattr(scenet.cli, "compile_book_file", vanish_then_compile)
        assert main(["build", str(panel)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert str(panel) in err

    def test_a_source_that_vanishes_before_check_reads_it(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        diagnose_file = scenet.cli.diagnose_file

        def vanish_then_check(source: Path, **options: Any) -> Any:
            source.unlink()
            return diagnose_file(source, **options)

        monkeypatch.setattr(scenet.cli, "diagnose_file", vanish_then_check)
        assert main(["check", str(panel)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert err.startswith(f"scenet: {panel}: ")

    def test_check_on_a_folder(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        folder = tmp_path / "folder.panel.yaml"
        folder.mkdir()
        assert main(["check", str(folder)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert err.startswith(f"scenet: {folder}: ")

    def test_a_closed_pipe_ends_quietly(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        """`scenet schema | head -1`: the reader left, so there is nobody to tell."""
        monkeypatch.setattr(scenet.cli, "_print_document", _raise(BrokenPipeError(errno.EPIPE, "")))
        assert main(["schema"]) == 1
        assert capsys.readouterr().err == ""


class TestCheckReadsAnyBytes:
    def test_a_document_that_is_not_utf8_is_a_syntax_finding(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """`build` already said so in one line; `check` crashed on it."""
        source = tmp_path / "bytes.panel.yaml"
        source.write_bytes(b"cast: {}\n\xff\xfe\n")
        assert main(["check", str(source)]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert err == (
            f"{source}:1:1: syntax: not UTF-8 text: byte 9 is 0xff; save the file as UTF-8\n"
        )

    def test_a_script_that_is_not_utf8_is_one_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        source = tmp_path / "bytes.script"
        source.write_bytes(b"\x80")
        assert main(["check", str(source)]) == 1
        assert ": syntax: not UTF-8 text: byte 0 is 0x80" in capsys.readouterr().err


class TestTheInstalledCommand:
    def test_an_unwritable_output_prints_no_traceback(self, panel: Path, tmp_path: Path):
        """Through the interpreter, as a user runs it, not only through `main`."""
        (tmp_path / "taken").write_text("a file", encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if key != "SCENET_DEBUG"}
        # The system's reason comes in its own language, which needs no code page to read.
        environment["PYTHONIOENCODING"] = "utf-8"
        run = subprocess.run(  # noqa: S603 -- our own interpreter, on a file written here
            [sys.executable, "-m", "scenet.cli", "build", str(panel), "-o", "taken/x/duel.svg"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        assert run.returncode == 1
        assert "Traceback" not in run.stderr
        assert run.stderr.startswith("scenet: ")


def _call_twice(tool: str, arguments: dict[str, Any]) -> list[Any]:
    """The failing call, then a call that works, through one client session."""

    async def go() -> list[Any]:
        async with Client(build_server()) as client:
            failed = await client.call_tool(tool, arguments)
            after = await client.call_tool("get_spec", {})
            return [failed, after]

    return anyio.run(go)


#: The function inside each tool a fault is injected in.
_TOOL_INSIDES = {
    "get_spec": ("part", {}),
    "list_puppets": ("default_library", {}),
    "validate": ("diagnose_source", {"source": PANEL}),
    "compile": ("compile_book", {"source": PANEL}),
    "render": ("compile_book", {"source": PANEL}),
}


class TestTheMcpServer:
    @pytest.mark.parametrize("tool", sorted(_TOOL_INSIDES))
    def test_a_crash_in_a_tool_is_an_error_result_and_the_server_lives(
        self, tool: str, monkeypatch: pytest.MonkeyPatch
    ):
        inside, arguments = _TOOL_INSIDES[tool]
        original = getattr(scenet.mcp, inside)
        calls = 0

        def fail_once(*args: object, **kwargs: object) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("the frobnicator fell over")
            return original(*args, **kwargs)

        monkeypatch.setattr(scenet.mcp, inside, fail_once)
        failed, after = _call_twice(tool, arguments)
        assert failed.is_error
        (block,) = failed.content
        assert "internal error (RuntimeError: the frobnicator fell over)" in block.text
        assert ISSUES in block.text
        assert "Traceback" not in block.text
        assert not after.is_error


class TestTheLinesItPrints:
    """What each failure says, held word for word (from the mutation run)."""

    @pytest.mark.parametrize(
        ("error", "said"),
        [
            (OSError(errno.EACCES, "Permission denied", "a.svg"), "a.svg: Permission denied"),
            (OSError("the disk said no"), "the disk said no"),
            (OSError(), "OSError"),
            (PermissionError(), "PermissionError"),
        ],
    )
    def test_a_file_the_system_refuses(self, error: OSError, said: str):
        assert describe_failure(error) == said

    def test_a_watch_says_why_a_rebuild_failed(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        def once(_dependencies: object, rebuild: Callable[[], None]) -> None:
            monkeypatch.setattr(scenet.cli, "compile_book_file", _raise(RuntimeError("boom")))
            rebuild()

        monkeypatch.setattr(scenet.cli, "watch_loop", once)
        assert main(["build", str(panel), "--watch", "--quiet"]) == 0
        err = capsys.readouterr().err
        assert err == (
            "scenet: watch rebuild failed: internal error (RuntimeError: boom) -- this is a bug; "
            f"please report it at {ISSUES}\n"
        )

    def test_a_key_the_document_lacks_is_said_without_quotes(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        """A `KeyError`'s own text is a repr; the message under it is what is said."""
        monkeypatch.setattr(
            scenet.cli, "compile_book_file", _raise(UnknownActorError("no actor 'zed' here"))
        )
        assert main(["build", str(panel)]) == 1
        assert capsys.readouterr().err == "scenet: no actor 'zed' here\n"

    def test_a_scenet_error_that_is_no_key_error_is_said_whole(
        self, panel: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(scenet.cli, "compile_book_file", _raise(LayoutError()))
        assert main(["build", str(panel)]) == 1
        assert capsys.readouterr().err == f"scenet: {LayoutError()}\n"


class TestAClosedPipe:
    def test_stdout_is_pointed_at_the_null_device(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Once the reader has gone, nothing the interpreter flushes can fail again."""
        with (tmp_path / "out.txt").open("w", encoding="utf-8") as stdout:
            monkeypatch.setattr(sys, "stdout", stdout)
            _silence_stdout()
            stdout.write("lost")
            stdout.flush()
        assert (tmp_path / "out.txt").read_text(encoding="utf-8") == ""


class TestTheServerLogsACrash:
    def test_the_original_exception_with_the_tool_s_name(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        crash = RuntimeError("the frobnicator fell over")
        monkeypatch.setattr(scenet.mcp, "part", _raise(crash))
        with caplog.at_level(logging.ERROR, logger="scenet.mcp"):
            _call_twice("get_spec", {})
        record, *_ = [r for r in caplog.records if r.name == "scenet.mcp"]
        assert record.getMessage() == "tool 'get_spec' crashed"
        assert isinstance(record.exc_info, tuple)
        assert record.exc_info[1] is crash

    def test_a_crash_with_no_cause_is_said_as_itself(self, monkeypatch: pytest.MonkeyPatch):
        async def crashed(*_args: object, **_kwargs: object) -> None:
            raise UnexpectedToolError("Error executing tool x")

        monkeypatch.setattr(MCPServer, "call_tool", crashed)

        async def go() -> Any:
            return await build_server().call_tool("get_spec", {})

        with pytest.raises(ToolError) as raised:
            anyio.run(go)
        assert "internal error (UnexpectedToolError: Error executing tool x)" in str(raised.value)
