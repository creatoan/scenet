"""Where in the source a value came from.

`yaml.safe_load` returns values and throws away everything about where they were
written, which is fine for compiling and useless for reporting. `yaml.compose` parses
the same text into a *node* tree instead, and every node carries `start_mark` and
`end_mark`. So the document is composed a second time, purely to answer "where is
`script.0.say.by`?".

**`ruamel.yaml` is the library usually reached for here**, and its `.lc` line/column
marks would do the same job. It was not used: PyYAML is already a dependency and this
needs one function, so adding a second YAML implementation to the runtime -- and to the
licence gate -- would buy nothing.

Marks are 0-based; SARIF is 1-based. The conversion happens once, here, at the boundary.
"""

import functools
from dataclasses import dataclass

import yaml

from scenet.safe_json import compose as compose_json
from scenet.safe_yaml import is_json

__all__ = ["KEY", "Position", "Region", "locate"]

#: The last step of a path to a mapping's key rather than to its value, as pydantic writes
#: one: `("cast", "old man", "[key]")` is the key `old man`.
KEY = "[key]"


@dataclass(frozen=True, slots=True, order=True)
class Position:
    """A one-based line and column, as SARIF and every editor count them.

    Attributes:
        line: One-based line number.
        column: One-based column number.
    """

    line: int
    column: int


@dataclass(frozen=True, slots=True, order=True)
class Region:
    """A span of source, from `start` up to `end`.

    Attributes:
        start: Where the value begins.
        end: Where it ends. SARIF treats the end column as exclusive, which is also how
            PyYAML's end marks behave, so the two agree without adjustment.
    """

    start: Position
    end: Position


#: Where a diagnostic points when nothing better is known. SARIF requires a region on
#: every result, and refusing to emit one would lose the finding entirely.
DOCUMENT_START = Region(start=Position(line=1, column=1), end=Position(line=1, column=2))


def _mark_to_region(node: yaml.Node) -> Region:
    """Convert a node's PyYAML marks into a one-based region."""
    return Region(
        start=Position(line=node.start_mark.line + 1, column=node.start_mark.column + 1),
        end=Position(line=node.end_mark.line + 1, column=node.end_mark.column + 1),
    )


def _step(node: yaml.Node, step: str | int) -> tuple[yaml.Node, yaml.Node | None] | None:
    """Take one step into a composed node tree.

    Args:
        node: The node to step from.
        step: A mapping key, a sequence index, or the name an item of a list form gives
            itself.

    Returns:
        The child node and the node that names it -- its key, or the name the item gives
        itself, and `None` for a sequence index. `None` if this node cannot be stepped into
        that way, which happens routinely, because a pydantic `loc` path may name a field
        of a value that is not the shape the schema expected.
    """
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            # Compare as text: YAML keys arrive as scalar nodes, and `1` written as a
            # key is the string "1" here whether the path step is an int or a str.
            if isinstance(key, yaml.ScalarNode) and key.value == str(step):
                return value, key
        return None

    if isinstance(node, yaml.SequenceNode) and isinstance(step, int):
        if 0 <= step < len(node.value):
            return node.value[step], None
        return None

    if isinstance(node, yaml.SequenceNode):
        # A panel or an actor of a list form, `[{name: one, ...}]`, named as the mapping
        # form names it once the list is lowered (`scenet.compose.lowered`).
        return _named_item(node, step)

    return None


#: The key an item of a list form is named by: `scenet.compose.ID_KEY`.
_NAMING_KEYS = ("id",)


def _named_item(node: yaml.SequenceNode, step: str | int) -> tuple[yaml.Node, yaml.Node] | None:
    """The item of a list form that names itself `step`, and the node of its name."""
    for item in node.value:
        if not isinstance(item, yaml.MappingNode):
            continue
        for key, value in item.value:
            if (
                isinstance(key, yaml.ScalarNode)
                and key.value in _NAMING_KEYS
                and isinstance(value, yaml.ScalarNode)
                and value.value == str(step)
            ):
                return item, value
    return None


def locate(text: str, path: tuple[str | int, ...]) -> Region | None:
    r"""Find where `path` was written in `text`.

    Walks as far down the path as the document allows and reports the deepest node it
    reached, so a path naming a field of something malformed still points at the
    malformed thing rather than giving up and pointing at the document.

    Args:
        text: The YAML source.
        path: A pydantic-style location, as in `("script", 0, "say", "by")`. Ending in
            :data:`KEY`, it names the key the step before it is written under.

    Returns:
        The region, or `None` if the text does not compose at all -- in which case the
        caller has a syntax error to report and no use for a path. So when one path is
        not found, no shorter path in the same text is either.

    Example:
        >>> from scenet.frontends.positions import locate
        >>> region = locate("cast:\n  alice: {reference: alice}\n", ("cast", "alice"))
        >>> region.start.line
        2
        >>> key = locate("cast: {alice: {}}\n", ("cast", "alice", "[key]"))
        >>> key.start.column, key.end.column
        (8, 13)
    """
    node = _composed(text)
    if node is None:
        return None

    deepest = node
    key: yaml.Node | None = None
    above: yaml.Node | None = None
    for step in path:
        if step == KEY and key is not None:
            # The key itself rather than its value: an actor id or a panel name refused.
            return _mark_to_region(key)
        stepped = _step(deepest, step)
        if stepped is None:
            break
        child, key = stepped
        # The name of an item is inside it, where the item already starts.
        above = key if isinstance(deepest, yaml.MappingNode) else None
        deepest = child

    region = _mark_to_region(deepest)
    # A block written beneath its key starts on the line after it, at whichever field
    # happens to come first -- which names nothing about the fault. The key does.
    is_block = isinstance(deepest, yaml.CollectionNode) and not deepest.flow_style
    if above is not None and is_block:
        return Region(start=_mark_to_region(above).start, end=region.end)
    return region


#: libyaml's loader when PyYAML was built with it, which composes a long document many
#: times faster than PyYAML's own: a line of a megabyte took most of a second.
_FAST_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


@functools.lru_cache(maxsize=8)
def _composed(text: str) -> yaml.Node | None:
    """The document's node tree, composed once however many findings locate in it.

    Never changed by a caller: a node is read, not written. `None` for text that does not
    compose, or composes to nothing.
    """
    try:
        # A JSON document is composed into the same node tree, marked the same way (#354).
        return compose_json(text) if is_json(text) else yaml.compose(text, Loader=_FAST_LOADER)
    except yaml.YAMLError:
        return None


def syntax_error_region(exc: yaml.YAMLError) -> Region:
    """Where a YAML parse error happened.

    Args:
        exc: The error PyYAML raised.

    Returns:
        The problem mark as a region, or the start of the document when the error
        carries no mark -- which some do.
    """
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return DOCUMENT_START
    start = Position(line=mark.line + 1, column=mark.column + 1)
    # An error found at the end of the input -- a bracket never closed -- is marked just
    # past the final newline, on a line the file does not have. It belongs at the end of
    # the last line, where an editor can show it.
    buffer = getattr(mark, "buffer", None)
    if isinstance(buffer, str):
        lines = buffer.rstrip("\0").splitlines()
        if lines and start.line > len(lines):
            start = Position(line=len(lines), column=len(lines[-1]) + 1)
    return Region(start=start, end=Position(line=start.line, column=start.column + 1))
