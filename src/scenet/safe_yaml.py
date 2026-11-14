"""Scenet YAML: reading a document so that ordinary dialogue is never mistyped.

PyYAML reads YAML 1.1, in which `No` is false, `1984` a number, `12:30` the sexagesimal
750, `2024-05-01` a date and `01750` the octal 1000. For a language whose values are
mostly lines of dialogue, that refused `text: No` and silently drew a panel 1000 units
tall. And it reads features no panel needs -- tags that build any object they name,
anchors and aliases that expand without bound, merge keys -- which are a confusion and an
attack surface.

So every panel, scene, script front matter and puppet is read through :func:`load`, by a
loader built from PyYAML's own parts with three of them replaced. The profile they
implement is stated, normatively, in `docs/reference/language/yaml_profile.md`:

- **The resolver** (:class:`ProfileResolver`) types a plain scalar as the YAML 1.2 JSON
  schema does: `true`, `false`, `null` (or nothing at all), and integers and floats as
  JSON spells them. Every other plain scalar is text, exactly as written.
- **The scanner** refuses a tag, an anchor or an alias where it is written, and a tab
  where a token would start, in words an author recognises.
- **The composer and the constructor** refuse a merge key, a key that is not a scalar and
  a key written twice; every key is text, exactly as written, so `cast: {on: ..., no: ...}`
  names two actors. A number keeps its source (:class:`WrittenInt`, :class:`WrittenFloat`),
  so where the language expects text, :func:`as_written` gives back what was typed:
  `text: 1984` letters 1984 and `text: 1.50` letters 1.50.

Each refusal is a :class:`ProfileError`, which is a `yaml.YAMLError` -- so anything that
already handles malformed YAML handles it -- and carries the rule it breaks and the span
it covers, for a finding at exactly the text at fault.

`ruamel.yaml` reads YAML 1.2 and refuses a repeated key by default, but a second YAML
implementation in the runtime, and in the licence gate, would buy little: every rule here
is a few lines on top of PyYAML's machinery, and the same trade was declined for source
positions (`frontends/positions.py`).
"""

import math
import re
from collections.abc import Hashable
from typing import Any, ClassVar, cast

import yaml
from yaml.composer import Composer
from yaml.constructor import SafeConstructor
from yaml.error import Mark
from yaml.nodes import MappingNode, Node, ScalarNode
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import BaseResolver
from yaml.scanner import Scanner
from yaml.tokens import AliasToken, AnchorToken, TagToken

__all__ = [
    "ALIAS_HINT",
    "DuplicateKeyError",
    "NestingError",
    "ProfileError",
    "ProfileResolver",
    "WrittenFloat",
    "WrittenInt",
    "as_written",
    "describe",
    "load",
    "mistyped",
]

#: The tags the profile's plain scalars resolve to, besides text.
BOOL_TAG = "tag:yaml.org,2002:bool"
NULL_TAG = "tag:yaml.org,2002:null"
INT_TAG = "tag:yaml.org,2002:int"
FLOAT_TAG = "tag:yaml.org,2002:float"

#: An integer as JSON writes it: no sign but a minus, no leading zero, no underscore.
INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)")

#: A float as the YAML 1.2 JSON schema writes it. An integer matches too, which is why
#: the integer resolver is registered first: the first that matches wins.
FLOAT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?")

#: What every refusal of a feature says it is instead, so the message is one sentence.
_WITHOUT = "Scenet YAML has no"


class ProfileError(yaml.MarkedYAMLError):
    """Something the profile refuses, at the span of source it covers.

    Attributes:
        rule: The rule it breaks, a key into :data:`RULES <scenet.diagnostics.RULES>`.
        summary: One line saying what is wrong and what to write instead, without
            PyYAML's position block, for a diagnostic that carries the position separately.
        line: One-based line where the span starts.
        column: One-based column where it starts.
        end_line: One-based line where it ends.
        end_column: One-based column just past its last character.
    """

    def __init__(self, rule: str, summary: str, start: Mark, end: Mark) -> None:
        """Build the error from what it says and the marks around the text at fault.

        Args:
            rule: The rule it breaks.
            summary: What is wrong, in an author's words.
            start: PyYAML's mark at the first character of the span.
            end: Its mark just past the last.
        """
        self.rule = rule
        self.summary = summary
        self.line = start.line + 1
        self.column = start.column + 1
        self.end_line = end.line + 1
        self.end_column = end.column + 1
        super().__init__(problem=summary, problem_mark=start)


class DuplicateKeyError(ProfileError):
    """A key written twice in one mapping.

    The YAML specification requires every key in a mapping to be unique, so a document
    that repeats one is not valid YAML. PyYAML builds it anyway: the dictionary keeps the
    **last** value, and the first disappears without a word (yaml/pyyaml#41, still open).
    A strict language that rejects every unknown key would otherwise lose a whole known
    one -- a panel, a character, a pose -- and compile whatever was left.

    Attributes:
        key: The repeated key, as written.
        first_line: One-based line of the first occurrence. `line` and `column` are the
            second's, which is where the fault is.
    """

    def __init__(self, key: str, first: Node, second: Node) -> None:
        """Build the error from the two key nodes.

        Args:
            key: The repeated key, as written.
            first: The node of its first occurrence.
            second: The node of the one that repeats it.
        """
        self.key = key
        self.first_line = first.start_mark.line + 1
        line = second.start_mark.line + 1
        summary = (
            f"key {key!r} appears twice in one mapping, first on line {self.first_line} and "
            f"again on line {line}; YAML would keep only the last"
        )
        super().__init__("duplicate-key", summary, second.start_mark, second.end_mark)


class NestingError(yaml.YAMLError):
    """The document is nested more deeply than the parser can follow.

    PyYAML parses and builds a document recursively, so nesting a few hundred levels
    deep reaches Python's recursion limit. `RecursionError` is not a YAML error, and it
    escaped every handler that catches one -- `scenet check` and `build` both ended in a
    traceback. No panel is nested more than a handful of levels, so a document this deep
    is a mistake or an attack, and is reported as one.
    """

    def __init__(self) -> None:
        """Say what went wrong in the words the diagnostic will show."""
        super().__init__("the document is nested too deeply to read")


class WrittenInt(int):
    """An integer, and the text it was written as.

    It is the integer everywhere a number is expected, and its `source` where text is:
    see :func:`as_written`. JSON writes it as the integer it is.

    Example:
        >>> from scenet.safe_yaml import WrittenInt
        >>> number = WrittenInt(1984, "1984")
        >>> number + 1, number.source
        (1985, '1984')
    """

    source: str

    def __new__(cls, value: int, source: str) -> "WrittenInt":
        """Make the integer, remembering how it was written."""
        made = super().__new__(cls, value)
        made.source = source
        return made

    def __reduce__(self) -> tuple[type["WrittenInt"], tuple[int, str]]:
        """What `copy` and `pickle` rebuild it from: the value and the source."""
        return WrittenInt, (int(self), self.source)


class WrittenFloat(float):
    """A float, and the text it was written as: `1.50` is 1.5, and letters 1.50.

    Example:
        >>> from scenet.safe_yaml import WrittenFloat
        >>> number = WrittenFloat(1.5, "1.50")
        >>> number * 2, number.source
        (3.0, '1.50')
    """

    source: str

    def __new__(cls, value: float, source: str) -> "WrittenFloat":
        """Make the float, remembering how it was written."""
        made = super().__new__(cls, value)
        made.source = source
        return made

    def __reduce__(self) -> tuple[type["WrittenFloat"], tuple[float, str]]:
        """What `copy` and `pickle` rebuild it from: the value and the source."""
        return WrittenFloat, (float(self), self.source)


def as_written(value: object) -> object:
    """A scalar as the text it was written as, for a field that expects text.

    `true` and `false` are the only spellings of a boolean, so they are their own text. A
    number read from YAML remembers its source; one built in Python is written as Python
    writes it. `null` is never text -- it means no value -- and anything else is passed
    through, for validation to accept or refuse.

    Example:
        >>> from scenet.safe_yaml import as_written, load
        >>> line = load("text: 1.50")["text"]
        >>> line, as_written(line), as_written(True), as_written(None)
        (1.5, '1.50', 'true', None)
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, WrittenInt | WrittenFloat):
        return value.source
    if isinstance(value, int | float):
        return str(value)
    return value


class ProfileResolver(BaseResolver):
    """Types a plain scalar as the YAML 1.2 JSON schema does, and every other one as text.

    PyYAML's own resolver implements YAML 1.1. This one starts from `BaseResolver`, which
    resolves nothing, and registers four patterns: so `yes`, `True`, `~`, `0x400`, `01750`,
    `1_0`, `.inf`, `12:30` and `2024-05-01` are all text, and a quoted scalar always is.

    Example:
        >>> from scenet.safe_yaml import load
        >>> load("[true, True, null, ~, 1984, 01750, 1.5, .5]")
        [True, 'True', None, '~', 1984, '01750', 1.5, '.5']
    """


ProfileResolver.add_implicit_resolver(BOOL_TAG, re.compile(r"^(?:true|false)$"), list("tf"))
ProfileResolver.add_implicit_resolver(NULL_TAG, re.compile(r"^(?:null|)$"), ["n", ""])
ProfileResolver.add_implicit_resolver(
    INT_TAG, re.compile(f"^{INTEGER.pattern}$"), list("-0123456789")
)
ProfileResolver.add_implicit_resolver(
    FLOAT_TAG, re.compile(f"^{FLOAT.pattern}$"), list("-0123456789")
)


#: YAML 1.1's spellings of a yes and a no, any case, and the 1.2 core schema's capitalised
#: `True` and `False`: all text in Scenet YAML, and each meant one of the two.
_YES = frozenset({"y", "yes", "on", "true"})
_NO = frozenset({"n", "no", "off", "false"})

#: Numbers as YAML 1.1 or another reader would read them, and Scenet YAML does not: a
#: base prefix, a leading zero, an underscore, a sign or a point with no digit before it.
_BASED = re.compile(r"(?P<sign>[-+]?)0(?P<base>[xob])(?P<digits>[0-9a-f_]+)", re.IGNORECASE)
_DECIMAL = re.compile(
    r"(?P<sign>[-+]?)(?P<whole>[0-9_]*)(?P<rest>(?:\.[0-9_]*)?(?:e[-+]?[0-9]+)?)", re.I
)
_NOT_FINITE = re.compile(r"[-+]?\.(?:inf|nan)", re.IGNORECASE)
_BASES = {"x": 16, "o": 8, "b": 2}


def mistyped(written: str, expected: str) -> str | None:
    """What to write instead of text that a yes-or-no or a number field was given.

    Scenet YAML reads `yes`, `On` and `True` as text, and `0x400`, `01750` and `1_0` too --
    YAML 1.1 read them as a boolean or a number, so they are what an author used to write,
    and what a model trained on YAML 1.1 still writes. Each says what it is now, and what
    it would be written as.

    Args:
        written: The text the field was given.
        expected: `"bool"` for a yes-or-no field, `"number"` for a number.

    Returns:
        The message, or `None` for text that spells neither.

    Example:
        >>> from scenet.safe_yaml import mistyped
        >>> mistyped("yes", "bool").endswith("only true and false as a yes or a no: write true")
        True
        >>> mistyped("0x400", "number").endswith("only as JSON writes it, in decimal: write 1024")
        True
        >>> mistyped("hello", "number") is None
        True
    """
    if expected == "bool":
        return _mistyped_flag(written)
    if _NOT_FINITE.fullmatch(written):
        return f"'{written}' is text in Scenet YAML, and a number here is finite: write one"
    decimal, octal = _as_decimal(written)
    if decimal is None:
        return None
    if decimal == written:
        return f"'{written}' is quoted, so it is text: write {written}, without the quotes"
    message = (
        f"'{written}' is text in Scenet YAML, which reads a number only as JSON writes it, in "
        f"decimal: write {decimal}"
    )
    if octal is not None:
        message += f" (YAML 1.1 read it as the octal {octal})"
    return message


def _mistyped_flag(written: str) -> str | None:
    """`mistyped` for a yes-or-no field."""
    word = written.lower()
    if word not in _YES | _NO:
        return None
    if written in {"true", "false"}:
        return f"'{written}' is quoted, so it is text: write {written}, without the quotes"
    return (
        f"'{written}' is text in Scenet YAML, which reads only true and false as a yes or a no: "
        f"write {'true' if word in _YES else 'false'}"
    )


def _as_decimal(written: str) -> tuple[str | None, int | None]:
    """The decimal a number-like text spells, and what YAML 1.1 read it as when that differs.

    `(None, None)` for text that is no number at all, or that is a number already.
    """
    based = _BASED.fullmatch(written)
    if based is not None:
        digits = based["digits"].replace("_", "")
        try:
            value = int(digits, _BASES[based["base"].lower()])
        except ValueError:
            return None, None
        return f"{'-' if based['sign'] == '-' else ''}{value}", None
    found = _DECIMAL.fullmatch(written)
    if found is None or not any(char.isdigit() for char in written):
        return None, None
    whole = found["whole"].replace("_", "")
    rest = found["rest"].replace("_", "")
    if not whole and not (rest.startswith(".") and rest[1:2].isdigit()):
        return None, None
    decimal = f"{'-' if found['sign'] == '-' else ''}{whole.lstrip('0') or '0'}{rest}"
    octal = None
    if not rest and whole.startswith("0") and set(whole) <= set("01234567"):
        # YAML 1.1 read a leading zero as octal: say so where that was another number.
        value = int(whole, 8)
        octal = value if value != int(whole) else None
    return decimal, octal


#: What an author who wrote `*told*` meant, said in their terms rather than YAML's.
ALIAS_HINT = (
    "a value that starts with '*' is read by YAML as an alias to an anchor, so quote the "
    "whole value. To stress a word, write it between underscores instead: _told_"
)


class _ProfileScanner(Reader, Scanner):
    """PyYAML's scanner, refusing tags, anchors and aliases, and a tab before a token."""

    def scan_anchor(self, TokenClass: type[AnchorToken | AliasToken]) -> AnchorToken | AliasToken:  # noqa: N803 -- PyYAML's name
        """Read an anchor or an alias, then refuse it where it is written."""
        token = super().scan_anchor(TokenClass)
        if TokenClass is AliasToken:
            summary = (
                f"'*{token.value}' is a YAML alias, and {_WITHOUT} anchors or aliases: {ALIAS_HINT}"
            )
        else:
            summary = (
                f"'&{token.value}' is a YAML anchor, and {_WITHOUT} anchors or aliases: write "
                "the value out where it is used, or inherit it with `over:` or a scene's "
                "defaults"
            )
        raise ProfileError("yaml-anchor", summary, token.start_mark, token.end_mark)

    def scan_tag(self) -> TagToken:
        """Read a tag, then refuse it where it is written."""
        token = super().scan_tag()
        handle, suffix = token.value
        summary = (
            f"'{handle or ''}{suffix}' is a YAML tag, and {_WITHOUT} tags: a value means what "
            "it says. Delete the tag, and quote the value if it is text"
        )
        raise ProfileError("yaml-tag", summary, token.start_mark, token.end_mark)

    def scan_to_next_token(self) -> None:
        """Skip to the next token, and refuse a tab found where one would start.

        PyYAML refuses it too, as "found character that cannot start any token", which
        tells nobody that the fix is to press space instead.
        """
        super().scan_to_next_token()
        if self.peek() != "\t":
            return
        start = self.get_mark()
        length = 1
        while self.peek(length) == "\t":
            length += 1
        before = self.buffer[self.pointer - self.column : self.pointer]
        if before.strip(" "):
            summary = (
                f"line {start.line + 1} has a tab at column {start.column + 1}, and outside "
                "quotes YAML separates with spaces only: replace the tab with spaces"
            )
        else:
            summary = (
                f"line {start.line + 1} is indented with a tab, and YAML indents with spaces "
                "only: replace the tab with spaces"
            )
        self.forward(length)
        raise ProfileError("syntax", summary, start, self.get_mark())


class _ProfileComposer(Composer):
    """PyYAML's composer, refusing a merge key and a key that is not a scalar."""

    def compose_node(self, parent: Node | None, index: object) -> Node | None:
        """Compose a node; if it is a mapping's key, refuse one the profile does not allow.

        A key is composed with no index, which is how it is told from a value. PyYAML's
        stubs say the index is an `int`; it is that for a list item, the key's node for a
        mapping's value, and `None` for a key or the document.
        """
        node = super().compose_node(parent, cast("int", index))
        if node is None or not isinstance(parent, MappingNode) or index is not None:
            return node
        if not isinstance(node, ScalarNode):
            raise ProfileError(
                "syntax",
                "a key is a name, and this one is a list or a mapping: write a name, quoted "
                "if need be",
                node.start_mark,
                node.end_mark,
            )
        if node.value == "<<" and node.style is None:
            raise ProfileError(
                "yaml-merge-key",
                f"'<<' is a YAML merge key, and {_WITHOUT} merge keys: write the keys out, or "
                "inherit them with `over:` or a scene's defaults",
                node.start_mark,
                node.end_mark,
            )
        return node


class _ProfileConstructor(SafeConstructor):
    """Builds what the profile's resolver typed, and nothing else.

    Its table of constructors starts empty: a tag is refused before anything is built,
    and the resolver yields only these seven, so PyYAML's timestamps, sets and binaries
    cannot be reached even by mistake.
    """

    yaml_constructors: ClassVar[dict[str | None, Any]]

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        """A mapping, every key the text it was written as, none of them twice."""
        mapping: dict[Hashable, Any] = {}
        seen: dict[str, Node] = {}
        for key_node, value_node in node.value:
            # The composer refused every key that is not a scalar.
            key = str(key_node.value)
            first = seen.setdefault(key, key_node)
            if first is not key_node:
                raise DuplicateKeyError(key, first, key_node)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping

    def construct_written_int(self, node: ScalarNode) -> WrittenInt:
        """An integer, remembering how it was written."""
        try:
            value = int(node.value)
        except ValueError as exc:
            # Python reads no integer of more than 4300 digits.
            raise ProfileError(
                "syntax",
                f"the number on line {node.start_mark.line + 1} has more digits than a "
                "number can have: quote it if it is text",
                node.start_mark,
                node.end_mark,
            ) from exc
        return WrittenInt(value, node.value)

    def construct_written_float(self, node: ScalarNode) -> WrittenFloat:
        """A float, remembering how it was written."""
        return WrittenFloat(float(node.value), node.value)


# The whole table, written out: `add_constructor`'s stubs accept only PyYAML's own loaders.
_ProfileConstructor.yaml_constructors = {
    "tag:yaml.org,2002:str": SafeConstructor.construct_yaml_str,
    "tag:yaml.org,2002:seq": SafeConstructor.construct_yaml_seq,
    "tag:yaml.org,2002:map": SafeConstructor.construct_yaml_map,
    NULL_TAG: SafeConstructor.construct_yaml_null,
    BOOL_TAG: SafeConstructor.construct_yaml_bool,
    INT_TAG: _ProfileConstructor.construct_written_int,
    FLOAT_TAG: _ProfileConstructor.construct_written_float,
}


class _ProfileLoader(
    _ProfileScanner, Parser, _ProfileComposer, _ProfileConstructor, ProfileResolver
):
    """PyYAML's loader, assembled from the profile's parts as `SafeLoader` is from its own."""

    def __init__(self, stream: str) -> None:
        """Set up every stage on one stream, as PyYAML's own loaders do."""
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        SafeConstructor.__init__(self)
        BaseResolver.__init__(self)


def load(text: str) -> object:
    r"""Parse a Scenet YAML document.

    Args:
        text: The YAML source.

    Returns:
        The parsed document, or `None` for an empty one. Typed as `object`, which is what
        an untrusted document is: every caller checks its shape before using it.

    Raises:
        ProfileError: A tag, an anchor, an alias, a merge key, a key that is not a scalar,
            or a tab where a token would start; or, as a :class:`DuplicateKeyError`, a key
            written twice in one mapping.
        NestingError: The document is nested too deeply to parse.
        yaml.YAMLError: The text is not valid YAML for any other reason.

    Example:
        >>> from scenet.safe_yaml import DuplicateKeyError, load
        >>> load("cast: {no: {reference: alice}}\nscript: [{say: {by: no, text: No}}]")
        {'cast': {'no': {'reference': 'alice'}}, 'script': [{'say': {'by': 'no', 'text': 'No'}}]}
        >>> try:
        ...     load("cast:\n  alice: {}\n  alice: {}\n")
        ... except DuplicateKeyError as exc:
        ...     print(exc.key, exc.first_line, exc.line)
        alice 2 3
    """
    loader = _ProfileLoader(text)
    try:
        return loader.get_single_data()
    except RecursionError as exc:
        raise NestingError from exc
    finally:
        loader.dispose()


def describe(error: yaml.YAMLError) -> str:
    """The parser's message, with a hint when the fault is a `*` that opened an alias.

    PyYAML's own wording is about anchors and aliases, which nobody writing a line of
    dialogue would recognise. `text: *told* you` is the likeliest way to meet it: Markdown
    stresses a word that way, and in YAML an unquoted value starting with `*` is an alias.

    Args:
        error: What the parser raised.

    Returns:
        A message for the author.

    Example:
        >>> import yaml
        >>> from scenet.safe_yaml import describe, load
        >>> try:
        ...     load("text: *told* you")
        ... except yaml.YAMLError as exc:
        ...     "quote the whole value" in describe(exc)
        True
    """
    context = str(getattr(error, "context", "") or "")
    if "scanning an alias" in context:
        return f"{error}\n{ALIAS_HINT}"
    hint = _indentation_hint(error)
    if hint is not None:
        return f"{error}\n{hint}"
    return str(error)


def _indentation_hint(error: yaml.YAMLError) -> str | None:
    r"""Where a line belongs, when the parser stopped at it and it lines up with nothing above.

    A line indented a space too far or too short is the syntax error people make most by
    hand -- deleting the `#` of a commented line and leaving its space, say -- and PyYAML
    calls it "expected <block end>". Walking up from that line, a line further out than
    every line after it is a block still open there: those are the only places the line
    could line up. If it lines up with none, say how far in it is, and how far in the
    nearest of them is, a list item preferring a list item and a key a key.

    Example:
        >>> import yaml
        >>> from scenet.safe_yaml import _indentation_hint, load
        >>> try:
        ...     load("cast:\n  a: {x: 1}\n   b: {x: 2}\n")
        ... except yaml.YAMLError as exc:
        ...     _indentation_hint(exc).endswith("if it goes with line 2, indent it 2 spaces")
        True
    """
    mark = getattr(error, "problem_mark", None)
    buffer = getattr(mark, "buffer", None)
    problem = str(getattr(error, "problem", "") or "")
    if (
        mark is None
        or not isinstance(buffer, str)
        or not problem.startswith("expected <block end>")
    ):
        return None
    lines = buffer.rstrip("\0").split("\n")
    if mark.line >= len(lines):
        return None
    here = lines[mark.line]
    indent = len(here) - len(here.lstrip(" "))
    item = _is_item(here)
    # Each open block: how far in it is, whether it is a list item, and its line.
    levels: list[tuple[int, bool, int]] = []
    ceiling = math.inf
    for index in range(mark.line - 1, -1, -1):
        line = lines[index]
        written = line.strip()
        if not written or written.startswith("#"):
            continue
        start = len(line) - len(line.lstrip(" "))
        if start >= ceiling:
            continue
        if _is_item(line) and written[1:].strip():
            # What follows the dash is a block of its own, as far in as it starts.
            inside = start + 1 + len(written[1:]) - len(written[1:].lstrip())
            if inside < ceiling:
                levels.append((inside, False, index + 1))
        levels.append((start, _is_item(line), index + 1))
        ceiling = start
    if not levels or any(level == indent for level, _, _ in levels):
        return None
    alike = [entry for entry in levels if entry[1] == item] or levels
    # `min` keeps the first of equals, and the list runs from the nearest line up.
    level, _, number = min(alike, key=lambda entry: abs(entry[0] - indent))
    where = "do not indent it" if level == 0 else f"indent it {level} {_spaces(level)}"
    return (
        f"line {mark.line + 1} is indented {indent} {_spaces(indent)}, which lines up with no "
        "line above it. YAML reads what belongs with what from indentation alone: if it goes "
        f"with line {number}, {where}"
    )


def _is_item(line: str) -> bool:
    """Whether a line opens a list item: a dash, then a space or nothing."""
    written = line.strip()
    return written == "-" or written.startswith("- ")


def _spaces(count: int) -> str:
    return "space" if count == 1 else "spaces"
