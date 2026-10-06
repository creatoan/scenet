"""Reading YAML without losing a key written twice.

The YAML specification requires every key in a mapping to be unique, so a document that
repeats one is not valid YAML. PyYAML builds it anyway: the dictionary keeps the **last**
value, and the first disappears without a word. Upstream has long been asked to refuse
(yaml/pyyaml#41, still open).

For Scenet that is exactly the failure the rest of the validation exists to prevent. A
strict language that rejects every unknown key would otherwise lose a whole known one --
a panel, a character, a pose -- and compile whatever was left. So every panel, scene,
script front matter and puppet is read through :func:`load`, a `SafeLoader` that refuses
a repeated key. `ruamel.yaml` refuses by default, but a second YAML implementation in the
runtime, and in the licence gate, would buy this one check; the same trade was declined
for source positions (`frontends/positions.py`).

Two subtleties:

- **A merge key is not a repeat.** `<<: *base` followed by the key again is how YAML
  spells an override, and PyYAML copies the merged keys into the mapping before building
  it. The check looks at the keys as written, before that copy.
- **Keys are compared as loaded.** `1`, `1.0` and `true` are three keys in the text and one
  in the result, so they count as a repeat: one of them would be lost all the same.
"""

from collections.abc import Hashable
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node

__all__ = ["DuplicateKeyError", "load"]

#: The tag PyYAML gives `<<`, the merge key.
MERGE_TAG = "tag:yaml.org,2002:merge"


class DuplicateKeyError(ConstructorError):
    """A key written twice in one mapping.

    A `yaml.YAMLError`, so anything that already handles malformed YAML handles this.

    Attributes:
        key: The repeated key, as loaded.
        line: One-based line of the second occurrence, which is where the fault is.
        column: One-based column of the second occurrence.
        first_line: One-based line of the first occurrence.
        summary: One line saying what is wrong, without PyYAML's position block, for a
            diagnostic that carries the position separately.
    """

    def __init__(self, key: object, first: Node, second: Node) -> None:
        """Build the error from the two key nodes.

        Args:
            key: The repeated key, as loaded.
            first: The node of its first occurrence.
            second: The node of the one that repeats it.
        """
        self.key = key
        self.line = second.start_mark.line + 1
        self.column = second.start_mark.column + 1
        self.first_line = first.start_mark.line + 1
        self.summary = (
            f"key {key!r} appears twice in one mapping, first on line {self.first_line} and "
            f"again on line {self.line}; YAML would keep only the last"
        )
        super().__init__(problem=self.summary, problem_mark=second.start_mark)


class _NoRepeatsLoader(yaml.SafeLoader):
    """`SafeLoader`, refusing a key written twice in one mapping."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        """Check the keys as written, then build the mapping as `SafeLoader` does."""
        if isinstance(node, MappingNode):
            seen: dict[Any, Node] = {}
            for key_node, _value in node.value:
                if key_node.tag == MERGE_TAG:
                    continue
                key = self.construct_object(key_node, deep=True)
                try:
                    first = seen.setdefault(key, key_node)
                except TypeError:
                    # An unhashable key: SafeLoader reports that itself, below.
                    continue
                if first is not key_node:
                    raise DuplicateKeyError(key, first, key_node)
        return super().construct_mapping(node, deep=deep)


def load(text: str) -> object:
    r"""Parse YAML exactly as `yaml.safe_load` does, except that a repeated key is an error.

    Args:
        text: The YAML source.

    Returns:
        The parsed document, or `None` for an empty one. Typed as `object`, which is what
        an untrusted document is: every caller checks its shape before using it.

    Raises:
        DuplicateKeyError: A mapping has the same key twice.
        yaml.YAMLError: The text is not valid YAML for any other reason.

    Example:
        >>> from scenet.safe_yaml import DuplicateKeyError, load
        >>> load("cast: {alice: {reference: alice}}")
        {'cast': {'alice': {'reference': 'alice'}}}
        >>> try:
        ...     load("cast:\n  alice: {}\n  alice: {}\n")
        ... except DuplicateKeyError as exc:
        ...     print(exc.key, exc.first_line, exc.line)
        alice 2 3
    """
    # What `yaml.load` does, written out: calling it with a custom loader would hide
    # from the security lint that the loader is a SafeLoader.
    loader = _NoRepeatsLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()
