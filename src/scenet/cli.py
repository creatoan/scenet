"""Command-line entry point."""

import argparse
import importlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

from scenet import __version__
from scenet.assets.artwork import CONTRACT_SUFFIX
from scenet.diagnostics import Diagnostic, diagnose_file, to_sarif
from scenet.emit.debug_svg import render_debug
from scenet.emit.export import EXPORTS
from scenet.emit.page import render_page
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.errors import ScenetError
from scenet.pipeline import FRONTENDS, Book, compile_book_file
from scenet.schema import artwork_schema, panel_schema, scene_schema

DESCRIPTION = "Compile a semantic comic-panel description into SVG."

EPILOGUE = """\
Scenet is a deterministic compiler: the same source always produces byte-identical
output. No generative image model is involved at any stage.

See docs/reference/language.md for the language.
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the `scenet` command.

    Exposed separately from :func:`main <scenet.cli.main>` so that tests, shell-completion
    generators and documentation tooling can inspect the interface without running it.

    Returns:
        A parser with the `build`, `check`, `schema` and `mcp` subcommands defined.
    """
    parser = argparse.ArgumentParser(
        prog="scenet",
        description=DESCRIPTION,
        epilog=EPILOGUE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"scenet {__version__}")

    subcommands = parser.add_subparsers(dest="command")
    build = subcommands.add_parser("build", help="compile a panel source to SVG")
    build.add_argument(
        "source",
        type=Path,
        help="a *.panel.yaml or *.scene.yaml document, or a *.script comic script",
    )
    build.add_argument(
        "-o",
        "--output",
        help=(
            "output SVG path, or a directory to write into under the default name "
            "(default: alongside the source)"
        ),
    )
    build.add_argument(
        "--core",
        action="store_true",
        help="also write the resolved Panel Core JSON, the inspectable intermediate tier",
    )
    build.add_argument(
        "--debug",
        action="store_true",
        help="also write a diagnostic overlay showing hulls, face zones, anchors and gaze",
    )
    build.add_argument(
        "--conditioning",
        action="store_true",
        help=(
            "also export each panel's staging for image models: an OpenPose pose, boxes "
            "with phrases, a depth map, a mask and the semantics, beside its SVG"
        ),
    )
    build.add_argument(
        "--live-text",
        action="store_true",
        help=(
            "emit selectable <text> instead of glyph outlines; smaller, but depends on the "
            "reader having a metrically compatible font installed"
        ),
    )
    build.add_argument(
        "--mono",
        action="store_true",
        help=(
            "draw every value as its grey, ignoring any palette's colour: a black-and-white "
            "edition, byte for byte what palette: mono draws"
        ),
    )
    build.add_argument(
        "--no-aria",
        dest="aria",
        action="store_false",
        help=(
            "write no accessibility markup -- no role, title, desc or aria attributes -- "
            "for a pipeline that post-processes the SVG; it is otherwise byte-identical"
        ),
    )
    build.add_argument(
        "--embed-images",
        action="store_true",
        help=(
            "write each supplied picture into the SVG as a data: URI, so the file stands "
            "alone; by default it links the picture by the path the document wrote"
        ),
    )
    build.add_argument(
        "--strip",
        action="store_true",
        help="for a multi-panel document, also lay the panels out as a strip",
    )
    build.add_argument("--quiet", action="store_true", help="suppress diagnostic notes")

    check = subcommands.add_parser(
        "check",
        help="validate documents without compiling them",
        description=(
            "Report everything wrong with one or more documents, and exit non-zero if "
            "anything is an error. A note -- a balloon over a publisher's word limit, say "
            "-- is reported but does not fail the check. Nothing is written unless you ask "
            "for it.\n\n"
            "The default output is the same prose the compiler prints. `--format sarif` "
            "emits SARIF 2.1.0, which GitHub code scanning ingests directly and which "
            "editors and agents can consume -- the checks that matter most here, such as "
            "an actor id that does not resolve to a cast member, cannot be expressed in "
            "the published JSON Schema, so this is the only machine-readable form of "
            "them."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    check.add_argument(
        "sources",
        type=Path,
        nargs="+",
        help="documents to check; several may be given, and all are reported together",
    )
    check.add_argument(
        "--format",
        choices=("text", "sarif"),
        default="text",
        dest="format",
        help="text for people (default), sarif for everything else",
    )
    check.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write the report to a file instead of stdout",
    )
    check.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the per-file success line; findings are always reported",
    )
    check.add_argument(
        "--deep",
        action="store_true",
        help=(
            "also run the full compiler on documents that pass every cheap check, to "
            "additionally catch layout and balloon-placement failures; costs a real "
            "compile, including font metrics, so off by default"
        ),
    )

    schema = subcommands.add_parser(
        "schema",
        help="print the JSON Schema for a panel document",
        description=(
            "Emit the JSON Schema describing a panel, derived from the same models the "
            "compiler validates against. Editors use it for completion and inline "
            "validation, so what the editor suggests cannot drift from what compiles."
        ),
    )
    schema.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")
    which = schema.add_mutually_exclusive_group()
    which.add_argument(
        "--scene",
        action="store_true",
        help="emit the multi-panel scene schema instead of the single-panel one",
    )
    which.add_argument(
        "--artwork",
        action="store_true",
        help="emit the schema for an artwork contract, the *.art.yaml beside a picture",
    )

    mcp = subcommands.add_parser(
        "mcp",
        help="serve the compiler to a model over the Model Context Protocol",
        description=(
            "Run an MCP server whose tools read the specification, list the characters, "
            "validate, compile and render -- so a model can check its own panel and fix "
            "what it got wrong, with nobody relaying error text. Needs the optional "
            "extra: pip install 'scenet[mcp]'.\n\n"
            "stdio is for a client that launches the server itself; streamable-http "
            "listens for remote clients, and has no authentication, so it binds to "
            "localhost unless told otherwise."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mcp.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio (default) or streamable-http",
    )
    mcp.add_argument(
        "--host", default="127.0.0.1", help="address to listen on, for streamable-http"
    )
    mcp.add_argument("--port", type=int, default=8000, help="port, for streamable-http")
    return parser


def _refuse_unsupported(paths: Sequence[Path]) -> bool:
    """Report every path no frontend reads, and say whether there were any.

    `build` dispatches on the extension, so a file it has no frontend for is a mistake in
    the invocation rather than in a panel -- the same class as a missing file, and
    reported the same way rather than escaping as a traceback.
    """
    expected = ", ".join(sorted(FRONTENDS))
    refused = [path for path in paths if path.suffix.lower() not in FRONTENDS]
    for path in refused:
        print(
            f"scenet: {path}: unsupported extension '{path.suffix}'; expected one of {expected}",
            file=sys.stderr,
        )
    # A contract is YAML, and read as a panel it would be a page of unknown keys. It is
    # checked through a panel that casts its figures, which is what knows its picture.
    contracts = [path for path in paths if path.name.lower().endswith(CONTRACT_SUFFIX)]
    for path in contracts:
        print(
            f"scenet: {path}: an artwork contract is not a document; it is checked through "
            "the panel that casts its figures, beside its picture",
            file=sys.stderr,
        )
    return bool(refused or contracts)


def run_build(args: argparse.Namespace) -> int:
    """Run the `build` subcommand: compile a document and write its outputs.

    Args:
        args: Parsed arguments from :func:`build_parser <scenet.cli.build_parser>`.

    Returns:
        A process exit status: `0` on success, `1` when the document could not be
        compiled, `2` when the source file does not exist or has an extension no
        frontend reads.

    Every error the compiler can raise inherits `ScenetError`, and all of them mean
    "your panel cannot be compiled" rather than "scenet broke" -- so they are reported
    as a plain one-line message rather than a traceback.
    """
    source: Path = args.source
    if not source.exists():
        print(f"scenet: no such file: {source}", file=sys.stderr)
        return 2
    if _refuse_unsupported([source]):
        return 2

    try:
        book = compile_book_file(source)
    except ScenetError as exc:
        # Every ScenetError is "your panel cannot be compiled" rather than "scenet
        # broke", so they all get a plain message instead of a traceback.
        #
        # KeyError stringifies as repr(args[0]), which wraps the message in whichever
        # quote style avoids escaping -- so a message containing an apostrophe comes
        # out double-quoted. Reading args[0] directly sidesteps that entirely.
        message = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
        print(f"scenet: {message}", file=sys.stderr)
        return 1

    # `foo.panel.yaml` becomes `foo.svg`, not `foo.panel.svg`.
    stem = (
        source.name.removesuffix(".yaml")
        .removesuffix(".yml")
        .removesuffix(".script")
        .removesuffix(".panel")
        .removesuffix(".scene")
    )
    base = _output_base(args.output, source, f"{stem}.svg")
    base.parent.mkdir(parents=True, exist_ok=True)

    single = len(book.panels) == 1 and "panel" in book.panels
    if _refuse_unusable_names(book):
        return 2
    outputs = _outputs(book, base, args, single=single)
    if _refuse_clashes(outputs):
        return 2

    # Everything is checked before anything is written, so a refusal leaves no half-built
    # set of files behind.
    for path, content in outputs:
        path.write_text(content(), encoding="utf-8", newline="\n")

    if not args.quiet:
        for path, _ in outputs:
            print(f"wrote {path}")
        # What reading the document noticed, each naming its line, then what the compiler
        # decided in each panel.
        for note in book.notes:
            print(f"note: {note}")
        for note in _links_away_from(book, source, base, embedded=args.embed_images):
            print(f"note: {note}")
        for name, result in book.panels.items():
            for note in result.notes:
                print(f"note: {note}" if single else f"note: {name}: {note}")
    return 0


def _links_away_from(book: Book, source: Path, base: Path, *, embedded: bool) -> list[str]:
    """What to say about pictures linked from an SVG written away from its document.

    A link is the path the document wrote, which a viewer reads from beside the SVG. Beside
    the document -- where `build` writes by default -- that finds the picture; anywhere
    else it does not, and the SVG would show nothing where the picture should be. The
    path is not rewritten to climb back: librsvg refuses a link out of the SVG's folder,
    so that would only move the failure.
    """
    if embedded or base.parent.resolve() == source.parent.resolve():
        return []
    linked = sorted(
        {
            result.core.backdrop.image.href
            for result in book.panels.values()
            if result.core.backdrop is not None and result.core.backdrop.image is not None
        }
    )
    return [
        f"{href} is linked, and a viewer looks for it beside the SVG, in {base.parent}, "
        "not beside the document; copy it there, or build with --embed-images"
        for href in linked
    ]


#: One file `build` will write, and how to produce what goes in it -- deferred, so that
#: the whole set can be checked for clashes before any of it is rendered.
_Output = tuple[Path, Callable[[], str]]


def _outputs(book: Book, base: Path, args: argparse.Namespace, *, single: bool) -> list[_Output]:
    """Every file a build writes, in the order it writes them.

    A single-panel document writes to the requested name; a sequence suffixes each panel
    with its own name, so the mapping back to source is obvious. A strip needs more than
    one panel to lay out. Each page goes to `stem.page-<n>.svg`, beside the panels. The
    exports for image models are per panel only: a page adds no layout to a panel, and its
    Page Core says where every frame is.
    """
    outputs: list[_Output] = []
    embed = book.images if args.embed_images else None
    for name, result in book.panels.items():
        core = result.core
        target = base if single else base.with_name(f"{base.stem}.{name}{base.suffix}")
        outputs.append(
            (
                target,
                partial(
                    render,
                    core,
                    fonts=book.fonts,
                    live_text=args.live_text,
                    mono=args.mono,
                    aria=args.aria,
                    embed=embed,
                ),
            )
        )
        if args.core:
            outputs.append((target.with_suffix(".core.json"), core.to_json))
        if args.debug:
            outputs.append(
                (target.with_name(f"{target.stem}.debug.svg"), partial(render_debug, core))
            )
        if args.conditioning:
            outputs.extend(
                (target.with_name(f"{target.stem}{suffix}"), partial(export, core))
                for suffix, export in EXPORTS
            )

    if args.strip and len(book.panels) > 1:
        strip = [(name, result.core) for name, result in book.panels.items()]
        outputs.append(
            (
                base.with_name(f"{base.stem}.strip.svg"),
                partial(
                    render_strip,
                    strip,
                    live_text=args.live_text,
                    mono=args.mono,
                    fonts=book.fonts,
                    aria=args.aria,
                    embed=embed,
                ),
            )
        )

    cores = {name: result.core for name, result in book.panels.items()}
    for number, page in enumerate(book.pages, start=1):
        target = base.with_name(f"{base.stem}.page-{number}{base.suffix}")
        outputs.append(
            (
                target,
                partial(
                    render_page,
                    page,
                    cores,
                    live_text=args.live_text,
                    mono=args.mono,
                    fonts=book.fonts,
                    aria=args.aria,
                    embed=embed,
                ),
            )
        )
        if args.core:
            outputs.append((target.with_suffix(".core.json"), page.to_json))
        if args.debug:
            outputs.append(
                (
                    target.with_name(f"{target.stem}.debug.svg"),
                    partial(render_page, page, cores, debug=True),
                )
            )
    return outputs


#: Characters a panel's name cannot hold once it is part of a file name. Both
#: separators, on every platform, so a document builds the same everywhere.
_UNUSABLE_IN_A_NAME = ("/", "\\")


def _refuse_unusable_names(book: Book) -> bool:
    """Report a panel whose name would make its file a path into another directory.

    Returns:
        Whether one was refused.
    """
    unusable = sorted(
        name for name in book.panels if any(mark in name for mark in _UNUSABLE_IN_A_NAME)
    )
    if unusable:
        print(
            f"scenet: panel name {unusable[0]!r} cannot be part of a file name, because "
            "'/' and '\\' separate directories; rename the panel",
            file=sys.stderr,
        )
        return True
    return False


def _refuse_clashes(outputs: list[_Output]) -> bool:
    """Report two outputs that would be written to the same file.

    A panel named `page-1`, `strip` or `x.debug` would otherwise silently replace a page,
    the strip or panel `x`'s overlay -- exactly the kind of loss Scenet refuses everywhere
    else. Paths are compared ignoring case, because Windows and macOS do, and a document
    should build the same set of files everywhere.

    Returns:
        Whether a clash was refused.
    """
    seen: dict[str, Path] = {}
    for path, _ in outputs:
        key = str(path).casefold()
        if key in seen:
            print(
                f"scenet: two outputs would both be written to {path}"
                + (f" (and {seen[key]})" if seen[key] != path else "")
                + "; rename the panel that clashes",
                file=sys.stderr,
            )
            return True
        seen[key] = path
    return False


def _output_base(written: str | None, source: Path, default: str) -> Path:
    """Where `build` writes its main output, from what `-o` said.

    A path naming a directory -- one that exists, or one written with a trailing
    separator, as `out/` -- takes the default name inside it, as `cp` does. Anything
    else is the file to write, whether or not it has a suffix.

    Args:
        written: The `-o` argument exactly as given, or `None` when there was none.
        source: The document being built.
        default: The name the output takes beside its source.

    Returns:
        The path of the main SVG; every other output is named after it.
    """
    if written is None:
        return source.with_name(default)
    path = Path(written)
    separators = tuple(separator for separator in (os.sep, os.altsep) if separator)
    if written.endswith(separators) or path.is_dir():
        return path / default
    return path


def _refuse_directory(output: Path | None) -> bool:
    """Report an `-o` that names a directory, for a command that writes one file.

    Returns:
        Whether it was refused.
    """
    if output is not None and output.is_dir():
        print(f"scenet: {output} is a directory; -o names the file to write", file=sys.stderr)
        return True
    return False


def run_check(args: argparse.Namespace) -> int:
    """Run the `check` subcommand: validate documents and report what is wrong.

    Args:
        args: Parsed arguments from :func:`build_parser <scenet.cli.build_parser>`.

    Returns:
        A process exit status: `0` when no document has an error (notes may have been
        printed), `1` when any has one, `2` when a file does not exist or has an
        extension no frontend reads.

    Unlike `build`, this never stops at the first fault. pydantic reports every field
    error at once and a run over several files reports all of them, because a caller
    fixing them -- a person or an agent -- wants the whole list, not one round trip per
    mistake.
    """
    sources: list[Path] = args.sources
    missing = [path for path in sources if not path.exists()]
    for path in missing:
        print(f"scenet: no such file: {path}", file=sys.stderr)
    if missing:
        return 2
    # Checked as `build` would read it, or not at all: calling a file `build` refuses
    # "ok" would be a confident false clean.
    if _refuse_unsupported(sources) or _refuse_directory(args.output):
        return 2

    found: list[Diagnostic] = []
    for path in sources:
        found.extend(diagnose_file(path, deep=args.deep))
    # A note reports a house limit, and the document still compiles: only an error fails.
    status = 1 if any(item.level == "error" for item in found) else 0

    if args.format == "sarif":
        # Relative to the working directory, which is the repository root under CI and
        # is what code scanning matches results against.
        document = to_sarif(found, root=Path.cwd())
        # A trailing newline because this is a text file people will `cat`, and JSON
        # without one is a nuisance in a terminal and in a diff.
        report = f"{json.dumps(document, indent=2, ensure_ascii=False)}\n"
        if args.output:
            _write_report(args.output, report, quiet=args.quiet)
        else:
            # stdout carries the document and nothing else, so that
            # `scenet check --format sarif x > results.sarif` produces a parseable file.
            _print_document(report)
        return status

    lines = []
    for item in found:
        where = item.source if item.source else "<string>"
        line = item.region.start.line if item.region else 1
        column = item.region.start.column if item.region else 1
        # A note says so where a compiler puts it, after the position; an error's line is
        # unchanged, so nothing that reads it has to learn a new shape.
        level = "note: " if item.level == "note" else ""
        lines.append(f"{where}:{line}:{column}: {level}{item.rule}: {item.message}\n")
    if args.output:
        # The report and nothing else, as for SARIF: empty when every document is valid.
        _write_report(args.output, "".join(lines), quiet=args.quiet)
        return status
    sys.stderr.write("".join(lines))

    if not status and not args.quiet:
        for path in sources:
            print(f"{path}: ok")
    return status


def _write_report(output: Path, report: str, *, quiet: bool) -> None:
    """Write a report where `-o` said, and say so unless asked to be quiet."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    if not quiet:
        print(f"wrote {output}")


def run_schema(args: argparse.Namespace) -> int:
    """Emit the panel JSON Schema.

    Generated from the pydantic models rather than hand-written, so editor completion
    is derived from the compiler's own definition of the language and the two cannot
    disagree. It describes the syntax as written, not the IR it normalises into; see
    :mod:`scenet.schema <scenet.schema>`.
    """
    if _refuse_directory(args.output):
        return 2
    which = "artwork" if args.artwork else "scene" if args.scene else "panel"
    schema = {"panel": panel_schema, "scene": scene_schema, "artwork": artwork_schema}[which]()
    document = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        _print_document(document)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    return 0


def _print_document(document: str) -> None:
    """Write a document to stdout as UTF-8 with LF line endings, whatever the platform.

    A text-mode stdout translates each line ending to the platform's and encodes with
    the console's code page, so on Windows `scenet schema > schema.json` came out with
    CRLF, unlike the same command on Linux, and a SARIF report naming a character outside
    cp1252 could not be printed at all. A document redirected to a file is held to the same
    rule as one written with `-o`: the same bytes everywhere.
    """
    sys.stdout.flush()
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        # Replaced by something with no bytes underneath, such as a `StringIO`; there is
        # no translation to avoid.
        sys.stdout.write(document)
        return
    buffer.write(document.encode("utf-8"))
    buffer.flush()


def run_mcp(args: argparse.Namespace) -> int:
    """Run the `mcp` subcommand: serve the tools until the client disconnects.

    Args:
        args: Parsed arguments from :func:`build_parser <scenet.cli.build_parser>`.

    Returns:
        A process exit status: `0` once the client has gone, `2` when the optional `mcp`
        dependency is not installed.

    Nothing is printed to stdout, before or after: on the stdio transport stdout is the
    protocol stream. The server module is imported here rather than at the top of the
    file, so every other command works without the extra installed.
    """
    try:
        server = importlib.import_module("scenet.mcp")
    except ImportError as exc:
        # Only a missing `mcp` package means a missing extra. Anything else is a real
        # fault inside Scenet, and dressing it up as an installation hint would hide it.
        if not (exc.name or "").partition(".")[0] == "mcp":
            raise
        print(
            "scenet: the MCP server needs the optional 'mcp' dependency: pip install 'scenet[mcp]'",
            file=sys.stderr,
        )
        return 2

    if args.transport == "stdio":
        server.serve("stdio")
    else:
        server.serve("streamable-http", host=args.host, port=args.port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the `scenet` command.

    Args:
        argv: Arguments to parse. Defaults to `sys.argv[1:]`, which is what happens
            when the installed console script runs; pass a list explicitly from tests.

    Returns:
        A process exit status. `0` on success, `1` for a document that will not
        compile, `2` for a usage error or a missing file.

    Example:
        >>> from scenet.cli import main
        >>> main(["--definitely-not-a-flag"])
        Traceback (most recent call last):
          ...
        SystemExit: 2
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build":
        return run_build(args)
    if args.command == "check":
        return run_check(args)
    if args.command == "schema":
        return run_schema(args)
    if args.command == "mcp":
        return run_mcp(args)
    # No subcommand. Help goes to stderr and the status is 2, matching the convention
    # argparse itself uses for a usage error -- a bare `scenet` did not do anything,
    # and a script that runs it should not read that as success.
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
