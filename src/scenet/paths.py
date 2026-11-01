"""Files a document names, found beside the document.

A document may point at a file it does not contain -- a lettering face, or a picture to
letter over (#70). Every such path is read **relative to the folder the document
is in**, the way a link in a web page is, and never as an absolute path. That is what
lets a document and the files it names travel together and compile the same anywhere,
and what stops a server compiling documents it was sent from being steered at files of
its own.

The folder is the document's, not the working directory's: `scenet build
comics/one.panel.yaml` reads `fonts/x.ttf` from `comics/fonts/`, wherever it was run
from. Text compiled with no file behind it has no folder, and can name no file unless
the caller says which folder it belongs to -- or hands over the files themselves, by the
path the document writes, which is how a server is sent them: it never reads a folder of
its own. Both are read the same way, `./art/a.png` and `art/a.png` alike.

Nothing here reaches the output. A resolved path is used to open a file and is then
forgotten; what a Core records about a font is what is in it.
"""

import posixpath
import re
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath, PureWindowsPath

from scenet.errors import PanelSyntaxError

__all__ = [
    "Folder",
    "check_relative",
    "read_relative",
    "record_dependency",
    "resolve_relative",
    "track_dependencies",
]

_DEPENDENCIES: ContextVar[set[Path] | None] = ContextVar("scenet_dependencies", default=None)


@contextmanager
def track_dependencies(
    dependencies: set[Path] | None,
) -> Generator[None, None, None]:
    """Collect filesystem paths read during one compilation, without changing its result."""
    token = _DEPENDENCIES.set(dependencies)
    try:
        yield
    finally:
        _DEPENDENCIES.reset(token)


def record_dependency(path: Path) -> None:
    """Report a filesystem path to the active compilation, including missing paths."""
    dependencies = _DEPENDENCIES.get()
    if dependencies is not None:
        dependencies.add(path.resolve())


#: Where the files a document names are: the folder it is in, or the files themselves, by
#: the path the document writes.
Folder = Path | Mapping[str, bytes]

#: The C0 controls and DEL. Python refuses a NUL in any path, raising an error no finding
#: was made from, and Windows refuses every one of these in a file name, so a path holding
#: one opened a file on some systems and crashed the compiler on others. Nobody types one
#: on purpose: it is a slip, reported as one.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def resolve_relative(
    declared: str,
    base: Path | None,
    *,
    what: str,
    rule: str,
    loc: tuple[str | int, ...] = (),
) -> Path:
    """Resolve a path a document wrote against the folder the document is in.

    Args:
        declared: The path as written, with `/` between folders.
        base: The document's folder, or `None` when the text has no file behind it.
        what: What the file is, for the message: `font`, say.
        rule: The rule a bad path breaks, for the finding.
        loc: Where in the document the path was written.

    Returns:
        The file's path. Not checked to exist: whoever opens it says what it found.

    Raises:
        PanelSyntaxError: The path is empty or absolute, has a backslash or a control
            character in it, or there is no folder to read it from.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import resolve_relative
        >>> found = resolve_relative("fonts/a.ttf", Path("comic"), what="font", rule="font-file")
        >>> found.as_posix()
        'comic/fonts/a.ttf'
    """
    check_relative(declared, what=what, rule=rule, loc=loc)
    if base is None:
        raise _no_folder(declared, what=what, rule=rule, loc=loc)
    return base / declared


def read_relative(
    declared: str,
    base: Folder | None,
    *,
    what: str,
    rule: str,
    loc: tuple[str | int, ...] = (),
) -> bytes:
    """Read a file a document names, from its folder or from the files sent with it.

    Args:
        declared: The path as written, with `/` between folders.
        base: The document's folder; or the files beside it, by the path the document
            writes, when it was sent as text; or `None` when it has neither.
        what: What the file is, for the message: `font`, say.
        rule: The rule every failure is reported under.
        loc: Where in the document the path was written.

    Returns:
        The file's bytes.

    Raises:
        PanelSyntaxError: Anything :func:`resolve_relative` refuses, or the file is not
            there, or cannot be read. The message names the path as written, never as
            resolved: a finding is output too, and a folder in it would differ between
            two checkouts.

    Example:
        >>> from scenet.paths import read_relative
        >>> read_relative("./art/a.png", {"art/a.png": b"..."}, what="image", rule="image-file")
        b'...'
    """
    if base is None or isinstance(base, Path):
        path = resolve_relative(declared, base, what=what, rule=rule, loc=loc)
        record_dependency(path)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise _not_found(declared, what=what, rule=rule, loc=loc) from exc
        # `ValueError` too: a path the file system cannot spell is a path that cannot be
        # read, and is the author's to fix, whatever the system's reason.
        except (OSError, ValueError) as exc:
            reason = exc.strerror if isinstance(exc, OSError) else None
            raise PanelSyntaxError(
                f"{what} file {declared!r} cannot be read: {reason or type(exc).__name__}",
                rule=rule,
                loc=loc,
            ) from exc
    check_relative(declared, what=what, rule=rule, loc=loc)
    sent = {posixpath.normpath(name): data for name, data in base.items()}
    found = sent.get(posixpath.normpath(declared))
    if found is None:
        raise _not_found(declared, what=what, rule=rule, loc=loc)
    return found


def _not_found(
    declared: str, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return PanelSyntaxError(
        f"{what} file {declared!r} was not found beside the document", rule=rule, loc=loc
    )


def _no_folder(
    declared: str, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return PanelSyntaxError(
        f"the {what} {declared!r} is read from beside the document, and this document "
        "has no folder: it was compiled from text, not from a file",
        rule=rule,
        loc=loc,
    )


def check_relative(declared: str, *, what: str, rule: str, loc: tuple[str | int, ...] = ()) -> None:
    """Refuse a path that could not be read the same way on every system, or at all.

    Everything :func:`resolve_relative` refuses but the want of a folder: for a path that
    is kept rather than opened, as Panel Core keeps a picture's.

    Raises:
        PanelSyntaxError: The path is empty or absolute, or has a backslash or a control
            character in it.
    """
    control = _CONTROL.search(declared)
    if control is not None:
        raise PanelSyntaxError(
            f"the {what} path {declared!r} contains U+{ord(control.group()):04X}, a control "
            "character a file name cannot hold on every system; delete it",
            rule=rule,
            loc=loc,
        )
    if not declared.strip():
        raise PanelSyntaxError(f"the {what} path is empty", rule=rule, loc=loc)
    if PurePosixPath(declared).is_absolute() or PureWindowsPath(declared).anchor:
        raise PanelSyntaxError(
            f"the {what} path {declared!r} is absolute; write it relative to the folder the "
            "document is in, so the document and its files compile the same anywhere",
            rule=rule,
            loc=loc,
        )
    # Windows reads a backslash as a separator and every other system as part of a name,
    # so a path written with one opened its file on one machine and not on the next.
    if "\\" in declared:
        raise PanelSyntaxError(
            f"the {what} path {declared!r} has a backslash in it; write / between folders, "
            "which every system reads the same way",
            rule=rule,
            loc=loc,
        )
