"""Files a document names, found beside the document.

A document may point at a file it does not contain -- a lettering face, or a picture to
letter over. Every such path is read **relative to the folder the document
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

Some of those files are text an author writes: a picture's artwork contract, a puppet
a cast member names. :func:`read_model <scenet.paths.read_model>` reads one the same
way for both, and a fault in it is a :exc:`NamedFileError <scenet.paths.NamedFileError>`,
located in the file as well as where the document names it.

.. rubric:: What is read, and what is not

Every file a document names must be inside its **root**: the folder `--root` or `root=`
names; else the nearest folder at or above the document's that holds a `scenet.toml`; else
the document's own folder. With `base=Path(d)` it is `root=`, or else `d`, with no
`scenet.toml` looked for. With the files themselves, in a mapping, it is the mapping. A
path that leaves it, by `..` or through a symbolic link, is refused under the rule of the
file it names, before anything outside the root is opened or looked at: first by what it
says, then once its links are followed. A `scenet.toml` holds nothing yet: a key in it is
kept for a later version, and refused.

Only a regular file is read: a folder, a device or a pipe is refused by what it is, before
it is opened, since opening a pipe waits for a writer and a device may never end. A file is
read up to its bound in :mod:`scenet.limits <scenet.limits>`, and one larger is refused by
its size.

A file a document names, read from disk, may be one its author never had. A fault in it is
reported by its line and what kind of fault it is, and never by what it holds: no value and
no key it writes is quoted back. A file sent with the document, in a mapping, is its
sender's, who is told which key is wrong.
"""

import errno
import os
import posixpath
import re
import stat
import tomllib
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import ClassVar

import yaml
from pydantic import BaseModel, ValidationError

from scenet import limits
from scenet.errors import FileReadError, PanelSyntaxError, RuleViolationError, SourceError
from scenet.frontends.common import errors_of
from scenet.frontends.positions import Position, Region, locate
from scenet.namespace import ASSET_KEYS, AssetHead, language_fault, split_head, stripped
from scenet.safe_yaml import ProfileError, carrier, describe, is_json_file, load

__all__ = [
    "MARKER",
    "FileTooLargeError",
    "Folder",
    "MarkerError",
    "NamedFileError",
    "NotRegularFileError",
    "OutsideRootError",
    "check_relative",
    "contained",
    "find_marker",
    "read_bounded",
    "read_document",
    "read_file",
    "read_model",
    "read_relative",
    "reading_within",
    "record_dependency",
    "resolve_relative",
    "track_dependencies",
    "within",
]

_DEPENDENCIES: ContextVar[set[Path] | None] = ContextVar("scenet_dependencies", default=None)
_ROOT: ContextVar[Path | None] = ContextVar("scenet_root", default=None)


#: The file that marks the top of a project: the folder it is in is the root of every
#: document below it that names no root of its own. It holds nothing yet.
MARKER = "scenet.toml"


@contextmanager
def contained(root: Path) -> Generator[None, None, None]:
    """Read every file a document names from inside one folder, and refuse any other.

    What :func:`reading_within <scenet.paths.reading_within>` sets for a compile, once it
    has chosen the root. Each thread and each `asyncio` task has its own root, as it has its
    own dependencies.

    Args:
        root: The folder.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import contained, read_relative
        >>> with contained(Path("comic")):
        ...     read_relative("../../a.png", Path("comic/pages"), what="image", rule="image-file")
        Traceback (most recent call last):
          ...
        scenet.errors.PanelSyntaxError: image file '../../a.png' is outside the root folder, ...
    """
    token = _ROOT.set(_lexical(root))
    try:
        yield
    finally:
        _ROOT.reset(token)


class MarkerError(PanelSyntaxError):
    """A `scenet.toml` that holds something: it holds nothing yet.

    Attributes:
        marker: The file.
        line: The line of what it holds, from 1.
        reason: What is wrong, without the file's name.
        kind: The rule it breaks, as `rule` holds it.
    """

    def __init__(self, message: str, *, marker: Path, line: int, rule: str) -> None:
        """Build the error.

        Args:
            message: What is wrong.
            marker: The file.
            line: Where in it, from 1.
            rule: `not-yet` for a key, `syntax` for a file that is not TOML.
        """
        self.marker = marker
        self.line = line
        self.reason = message
        self.kind = rule
        super().__init__(message, source=marker, rule=rule)


class OutsideRootError(SourceError):
    """A document outside the root it was told to read within."""


def find_marker(folder: Path) -> Path | None:
    """The nearest `scenet.toml` in a folder or any folder above it.

    Args:
        folder: Where to start: the folder a document is in.

    Returns:
        The file, or `None` when no folder up to the top of the file system holds one.
    """
    start = _lexical(folder)
    for candidate in (start, *start.parents):
        marker = candidate / MARKER
        if marker.is_file():
            return marker
    return None


def marker_fault(marker: Path) -> MarkerError | None:
    """What is wrong with a `scenet.toml`, if anything: it holds comments, or nothing.

    Args:
        marker: The file.

    Returns:
        The fault, or `None` for a file that holds nothing.
    """
    try:
        text = read_bounded(marker, limits.DOCUMENT_BYTES, what="a scenet.toml").decode()
        held = tomllib.loads(text)
    except UnicodeDecodeError:
        return MarkerError(
            "scenet.toml is not UTF-8 text; it holds nothing yet, so it can be empty",
            marker=marker,
            line=1,
            rule="syntax",
        )
    except tomllib.TOMLDecodeError as exc:
        return MarkerError(
            f"scenet.toml is not TOML: {exc}; it holds nothing yet, so it can be empty",
            marker=marker,
            line=_toml_line(exc),
            rule="syntax",
        )
    except OSError as exc:
        return MarkerError(
            f"scenet.toml cannot be read: {exc.strerror or type(exc).__name__}",
            marker=marker,
            line=1,
            rule="syntax",
        )
    if not held:
        return None
    key = next(iter(held))
    # A file TOML read a key from has a line that is neither blank nor a comment.
    line = next(
        number
        for number, written in enumerate(text.splitlines(), start=1)
        if written.strip() and not written.lstrip().startswith("#")
    )
    return MarkerError(
        f"scenet.toml holds {key!r}, and a scenet.toml holds nothing yet: it marks the root "
        "of a project, and what it may say is kept for a later version of Scenet",
        marker=marker,
        line=line,
        rule="not-yet",
    )


def _toml_line(exc: tomllib.TOMLDecodeError) -> int:
    """The line a TOML fault is on, which every Python's message gives: `(at line 2, ...)`."""
    found = re.search(r"at line (\d+)", str(exc))
    return int(found.group(1)) if found else 1


def _chosen_root(
    root: Path | None, base: "Folder | None", source: Path | None
) -> tuple[Path | None, Path | None]:
    """The root a compile reads within, and the `scenet.toml` that chose it, if one did."""
    if root is not None:
        return root, None
    if isinstance(base, Path):
        return base, None
    if base is None and source is not None:
        marker = find_marker(source.parent)
        return (source.parent, None) if marker is None else (marker.parent, marker)
    return None, None


@contextmanager
def reading_within(
    *, root: Path | None, base: "Folder | None", source: Path | None
) -> Generator[None, None, None]:
    """Choose the root a compile reads within, and read within it.

    The root is `root` when given; else, for a document on disk with no `base`, the nearest
    folder at or above its own that holds a `scenet.toml`, or else its own folder; else the
    `base` folder. Files sent as a mapping are their own root. Inside a compile that has
    chosen one already, a call that names no root keeps it: a page compiles each of its
    panels, and they read within the page's root.

    Args:
        root: The root a caller named, or `None`.
        base: Where the files the document names are, as the compile was given it.
        source: The document's path, when it has one.

    Raises:
        MarkerError: The `scenet.toml` that would choose the root holds something.
        OutsideRootError: `root` does not hold the document.
    """
    if root is None and _ROOT.get() is not None:
        yield
        return
    chosen, marker = _chosen_root(root, base, source)
    if marker is not None:
        record_dependency(marker)
        fault = marker_fault(marker)
        if fault is not None:
            raise fault
    if root is not None and source is not None and not within(source, root):
        raise OutsideRootError(
            "the document is outside its root folder, which must hold it", source=source
        )
    if chosen is None:
        yield
        return
    with contained(chosen):
        yield


def _lexical(path: Path) -> Path:
    """A path made absolute, and `..` and `.` taken out by what it says: nothing is opened."""
    # Not `resolve()`, which follows links, and so looks at the disk outside the root.
    return Path(os.path.abspath(path))  # noqa: PTH100 -- lexical on purpose, see above


def within(path: Path, root: Path) -> bool:
    """Whether a path is inside a folder: by what it says, then once links are followed.

    The first test opens nothing, so nothing outside the folder is so much as looked at
    unless the path says it is inside; the second refuses a link that leads out.

    Args:
        path: The path.
        root: The folder.

    Returns:
        Whether it is inside, and its links lead nowhere out.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import within
        >>> (
        ...     within(Path("comic/art/../a.png"), Path("comic")),
        ...     within(Path("comic/../a.png"), Path("comic")),
        ... )
        (True, False)
    """
    if not _lexical(path).is_relative_to(_lexical(root)):
        return False
    # A loop of links is `RuntimeError` on 3.12 and `OSError` later; either is no way in.
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


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
        The file's path. Not checked to exist -- whoever opens it says what it found.

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


#: How a file is opened: for reading; as bytes, where the system tells text from bytes; and
#: without waiting, where it can, so that a pipe put in a file's place is opened at once.
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)


class NotRegularFileError(OSError):
    """A path to something that is not a regular file: a folder, a device, a pipe."""

    def __init__(self, path: Path) -> None:
        """Build the error.

        Args:
            path: The path.
        """
        super().__init__(errno.EINVAL, "not a regular file", str(path))


class FileTooLargeError(OSError):
    """A regular file larger than the most Scenet reads of it.

    Attributes:
        limit: The bound, in bytes.
    """

    def __init__(self, path: Path, limit: int, what: str) -> None:
        """Build the error.

        Args:
            path: The file.
            limit: The bound, in bytes.
            what: What the file is, for the message: `a document`, say.
        """
        self.limit = limit
        super().__init__(
            errno.EFBIG,
            f"larger than {limits.describe(limit)}, the most Scenet reads of {what}",
            str(path),
        )


def read_bounded(path: Path, limit: int | None, *, what: str = "a file") -> bytes:
    """Read a regular file whole, if it is no larger than a bound.

    What it is and how big are read first, and a folder, a device, a pipe, or a file over
    the bound is refused without being opened -- opening a pipe would wait for a writer.
    It is checked again once opened, in case it was swapped in between, and never more than
    one byte past the bound is read.

    Args:
        path: The file.
        limit: The most bytes to read, or `None` for no bound.
        what: What the file is, for the message of a file too large: `a document`, say.

    Returns:
        Its bytes.

    Raises:
        NotRegularFileError: It is not a regular file. An `OSError`.
        FileTooLargeError: It is larger than `limit`. An `OSError`.
        OSError: The system will not read it.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import read_bounded
        >>> read_bounded(Path("."), 10)
        Traceback (most recent call last):
          ...
        scenet.paths.NotRegularFileError: [Errno 22] not a regular file: '.'
    """
    try:
        status = path.stat()
    except OSError as exc:
        # In the words every system's C library has for it, not in the language a Windows
        # machine happens to be set to: a message is output, and the same everywhere.
        if exc.errno is None:
            raise
        raise type(exc)(exc.errno, os.strerror(exc.errno), str(path)) from exc
    if not stat.S_ISREG(status.st_mode):
        raise NotRegularFileError(path)
    if limit is not None and status.st_size > limit:
        raise FileTooLargeError(path, limit, what)
    # Not blocking where the system has the flag, in case a pipe was put in its place
    # since: opened that way, it is opened at once, and refused below.
    with os.fdopen(os.open(path, _READ_FLAGS), "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise NotRegularFileError(path)
        if limit is None:
            return file.read()
        data = file.read(limit + 1)
    # At most one byte past the bound was read: that byte is what makes it too large.
    if len(data) == limit + 1:
        raise FileTooLargeError(path, limit, what)
    return data


def read_file(path: Path, *, limit: int | None = None, what: str = "a file") -> bytes:
    """Read a file a caller names -- not one a document names -- whole.

    Args:
        path: The file, as the caller gave it.
        limit: The most bytes to read, or `None` for no bound.
        what: What the file is, for the message of a file too large: `a font`, say.

    Returns:
        Its bytes.

    Raises:
        FileReadError: The system will not read it, or it is not a regular file, or it is
            larger than `limit`. A :exc:`MissingFileError <scenet.errors.MissingFileError>`
            when it is not there; either keeps the system's `errno`, `strerror` and
            `filename`, and is an `OSError`.
    """
    try:
        return read_bounded(path, limit, what=what)
    except OSError as exc:
        raise FileReadError.of(exc) from exc


def read_document(path: Path, *, error: type[PanelSyntaxError] = PanelSyntaxError) -> str:
    """Read a document a caller names, as UTF-8 text.

    No more than :data:`DOCUMENT_BYTES <scenet.limits.DOCUMENT_BYTES>` is read.

    Args:
        path: The document.
        error: What a document that is not UTF-8 is: a
            :exc:`ScriptSyntaxError <scenet.errors.ScriptSyntaxError>` for a script.

    Returns:
        Its text, read as :meth:`pathlib.Path.read_text` reads it.

    Raises:
        FileReadError: The system will not read it, or it is not a regular file, or it is
            larger than the bound.
        PanelSyntaxError: Rule `syntax`: it is not UTF-8, so it is no document at all.
            Raised as `error`.
    """
    try:
        data = read_bounded(path, limits.DOCUMENT_BYTES, what="a document")
        # As `Path.read_text` reads it: a line may end in CR LF or CR.
        return data.decode().replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise error(
            f"not UTF-8 text: byte {exc.start} is {exc.object[exc.start]:#04x}; save the "
            "file as UTF-8",
            source=path,
            rule="syntax",
        ) from exc
    except OSError as exc:
        raise FileReadError.of(exc) from exc


def read_relative(
    declared: str,
    base: Folder | None,
    *,
    what: str,
    rule: str,
    loc: tuple[str | int, ...] = (),
    limit: int | None = None,
    root: Path | None = None,
) -> bytes:
    """Read a file a document names, from its folder or from the files sent with it.

    Args:
        declared: The path as written, with `/` between folders.
        base: The document's folder; or the files beside it, by the path the document
            writes, when it was sent as text; or `None` when it has neither.
        what: What the file is, for the message: `font`, say.
        rule: The rule every failure is reported under.
        loc: Where in the document the path was written.
        limit: The most bytes to read. Defaults to :data:`DOCUMENT_BYTES
            <scenet.limits.DOCUMENT_BYTES>`, the bound on a text file.
        root: The folder the file must be inside. Defaults to the root of the compile in
            progress, and with none, to `base`. Kept apart from `base`, which is where the
            path is read from, and which a file another one includes will have of its own.

    Returns:
        The file's bytes.

    Raises:
        PanelSyntaxError: Anything :func:`resolve_relative` refuses, or the file is outside
            the root -- a mapping's paths may not climb out of it either -- or is not there,
            or cannot be read, or is not a regular file, or is larger than the bound. The
            message names the path as written, never as resolved: a finding is output too,
            and a folder in it would differ between two checkouts.

    Example:
        >>> from scenet.paths import read_relative
        >>> read_relative("./art/a.png", {"art/a.png": b"..."}, what="image", rule="image-file")
        b'...'
    """
    bound = limits.DOCUMENT_BYTES if limit is None else limit
    if base is None or isinstance(base, Path):
        path = resolve_relative(declared, base, what=what, rule=rule, loc=loc)
        inside = root or _ROOT.get() or base
        if inside is not None and not within(path, inside):
            # Not recorded: a file outside the root is no input of this compile.
            raise _outside(declared, what=what, rule=rule, loc=loc)
        record_dependency(path)
        try:
            return read_bounded(path, bound)
        except NotRegularFileError as exc:
            raise PanelSyntaxError(
                f"{what} file {declared!r} is not a regular file; a folder, a device or a "
                "pipe is never read",
                rule=rule,
                loc=loc,
            ) from exc
        except FileTooLargeError as exc:
            raise _too_large(declared, bound, what=what, rule=rule, loc=loc) from exc
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
    wanted = posixpath.normpath(declared)
    if wanted == ".." or wanted.startswith("../"):
        raise _outside(declared, what=what, rule=rule, loc=loc)
    sent = {posixpath.normpath(name): data for name, data in base.items()}
    found = sent.get(wanted)
    if found is None:
        raise _not_found(declared, what=what, rule=rule, loc=loc)
    if len(found) > bound:
        raise _too_large(declared, bound, what=what, rule=rule, loc=loc)
    return found


def _outside(
    declared: str, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return PanelSyntaxError(
        f"{what} file {declared!r} is outside the root folder, the only one this compile reads "
        "from; an empty scenet.toml in a folder that holds both, or a wider --root, lets it in",
        rule=rule,
        loc=loc,
    )


def _too_large(
    declared: str, limit: int, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return PanelSyntaxError(
        f"{what} file {declared!r} is larger than {limits.describe(limit)}, the most Scenet "
        f"reads of one {what} file",
        rule=rule,
        loc=loc,
    )


class NotBesideError(PanelSyntaxError):
    """A file a document names that is not beside it: neither in its folder nor sent with it.

    Apart from a file that is there and cannot be read, so a reader that takes either of
    two names -- an artwork contract in YAML or in JSON -- can try the second.
    """


def _not_found(
    declared: str, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return NotBesideError(
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


class NamedFileError(PanelSyntaxError):
    """A file a document names, there and wrong: located in it, as well as where it is named.

    A fault inside an artwork contract or a puppet file is fixed in that file, so `scenet
    check` reports it there when the document was checked as a file. Checked as text --
    the playground, a model over MCP -- there is no such file to open, and it is reported
    where the document names it, with the file's own line in the message.

    Each kind of file is a subclass, which says what the file is called and the rule its
    faults are reported under: :exc:`ContractError <scenet.assets.artwork.ContractError>`
    and :exc:`PuppetFileError <scenet.assets.contract.PuppetFileError>`.

    Attributes:
        file: The file's path, relative to the document, as the document reaches it.
        inner: Where in the file the fault is, in pydantic's `loc` form; empty for the file
            as a whole.
        region: The fault's span in the file's text, when it was parsed far enough to find
            it.
    """

    #: What a file of this kind is called in a message, before its path.
    KIND: ClassVar[str]
    #: The rule every fault in a file of this kind is reported under.
    RULE: ClassVar[str]

    def __init__(
        self,
        message: str,
        *,
        file: str,
        inner: tuple[str | int, ...] = (),
        region: Region | None = None,
        loc: tuple[str | int, ...] = (),
    ) -> None:
        """Build the error.

        Args:
            message: What is wrong, without the file's name.
            file: The file's path, relative to the document.
            inner: Where in the file.
            region: Where in its text.
            loc: Where in the document the file is named.
        """
        self.file = file
        self.inner = inner
        self.region = region
        line = f", line {region.start.line}" if region is not None else ""
        super().__init__(f"{self.KIND} {file!r}{line}: {message}", rule=self.RULE, loc=loc)


def read_model[M: BaseModel](
    declared: str,
    base: Folder | None,
    model: type[M],
    *,
    what: str,
    error: type[NamedFileError],
    holds: str,
    unknown_key: str,
    loc: tuple[str | int, ...] = (),
    tags: frozenset[str] = frozenset(),
    root: Path | None = None,
) -> tuple[M, str, bytes]:
    """Read a YAML file a document names, and validate it, each fault located in it.

    Args:
        declared: The path as the document writes it.
        base: The document's folder, or the files sent with it, or `None` for text with
            neither.
        model: What the file holds.
        what: What the file is, for a message about its path: `puppet`, say.
        error: The kind of file, which says how a fault inside it is reported.
        holds: What its top-level mapping holds, for the message when it is not one.
        unknown_key: The message for a key the model does not have.
        loc: Where in the document the file is named.
        tags: The tags of a tagged union the model validates a list's items with. pydantic
            puts one in a fault's location after the item's index, where the file has no
            key, so it is left out to locate the fault where it is written.
        root: The folder the file must be inside, as for :func:`read_relative`.

    Returns:
        What the file declares, its text, and its bytes.

    Raises:
        PanelSyntaxError: Under the error's rule, for a path that cannot be read, as
            :func:`read_relative <scenet.paths.read_relative>` reports it -- located where
            the document names the file.
        NamedFileError: The error given, for a file that is there and wrong, located in it
            too: not UTF-8 text, not YAML, a key written twice, not a mapping, written for
            a later language, or not what the model allows -- the first fault, at the key
            that is wrong. Read from disk, the message quotes nothing the file holds; sent
            in a mapping, it names the key and the value.
    """
    data = read_relative(declared, base, what=what, rule=error.RULE, loc=loc, root=root)
    # Sent with the document, the file is its sender's, and quoting it tells them nothing
    # they did not have. Read from disk, it may be any file the document reached.
    quoted = isinstance(base, Mapping)
    try:
        text = data.decode()
    except UnicodeDecodeError as exc:
        raise error("it is not UTF-8 text", file=declared, loc=loc) from exc
    try:
        raw = load(text, as_json=is_json_file(declared))
    except ProfileError as exc:
        region = Region(
            start=Position(line=exc.line, column=exc.column),
            end=Position(line=exc.end_line, column=exc.end_column),
        )
        summary = exc.summary if quoted else _PROFILE_FAULTS.get(exc.rule, "it is not Scenet YAML")
        raise error(summary, file=declared, region=region, loc=loc) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        region = _whole_line(mark.line + 1) if mark is not None else None
        problem = getattr(exc, "problem", None) or describe(exc)
        written = carrier(text, as_json=is_json_file(declared))
        raise error(
            f"it is not valid {written}: {problem}" if quoted else f"it is not valid {written}",
            file=declared,
            region=region,
            loc=loc,
        ) from exc
    if not isinstance(raw, dict):
        raise error(f"it must be a mapping of {holds}", file=declared, loc=loc)
    # Its extension keys are nobody's, and its own keys -- its language, its schema -- are
    # not the model's: a file of a later language is that, and nothing else (#357).
    head, raw = split_head(stripped(raw), ASSET_KEYS)
    later = language_fault(head)
    if later is not None:
        raise error(
            f"scenet: {later}" if quoted else "its `scenet:` is not a language this Scenet reads",
            file=declared,
            inner=later.loc,
            region=locate(text, later.loc),
            loc=loc,
        )
    try:
        AssetHead.model_validate(head)
        return model.model_validate(raw), text, data
    except ValidationError as exc:
        first = errors_of(exc)[0]
        original = (first.get("ctx") or {}).get("error")
        if isinstance(original, RuleViolationError):
            inner, message = original.loc, str(original)
        else:
            inner = _untagged(tuple(first["loc"]), tags)
            message = unknown_key if first["type"] == "extra_forbidden" else first["msg"]
        where = ".".join(str(part) for part in inner)
        if not quoted:
            where, message = "", _unquoted(first["type"], unknown_key, inner)
        raise error(
            f"{where}: {message}" if where else message,
            file=declared,
            inner=inner,
            region=locate(text, inner),
            loc=loc,
        ) from exc


#: What each fault Scenet YAML refuses is, in words that quote nothing a file holds.
_PROFILE_FAULTS = {
    "yaml-tag": "it holds a YAML tag, which Scenet YAML refuses",
    "yaml-anchor": "it holds a YAML anchor or alias, which Scenet YAML refuses",
    "yaml-merge-key": "it holds a YAML merge key, which Scenet YAML refuses",
    "duplicate-key": "it writes a key twice in one mapping",
}


def _unquoted(kind: str, unknown_key: str, inner: tuple[str | int, ...]) -> str:
    """What is wrong at a place in a file, in words that quote nothing it holds.

    A key that is missing is named: the format names it, not the file. A rule a validator
    broke is pydantic's `value_error`, and a value it does not allow.
    """
    if kind == "extra_forbidden":
        return unknown_key
    if kind == "missing":
        missing = inner[-1] if inner else None
        return (
            f"`{missing}` is missing here" if isinstance(missing, str) else "a key is missing here"
        )
    return "a value it does not allow here"


def _untagged(loc: tuple[str | int, ...], tags: frozenset[str]) -> tuple[str | int, ...]:
    """A fault's location with a union's tag left out after a list item's index."""
    return tuple(
        step
        for index, step in enumerate(loc)
        if not (step in tags and index > 0 and isinstance(loc[index - 1], int))
    )


def _whole_line(number: int) -> Region:
    """A whole line, for a fault the parser knows only the line of."""
    return Region(start=Position(line=number, column=1), end=Position(line=number + 1, column=1))
