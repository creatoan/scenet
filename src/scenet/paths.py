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

Only a regular file is read: a folder, a device or a pipe is refused by what it is, before
it is opened, since opening a pipe waits for a writer and a device may never end. A file is
read up to its bound in :mod:`scenet.limits <scenet.limits>`, and one larger is refused by
its size. Inside :func:`contained <scenet.paths.contained>` -- `--root` on the command line
-- every file a document names must resolve inside the root folder, symbolic links
followed, and one that does not is refused without being opened.

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
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import ClassVar

import yaml
from pydantic import BaseModel, ValidationError

from scenet import limits
from scenet.errors import FileReadError, PanelSyntaxError, RuleViolationError
from scenet.frontends.common import errors_of
from scenet.frontends.positions import Position, Region, locate
from scenet.namespace import ASSET_KEYS, AssetHead, language_fault, split_head, stripped
from scenet.safe_yaml import ProfileError, describe, load

__all__ = [
    "Folder",
    "NamedFileError",
    "check_relative",
    "contained",
    "read_bounded",
    "read_document",
    "read_file",
    "read_model",
    "read_relative",
    "record_dependency",
    "resolve_relative",
    "track_dependencies",
]

_DEPENDENCIES: ContextVar[set[Path] | None] = ContextVar("scenet_dependencies", default=None)
_ROOT: ContextVar[Path | None] = ContextVar("scenet_root", default=None)


@contextmanager
def contained(root: Path | None) -> Generator[None, None, None]:
    """Read every file a document names from inside one folder, and refuse any other.

    For a document from someone else: `..` and symbolic links may otherwise reach any file
    the process can read. A path is resolved, links followed, before it is opened, and one
    that resolves outside the root is a finding of the read's rule, located where the
    document names it. Files sent in a mapping are not on disk, and are not affected.

    Each thread and each `asyncio` task has its own root, as it has its own dependencies.

    Args:
        root: The folder, or `None` for no containment.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import contained, read_relative
        >>> with contained(Path("comic")):
        ...     read_relative("../secret.png", Path("comic"), what="image", rule="image-file")
        Traceback (most recent call last):
          ...
        scenet.errors.PanelSyntaxError: image file '../secret.png' is outside the root folder, \
the only one this compile may read from
    """
    token = _ROOT.set(None if root is None else root.resolve())
    try:
        yield
    finally:
        _ROOT.reset(token)


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
    status = path.stat()
    if not stat.S_ISREG(status.st_mode):
        raise NotRegularFileError(path)
    if limit is not None and status.st_size > limit:
        raise FileTooLargeError(path, limit, what)
    # Not blocking where the system has the flag, in case a pipe was put in its place
    # since: opened that way, it is opened at once, and refused below.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise NotRegularFileError(path)
        data = file.read() if limit is None else file.read(limit + 1)
    if limit is not None and len(data) > limit:
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
        return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
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

    Returns:
        The file's bytes.

    Raises:
        PanelSyntaxError: Anything :func:`resolve_relative` refuses, or the file is not
            there, or cannot be read, or is not a regular file, or is larger than the
            bound, or is outside the root of :func:`contained`. The message names the path
            as written, never as resolved: a finding is output too, and a folder in it
            would differ between two checkouts.

    Example:
        >>> from scenet.paths import read_relative
        >>> read_relative("./art/a.png", {"art/a.png": b"..."}, what="image", rule="image-file")
        b'...'
    """
    bound = limits.DOCUMENT_BYTES if limit is None else limit
    if base is None or isinstance(base, Path):
        path = resolve_relative(declared, base, what=what, rule=rule, loc=loc)
        record_dependency(path)
        try:
            _refuse_outside(path)
            return read_bounded(path, bound)
        except _OutsideError as exc:
            raise PanelSyntaxError(
                f"{what} file {declared!r} is outside the root folder, the only one this "
                "compile may read from",
                rule=rule,
                loc=loc,
            ) from exc
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
    sent = {posixpath.normpath(name): data for name, data in base.items()}
    found = sent.get(posixpath.normpath(declared))
    if found is None:
        raise _not_found(declared, what=what, rule=rule, loc=loc)
    if len(found) > bound:
        raise _too_large(declared, bound, what=what, rule=rule, loc=loc)
    return found


class _OutsideError(Exception):
    """A path that resolves outside the root folder."""


def _refuse_outside(path: Path) -> None:
    """Refuse a path outside the root of :func:`contained`, once links are followed."""
    root = _ROOT.get()
    if root is None:
        return
    # A loop of links is `RuntimeError` on 3.12 and `OSError` later; either is no way in.
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise _OutsideError from exc
    if not resolved.is_relative_to(root):
        raise _OutsideError


def _too_large(
    declared: str, limit: int, *, what: str, rule: str, loc: tuple[str | int, ...]
) -> PanelSyntaxError:
    return PanelSyntaxError(
        f"{what} file {declared!r} is larger than {limits.describe(limit)}, the most Scenet "
        f"reads of one {what} file",
        rule=rule,
        loc=loc,
    )


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
    data = read_relative(declared, base, what=what, rule=error.RULE, loc=loc)
    # Sent with the document, the file is its sender's, and quoting it tells them nothing
    # they did not have. Read from disk, it may be any file the document reached.
    quoted = isinstance(base, Mapping)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise error("it is not UTF-8 text", file=declared, loc=loc) from exc
    try:
        raw = load(text)
    except ProfileError as exc:
        region = Region(
            start=Position(line=exc.line, column=exc.column),
            end=Position(line=exc.end_line, column=exc.end_column),
        )
        summary = exc.summary if quoted else "it is not Scenet YAML"
        raise error(summary, file=declared, region=region, loc=loc) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        region = _whole_line(mark.line + 1) if mark is not None else None
        problem = getattr(exc, "problem", None) or describe(exc)
        raise error(
            f"it is not valid YAML: {problem}" if quoted else "it is not valid YAML",
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
            where, message = "", _unquoted(first["type"], original, unknown_key)
        raise error(
            f"{where}: {message}" if where else message,
            file=declared,
            inner=inner,
            region=locate(text, inner),
            loc=loc,
        ) from exc


def _unquoted(kind: str, original: object, unknown_key: str) -> str:
    """What is wrong at a place in a file, in words that quote nothing it holds."""
    if isinstance(original, RuleViolationError):
        return "a value it does not allow here"
    if kind == "extra_forbidden":
        return unknown_key
    if kind == "missing":
        return "a key it needs is missing here"
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
