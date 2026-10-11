"""Files a document names, found beside the document.

A document may point at a file it does not contain -- a lettering face now, an image to
letter over later (#70). Every such path is read **relative to the folder the document
is in**, the way a link in a web page is, and never as an absolute path. That is what
lets a document and the files it names travel together and compile the same anywhere,
and what stops a server compiling documents it was sent from being steered at files of
its own.

The folder is the document's, not the working directory's: `scenet build
comics/one.panel.yaml` reads `fonts/x.ttf` from `comics/fonts/`, wherever it was run
from. Text compiled with no file behind it has no folder, and can name no file unless
the caller says which folder it belongs to.

Nothing here reaches the output. A resolved path is used to open a file and is then
forgotten; what a Core records about a font is what is in it.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath

from scenet.errors import PanelSyntaxError

__all__ = ["resolve_relative"]


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
        PanelSyntaxError: The path is empty or absolute, or there is no folder to read
            it from.

    Example:
        >>> from pathlib import Path
        >>> from scenet.paths import resolve_relative
        >>> found = resolve_relative("fonts/a.ttf", Path("comic"), what="font", rule="font-file")
        >>> found.as_posix()
        'comic/fonts/a.ttf'
    """
    if not declared.strip():
        raise PanelSyntaxError(f"the {what} path is empty", rule=rule, loc=loc)
    if PurePosixPath(declared).is_absolute() or PureWindowsPath(declared).anchor:
        raise PanelSyntaxError(
            f"the {what} path {declared!r} is absolute; write it relative to the folder the "
            "document is in, so the document and its files compile the same anywhere",
            rule=rule,
            loc=loc,
        )
    if base is None:
        raise PanelSyntaxError(
            f"the {what} {declared!r} is read from beside the document, and this document "
            "has no folder: it was compiled from text, not from a file",
            rule=rule,
            loc=loc,
        )
    return base / declared
