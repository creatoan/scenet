"""An MCP server, so a model can check and render the panels it writes.

The spec pack tells a model what the language is; this lets it find out what it got
wrong. A model writes a document, calls `validate`, reads findings that each name a
rule, a line and a fix, corrects its own output and calls `render` -- with no human
copying error text between a terminal and a chat window. It is the only part of the
agent-facing surface that closes that loop.

Install it with the extra, and start it with the `scenet mcp` command:

.. code-block:: bash

    pip install 'scenet[mcp]'
    scenet mcp                             # stdio, for a local client
    scenet mcp --transport streamable-http # for a remote one

.. rubric:: The official SDK, and only as an extra

Built on the official `mcp <https://github.com/modelcontextprotocol/python-sdk>`__
package, which already speaks protocol revision 2026-07-28 -- the stateless core, the
extensions framework, cacheable list results -- and adds nothing FastMCP would have to
supply. Over HTTP the server keeps no session either: a request needs no session id, as
the revision that removed protocol-level sessions says. It is an extra rather than a
dependency because it brings an HTTP stack the compiler has no use for: the browser
playground installs the base wheel into Pyodide, and someone who only wants `scenet build`
should not have to put Starlette through their own licence review.

Transports are stdio and Streamable HTTP. Not SSE: the protocol has deprecated it, and
Streamable HTTP replaced it.

.. rubric:: Five tools, shaped after compilers that are already served this way

`typst-mcp <https://github.com/johannesbrandenburger/typst-mcp>`__ serves its
documentation one chapter at a time, checks a snippet, and renders one;
`d2-mcp <https://github.com/h0rv/d2-mcp>`__ has a cheat sheet, `compile` to validate and
`render` to draw. The same shapes, rather than new ones:

- `get_spec` -- the spec pack, one part at a time, so a model need not read all of it
- `list_puppets` -- the characters it may cast, with their poses and expressions --
  the shipped ones, and any puppet file sent with a document
- `validate` -- every finding at once, shaped rather than dumped as raw SARIF
- `compile` -- the Panel Core: where the compiler put everything, and why
- `render` -- the SVG, byte-identical to what `scenet build --embed-images` writes

Each takes the document as **text**, not a path. A remote client shares no file
system with the server, and one calling convention for both transports is one less
thing to get wrong. Every tool is read-only and closed-world, and says so in its
annotations: nothing here writes a file or reaches the network.

A document that names a file -- a picture behind the cast, a lettering face, a puppet of
its own -- is sent with it: `files` maps the path the document writes to the file's
bytes, in base64. They stand in for the document's folder and are read in memory; the
server never reads a folder of its own, and never writes one.

.. rubric:: Bounded, and local unless told otherwise

Over HTTP the server listens on this machine alone unless `scenet mcp --allow-remote` says
otherwise. A `Host` it does not serve is refused with 421, and an `Origin` other than its own
-- `http://localhost` at its own port -- with 403, so no web page can reach it by DNS
rebinding; `--allow-origin` adds one, for a client that runs in a browser. A request body
over :data:`MAX_REQUEST_BYTES <scenet.mcp.MAX_REQUEST_BYTES>` is refused with 413 before it
is read. It authenticates nobody and encrypts nothing: that is for whatever is put in front
of it.

On either transport, `scenet mcp` runs each tool call in a worker process of its own, and
stops it -- the process is killed, so its work stops too -- once it has run for
:data:`DEFAULT_TIMEOUT <scenet.mcp.DEFAULT_TIMEOUT>` seconds or `--timeout`, or once the
client cancels it; the call is answered with an error, and the server goes on serving. A
thread could not be stopped: the work of a call its client had given up on would go on
taking the server's processor. :func:`build_server <scenet.mcp.build_server>` runs calls in
process unless given a `timeout`.

.. rubric:: Keeping stdout clean

On stdio, stdout *is* the protocol stream, and one stray line corrupts it. That is why
nothing here goes through `cli.run_build`, which prints `wrote` and `note:` lines --
the easiest way there is to ship a broken stdio server. Notes travel in the tool
result instead. The SDK also points file descriptor 1 at stderr while it serves, which
catches a stray `print` from a dependency; the test suite drives a real stdio session
against the installed command to make sure neither ever matters.
"""

import base64
import binascii
import functools
import inspect
import json
import logging
import multiprocessing
import re
from collections.abc import Awaitable, Callable, Sequence
from multiprocessing.connection import Connection
from typing import Annotated, Any, Literal

import anyio
from anyio import to_thread
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    InputRequiredResult,
    TextContent,
    TextResourceContents,
    ToolAnnotations,
)
from pydantic import BaseModel, Field

from scenet import __version__
from scenet.assets.contract import PuppetSpec, default_library, is_puppet_file, load_puppet_file
from scenet.cli import describe_failure
from scenet.diagnostics import (
    RULE_NAMESPACE,
    RULES,
    Diagnostic,
    diagnose_script,
    diagnose_source,
    help_uri,
)
from scenet.emit.export import EXPORTS
from scenet.emit.page import render_page
from scenet.emit.svg import render
from scenet.errors import ScenetError
from scenet.frontends.positions import DOCUMENT_START
from scenet.paths import check_relative
from scenet.pipeline import Book, compile_book, compile_script
from scenet.spec_pack import part

__all__ = [
    "DEFAULT_TIMEOUT",
    "MAX_REQUEST_BYTES",
    "CompileReport",
    "CompiledPage",
    "CompiledPanel",
    "Finding",
    "Puppet",
    "PuppetCatalogue",
    "Server",
    "ValidationReport",
    "build_server",
    "compile_panel",
    "get_spec",
    "list_puppets",
    "render_panel",
    "serve",
    "validate",
]

#: The documentation site, which the server names as its website.
WEBSITE = "https://creatoan.github.io/scenet/"

#: The most seconds one tool call may take, unless `scenet mcp --timeout` says otherwise:
#: well past what any document a person writes takes, and short of a client giving up.
DEFAULT_TIMEOUT = 60.0

#: How many tool calls run at once; a further one waits for a free worker.
WORKERS = 4

#: The largest HTTP request body accepted: a document and the files it names, in base64,
#: which makes a 12 MiB picture about 16 MiB. A bigger one is refused with 413, unread.
MAX_REQUEST_BYTES = 16 * 2**20

#: What a client is told when it connects. Many hosts hand this straight to the model,
#: so it says what to do first rather than what the server is.
INSTRUCTIONS = """\
Scenet compiles a semantic description of a comic panel -- who is in it, how they \
relate, what they say -- into SVG, deterministically. There is no image model, and you \
never write coordinates: the compiler decides every one.

Before writing a document, call get_spec with no arguments for the essentials and the \
mistakes to avoid; call it with a section for the full language, the comic-script \
format or worked examples. list_puppets names the characters you can cast.

Then validate the document, fix every finding -- each names its rule, line and fix -- \
and validate again until it is clean. compile shows where everything was placed; \
render returns the SVG. Pass the document's text, not a path; if it names a picture, \
a font or a puppet file of its own (reference: puppets/pip.puppet.yaml), pass that \
file's bytes in files, by the path the document writes, and list_puppets with the same \
files says what poses and expressions the puppet has. A cast of figure: members is \
drawn by its picture, whose artwork contract sits beside it, named after it \
(art/p01.png, art/p01.art.yaml): pass that file too."""

#: Every tool here is a pure function of its arguments.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

#: The parts of the spec pack, as the tool schema offers them. Spelled out because a
#: `Literal` must be; `tests/test_mcp.py` checks it against `SPEC_PARTS`.
Section = Literal[
    "preamble",
    "language",
    "shot-types",
    "comic-script",
    "characters",
    "diagnostics",
    "schema",
    "gallery",
]

#: The two frontends. YAML covers both a single panel and a `panels:` sequence, which
#: the document itself distinguishes, so a caller never has to.
Syntax = Literal["yaml", "script"]

# Parameter descriptions live in the annotations rather than in an `Args:` section,
# because the annotation is what reaches the tool's input schema -- which is the only
# documentation a model calling the tool ever sees.
SourceArg = Annotated[
    str,
    Field(description="The whole document as text: a YAML panel or scene, or a comic script"),
]
FilesArg = Annotated[
    dict[str, str] | None,
    Field(
        description=(
            "The files the document names -- a picture behind the cast, a font, a puppet "
            "file a cast member's `reference` names -- by the path it writes, such as "
            "`art/p01.png` or `puppets/pip.puppet.yaml`, each as base64, and the artwork "
            "contract beside a picture whose figures the cast names, such as "
            "`art/p01.art.yaml`. They stand in for the document's folder, which a server "
            "never reads; left out, a document that names a file is refused"
        )
    ),
]
SyntaxArg = Annotated[
    Syntax,
    Field(
        description=(
            "`yaml` for a *.panel.yaml or *.scene.yaml document, "
            "`script` for a *.script comic script"
        )
    ),
]


class Finding(BaseModel):
    """One thing wrong with a document: which rule, where, and what to do about it."""

    rule: str = Field(description="Stable rule id, such as `scenet/unknown-actor`")
    level: Literal["error", "note"] = Field(
        description="`error` stops the document compiling; a `note` reports a house limit, "
        "such as a balloon over the words a publisher asks for, and the document still compiles"
    )
    message: str = Field(description="What is wrong, naming the offending construct")
    fix: str = Field(description="What to do about it")
    help_uri: str = Field(
        description="Where the rule is explained, with a document that gives it and its fix"
    )
    where: str = Field(description="Path to the offending value, such as `script.0.say.by`")
    line: int = Field(description="1-based line the finding starts on")
    column: int = Field(description="1-based column the finding starts at")
    end_line: int = Field(description="1-based line the finding ends on")
    end_column: int = Field(description="1-based column the finding ends before")


class ValidationReport(BaseModel):
    """Everything wrong with a document, all at once."""

    valid: bool = Field(description="True when no finding is an error; notes may remain")
    findings: list[Finding] = Field(
        description="In source order; fix every error, and weigh each note"
    )


class CompiledPanel(BaseModel):
    """One compiled panel."""

    name: str = Field(description="`panel` for a single panel, else its name or number")
    notes: list[str] = Field(
        description="Decisions the compiler made that the source did not literally ask for"
    )
    core: dict[str, Any] = Field(
        description="The Panel Core: every resolved coordinate, as `scenet build --core` writes it"
    )


class CompiledPage(BaseModel):
    """One page: where each panel's frame is."""

    number: int = Field(description="The page's number, from 1")
    core: dict[str, Any] = Field(
        description=(
            "The Page Core: the page's size, the type height its panels share, and one frame "
            "per panel in reading order, as `scenet build --core` writes it"
        )
    )


class CompileReport(BaseModel):
    """Every panel in a document, compiled, and the pages they are laid out on."""

    panels: list[CompiledPanel] = Field(description="In reading order")
    pages: list[CompiledPage] = Field(
        default_factory=list, description="In order; empty when the document has no `pages:`"
    )


class Puppet(BaseModel):
    """A character a cast member's `reference` can name."""

    name: str = Field(
        description="What `reference` writes: a shipped puppet's name, or a puppet file's path"
    )
    heads_tall: float = Field(description="Height in head-heights; taller reads as older")
    poses: list[str] = Field(description="Every value `pose` may take for this puppet")
    expressions: list[str] = Field(description="Every value `expression` may take")


class PuppetCatalogue(BaseModel):
    """The puppet library."""

    puppets: list[Puppet] = Field(description="Every puppet the library holds, by name")


def get_spec(
    section: Annotated[
        Section | None,
        Field(description="Which part to read. Omit it for the essentials and a list of parts"),
    ] = None,
) -> str:
    """Read the Scenet language specification, one part at a time.

    With no section: what Scenet is, the two ways to write a panel, the check-and-fix
    loop, the mistakes generators make most, and what every other part holds. Read it
    first. With a section: that part in full -- `language` for every construct,
    `comic-script` for the script format, `gallery` for worked examples that are known
    to compile.

    Returns:
        Markdown, exactly as it appears in the spec pack.
    """
    if section is None:
        preamble = part("preamble").rstrip("\n")
        return f"{preamble}\n\nCall get_spec with a section to read any of these.\n"
    return part(section)


def list_puppets(files: FilesArg = None) -> PuppetCatalogue:
    """List the characters a panel can cast, with every pose and expression each declares.

    A cast member's `reference` names one of these; its `pose` and `expression` must be
    names that puppet declares. Anything else fails validation. A puppet of your own is a
    `*.puppet.yaml` file a cast member names by its path, `reference:
    puppets/pip.puppet.yaml`: send it in `files`, as validate, compile and render take
    it, and it is listed after the shipped ones, by that path.

    Returns:
        Every shipped puppet, by name, then every puppet file sent, by path -- each with
        its poses and expressions sorted.
    """
    library = default_library()
    puppets = [_puppet(name, library.get(name)) for name in library.names()]
    sent = _files(files) or {}
    for name in sorted(sent):
        if not is_puppet_file(name):
            continue
        try:
            puppets.append(_puppet(name, load_puppet_file(name, sent)))
        except ScenetError as exc:
            raise ToolError(f"files: {name!r} is not a puppet: {exc}") from exc
    return PuppetCatalogue(puppets=puppets)


def _puppet(name: str, puppet: PuppetSpec) -> Puppet:
    """One puppet, as a model is told about it: what to write, and what it can do."""
    return Puppet(
        name=name,
        heads_tall=round(puppet.heads_tall, 1),
        poses=sorted(puppet.poses),
        expressions=sorted(puppet.expressions),
    )


def validate(
    source: SourceArg,
    syntax: SyntaxArg = "yaml",
    deep: Annotated[
        bool,
        Field(
            description=(
                "Also run the solver, to catch layout and balloon-placement failures the "
                "cheap check cannot see. Slower"
            )
        ),
    ] = False,
    files: FilesArg = None,
) -> ValidationReport:
    """Check a document and report everything wrong with it, without compiling it.

    Runs the checks `scenet check` runs: the language, every actor id resolving to a
    cast member, staging order that does not loop, and every puppet, pose and
    expression existing. These are the faults no JSON Schema can catch. Each finding
    names its rule, its line and column, and the fix. Fix them all and validate again.

    Returns:
        Whether the document is valid, and every finding in source order.
    """
    found = _diagnose(source, syntax, deep=deep, files=_files(files))
    return ValidationReport(
        valid=not any(item.level == "error" for item in found),
        findings=[_finding(item) for item in found],
    )


def compile_panel(
    source: SourceArg, syntax: SyntaxArg = "yaml", files: FilesArg = None
) -> CompileReport:
    """Compile a document and return where the compiler put everything.

    The result is the Panel Core for each panel: every figure's position and scale,
    every balloon's box and tail. Its notes say what the compiler did that the source
    did not literally ask for -- a camera that retreated so the cast would fit, a
    tail that bent around a face. A document that does not compile is an error
    carrying the same findings `validate` reports.

    A document with `pages:` also gets each page's Page Core: where every panel's frame
    is. A panel on a page is compiled at its frame's size.

    Returns:
        Every panel, in reading order, with its notes and its Panel Core, then the pages.

    Raises:
        ~mcp.server.mcpserver.exceptions.ToolError: The document does not compile. The
            message lists every finding.
    """
    book = _compile(source, syntax, _files(files))
    return CompileReport(
        panels=[
            CompiledPanel(
                name=name, notes=list(result.notes), core=json.loads(result.core.to_json())
            )
            for name, result in book.panels.items()
        ],
        pages=[
            CompiledPage(number=number, core=json.loads(page.to_json()))
            for number, page in enumerate(book.pages, start=1)
        ],
    )


def render_panel(
    source: SourceArg,
    syntax: SyntaxArg = "yaml",
    live_text: Annotated[
        bool,
        Field(
            description=(
                "Emit selectable <text> rather than glyph outlines: about a third the size, "
                "but it depends on the viewer having a matching font"
            )
        ),
    ] = False,
    aria: Annotated[
        bool,
        Field(
            description=(
                "Make each panel an image a screen reader can read: named with what it shows, "
                "then everything said in it, in reading order. False writes none of it, for "
                "a pipeline that post-processes the SVG"
            )
        ),
    ] = True,
    files: FilesArg = None,
    *,
    mono: Annotated[
        bool,
        Field(
            description=(
                "Draw every value as its grey and ignore any palette's colour, as `scenet "
                "build --mono` does: a black-and-white edition, byte for byte what "
                "`palette: mono` draws"
            )
        ),
    ] = False,
    conditioning: Annotated[
        bool,
        Field(
            description=(
                "Also export each panel's staging for image models, as `scenet build "
                "--conditioning` does: an OpenPose pose, boxes with phrases, a depth map, a "
                "mask and the semantics, five more resources per panel after the pages"
            )
        ),
    ] = False,
) -> list[TextContent | EmbeddedResource]:
    """Compile a document and return each panel as SVG.

    The SVG is exactly what `scenet build --embed-images` writes, one embedded
    `image/svg+xml` resource per panel, after a short text summary with the compiler's
    notes. A picture the document is drawn over is written into it, since whoever reads
    the SVG has no folder to find a linked one in. A
    document that does not compile is an error carrying the same findings `validate`
    reports.

    A document with `pages:` gets one more resource per page, `scenet://pages/<n>.svg`,
    after the panels: each panel at its frame, exactly as `scenet build` writes the page.

    With `conditioning`, each panel's exports for image models follow, five per panel:
    `scenet://panels/<name>.pose.json`, `.boxes.json`, `.depth.svg`, `.mask.svg` and
    `.semantics.json`, exactly as `scenet build --conditioning` writes them.

    Returns:
        A summary, then one SVG resource per panel in reading order, then one per page,
        then, when asked, each panel's exports for image models.

    Raises:
        ~mcp.server.mcpserver.exceptions.ToolError: The document does not compile. The
            message lists every finding.
    """
    book = _compile(source, syntax, _files(files))
    results = book.panels
    count = f"{len(results)} panel{'' if len(results) == 1 else 's'}"
    pages = f" and {len(book.pages)} page{'' if len(book.pages) == 1 else 's'}"
    lines = [f"Rendered {count}{pages if book.pages else ''}: {', '.join(results)}."]
    if conditioning:
        lines.append("Each panel's staging is exported for image models, after the pages.")
    lines.extend(
        f"note ({name}): {note}" for name, result in results.items() for note in result.notes
    )
    # SVG goes out as an embedded resource and never as an image block. Hosts pass image
    # blocks to the model, and model APIs that accept images do not accept SVG -- so an
    # image block would fail the whole turn rather than show a picture.
    blocks: list[TextContent | EmbeddedResource] = [TextContent(type="text", text="\n".join(lines))]
    blocks.extend(
        EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri=f"scenet://panels/{name}.svg",
                mime_type="image/svg+xml",
                text=render(
                    result.core,
                    fonts=result.fonts,
                    live_text=live_text,
                    mono=mono,
                    aria=aria,
                    embed=book.images,
                ),
            ),
        )
        for name, result in results.items()
    )
    cores = {name: result.core for name, result in results.items()}
    blocks.extend(
        EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri=f"scenet://pages/{number}.svg",
                mime_type="image/svg+xml",
                text=render_page(
                    page,
                    cores,
                    live_text=live_text,
                    mono=mono,
                    fonts=book.fonts,
                    aria=aria,
                    embed=book.images,
                ),
            ),
        )
        for number, page in enumerate(book.pages, start=1)
    )
    if conditioning:
        blocks.extend(
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=f"scenet://panels/{name}{suffix}",
                    mime_type="application/json" if suffix.endswith(".json") else "image/svg+xml",
                    text=export(result.core),
                ),
            )
            for name, result in results.items()
            for suffix, export in EXPORTS
        )
    return blocks


#: Tool name, title and function. `compile` is the name a client sees; the Python
#: function is `compile_panel`, so as not to shadow the builtin.
TOOLS: tuple[tuple[str, str, Callable[..., Any]], ...] = (
    ("get_spec", "Read the Scenet specification", get_spec),
    ("list_puppets", "List the characters", list_puppets),
    ("validate", "Check a panel document", validate),
    ("compile", "Compile a panel to Panel Core", compile_panel),
    ("render", "Render a panel to SVG", render_panel),
)


_LOG = logging.getLogger(__name__)


class Server(MCPServer[Any]):
    """The SDK's server, with a crash in a tool reported as the bug it is, and closable.

    The SDK already turns any exception a tool raises into an error result, so a crash
    never ends the session; but the result says only "Error executing tool render",
    which nobody can act on. Here it says what the command line says of the same crash:
    an internal error, its type and message, and where to report it. The traceback goes
    to the server's log, on stderr, and never to the client.
    """

    def __init__(self, *, workers: "_Workers | None" = None, **options: Any) -> None:  # noqa: ANN401 -- the SDK's own options
        """Build the server.

        Args:
            workers: The worker processes its calls run in, when they are bounded in time.
            **options: The SDK's: its name, title, version, instructions and website.
        """
        super().__init__(**options)
        self._workers = workers

    def close(self) -> None:
        """Stop every worker process the server started, idle or not."""
        if self._workers is not None:
            self._workers.close()

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Context[Any, Any] | None = None
    ) -> CallToolResult | InputRequiredResult:
        """Call a tool, a crash in it reported as the command line reports one.

        :meta private:

        Args:
            name: The tool.
            arguments: Its arguments.
            context: The SDK's request context.

        Returns:
            The tool's result.
        """
        try:
            return await super().call_tool(name, arguments, context)
        except UnexpectedToolError as exc:
            crash = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
            _LOG.error("tool %r crashed", name, exc_info=crash)
            raise ToolError(describe_failure(crash)) from crash


def build_server(*, timeout: float | None = None) -> "Server":
    """Build the server with every tool registered, without starting it.

    Separate from :func:`serve <scenet.mcp.serve>` so that a test, or a host embedding
    Scenet in a server of its own, can connect to it in process.

    Args:
        timeout: The most seconds one tool call may take. Given, each call runs in a
            worker process that is stopped once it runs past it, or once the client
            cancels it. `None`, the default, runs every call in process, unbounded.

    Returns:
        The server, ready to run on any transport. Its `close()` stops the worker
        processes it started; :func:`serve` calls it once the server has stopped.
    """
    workers = None if timeout is None else _Workers(timeout)
    server = Server(
        workers=workers,
        name="scenet",
        title="Scenet",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url=WEBSITE,
    )
    for name, title, function in TOOLS:
        run = function if workers is None else _bounded(name, function, workers)
        server.tool(name=name, title=title, description=_describe(function), annotations=READ_ONLY)(
            run
        )
    return server


def serve(
    transport: Literal["stdio", "streamable-http"],
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: float = DEFAULT_TIMEOUT,
    origins: Sequence[str] = (),
) -> None:
    """Run the server until the client disconnects.

    Over Streamable HTTP it keeps no session, refuses a body over
    :data:`MAX_REQUEST_BYTES`, and serves only a `Host` naming it and an `Origin` of its own
    -- or one of `origins`. Whether it may listen beyond this machine is the caller's to
    decide: `scenet mcp` refuses to without `--allow-remote`.

    Args:
        transport: `stdio` for a local client that launches the server itself, or
            `streamable-http` to listen for remote ones.
        host: Where Streamable HTTP listens.
        port: Its port.
        timeout: The most seconds one tool call may take.
        origins: Origins a browser client may call from, beyond the server's own.
    """
    server = build_server(timeout=timeout)
    try:
        if transport == "stdio":
            server.run("stdio")
            return
        server.run(
            "streamable-http",
            host=host,
            port=port,
            stateless_http=True,
            max_request_body_size=MAX_REQUEST_BYTES,
            transport_security=_security(host, port, origins),
        )
    finally:
        server.close()


def _security(host: str, port: int, origins: Sequence[str]) -> TransportSecuritySettings:
    """Which `Host` and `Origin` headers the server answers: its own, at its own port.

    The SDK's own default for a local server accepts an `Origin` of `http://localhost` at
    any port, which is any local web page; here it is the server's port alone, and whatever
    `origins` adds.
    """
    local = ["127.0.0.1", "localhost", "[::1]"]
    named = f"[{host}]" if ":" in host else host
    hosts = [*local, *([] if named in local else [named])]
    # DNS-rebinding protection is the settings' own default, and stays on.
    return TransportSecuritySettings(
        allowed_hosts=[f"{name}:{port}" for name in hosts],
        allowed_origins=[*(f"http://{name}:{port}" for name in local), *origins],
    )


def _bounded(
    name: str, function: Callable[..., Any], workers: "_Workers"
) -> Callable[..., Awaitable[Any]]:
    """A tool that runs `function` in a worker, with its signature, so its schema is its own."""

    @functools.wraps(function)
    async def call(**arguments: Any) -> Any:  # noqa: ANN401 -- whatever the tool returns
        return await workers.call(name, arguments)

    return call


class _Worker:
    """One process that runs tool calls, one at a time, until it is stopped."""

    def __init__(self) -> None:
        context = multiprocessing.get_context("spawn")
        self._connection, theirs = context.Pipe()
        self._process = context.Process(target=_serve_calls, args=(theirs,), daemon=True)
        self._process.start()
        theirs.close()
        self._starting = True

    async def ready(self) -> None:
        """Wait until it has started, imported the compiler and read the shipped files.

        Not part of any call's time: a call is timed from when a worker can take it.
        """
        if self._starting:
            await to_thread.run_sync(self._connection.recv, abandon_on_cancel=True)
            self._starting = False

    async def run(self, name: str, arguments: dict[str, Any]) -> tuple[str, Any]:
        """Send one call, and wait, without holding the event loop, for what came of it."""
        self._connection.send((name, arguments))
        return await to_thread.run_sync(self._connection.recv, abandon_on_cancel=True)

    def stop(self) -> None:
        """Kill the process, whatever it is doing."""
        self._process.kill()
        self._process.join()
        self._connection.close()


class _Workers:
    """Tool calls in worker processes: at most `WORKERS` at once, each bounded in time."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._idle: list[_Worker] = []
        self._slots = anyio.CapacityLimiter(WORKERS)

    def close(self) -> None:
        """Stop every idle worker; a busy one is stopped by the call that holds it."""
        while self._idle:
            self._idle.pop().stop()

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:  # noqa: ANN401
        async with self._slots:
            worker = self._idle.pop() if self._idle else _Worker()
            try:
                await worker.ready()
                with anyio.fail_after(self.timeout):
                    outcome, value = await worker.run(name, arguments)
            except TimeoutError:
                worker.stop()
                # The next call should not wait for a worker to start: one starts now.
                self._idle.append(_Worker())
                raise ToolError(
                    f"the call took longer than {self.timeout:g} seconds, the most this server "
                    "gives one, and was stopped; a balloon of hundreds of words is the usual "
                    "cause: shorten it, or split it into several"
                ) from None
            except BaseException:
                # Cancelled by the client, or the server is stopping: the work stops too.
                worker.stop()
                raise
            self._idle.append(worker)
        if outcome != "done":
            raise ToolError(value)
        return value


#: A panel whose compile reads every shipped file a first call would.
_WARM = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"


def _serve_calls(connection: Connection) -> None:
    """A worker's loop: run each call it is sent, and send back what came of it.

    A tool's own error comes back as its message; any other failure as the line the
    command line prints for one, since an exception need not survive the trip back.
    """
    functions = {name: function for name, _, function in TOOLS}
    # The first compile in a process reads the shipped fonts and puppets: done here, before
    # the worker says it is ready, so that no call's time is spent on it.
    compile_book(_WARM)
    connection.send(("ready", None))
    while True:
        try:
            name, arguments = connection.recv()
        except EOFError:
            return
        try:
            connection.send(("done", functions[name](**arguments)))
        except ToolError as exc:
            connection.send(("error", str(exc)))
        except Exception as exc:
            connection.send(("crash", describe_failure(exc)))


def _describe(function: Callable[..., Any]) -> str:
    """A tool's description: its docstring, up to the first Google-style section.

    `Returns:` and `Raises:` are for Python readers; the schema already says what comes
    back. Everything before them is written for the model.
    """
    doc = inspect.getdoc(function) or ""
    match = re.search(r"^(Args|Returns|Raises|Example|Examples):$", doc, re.MULTILINE)
    return (doc[: match.start()] if match else doc).strip()


def _files(sent: dict[str, str] | None) -> dict[str, bytes] | None:
    """The files sent beside a document, decoded, or a tool error saying which one is bad.

    A path is held to the rules a document's own paths are -- relative, `/` between
    folders -- so a file sent is one a document could have named.
    """
    if not sent:
        return None
    decoded: dict[str, bytes] = {}
    for name, encoded in sent.items():
        try:
            check_relative(name, what="file", rule="image-file")
            decoded[name] = base64.b64decode(encoded, validate=True)
        except (ScenetError, binascii.Error, ValueError) as exc:
            raise ToolError(f"files: {name!r} cannot be taken: {exc}") from exc
    return decoded


def _diagnose(
    source: str, syntax: Syntax, *, deep: bool, files: dict[str, bytes] | None = None
) -> list[Diagnostic]:
    if syntax == "script":
        return diagnose_script(source, deep=deep, base=files)
    return diagnose_source(source, deep=deep, base=files)


def _finding(item: Diagnostic) -> Finding:
    region = item.region or DOCUMENT_START
    return Finding(
        rule=f"{RULE_NAMESPACE}/{item.rule}",
        level=item.level,
        message=item.message,
        fix=RULES[item.rule].help,
        help_uri=help_uri(item.rule),
        where=".".join(str(step) for step in item.path),
        line=region.start.line,
        column=region.start.column,
        end_line=region.end.line,
        end_column=region.end.column,
    )


def _compile(source: str, syntax: Syntax, files: dict[str, bytes] | None = None) -> Book:
    """Compile every panel and page, or raise a tool error that lists every finding.

    The success path compiles once. Only a failure pays for the deep check, which is
    what turns "the solver gave up" into a located finding with a rule and a fix.
    """
    try:
        library = default_library()
        if syntax == "yaml":
            return compile_book(source, library=library, base=files)
        return compile_script(source, library=library, base=files)
    except ScenetError as exc:
        # Only errors explain a failure: a note is a house limit the document can exceed.
        # The cheap check first, which costs no compile: only a document it finds clean
        # pays for the deep one. Either runs in the same worker, under the same clock, as
        # the compile that failed.
        found = _errors(_diagnose(source, syntax, deep=False, files=files)) or _errors(
            _diagnose(source, syntax, deep=True, files=files)
        )
        if not found:
            # A clean deep check means a successful build -- the diagnostics tests hold
            # the two to that -- so this is a disagreement between them, and is reported
            # as one rather than hidden behind an empty list.
            raise ToolError(
                f"the document did not compile, but no rule explains why: {exc}"
            ) from exc
        raise ToolError(_report(found)) from exc


def _errors(found: list[Diagnostic]) -> list[Diagnostic]:
    """The findings that are errors: a note is a house limit a document can exceed."""
    return [item for item in found if item.level == "error"]


def _report(found: list[Diagnostic]) -> str:
    """Findings as text, for hosts that show a model only the text of an error."""
    count = f"{len(found)} problem{'' if len(found) == 1 else 's'}"
    entries = []
    for item in found:
        finding = _finding(item)
        where = f" at {finding.where}" if finding.where else ""
        entries.append(
            f"{finding.line}:{finding.column} {finding.rule}{where}\n"
            f"  {finding.message}\n"
            f"  fix: {finding.fix}"
        )
    return f"The document has {count}. Fix each, then validate again.\n\n" + "\n\n".join(entries)
