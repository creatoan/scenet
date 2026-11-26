"""`scenet mcp` over HTTP: local by default, bounded requests, bounded work (#380).

What the server guarantees, each held here against a real server on a real port:

- it listens on this machine alone unless told `--allow-remote`, whose help states the risk;
- a `Host` it does not serve is refused with 421, and an `Origin` other than its own with
  403, so a web page cannot reach it by DNS rebinding;
- a request body over `MAX_REQUEST_BYTES` is refused with 413 before it is read;
- a tool call that runs past `--timeout` is stopped -- its worker process is killed, so the
  work stops too -- and answered with an error, and the server goes on serving;
- it keeps no session: a request needs no session id;
- it never reads the file system for a document sent to it, nor for the files it names.

What it does not do -- authenticate, encrypt -- is the operator's, and `SECURITY.md` says so.
"""

import argparse
import contextlib
import json
import multiprocessing
import os
import site
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import anyio
import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

import scenet.mcp
import scenet.paths
from scenet.cli import build_parser, main
from scenet.mcp import DEFAULT_TIMEOUT, MAX_REQUEST_BYTES, build_server, serve

PANEL = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
#: A balloon of four hundred words: the deep check takes minutes on it (#371).
LONG = (
    "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: "
    + " ".join(["word"] * 400)
    + "}}]\n"
)


#: Passes every cheap check, and fails only once its balloon is placed. A depth cycle did,
#: until `scenet check` found one as `ordering-cycle`.
UNPLACEABLE = (
    "camera: {shot: extreme_close_up}\npanel: {size: [300, 300]}\n"
    "cast: {alice: {reference: alice}}\n"
    'script: [{say: {by: alice, text: "There is no room anywhere in this panel '
    'for a line this long."}}]\n'
)


def _recording(into: list[dict[str, Any]]) -> Callable[..., None]:
    """A stand-in for `serve` that records the options it was called with."""

    def record(*_args: object, **options: Any) -> None:
        into.append(options)

    return record


def _making(made: object) -> Callable[..., Any]:
    """A stand-in for `build_server` that hands back `made`, whatever it is asked."""

    def make(**_options: object) -> Any:
        return made

    return make


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """A real `scenet mcp` on a free port, with a short budget for each call."""
    port = _free_port()
    process = subprocess.Popen(  # noqa: S603 -- our own interpreter, our own module
        [
            sys.executable,
            "-m",
            "scenet.cli",
            "mcp",
            "--transport",
            "streamable-http",
            "--port",
            str(port),
            "--timeout",
            "3",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.2)
    else:
        process.kill()
        pytest.fail("the server did not start listening")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        process.kill()
        process.wait()


def _rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


@dataclass(frozen=True)
class _Response:
    status_code: int
    headers: dict[str, str]
    text: str


def _post(url: str, body: bytes, **headers: str) -> _Response:
    """One POST with the standard library, so the test needs no HTTP client of its own."""
    request = urllib.request.Request(  # noqa: S310 -- a local server this test started
        f"{url}/mcp", data=body, headers={**HEADERS, **headers}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310
            return _Response(
                answer.status,
                {key.lower(): value for key, value in answer.headers.items()},
                answer.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as refused:
        try:
            said = refused.read().decode("utf-8", "replace")
        except ConnectionError:
            # The status came; the server closed before the client read the rest.
            said = ""
        return _Response(refused.code, {}, said)
    except (ConnectionError, urllib.error.URLError):
        # A body refused unread may close the connection before the answer is read.
        return _Response(413, {}, "")


class TestListening:
    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "example.org"])  # noqa: S104
    def test_beyond_this_machine_is_refused_without_the_flag(
        self, host: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        assert main(["mcp", "--transport", "streamable-http", "--host", host]) == 2
        assert started == []
        assert capsys.readouterr().err == (
            f"scenet: --host {host} listens beyond this machine, and the server has no "
            "authentication; put one in front of it, then pass --allow-remote\n"
        )

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.9", "localhost", "::1"])
    def test_this_machine_needs_no_flag(self, host: str, monkeypatch: pytest.MonkeyPatch):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        assert main(["mcp", "--transport", "streamable-http", "--host", host]) == 0
        assert [options["host"] for options in started] == [host]

    def test_the_flag_lets_it_listen_beyond(self, monkeypatch: pytest.MonkeyPatch):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        argv = ["mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"]  # noqa: S104
        assert main(argv) == 0
        assert started[0]["host"] == "0.0.0.0"  # noqa: S104

    def test_the_flag_says_the_risk(self, capsys: pytest.CaptureFixture[str]):
        with pytest.raises(SystemExit):
            main(["mcp", "--help"])
        help_text = " ".join(capsys.readouterr().out.split())
        assert "--allow-remote" in help_text
        assert "no authentication" in help_text

    def test_the_sdk_is_given_every_bound(self, monkeypatch: pytest.MonkeyPatch):
        runs: list[dict[str, Any]] = []

        class Recorder:
            def run(self, transport: str, **options: Any) -> None:
                runs.append({"transport": transport, **options})

            def close(self) -> None:
                """Nothing to stop: it started no worker."""

        monkeypatch.setattr(scenet.mcp, "build_server", _making(Recorder()))
        serve("streamable-http", host="127.0.0.1", port=8123, origins=("http://localhost:6274",))
        (run,) = runs
        security = run.pop("transport_security")
        assert run == {
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 8123,
            "stateless_http": True,
            "max_request_body_size": MAX_REQUEST_BYTES,
        }
        assert security.enable_dns_rebinding_protection
        assert security.allowed_hosts == ["127.0.0.1:8123", "localhost:8123", "[::1]:8123"]
        assert security.allowed_origins == [
            "http://127.0.0.1:8123",
            "http://localhost:8123",
            "http://[::1]:8123",
            "http://localhost:6274",
        ]

    def test_a_remote_host_is_a_host_it_serves(self, monkeypatch: pytest.MonkeyPatch):
        runs: list[dict[str, Any]] = []

        class Recorder:
            def run(self, transport: str, **options: Any) -> None:
                runs.append(options)

            def close(self) -> None:
                """Nothing to stop: it started no worker."""

        monkeypatch.setattr(scenet.mcp, "build_server", _making(Recorder()))
        serve("streamable-http", host="comics.example", port=80)
        assert runs[0]["transport_security"].allowed_hosts[-1] == "comics.example:80"


class TestOverARealPort:
    def test_a_request_with_no_session_id_is_served(self, server: str):
        response = _post(server, json.dumps(_rpc("tools/list")).encode())
        assert response.status_code == 200, response.text
        assert "mcp-session-id" not in response.headers

    def test_a_foreign_host_is_421(self, server: str):
        response = _post(server, json.dumps(_rpc("tools/list")).encode(), Host="evil.example")
        assert response.status_code == 421

    @pytest.mark.parametrize(
        "origin", ["http://evil.example", "http://localhost:1", "https://127.0.0.1"]
    )
    def test_a_foreign_origin_is_403(self, server: str, origin: str):
        response = _post(server, json.dumps(_rpc("tools/list")).encode(), Origin=origin)
        assert response.status_code == 403

    def test_its_own_origin_is_served(self, server: str):
        port = server.rsplit(":", 1)[1]
        response = _post(
            server, json.dumps(_rpc("tools/list")).encode(), Origin=f"http://localhost:{port}"
        )
        assert response.status_code == 200

    def test_a_body_over_the_limit_is_413(self, server: str):
        call = _rpc(
            "tools/call",
            {"name": "validate", "arguments": {"source": "x" * (MAX_REQUEST_BYTES + 1)}},
        )
        started = time.monotonic()
        response = _post(server, json.dumps(call).encode())
        assert response.status_code == 413
        assert time.monotonic() - started < 30

    def test_a_call_past_its_time_is_stopped_and_the_server_goes_on(self, server: str):
        async def go() -> tuple[Any, float, Any]:
            async with Client(f"{server}/mcp") as client:
                started = time.monotonic()
                slow = await client.call_tool("validate", {"source": LONG, "deep": True})
                seconds = time.monotonic() - started
                after = await client.call_tool("validate", {"source": PANEL})
                return slow, seconds, after

        slow, seconds, after = anyio.run(go)
        assert slow.is_error
        assert "took longer than 3 seconds" in slow.content[0].text
        assert seconds < 30
        assert not after.is_error


@contextlib.asynccontextmanager
async def _bounded_client(timeout: float | None) -> AsyncGenerator[Client]:
    """A client of a server whose calls run in workers, every worker stopped afterwards.

    A worker left behind would outlive the test, and a runner that waits for any child
    process of its own -- mutmut's -- trips on one it never started.
    """
    server = build_server(timeout=timeout)
    try:
        async with Client(server) as client:
            yield client
    finally:
        server.close()


class TestTheBudget:
    def test_the_default_is_stated(self):
        assert DEFAULT_TIMEOUT == 60

    def test_in_process_a_call_past_its_time_is_stopped(self):
        async def go() -> tuple[Any, Any, float]:
            async with _bounded_client(2) as client:
                started = time.monotonic()
                slow = await client.call_tool("validate", {"source": LONG, "deep": True})
                seconds = time.monotonic() - started
                after = await client.call_tool("get_spec", {})
                return slow, after, seconds

        slow, after, seconds = anyio.run(go)
        assert slow.is_error
        assert "took longer than 2 seconds" in slow.content[0].text
        assert seconds < 20
        assert not after.is_error

    def test_a_failed_compile_is_explained_within_the_same_budget(self):
        """The second compile and the deep check that explain a failure run in the same
        worker, under the same clock, as the compile that failed."""

        async def go() -> Any:
            async with _bounded_client(2) as client:
                return await client.call_tool("render", {"source": LONG})

        started = time.monotonic()
        failed = anyio.run(go)
        assert failed.is_error
        assert time.monotonic() - started < 20

    def test_a_result_is_the_same_through_a_worker(self):
        async def go(timeout: float | None) -> Any:
            async with _bounded_client(timeout) as client:
                return await client.call_tool("render", {"source": PANEL})

        bounded, direct = anyio.run(go, 30), anyio.run(go, None)
        assert bounded.content == direct.content

    def test_a_tool_error_comes_back_as_it_was(self):
        async def go() -> Any:
            async with _bounded_client(30) as client:
                return await client.call_tool("compile", {"source": "cast: [1"})

        failed = anyio.run(go)
        assert failed.is_error
        assert "scenet/syntax" in failed.content[0].text


def _allowed() -> tuple[Path, ...]:
    """Where a call may open a file: the package, and the interpreter's own libraries."""
    import fonts  # noqa: PLC0415 -- the shipped faces' package, located only here

    places = {Path(scenet.__file__).parent, Path(fonts.__file__).parent}
    places |= {Path(place) for place in (sys.prefix, sys.base_prefix, sys.exec_prefix)}
    places |= {Path(place) for place in site.getsitepackages()}
    return tuple(place.resolve() for place in places)


class _Opened:
    """Every file the interpreter opens while `recording` is set."""

    recording = False
    seen: ClassVar[list[tuple[str, str, int]]] = []


def _audit(event: str, arguments: tuple[object, ...]) -> None:
    if not _Opened.recording or event != "open":
        return
    path, mode, flags = arguments
    if isinstance(path, str | bytes | os.PathLike):
        written = os.fsdecode(path)  # pyright: ignore[reportUnknownArgumentType]
        _Opened.seen.append((written, str(mode or ""), flags if isinstance(flags, int) else 0))


#: An audit hook cannot be removed, so it is added once, and records only when asked.
sys.addaudithook(_audit)

_WRITING = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


class TestNoFileIsOpened:
    """Started with neither `--root` nor `--output`, a call opens no file but the package's
    own, and writes none: an audit hook records every `open` the interpreter makes."""

    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [
            ("get_spec", {"section": "characters"}),
            ("list_puppets", {}),
            ("validate", {"source": PANEL + "setting: {image: ../../secret.png}\n", "deep": True}),
            ("compile", {"source": PANEL}),
            ("render", {"source": PANEL, "live_text": True}),
        ],
    )
    def test_a_call(
        self,
        tool: str,
        arguments: dict[str, Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "secret.png").write_bytes(b"not yours")

        async def go() -> Any:
            async with Client(build_server()) as client:
                return await client.call_tool(tool, arguments)

        _Opened.seen.clear()
        _Opened.recording = True
        try:
            anyio.run(go)
        finally:
            _Opened.recording = False
        allowed = _allowed()
        for path, mode, flags in _Opened.seen:
            where = Path(path).resolve()
            assert any(where.is_relative_to(place) for place in allowed), path
            assert not set(mode) & set("wax+"), (path, mode)
            assert not flags & _WRITING, (path, flags)


class TestTheFoldersAreRefused:
    @pytest.mark.parametrize("option", ["--root", "--output"])
    def test_over_http(
        self,
        option: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        assert main(["mcp", "--transport", "streamable-http", option, str(tmp_path)]) == 2
        assert started == []
        assert "they are for a server on stdio" in capsys.readouterr().err

    @pytest.mark.parametrize("option", ["--root", "--output"])
    def test_on_stdio_until_they_come(
        self,
        option: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        assert main(["mcp", option, str(tmp_path)]) == 2
        assert started == []
        assert "not in this version yet" in capsys.readouterr().err


class TestNoFileIsRead:
    """A document sent to the server, and the files it names, are read in memory only: a
    path in either never reaches the file system, wherever it points."""

    @pytest.mark.parametrize("tool", ["validate", "compile", "render", "list_puppets"])
    def test_a_path_that_climbs_reads_nothing(
        self, tool: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "secret.png").write_bytes(b"\x89PNG not yours")

        def never(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the server read a file a document named")

        # Every file a document names on disk is checked against its root first.
        monkeypatch.setattr(scenet.paths, "within", never)
        document = PANEL + "setting: {image: ../../secret.png}\n"
        arguments: dict[str, Any] = {"source": document}
        if tool == "list_puppets":
            arguments = {"files": {"puppets/../../secret.puppet.yaml": ""}}

        async def go() -> Any:
            async with Client(build_server()) as client:
                return await client.call_tool(tool, arguments)

        result = anyio.run(go)
        text = json.dumps(result.structured_content) + " ".join(
            getattr(block, "text", "") for block in result.content
        )
        assert "the server read a file" not in text
        assert "not yours" not in text


def test_closing_a_server_stops_its_workers():
    """`serve` closes the server it ran, and no worker it started is left behind."""

    async def go() -> list[Any]:
        server = build_server(timeout=30)
        async with Client(server) as client:
            await client.call_tool("get_spec", {})
        assert server._workers is not None
        idle = list(server._workers._idle)
        server.close()
        return idle

    stopped = anyio.run(go)
    assert stopped
    assert all(not worker._process.is_alive() for worker in stopped)


class TestWhatItIsGiven:
    """What `scenet mcp` and `serve` hand on, each compared (from the mutation run)."""

    @pytest.mark.parametrize("seconds", ["0.5", "1", "3600"])
    def test_a_timeout_above_nought_is_taken(self, seconds: str, monkeypatch: pytest.MonkeyPatch):
        started: list[dict[str, Any]] = []
        monkeypatch.setattr(scenet.mcp, "serve", _recording(started))
        assert main(["mcp", "--timeout", seconds]) == 0
        assert started[0]["timeout"] == float(seconds)

    def test_both_folders_are_named_in_one_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(scenet.mcp, "serve", _recording([]))
        argv = ["mcp", "--transport", "streamable-http", "--root", str(tmp_path)]
        assert main([*argv, "--output", str(tmp_path)]) == 2
        assert capsys.readouterr().err.startswith("scenet: --root and --output would let any")

    @pytest.mark.parametrize(
        ("option", "metavar", "help"),
        [
            (
                "--allow-remote",
                None,
                "let streamable-http listen beyond this machine, on a --host that is not a "
                "loopback address; the server has no authentication and no encryption, so put "
                "something that provides both in front of it first",
            ),
            (
                "--allow-origin",
                "ORIGIN",
                "an Origin a browser client may call streamable-http from, such as "
                "http://localhost:6274, beyond the server's own; may be repeated",
            ),
            (
                "--timeout",
                "SECONDS",
                "the most seconds one tool call may take before it is stopped (default: 60)",
            ),
            (
                "--root",
                "DIR",
                "a folder a stdio server's documents may name files in; refused over "
                "streamable-http, and not in this version yet",
            ),
            (
                "--output",
                "DIR",
                "a folder a stdio server's build tool writes new files in; refused over "
                "streamable-http, and not in this version yet",
            ),
        ],
    )
    def test_each_option_says_what_it_is(self, option: str, metavar: str | None, help: str):  # noqa: A002 -- argparse's name
        (group,) = [a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)]
        (action,) = [a for a in group.choices["mcp"]._actions if option in a.option_strings]
        assert (action.metavar, action.help) == (metavar, help)
        if option == "--timeout":
            assert action.default is None
        if option == "--allow-origin":
            assert action.default == []

    def test_serve_listens_here_by_default_and_hands_on_its_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        built: list[float | None] = []
        runs: list[dict[str, Any]] = []

        class Recorder:
            def run(self, transport: str, **options: Any) -> None:
                runs.append(options)

            def close(self) -> None:
                """Nothing to stop: it started no worker."""

        def build(*, timeout: float | None = None) -> Recorder:
            built.append(timeout)
            return Recorder()

        monkeypatch.setattr(scenet.mcp, "build_server", build)
        serve("streamable-http", timeout=7.5)
        assert built == [7.5]
        assert (runs[0]["host"], runs[0]["port"]) == ("127.0.0.1", 8000)

    def test_an_ipv6_host_is_bracketed(self, monkeypatch: pytest.MonkeyPatch):
        runs: list[dict[str, Any]] = []

        class Recorder:
            def run(self, transport: str, **options: Any) -> None:
                runs.append(options)

            def close(self) -> None:
                """Nothing to stop: it started no worker."""

        monkeypatch.setattr(scenet.mcp, "build_server", _making(Recorder()))
        serve("streamable-http", host="fe80::1", port=80)
        security = runs[0]["transport_security"]
        assert security.allowed_hosts[-1] == "[fe80::1]:80"
        assert security.enable_dns_rebinding_protection


class TestAWorker:
    def test_it_is_spawned_and_dies_with_the_server(self):
        worker = scenet.mcp._Worker()
        try:
            assert worker._process.daemon is True
            assert type(worker._process).__name__ == "SpawnProcess"
        finally:
            worker.stop()

    def test_an_idle_worker_takes_the_next_call(self, monkeypatch: pytest.MonkeyPatch):
        started: list[object] = []
        real = scenet.mcp._Worker

        def counted() -> Any:
            started.append(None)
            return real()

        monkeypatch.setattr(scenet.mcp, "_Worker", counted)

        async def go() -> None:
            async with _bounded_client(30) as client:
                await client.call_tool("get_spec", {})
                await client.call_tool("get_spec", {})

        anyio.run(go)
        assert len(started) == 1


class TestAFailedCompileExplained:
    def test_the_cheap_check_first_and_the_deep_one_only_when_it_finds_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        asked: list[bool] = []
        real = scenet.mcp._diagnose

        def recorded(*args: Any, **options: Any) -> Any:
            asked.append(options["deep"])
            return real(*args, **options)

        monkeypatch.setattr(scenet.mcp, "_diagnose", recorded)
        with pytest.raises(ToolError):
            scenet.mcp._compile("cast: {a: {reference: nobody}}\n", "yaml")
        assert asked == [False]
        asked.clear()
        with pytest.raises(ToolError):
            scenet.mcp._compile(UNPLACEABLE, "yaml")
        assert asked == [False, True]

    def test_a_script_is_explained_as_a_script(self):
        with pytest.raises(ToolError) as raised:
            scenet.mcp._compile(
                "PANEL 1" + chr(10) + "NOBODY" + chr(10) + "Hi." + chr(10), "script"
            )
        assert "scenet/unknown-actor" in str(raised.value)
        assert "scenet/not-a-mapping" not in str(raised.value)

    def test_the_files_sent_explain_it_too(self):
        """A picture sent with the document is there when the failure is explained."""
        from tests.images import tiny_png  # noqa: PLC0415 -- this test's own picture

        source = "setting: {image: art/a.png}\n" + UNPLACEABLE
        with pytest.raises(ToolError) as raised:
            scenet.mcp._compile(source, "yaml", {"art/a.png": tiny_png()})
        assert "scenet/balloon-placement" in str(raised.value)
        assert "image-file" not in str(raised.value)


def test_a_script_that_fails_only_once_laid_out_is_explained_as_a_script():
    """The deep check that explains it reads the script as a script, too."""
    nl = chr(10)
    script = nl.join(
        [
            "---",
            "cast: {A: {reference: alice}}",
            "---",
            "PANEL 1",
            "@shot: extreme_close_up",
            "@panel: {size: [300, 300]}",
            "A",
            "There is no room anywhere in this panel for a line this long.",
            "",
        ]
    )
    with pytest.raises(ToolError) as raised:
        scenet.mcp._compile(script, "script")
    assert "scenet/balloon-placement" in str(raised.value)
    assert "not-a-mapping" not in str(raised.value)


def test_waiting_for_a_worker_to_start_ends_when_the_wait_is_cancelled():
    """A call cancelled while its worker starts is let go at once, not when the worker is up."""
    worker = object.__new__(scenet.mcp._Worker)
    ours, theirs = multiprocessing.Pipe()
    worker._connection = ours
    worker._starting = True
    # Up after three seconds: what a wait that cannot be cancelled would sit through.
    up = threading.Timer(3, theirs.send, ("ready",))
    up.start()

    async def go() -> float:
        started = time.monotonic()
        with anyio.move_on_after(0.2):
            await worker.ready()
        return time.monotonic() - started

    try:
        assert anyio.run(go) < 2
        assert worker._starting
    finally:
        up.join()
        ours.close()
        theirs.close()
