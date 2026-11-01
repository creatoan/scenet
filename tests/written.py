"""What a document writes, read against the schema rather than as text (#239).

A word in a comment is not a construct, and `center` in `at: center` is not a span. So a
document is parsed and walked beside the schema that describes it: a key counts as the
property the schema names in that place, a value as a member of the enum the schema
expects there, and nothing else counts at all.

The schemas are the published ones, `scenet.schema`'s, so a key or a value the language
gains is something the gallery has to write the day it is added. The walk records five
things:

- **properties**, as `Owner.key`: the owner is the definition the key belongs to, named as
  the panel schema names it -- a scene's `PartialCastMember` is a `CastMember` -- or
  `document` outside every definition;
- **values**, as `Enum.value`, a staging sentence's predicate among them;
- **forms**: which of an `anyOf`'s alternatives a value took, when more than one of them is
  something to write -- `off_panel` as `true` or as a side, a font as one file or as faces;
- **signs**: whether a number is below zero or above it, for the few that may be either;
- **nulls**, where they are written: a null takes away what a panel would inherit.

A comic script is read through its front matter and its `@` directives, which are YAML and
mean what the same keys mean in a scene. Its prose, cues and dialogue are the script
frontend's own vocabulary, and another test's business (#241).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scenet.compose import DESCRIPTION_KEY, OVER_KEY
from scenet.frontends.script_front import CAMERA_DIRECTIVES, DIRECTIVE, FRONT_MATTER
from scenet.safe_yaml import load
from scenet.schema import panel_schema, scene_schema

__all__ = ["DOCUMENT", "Vocabulary", "Written", "read", "read_file", "union", "vocabulary"]

Schema = dict[str, Any]

#: The owner of every key outside a definition: a document's own, a panel's under
#: `panels:`, a script line's verb.
DOCUMENT = "document"

#: Directives whose value is kept as written, as the script frontend keeps it: YAML would
#: read the panel name `07` as a number, and a description with a colon as a mapping.
_VERBATIM = {OVER_KEY, DESCRIPTION_KEY}


@dataclass(frozen=True)
class Vocabulary:
    """Everything a schema lets a document write, by the names `Written` uses."""

    properties: frozenset[str]
    values: frozenset[str]
    forms: frozenset[str]
    #: Places whose number may be below zero or above it.
    signed: frozenset[str]

    def __or__(self, other: "Vocabulary") -> "Vocabulary":
        return Vocabulary(
            self.properties | other.properties,
            self.values | other.values,
            self.forms | other.forms,
            self.signed | other.signed,
        )


@dataclass
class Written:
    """What one or more documents write."""

    properties: set[str] = field(default_factory=set[str])
    values: set[str] = field(default_factory=set[str])
    forms: set[str] = field(default_factory=set[str])
    #: `place below zero` or `place above zero`.
    signs: set[str] = field(default_factory=set[str])
    nulls: set[str] = field(default_factory=set[str])
    #: Every mapping written, as its owner and its keys.
    mappings: set[tuple[str, frozenset[str]]] = field(
        default_factory=set[tuple[str, frozenset[str]]]
    )

    def __or__(self, other: "Written") -> "Written":
        return Written(
            self.properties | other.properties,
            self.values | other.values,
            self.forms | other.forms,
            self.signs | other.signs,
            self.nulls | other.nulls,
            self.mappings | other.mappings,
        )


def _owner(reference: str) -> str:
    """A definition's name as the panel schema has it: a scene loosens a few copies."""
    return reference.rsplit("/", 1)[1].removeprefix("Partial")


def _is_null(node: Schema) -> bool:
    return node.get("type") == "null"


def _label(node: Schema) -> str | None:
    """What an alternative is called in a form's name, or None if it is no shape at all."""
    if "$ref" in node:
        return _owner(node["$ref"])
    kind = node.get("type")
    return kind if isinstance(kind, str) else None


def _alternatives(node: Schema) -> list[Schema]:
    alternatives: list[Schema] = node.get("anyOf") or node.get("oneOf") or []
    return alternatives


def _forms(node: Schema) -> list[tuple[Schema, str]]:
    """The alternatives that are each something to write, when there are several.

    Alternatives of one shape are not forms: a script's three verbs are each a mapping, and
    which verb is written is a property, `say` or `sfx`.
    """
    shaped = [
        (alternative, label)
        for alternative in _alternatives(node)
        if not _is_null(alternative) and (label := _label(alternative)) is not None
    ]
    return shaped if len({label for _, label in shaped}) > 1 else []


def _is_signed(node: Schema, definitions: Schema) -> bool:
    """Whether a property's number may be negative and positive both."""
    for alternative in [node, *_alternatives(node)]:
        shape = (
            definitions[alternative["$ref"].rsplit("/", 1)[1]]
            if "$ref" in alternative
            else alternative
        )
        if shape.get("type") in ("number", "integer") and (
            shape.get("minimum", 0) < 0 < shape.get("maximum", 0)
        ):
            return True
    return False


def vocabulary(schema: Schema) -> Vocabulary:
    """Every property, enum value, form and signed number a document can reach."""
    definitions: Schema = schema["$defs"]
    properties: set[str] = set()
    values: set[str] = set()
    forms: set[str] = set()
    signed: set[str] = set()
    seen: set[str] = set()

    def walk(node: Schema, owner: str, place: str) -> None:
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            if name not in seen:
                seen.add(name)
                walk(definitions[name], _owner(node["$ref"]), _owner(node["$ref"]))
            return
        values.update(f"{owner}.{value}" for value in node.get("enum", []))
        forms.update(f"{place} as {label}" for _, label in _forms(node))
        for alternative in [*_alternatives(node), *node.get("allOf", [])]:
            walk(alternative, owner, place)
        for key, value in node.get("properties", {}).items():
            properties.add(f"{owner}.{key}")
            if _is_signed(value, definitions):
                signed.add(f"{owner}.{key}")
            walk(value, owner, f"{owner}.{key}")
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], owner, f"{place}.*")
        if isinstance(node.get("items"), dict):
            walk(node["items"], owner, place)
        for item in node.get("prefixItems", []):
            walk(item, owner, place)

    walk(schema, DOCUMENT, DOCUMENT)
    return Vocabulary(frozenset(properties), frozenset(values), frozenset(forms), frozenset(signed))


def _accepts(node: Schema, value: object, definitions: Schema) -> bool:
    """Whether a value has the shape an alternative describes -- its type, not its rules."""
    if "$ref" in node:
        return _accepts(definitions[node["$ref"].rsplit("/", 1)[1]], value, definitions)
    if "enum" in node:
        return value in node["enum"]
    if _alternatives(node):
        return any(_accepts(alternative, value, definitions) for alternative in _alternatives(node))
    kind = node.get("type")
    if kind is None:
        return True
    expected: dict[str, tuple[type, ...]] = {
        "null": (type(None),),
        "boolean": (bool,),
        "string": (str,),
        "object": (dict,),
        "array": (list,),
    }
    if kind in ("number", "integer"):
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, expected.get(kind, (object,)))


def read(schema: Schema, document: object) -> Written:
    """What a parsed document writes, walked beside the schema that describes it."""
    definitions: Schema = schema["$defs"]
    written = Written()

    def visit(value: object, node: Schema, owner: str, place: str) -> None:
        if value is None:
            # Where it is written, before any definition the place refers to.
            written.nulls.add(place)
            return
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            visit(value, definitions[name], _owner(node["$ref"]), _owner(node["$ref"]))
            return
        written.forms.update(
            f"{place} as {label}"
            for alternative, label in _forms(node)
            if _accepts(alternative, value, definitions)
        )
        for alternative in _alternatives(node):
            if not _is_null(alternative) and _accepts(alternative, value, definitions):
                visit(value, alternative, owner, place)
        if isinstance(value, dict):
            mapping(value, node, owner, place)
        elif isinstance(value, list):
            items = node.get("items")
            for item in value:
                if isinstance(items, dict):
                    visit(item, items, owner, place)
            for item, prefix in zip(value, node.get("prefixItems", []), strict=False):
                visit(item, prefix, owner, place)
        else:
            scalar(value, node, owner, place)

    def mapping(value: dict[Any, Any], node: Schema, owner: str, place: str) -> None:
        properties: Schema = node.get("properties", {})
        extra = node.get("additionalProperties")
        if properties or isinstance(extra, dict):
            written.mappings.add((owner, frozenset(str(key) for key in value)))
        for key, item in value.items():
            if key in properties:
                written.properties.add(f"{owner}.{key}")
                visit(item, properties[key], owner, f"{owner}.{key}")
            elif isinstance(extra, dict):
                visit(item, extra, owner, f"{place}.*")

    def scalar(value: object, node: Schema, owner: str, place: str) -> None:
        if isinstance(value, str):
            if value in node.get("enum", []):
                written.values.add(f"{owner}.{value}")
            elif owner == "Relation" and node.get("type") == "string":
                # A staging sentence, `alice left_of bob`: its middle word is a predicate.
                words = value.split()
                if len(words) == 3:
                    written.values.add(f"Predicate.{words[1]}")
        elif (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and value
            and node.get("type") in ("number", "integer")
        ):
            written.signs.add(f"{place} {'above' if value > 0 else 'below'} zero")

    visit(document, schema, DOCUMENT, DOCUMENT)
    return written


def _script(text: str) -> Written:
    """What a comic script writes: its front matter, read as a scene's defaults, and each
    `@` directive, read as a key of the panel it is in."""
    scene = scene_schema()
    panel: Schema = {
        **scene["properties"]["panels"]["additionalProperties"],
        "$defs": scene["$defs"],
    }
    match = FRONT_MATTER.match(text)
    written = read(scene, load(match.group(1)) or {}) if match else Written()
    for line in (text[match.end() :] if match else text).splitlines():
        directive = DIRECTIVE.match(line.strip())
        if directive is None:
            continue
        key, value = directive.group(1), directive.group(2).strip()
        if key in CAMERA_DIRECTIVES:
            written = written | read(panel, {"camera": {key: value}})
        else:
            written = written | read(panel, {key: value if key in _VERBATIM else load(value)})
    return written


def read_file(path: Path) -> Written:
    """What a gallery document writes, by its kind: a panel, a scene or a comic script."""
    text = path.read_text(encoding="utf-8")
    if path.name.endswith(".panel.yaml"):
        return read(panel_schema(), load(text))
    if path.name.endswith(".scene.yaml"):
        return read(scene_schema(), load(text))
    return _script(text)


def union(written: Iterable[Written]) -> Written:
    """Everything several documents write between them."""
    total = Written()
    for each in written:
        total = total | each
    return total
