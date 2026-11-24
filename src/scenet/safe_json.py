r"""Scenet JSON: the language's second carrier, beside Scenet YAML.

Models and programs write JSON, and JSON is not quite YAML: a tab between tokens, an
emoji escaped as two surrogates, a key longer than 1024 characters are all ordinary JSON
that a YAML parser refuses. So a document that is JSON is read by a JSON reader, into the
same data model Scenet YAML reads into: a string is text, a number is a
:class:`WrittenInt <scenet.safe_yaml.WrittenInt>` or a
:class:`WrittenFloat <scenet.safe_yaml.WrittenFloat>` that remembers how it was written
(`"text": 1.50` letters `1.50` in both carriers), and a key written twice in one object is
refused, as YAML's is.

**A document is JSON** when its file ends in `.json`, or when its text opens an object with
a quoted key: `{` and then `"` or `}`, past any white space. A YAML flow mapping, `{cast:
...}`, has an unquoted key, so it is still YAML.

The reader composes the text into PyYAML's own node tree, marks and all, so everything that
locates a value in a document -- `scenet check`, an editor -- reads a JSON document's lines
and columns exactly as it reads a YAML one's. It is written here rather than taken from the
standard library because `json.loads` keeps no position, and keeps the last of two keys
without a word.
"""

import json
import re
from collections.abc import Hashable

import yaml
from yaml.error import Mark
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from scenet.safe_yaml import (
    BOOL_TAG,
    FLOAT_TAG,
    INT_TAG,
    NULL_TAG,
    DuplicateKeyError,
    NestingError,
    ProfileError,
    WrittenFloat,
    WrittenInt,
    is_json,
)

__all__ = ["JsonSyntaxError", "compose", "dump", "is_json", "load"]

#: The tags of the nodes the reader makes, as PyYAML names them.
STR_TAG = "tag:yaml.org,2002:str"
SEQ_TAG = "tag:yaml.org,2002:seq"
MAP_TAG = "tag:yaml.org,2002:map"

#: JSON's white space: nothing else separates its tokens (RFC 8259, section 2).
_SPACE = re.compile(r"[ \t\n\r]*")

#: A string, a number and the three words, each as RFC 8259 writes it.
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_WORDS = {"true": BOOL_TAG, "false": BOOL_TAG, "null": NULL_TAG}


class JsonSyntaxError(yaml.MarkedYAMLError):
    """Text that is not JSON, at the character where reading it stopped.

    A `MarkedYAMLError`, so everything that reports a YAML syntax error -- with its line, its
    column and the line itself -- reports this one the same way.
    """

    def __init__(self, problem: str, mark: Mark) -> None:
        """Say what was expected, and where."""
        super().__init__(problem=problem, problem_mark=mark)


class _Reader:
    """One pass over the text, a character at a time, keeping its line and column."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        # Where the last mark was, on which line, and where that line starts. Reading moves
        # forward, so a mark counts the line breaks since the last one: counting them from
        # the start each time made reading a document take the square of its length.
        self._at = 0
        self._line = 0
        self._line_start = 0

    def mark(self, index: int | None = None) -> Mark:
        """PyYAML's mark at `index`, or where reading is: zero-based, as PyYAML's are."""
        at = self.index if index is None else index
        if at < self._at:
            # Back to a string's opening quote, to say it is never closed: once, at a fault.
            self._at = self._line = self._line_start = 0
        breaks = self.text.count("\n", self._at, at)
        if breaks:
            self._line += breaks
            self._line_start = self.text.rfind("\n", self._at, at) + 1
        self._at = at
        return Mark("<json>", at, self._line, at - self._line_start, self.text, at)

    def skip(self) -> None:
        match = _SPACE.match(self.text, self.index)
        if match is not None:
            self.index = match.end()

    def fault(self, expected: str) -> JsonSyntaxError:
        if self.index >= len(self.text):
            return JsonSyntaxError(f"expected {expected}, but the document ends", self.mark())
        found = self.text[self.index]
        # Never a space, which `skip` has passed: an unprintable one is shown by its number.
        shown = repr(found) if found.isprintable() else f"U+{ord(found):04X}"
        return JsonSyntaxError(f"expected {expected}, found {shown}", self.mark())

    def value(self) -> Node:
        self.skip()
        if self.index >= len(self.text):
            raise self.fault("a value")
        opening = self.text[self.index]
        if opening == "{":
            return self.mapping()
        if opening == "[":
            return self.sequence()
        if opening == '"':
            return self.string()
        number = _NUMBER.match(self.text, self.index)
        if number is not None:
            return self.scalar(number, FLOAT_TAG if re.search("[.eE]", number[0]) else INT_TAG)
        for word, tag in _WORDS.items():
            if self.text.startswith(word, self.index):
                return self.scalar(re.compile(word).match(self.text, self.index), tag)
        raise self.fault("a value: an object, a list, a string, a number, true, false or null")

    def scalar(self, match: re.Match[str] | None, tag: str) -> ScalarNode:
        assert match is not None  # noqa: S101 -- matched by the caller
        start = self.mark()
        self.index = match.end()
        return ScalarNode(tag, match[0], start, self.mark())

    def string(self) -> ScalarNode:
        match = _STRING.match(self.text, self.index)
        if match is None:
            raise self._bad_string()
        start = self.mark()
        self.index = match.end()
        # The standard library decodes the escapes, a surrogate pair to the one character.
        return ScalarNode(STR_TAG, json.loads(match[0]), start, self.mark(), style='"')

    def _bad_string(self) -> JsonSyntaxError:
        """Where a string goes wrong: an escape JSON has not, a control character, no end."""
        index = self.index + 1
        while index < len(self.text):
            # A closing quote is never reached: had nothing been wrong before it, the string
            # would have been read.
            character = self.text[index]
            if character == "\\":
                escape = self.text[index : index + 6]
                if not re.match(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})', escape):
                    return JsonSyntaxError(
                        f"{escape[:2]!r} is no escape JSON has: write \\\\ for a backslash",
                        self.mark(index),
                    )
                index += 6 if escape[1] == "u" else 2
                continue
            if ord(character) < 0x20:
                return JsonSyntaxError(
                    f"a string holds U+{ord(character):04X}, which JSON writes as an escape: "
                    "\\n for a line break, \\t for a tab",
                    self.mark(index),
                )
            index += 1
        return JsonSyntaxError("a string is opened and never closed", self.mark(self.index))

    def mapping(self) -> MappingNode:
        start = self.mark()
        self.index += 1
        pairs: list[tuple[Node, Node]] = []
        self.skip()
        if self.text.startswith("}", self.index):
            self.index += 1
            return MappingNode(MAP_TAG, pairs, start, self.mark(), flow_style=True)
        while True:
            self.skip()
            if not self.text.startswith('"', self.index):
                raise self.fault("a key, in double quotes: JSON quotes every key")
            key = self.string()
            self.skip()
            if not self.text.startswith(":", self.index):
                raise self.fault("':' after the key")
            self.index += 1
            pairs.append((key, self.value()))
            self.skip()
            if self.text.startswith(",", self.index):
                self.index += 1
                continue
            if self.text.startswith("}", self.index):
                self.index += 1
                return MappingNode(MAP_TAG, pairs, start, self.mark(), flow_style=True)
            raise self.fault("',' or '}'")

    def sequence(self) -> SequenceNode:
        start = self.mark()
        self.index += 1
        items: list[Node] = []
        self.skip()
        if self.text.startswith("]", self.index):
            self.index += 1
            return SequenceNode(SEQ_TAG, items, start, self.mark(), flow_style=True)
        while True:
            items.append(self.value())
            self.skip()
            if self.text.startswith(",", self.index):
                self.index += 1
                continue
            if self.text.startswith("]", self.index):
                self.index += 1
                return SequenceNode(SEQ_TAG, items, start, self.mark(), flow_style=True)
            raise self.fault("',' or ']'")


def compose(text: str) -> Node:
    r"""A JSON document as PyYAML's node tree, every node marked where it is written.

    Raises:
        JsonSyntaxError: The text is not one JSON value.
        NestingError: It is nested too deeply to read.

    Example:
        >>> from scenet.safe_json import compose
        >>> node = compose('{\n\t"cast": {}\n}')
        >>> key, _ = node.value[0]
        >>> key.value, key.start_mark.line, key.start_mark.column
        ('cast', 1, 1)
    """
    reader = _Reader(text.removeprefix("\ufeff"))
    try:
        node = reader.value()
    except RecursionError as exc:
        raise NestingError from exc
    reader.skip()
    if reader.index < len(reader.text):
        raise reader.fault("the end of the document, after its one value")
    return node


def _construct(node: Node) -> object:
    """What a node holds, as Scenet YAML's loader builds it."""
    if isinstance(node, MappingNode):
        mapping: dict[Hashable, object] = {}
        seen: dict[str, Node] = {}
        for key_node, value_node in node.value:
            key = str(key_node.value)
            first = seen.setdefault(key, key_node)
            if first is not key_node:
                raise DuplicateKeyError(key, first, key_node, reader="a JSON reader")
            mapping[key] = _construct(value_node)
        return mapping
    if isinstance(node, SequenceNode):
        return [_construct(item) for item in node.value]
    assert isinstance(node, ScalarNode)  # noqa: S101 -- the reader makes no other node
    return _scalar(node)


def _scalar(node: ScalarNode) -> object:
    """What a scalar node holds: text, a number that remembers its source, a flag, null."""
    written = str(node.value)
    if node.tag in (NULL_TAG, BOOL_TAG):
        return None if node.tag == NULL_TAG else written == "true"
    if node.tag == INT_TAG:
        try:
            return WrittenInt(int(written), written)
        except ValueError as exc:
            # Python reads no integer of more than 4300 digits.
            raise ProfileError(
                "syntax",
                f"the number on line {node.start_mark.line + 1} has more digits than a number "
                "can have: write it as a string if it is text",
                node.start_mark,
                node.end_mark,
            ) from exc
    if node.tag == FLOAT_TAG:
        return WrittenFloat(float(written), written)
    return node.value


def load(text: str) -> object:
    r"""Parse a Scenet JSON document into the data model Scenet YAML reads into.

    Raises:
        JsonSyntaxError: The text is not JSON.
        DuplicateKeyError: A key is written twice in one object.
        NestingError: The document is nested too deeply to read.

    Example:
        >>> from scenet.safe_json import load
        >>> load('{"script": [{"say": {"by": "a", "text": 1.50}}], "x": "\\ud83d\\ude00"}')
        {'script': [{'say': {'by': 'a', 'text': 1.5}}], 'x': '😀'}
    """
    node = compose(text)
    try:
        return _construct(node)
    except RecursionError as exc:
        raise NestingError from exc


#: Characters a JSON string writes as an escape here, though JSON would take them raw: the
#: surrogates, which no UTF-8 file can hold alone.
_SURROGATE = re.compile("[\ud800-\udfff]")


def dump(document: object) -> str:
    r"""A document as JSON, indented, with every number as it was written.

    Example:
        >>> from scenet.safe_json import dump
        >>> from scenet.safe_yaml import WrittenFloat
        >>> print(dump({"cast": {"Zoé": {}}, "text": WrittenFloat(1.5, "1.50")}), end="")
        {
          "cast": {
            "Zoé": {}
          },
          "text": 1.50
        }
    """
    return _dump(document, 0) + "\n"


def _dump(value: object, depth: int) -> str:
    inner, outer = "  " * (depth + 1), "  " * depth
    if isinstance(value, dict) and value:
        pairs = (
            f"{inner}{_text(str(key))}: {_dump(item, depth + 1)}" for key, item in value.items()
        )
        return "{\n" + ",\n".join(pairs) + f"\n{outer}}}"
    if isinstance(value, (list, tuple)) and value:
        return (
            "[\n" + ",\n".join(f"{inner}{_dump(item, depth + 1)}" for item in value) + f"\n{outer}]"
        )
    if isinstance(value, (dict, list, tuple)):
        return "{}" if isinstance(value, dict) else "[]"
    return _dump_scalar(value)


def _dump_scalar(value: object) -> str:
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, (WrittenInt, WrittenFloat)):
        return value.source
    if isinstance(value, (int, float)):
        return json.dumps(value, allow_nan=False)
    return _text(str(value))


def _text(value: str) -> str:
    return _SURROGATE.sub(
        lambda match: f"\\u{ord(match[0]):04x}", json.dumps(value, ensure_ascii=False)
    )
