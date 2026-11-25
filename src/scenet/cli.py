"""Command-line entry point."""

import argparse
import importlib
import ipaddress
import json
import math
import os
import posixpath
import sys
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from scenet import __version__
from scenet.assets.artwork import CONTRACT_SUFFIX
from scenet.assets.contract import PUPPET_SUFFIX
from scenet.core import PanelCore
from scenet.diagnostics import Diagnostic, diagnose_file, to_sarif
from scenet.emit.debug_svg import render_debug
from scenet.emit.export import EXPORTS
from scenet.emit.page import render_page
from scenet.emit.pdf import print_notes, printed_panels, render_pdf
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.errors import ScenetError
from scenet.paths import within
from scenet.pipeline import FRONTENDS, Book, compile_book_file
from scenet.schema import artwork_schema, panel_schema, puppet_schema, scene_schema
from scenet.watch import watch_loop

DESCRIPTION = "Compile a semantic comic-panel description into SVG."

EPILOGUE = """\
Scenet is a deterministic compiler: the same source always produces byte-identical
output. No generative image model is involved at any stage.

See https://creatoan.github.io/scenet/reference/language/ for the language.
"""

#: Where a bug is reported: what an internal error says to do.
ISSUES = "https://github.com/creatoan/scenet/issues"

#: The status of a fault in Scenet itself rather than in a document or a file:
#: `EX_SOFTWARE` from BSD's `sysexits.h`, which tells a script "not your input".
EXIT_INTERNAL = 70

#: The status of a command stopped by Ctrl-C: 128 plus `SIGINT`, as a shell reports it.
EXIT_INTERRUPTED = 130

#: Set to anything but empty or `0`, the same as `--traceback`.
DEBUG_VARIABLE = "SCENET_DEBUG"


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
    parser.add_argument(
        "--traceback",
        action="store_true",
        help=(
            f"print the traceback of an internal error, for its report; {DEBUG_VARIABLE}=1 "
            "does the same"
        ),
    )

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
            "the SVG to write, a name ending in .svg; or a folder to write into under the "
            "default name: one that exists, or a name ending in / or with no extension "
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
            "emit selectable <text> instead of glyph outlines; smaller, but the SVG depends "
            "on the reader having a metrically compatible font installed; the print PDF "
            "embeds its faces, where their licences allow"
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
    build.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "also write the document as a print PDF beside the SVGs: lettering on the black "
            "plate, a page unit printed as 0.1 mm, a page's bleed around its trim"
        ),
    )
    build.add_argument("--quiet", action="store_true", help="suppress diagnostic notes")
    build.add_argument(
        "--watch",
        action="store_true",
        help="rebuild when a source or compilation dependency changes",
    )
    build.add_argument(
        "--root",
        type=Path,
        metavar="DIR",
        help=(
            "the folder every file a document names must be inside, through .. or a symbolic "
            "link; by default, the nearest folder above the document holding a scenet.toml, "
            "else the document's own"
        ),
    )

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
    check.add_argument(
        "--root",
        type=Path,
        metavar="DIR",
        help=(
            "the folder every file a document names must be inside, through .. or a symbolic "
            "link; by default, the nearest folder above the document holding a scenet.toml, "
            "else the document's own"
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
    which.add_argument(
        "--puppet",
        action="store_true",
        help="emit the schema for a puppet file, the *.puppet.yaml a cast member names",
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
    mcp.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "let streamable-http listen beyond this machine, on a --host that is not a "
            "loopback address; the server has no authentication and no encryption, so put "
            "something that provides both in front of it first"
        ),
    )
    mcp.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help=(
            "an Origin a browser client may call streamable-http from, such as "
            "http://localhost:6274, beyond the server's own; may be repeated"
        ),
    )
    mcp.add_argument(
        "--timeout",
        type=_seconds,
        metavar="SECONDS",
        help="the most seconds one tool call may take before it is stopped (default: 60)",
    )
    mcp.add_argument(
        "--root",
        type=Path,
        metavar="DIR",
        help=(
            "a folder a stdio server's documents may name files in; refused over "
            "streamable-http, and not in this version yet"
        ),
    )
    mcp.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help=(
            "a folder a stdio server's build tool writes new files in; refused over "
            "streamable-http, and not in this version yet"
        ),
    )
    return parser


def _seconds(written: str) -> float:
    """A number of seconds greater than nought, for `--timeout`."""
    try:
        seconds = float(written)
    except ValueError:
        seconds = 0.0
    if not (math.isfinite(seconds) and seconds > 0):
        raise argparse.ArgumentTypeError(f"{written!r} is not a number of seconds above 0")
    return seconds


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
    # A puppet is YAML too, and is checked the same way: through a document that casts it.
    puppets = [path for path in paths if path.name.lower().endswith(PUPPET_SUFFIX)]
    for path in puppets:
        print(
            f"scenet: {path}: a puppet is not a document; it is checked through a document "
            "whose cast names it, with reference: and its path",
            file=sys.stderr,
        )
    return bool(refused or contracts or puppets)


def run_build(args: argparse.Namespace) -> int:
    """Run a one-shot build or keep rebuilding while compilation inputs change."""
    if not args.watch:
        return _run_build_once(args)

    dependencies: set[Path] = {args.source.resolve()}
    try:
        try:
            status = _run_build_once(args, dependencies)
        except Exception as exc:
            print(f"scenet: initial watch build failed: {describe_failure(exc)}", file=sys.stderr)
            status = 1

        # A bad initial save, missing source or output-name clash is recoverable in watch
        # mode. Keep watching until the source is fixed or the user stops the command.
        def rebuild() -> None:
            # Keep the previous dependency set if this build fails. Add dependencies seen
            # by the new attempt as well, so a partial failure cannot blind the watcher.
            attempted: set[Path] = {args.source.resolve()}
            try:
                _run_build_once(args, attempted)
            except Exception as exc:
                print(f"scenet: watch rebuild failed: {describe_failure(exc)}", file=sys.stderr)
            finally:
                dependencies.update(attempted)

        watch_loop(dependencies, rebuild)
    except KeyboardInterrupt:
        return 0
    return status


def _run_build_once(args: argparse.Namespace, dependencies: set[Path] | None = None) -> int:
    """Run the `build` subcommand: compile a document and write its outputs.

    Args:
        args: Parsed arguments from :func:`build_parser <scenet.cli.build_parser>`.
        dependencies: Optional set to populate with compilation inputs for watch mode.

    Returns:
        A process exit status -- `0` on success, `1` when the document could not be
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
    if (
        _refuse_unsupported([source])
        or _refuse_output(args.output)
        or _refuse_root(args.root, [source])
    ):
        return 2

    try:
        book = compile_book_file(source, dependencies=dependencies, root=args.root)
    except ScenetError as exc:
        print(f"scenet: {_compile_failure(exc)}", file=sys.stderr)
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

    single = len(book.panels) == 1 and "panel" in book.panels
    printed = _printed(book)
    pdf = (
        _print(book, printed, base, live_text=args.live_text, mono=args.mono) if args.pdf else None
    )
    outputs = [] if isinstance(pdf, int) else _outputs(book, base, args, single=single, pdf=pdf)
    copies = _Copies() if args.embed_images else _copies(book, source, base)
    outputs += copies.outputs
    refused = pdf if isinstance(pdf, int) else 2 if _refuse_clashes(outputs) else 0
    if refused:
        return refused

    # Everything is checked before anything is written, so a refusal leaves no half-built
    # set of files behind -- not even the folder they would have gone in.
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, content())
    # Said whatever `--quiet` asked: a file that was there is gone.
    for replaced in copies.replaced:
        print(f"scenet: {replaced}", file=sys.stderr)

    if not args.quiet:
        for path, _ in outputs:
            print(f"wrote {path}")
        # What reading the document noticed, each naming its line, then what the compiler
        # decided in each panel, then what print leaves out.
        notes = [*book.notes, *copies.notes]
        for name, result in book.panels.items():
            notes += [note if single else f"{name}: {note}" for note in result.notes]
        if args.pdf:
            notes += print_notes(
                printed, live_text=args.live_text, fonts=book.fonts, pages=book.pages
            )
        for note in notes:
            print(f"note: {note}")
    return 0


def _compile_failure(exc: ScenetError) -> str:
    """What `build` says of a document it could not compile, in one line.

    Every ScenetError is "your panel cannot be compiled" rather than "scenet broke", so
    they all get a plain message instead of a traceback.
    """
    # A file that cannot be read is an `OSError` too, and says which and why as any other
    # file the system refuses does.
    if isinstance(exc, OSError):
        return describe_failure(exc)
    # KeyError stringifies as repr(args[0]), which wraps the message in whichever quote
    # style avoids escaping -- so a message containing an apostrophe comes out
    # double-quoted. Reading args[0] directly sidesteps that entirely.
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def _write(path: Path, content: str | bytes) -> None:
    """One output: text with LF line endings everywhere, or a PDF's bytes as they are."""
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def _print(
    book: Book, printed: dict[str, PanelCore], base: Path, *, live_text: bool, mono: bool
) -> bytes | int:
    """The print PDF, built before anything is written; or the status a refusal exits with.

    A picture print cannot carry fails the whole build, and leaves no half-built set of
    files behind. An `-o` naming a PDF never gets here: `-o` names the SVG, or a folder, and
    the PDF goes beside it.
    """
    try:
        return render_pdf(
            book.pages,
            printed,
            fonts=book.fonts,
            images=book.images,
            live_text=live_text,
            mono=mono,
        )
    except ValueError as exc:
        print(f"scenet: {exc}", file=sys.stderr)
        return 1


def _printed(book: Book) -> dict[str, PanelCore]:
    """The panels a print PDF draws, which :func:`printed_panels` decides."""
    return printed_panels(book.pages, {name: result.core for name, result in book.panels.items()})


@dataclass(frozen=True)
class _Copies:
    """The pictures a build copies beside its SVGs, and what it says about them."""

    #: Each picture to write, where its SVG links it.
    outputs: list["_Output"] = field(default_factory=list)
    #: What to say of each picture linked, copied or not.
    notes: list[str] = field(default_factory=list)
    #: What to say, whatever `--quiet` asked, of each file a copy replaces.
    replaced: list[str] = field(default_factory=list)


def _copies(book: Book, source: Path, base: Path) -> _Copies:
    """The pictures to copy beside the SVGs, so that each link finds its picture there.

    A link is the path the document wrote, which a viewer reads from beside the SVG. Beside
    the document -- where `build` writes by default -- that finds the picture already;
    anywhere else, the picture is copied to that path beside the SVG, so the SVG shows it
    wherever it was written. The path is not rewritten instead: librsvg refuses a link out of
    the SVG's folder, so that would only move the failure. For the same reason a picture
    the document reaches with `..` is not copied, since its copy would land outside the
    folder the build writes in; a note says so.

    A file already where a copy goes is left alone when it is the picture, and replaced when
    it is not -- which the build says, since nothing is lost silently.
    """
    linked = sorted(
        {
            (result.core.backdrop.image.href, result.core.backdrop.image.sha256)
            for result in book.panels.values()
            if result.core.backdrop is not None and result.core.backdrop.image is not None
        }
    )
    copies = _Copies()
    for href, digest in linked:
        target = base.parent / href
        if target.resolve() == (source.parent / href).resolve():
            continue
        if posixpath.normpath(href).startswith(".."):
            copies.notes.append(
                f"{href} is linked, and is outside the document's folder, so it was not copied "
                f"beside the SVG, in {base.parent}; build with --embed-images, or beside the "
                "document"
            )
            continue
        data = book.images[digest]
        if target.is_file():
            if target.stat().st_size == len(data) and target.read_bytes() == data:
                continue
            copies.replaced.append(
                f"replaced {target}, which was not the picture {href} the document links"
            )
        copies.outputs.append((target, partial(bytes, data)))
        copies.notes.append(
            f"{href} is linked, so it was copied beside the SVG, to {target}; build with "
            "--embed-images for an SVG that stands alone"
        )
    return copies


#: One file `build` will write, and how to produce what goes in it -- deferred, so that
#: the whole set can be checked for clashes before any of it is rendered.
_Output = tuple[Path, Callable[[], str | bytes]]


def _outputs(
    book: Book, base: Path, args: argparse.Namespace, *, single: bool, pdf: bytes | None = None
) -> list[_Output]:
    """Every file a build writes, in the order it writes them.

    A single-panel document writes to the requested name; a sequence suffixes each panel
    with its own name, so the mapping back to source is obvious. A strip needs more than
    one panel to lay out. Each page goes to `stem.page-<n>.svg`, beside the panels. The
    exports for image models are per panel only: a page adds no layout to a panel, and its
    Page Core says where every frame is. The print PDF, already rendered, is one file for
    the whole document, `stem.pdf`.
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
    if pdf is not None:
        outputs.append((base.with_suffix(".pdf"), partial(bytes, pdf)))
    return outputs


def _refuse_clashes(outputs: list[_Output]) -> bool:
    r"""Report two outputs that would be written to the same file.

    A panel named `page-1` or `strip` would otherwise silently replace a page or the strip
    -- exactly the kind of loss Scenet refuses everywhere else. Paths are compared ignoring
    case, because Windows and macOS do, and a document should build the same set of files
    everywhere.

    A name that would climb out of the folder, or end in `.debug`, is no panel's: `.`, `/`
    and `\` are never part of an identifier, and validation refuses it before anything
    is built.

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

    A path naming a folder -- one that exists, one written with a trailing separator, as
    `out/`, or one with no extension, as `out` -- takes the default name inside it, as `cp`
    does, and is made if it is not there. Anything else is the SVG to write, and ends in
    `.svg`: :func:`_refuse_output <scenet.cli._refuse_output>` has refused the rest.

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
    return path / default if _names_folder(written) else path


def _names_folder(written: str) -> bool:
    """Whether an `-o` is a folder: one there, or a name ending in a separator or bare."""
    separators = tuple(separator for separator in (os.sep, os.altsep) if separator)
    path = Path(written)
    return written.endswith(separators) or path.is_dir() or not path.suffix


def _refuse_output(written: str | None) -> bool:
    """Report an `-o` for `build` that is neither a folder nor an SVG's name.

    Every SVG a build writes ends in `.svg`, and every other output is named after the
    main SVG, so `-o out.pdf` would put an SVG in a file named for a PDF -- and the PDF
    `--pdf` writes beside it on top of it.

    Returns:
        Whether it was refused.
    """
    if written is None or _names_folder(written) or Path(written).suffix.lower() == ".svg":
        return False
    print(
        f"scenet: -o names the SVG, which ends in .svg, or a folder; {written} is neither: "
        f"write {Path(written).with_suffix('.svg')} for the file, or {written}/ for a folder",
        file=sys.stderr,
    )
    return True


def _refuse_root(root: Path | None, sources: Sequence[Path]) -> bool:
    """Report a `--root` that is not a folder, or that does not hold every document.

    Returns:
        Whether it was refused.
    """
    if root is None:
        return False
    if not root.is_dir():
        print(f"scenet: --root {root} is not a folder", file=sys.stderr)
        return True
    outside = [source for source in sources if not within(source, root)]
    for source in outside:
        print(f"scenet: {source} is outside --root {root}, which must hold it", file=sys.stderr)
    return bool(outside)


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
        A process exit status -- `0` when no document has an error (notes may have been
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
    if (
        _refuse_unsupported(sources)
        or _refuse_directory(args.output)
        or _refuse_root(args.root, sources)
    ):
        return 2

    found: list[Diagnostic] = []
    for path in sources:
        found.extend(diagnose_file(path, deep=args.deep, root=args.root))
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
    which = next((kind for kind in ("scene", "artwork", "puppet") if getattr(args, kind)), "panel")
    schema = {
        "panel": panel_schema,
        "scene": scene_schema,
        "artwork": artwork_schema,
        "puppet": puppet_schema,
    }[which]()
    document = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        _print_document(document)
    else:
        _write_document(args.output, document)
        print(f"wrote {args.output}")
    return 0


def _write_document(output: Path, document: str) -> None:
    """Write a document where `-o` said, creating its folder."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(document.encode())


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
        A process exit status -- `0` once the client has gone, `2` when the optional `mcp`
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

    folders = [option for option in ("--root", "--output") if getattr(args, option[2:])]
    if folders:
        named = " and ".join(folders)
        if args.transport == "streamable-http":
            print(
                f"scenet: {named} would let any client of an HTTP server read or write a folder "
                "of the server's; they are for a server on stdio, which only its client talks to",
                file=sys.stderr,
            )
        else:
            print(
                f"scenet: {named} for scenet mcp is not in this version yet; without it, the "
                "server reads and writes no folder of its own",
                file=sys.stderr,
            )
        return 2
    timeout = server.DEFAULT_TIMEOUT if args.timeout is None else args.timeout
    if args.transport == "stdio":
        server.serve("stdio", timeout=timeout)
        return 0
    if not args.allow_remote and not _loopback(args.host):
        print(
            f"scenet: --host {args.host} listens beyond this machine, and the server has no "
            "authentication; put one in front of it, then pass --allow-remote",
            file=sys.stderr,
        )
        return 2
    server.serve(
        "streamable-http",
        host=args.host,
        port=args.port,
        timeout=timeout,
        origins=tuple(args.allow_origin),
    )
    return 0


def _loopback(host: str) -> bool:
    """Whether an address is this machine's alone: `localhost`, `127.0.0.0/8` or `::1`."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the `scenet` command.

    Args:
        argv: Arguments to parse. Defaults to `sys.argv[1:]`, which is what happens
            when the installed console script runs; pass a list explicitly from tests.

    Returns:
        A process exit status. `0` on success, `1` for a document that will not
        compile or a file the system will not read or write, `2` for a usage error or a
        missing file, `70` for a fault in Scenet itself, `130` when stopped by Ctrl-C.

    No traceback reaches the terminal unless asked for: a document's fault and a file's
    are one line each, and anything else is one line saying it is a bug and where to
    report it, with the traceback under `--traceback` or `SCENET_DEBUG=1`.

    Example:
        >>> from scenet.cli import main
        >>> main(["--definitely-not-a-flag"])
        Traceback (most recent call last):
          ...
        SystemExit: 2
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(parser, args)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        # The reader of stdout left, as `head` does once it has its lines: there is
        # nobody to tell. stdout is pointed at the null device so that the interpreter's
        # own flush at exit does not fail all over again.
        _silence_stdout()
        return 1
    except Exception as exc:
        if _debugging(args):
            traceback.print_exception(exc)
        print(f"scenet: {describe_failure(exc)}", file=sys.stderr)
        if not isinstance(exc, OSError):
            print(
                f"scenet: run it again with --traceback, or with {DEBUG_VARIABLE}=1, to see "
                "where it happened",
                file=sys.stderr,
            )
            return EXIT_INTERNAL
        return 1


def describe_failure(exc: Exception) -> str:
    """One line saying what went wrong, for an exception no command handled.

    An `OSError` is the system refusing a file, and says which file and why. Anything else
    is a bug in Scenet, and says so, with where to report it.

    Args:
        exc: The exception.

    Returns:
        The line, without the program's name that every message starts with.

    Example:
        >>> from scenet.cli import describe_failure
        >>> describe_failure(PermissionError(13, "Permission denied", "out/a.svg"))
        'out/a.svg: Permission denied'
    """
    if isinstance(exc, OSError):
        reason = exc.strerror or str(exc) or type(exc).__name__
        if exc.filename is None:
            return reason
        if exc.filename2 is None:
            return f"{exc.filename}: {reason}"
        return f"{exc.filename} -> {exc.filename2}: {reason}"
    said = " ".join(str(exc).split())
    what = f"{type(exc).__name__}: {said}" if said else type(exc).__name__
    return f"internal error ({what}) -- this is a bug; please report it at {ISSUES}"


def _debugging(args: argparse.Namespace) -> bool:
    """Whether a traceback was asked for, by flag or by the environment."""
    return bool(args.traceback) or os.environ.get(DEBUG_VARIABLE, "") not in ("", "0")


def _silence_stdout() -> None:
    """Point stdout at the null device, where a closed pipe can no longer fail a write."""
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, sys.stdout.fileno())
    except (OSError, ValueError):
        # No descriptor underneath, as under a test's capture: nothing will flush to it.
        return


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run the command the arguments name."""
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
