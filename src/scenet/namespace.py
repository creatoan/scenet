"""What a document says of itself: its language, its schema, its kind, and what a tool keeps.

The top of a scene used to be all defaults: every key beside `panels:` was one each panel
inherits, so no key could say anything of the document itself, and nothing told a document
of this language from one of the next. Now some keys are the document's own, and nobody's
default:

- `scenet: 1`, the **language** it is written in: the language's major version, an integer,
  separate from the version of the package. Left out, it is 1. A later one is refused with
  nothing else said, since a document of a later language is not one of this language with
  mistakes in it.
- `$schema`, the JSON Schema an editor validates the document with.
- `meta`, a mapping of whatever a tool keeps about the document, read by nobody yet.
- `kind`, in a panel, a scene or a comic script's front matter: `panel`, `scene` or `book`.
  A document is still read by its shape -- one with `panels:` is a scene -- and `kind` only
  says so, so a document that says one thing and is another is refused. Books are not yet.
- `include` and `defaults`, kept for a later version of the language, and refused today.

And any key that starts with `x-` is an **extension**: accepted and ignored in every mapping
of every document, so a tool can annotate one. No actor id or panel name starts with `x-`
(:mod:`scenet.identifiers`), so a key under `cast:` or `panels:` is never both.

`direction`, `page`, `pages` and `panels` are the document's too, and were already.

Example:
    >>> from scenet.namespace import LANGUAGE, split_head, stripped
    >>> document = stripped({"scenet": 1, "x-tool": "draft", "cast": {}})
    >>> split_head(document, ("scenet",)), LANGUAGE
    (({'scenet': 1}, {'cast': {}}), 1)
"""

from collections.abc import Collection
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field, StrictInt, WithJsonSchema

from scenet.errors import RuleViolationError
from scenet.identifiers import EXTENSION_PREFIX
from scenet.ir import Strict, Text

__all__ = [
    "ASSET_KEYS",
    "DOCUMENT_KEYS",
    "EXTENSION_PREFIX",
    "KIND_KEY",
    "LANGUAGE",
    "META_KEY",
    "NOT_YET_KEYS",
    "SCHEMA_KEY",
    "VERSION_KEY",
    "AssetHead",
    "DocumentHead",
    "Kind",
    "is_extension",
    "kind_fault",
    "language_fault",
    "own_document_key",
    "split_head",
    "stripped",
    "without_extensions",
]

#: The language this Scenet reads: the major version a document's `scenet:` names.
LANGUAGE = 1

#: The key a document's language is written under.
VERSION_KEY = "scenet"

#: The key naming the JSON Schema an editor checks the document with.
SCHEMA_KEY = "$schema"

#: The key a tool keeps what it knows about the document under.
META_KEY = "meta"

#: The key saying which kind of document it is.
KIND_KEY = "kind"

#: The keys a later version of the language will read, refused until then.
NOT_YET_KEYS = ("include", "defaults")

#: The keys every document has of its own: a puppet file and an artwork contract too.
ASSET_KEYS = (VERSION_KEY, SCHEMA_KEY, META_KEY)

#: The keys a panel, a scene and a comic script's front matter have of their own.
DOCUMENT_KEYS = (*ASSET_KEYS, KIND_KEY, *NOT_YET_KEYS)


class Kind(StrEnum):
    """Which kind of document it is: one panel, a scene of panels, or a book of scenes.

    A document is read by its shape whether it says or not: one with `panels:` is a scene,
    and one without is a panel. Books are for a later version of the language.
    """

    PANEL = "panel"
    """One panel: a document with no `panels:`."""
    SCENE = "scene"
    """Panels under `panels:`, and the pages they are laid out on."""
    BOOK = "book"
    """Reserved for a later version of the language, which reads books."""


def is_extension(key: object) -> bool:
    """Whether a key is an extension's, which every mapping takes and nobody reads.

    Example:
        >>> from scenet.namespace import is_extension
        >>> is_extension("x-tool"), is_extension("X-tool"), is_extension("xtool")
        (True, False, False)
    """
    return isinstance(key, str) and key.startswith(EXTENSION_PREFIX)


def without_extensions(node: object) -> object:
    """A document's value with every extension key taken out, at every depth.

    In lists too, where a mapping in a list -- a script event -- is a mapping like any other.

    Example:
        >>> from scenet.namespace import without_extensions
        >>> without_extensions([{"say": {"by": "a", "x-take": 2}, "x-id": 1}])
        [{'say': {'by': 'a'}}]
    """
    if isinstance(node, dict):
        return {
            key: without_extensions(value) for key, value in node.items() if not is_extension(key)
        }
    if isinstance(node, list):
        return [without_extensions(item) for item in node]
    return node


def stripped(data: dict[str, Any]) -> dict[str, Any]:
    """A document's top-level mapping with every extension key taken out, at every depth."""
    return {key: without_extensions(value) for key, value in data.items() if not is_extension(key)}


def split_head(
    data: dict[str, Any], keys: Collection[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A document's own keys, and the rest of it, each in the order it was written."""
    head = {key: value for key, value in data.items() if key in keys}
    rest = {key: value for key, value in data.items() if key not in keys}
    return head, rest


def whole(value: object) -> object:
    """A number written with a point but none after it, `1.0`, as the whole number it is.

    JSON has one kind of number, so a JSON Schema's `integer` is any number with nothing
    after its point, and a document that writes `scenet: 1.0` is of language 1 to an editor.
    So it is to Scenet. `1.5` is no whole number, and is left for validation to refuse.

    Example:
        >>> from scenet.namespace import whole
        >>> whole(1.0), whole(1.5), whole(True)
        (1, 1.5, True)
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def language_fault(head: dict[str, Any]) -> RuleViolationError | None:
    """The fault of a document written for a later language than this one, or None.

    Found before anything else, and alone: what a later language means by its keys is not
    this one's to say, so nothing more is checked.

    Example:
        >>> from scenet.namespace import language_fault
        >>> str(language_fault({"scenet": 2})).split(";")[0]
        'written for Scenet language 2'
        >>> language_fault({"scenet": 1}) is None
        True
    """
    value = whole(head.get(VERSION_KEY))
    if not isinstance(value, int) or isinstance(value, bool) or value <= LANGUAGE:
        return None
    return RuleViolationError(
        f"written for Scenet language {value}; this is language {LANGUAGE}. Compile it with "
        f"a later Scenet, one that reads language {value}",
        rule="language-version",
        loc=(VERSION_KEY,),
    )


def _not_yet(key: str, value: object, purpose: str, instead: str) -> object:
    """Refuse a key kept for a later language, unless it is written as `null`: not written."""
    if value is None:
        return None
    raise RuleViolationError(
        f"'{key}' is not yet in the language: a later version will read it, {purpose}. "
        f"Delete it; {instead}",
        rule="not-yet",
    )


def _no_include(value: object) -> object:
    """Refuse an `include`, kept for a later language."""
    return _not_yet(
        "include",
        value,
        "to read one document into another",
        "write here what it would include",
    )


def _no_defaults(value: object) -> object:
    """Refuse `defaults`, kept for a later language."""
    return _not_yet(
        "defaults",
        value,
        "to give the panels of a scene what they share",
        "in a scene, a key written beside `panels:` is a default every panel inherits",
    )


def _no_book(value: Kind) -> Kind:
    """Refuse `kind: book`, kept for a later language."""
    if value is Kind.BOOK:
        raise RuleViolationError(
            "'kind: book' is not yet in the language: a later version will read books. "
            "Write `kind: scene` for a scene, or leave `kind` out",
            rule="not-yet",
        )
    return value


#: The language a document is written in: a whole number, at least 1. One later than this
#: language is refused by :func:`language_fault`, which the schema says as a maximum.
Version = Annotated[
    StrictInt, Field(ge=1, json_schema_extra={"maximum": LANGUAGE}), BeforeValidator(whole)
]

#: A key kept for a later language. Only `null`, which is not writing it, is accepted.
Reserved = Annotated[object, WithJsonSchema({"type": "null"})]


class AssetHead(Strict):
    """What any document says of itself: a puppet file and an artwork contract as well."""

    scenet: Version | None = None
    """The language the document is written in: the major version of the Scenet language,
    an integer, which is not the version of the package. Left out, it is 1. A document
    written for a later language is refused, with nothing else said of it.
    """
    schema_: Text | None = Field(
        default=None,
        alias=SCHEMA_KEY,
        title="Schema",
        description=(
            "The JSON Schema an editor checks the document with: a path or a URL. Scenet "
            "reads its own schema, whatever this says."
        ),
    )
    meta: dict[Any, Any] | None = None
    """What a tool keeps about the document: a mapping of anything, which Scenet reads
    nothing of yet. A later version of the language gives it a shape.
    """


class DocumentHead(AssetHead):
    """What a panel, a scene or a comic script's front matter says of itself."""

    kind: Annotated[Kind, AfterValidator(_no_book)] | None = None
    """Which kind of document it is: `panel`, or `scene` for one with `panels:`. A document
    is read by its shape whether it says or not, so one that says it is a scene and has no
    `panels:` is refused, as is the other way round. `book` is kept for a later version of
    the language.
    """
    include: Annotated[Reserved, AfterValidator(_no_include)] = None
    """Kept for a later version of the language, which will read one document into
    another. Refused until then.
    """
    defaults: Annotated[Reserved, AfterValidator(_no_defaults)] = None
    """Kept for a later version of the language. Refused until then: in a scene, a key
    written beside `panels:` is a default every panel inherits.
    """


def kind_fault(
    head: dict[str, Any], shape: Kind, *, why: str | None = None
) -> RuleViolationError | None:
    """The fault of a document whose `kind` is not the kind its shape makes it, or None.

    Args:
        head: The document's own keys, as written.
        shape: What its shape makes it: a scene with `panels:`, a panel without.
        why: What to say in place of the message for its shape, for a comic script.

    Example:
        >>> from scenet.namespace import Kind, kind_fault
        >>> kind_fault({"kind": "scene"}, Kind.SCENE) is None
        True
        >>> kind_fault({"kind": "panel"}, Kind.SCENE).rule
        'document-kind'
    """
    written = head.get(KIND_KEY)
    # One that is not a kind, or a book, is the model's to refuse.
    if written not in (Kind.PANEL, Kind.SCENE) or written == shape:
        return None
    if why is None:
        why = (
            "this document says `kind: panel`, but it holds its panels under `panels:`, which "
            "makes it a scene: write `kind: scene`, or leave `kind` out"
            if shape is Kind.SCENE
            else "this document says `kind: scene`, but it has no `panels:`, so it is one "
            "panel: write `kind: panel`, or put its panels under `panels:`"
        )
    return RuleViolationError(why, rule="document-kind", loc=(KIND_KEY,))


def own_document_key(key: str, where: str) -> str:
    """Why a panel's own `scenet`, `meta` or `kind` is refused, and where to write it.

    Example:
        >>> from scenet.namespace import own_document_key
        >>> own_document_key("meta", "at the top of the document").endswith("the document")
        True
    """
    return (
        f"'{key}' says something of the whole document, so a panel cannot have one of its "
        f"own: write it once, {where}"
    )
