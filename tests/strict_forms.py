"""A document in the strict shape: what a model decoding against `strict_schema` writes.

Every key of every object the schema has is written, `null` where the document says
nothing; `cast` and `panels` are lists; a staging sentence, a font's one file and a panel's
name on a page are their mappings; text is a string.
"""

from typing import Any

from scenet.compose import as_lists, lowered, merge, resolve_beneath, resolve_overrides, settle
from scenet.namespace import DOCUMENT_KEYS
from scenet.safe_yaml import WrittenFloat, WrittenInt

__all__ = ["strict_document"]


def strict_document(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """The document as the strict schema has it written: a scene's panels each whole."""
    definitions: dict[str, Any] = schema.get("$defs", {})
    written = _fill(as_lists(_whole(document)), schema, definitions)
    assert isinstance(written, dict)
    return written


def _whole(document: dict[str, Any]) -> dict[str, Any]:
    """A scene with every panel's `over:` chain and defaults merged into it, as built."""
    if "panels" not in document:
        return document
    panels = lowered(document).document["panels"]
    head = {key: document[key] for key in (*DOCUMENT_KEYS, "direction") if key in document}
    layout = {key: document[key] for key in ("page", "pages") if key in document}
    defaults = {
        key: value
        for key, value in lowered(document).document.items()
        if key not in (*DOCUMENT_KEYS, "direction", "page", "pages", "panels")
    }
    composed = resolve_overrides(panels)
    standing = resolve_beneath(panels)
    whole = {
        name: settle(merge(defaults, composed[name]), beneath=merge(defaults, standing[name]))[0]
        for name in panels
    }
    return {**head, "panels": whole, **layout}


def _resolved(node: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = definitions[node["$ref"].rsplit("/", 1)[1]]
    return node


def _branches(node: dict[str, Any], definitions: dict[str, Any]) -> list[dict[str, Any]]:
    node = _resolved(node, definitions)
    if "anyOf" in node:
        return [found for branch in node["anyOf"] for found in _branches(branch, definitions)]
    return [node]


def _fits(value: object, node: dict[str, Any]) -> bool:
    kind = node.get("type")
    if "enum" in node:
        return value in node["enum"]
    if kind == "object":
        if not isinstance(value, dict):
            return False
        properties = node.get("properties", {})
        return set(value) <= set(properties) and all(
            key in value for key in node.get("required", ()) if _required(properties[key])
        )
    return {
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "null": value is None,
    }.get(str(kind), False)


def _required(node: dict[str, Any]) -> bool:
    """Whether a property takes no null: its branches never say `type: null`."""
    return {"type": "null"} not in node.get("anyOf", ())


def _as_mapping(value: str, node: dict[str, Any]) -> object:
    """A shorthand, written as the mapping it stands for."""
    properties = node.get("properties", {})
    if "subject" in properties:
        subject, predicate, target = value.split()
        return {"subject": subject, "predicate": predicate, "object": target}
    if "use" in properties:
        return {"use": value}
    if "regular" in properties:
        return {"regular": value}
    return value


def _fill(value: object, node: dict[str, Any], definitions: dict[str, Any]) -> object:
    if value is None:
        return None
    if isinstance(value, (WrittenInt, WrittenFloat)) and not _number_wanted(node, definitions):
        value = value.source
    if isinstance(value, bool) and not any(
        branch.get("type") == "boolean" or value in branch.get("enum", ())
        for branch in _branches(node, definitions)
    ):
        value = "true" if value else "false"
    branches = [branch for branch in _branches(node, definitions) if branch.get("type") != "null"]
    if isinstance(value, str) and not any(_fits(value, branch) for branch in branches):
        objects = [branch for branch in branches if branch.get("type") == "object"]
        if objects:
            value = _as_mapping(value, objects[0])
    chosen = next((branch for branch in branches if _fits(value, branch)), branches[0])
    if chosen.get("type") == "object" and isinstance(value, dict):
        return {
            key: _fill(value.get(key), inner, definitions)
            for key, inner in chosen["properties"].items()
        }
    if chosen.get("type") == "array" and isinstance(value, list):
        return [_fill(item, chosen["items"], definitions) for item in value]
    return value


def _number_wanted(node: dict[str, Any], definitions: dict[str, Any]) -> bool:
    return any(
        branch.get("type") in ("number", "integer") for branch in _branches(node, definitions)
    )
