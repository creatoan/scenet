"""`scenet schema --strict`: a schema that constrained decoding accepts (#375).

Structured-output modes let a model emit only documents that match a JSON Schema, and each
takes a subset of JSON Schema. The strict schema is the language in the subset they share:
`cast` and `panels` as lists, every key of every object present -- `null` where nothing is
meant -- relations, fonts and placements in their mapping forms, and no condition, pattern
or bound. The frontend reads that shape as it is: the list form, and explicit nulls.
"""

import json
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scenet.cli import main
from scenet.pipeline import compile_book
from scenet.safe_json import dump
from scenet.safe_yaml import load
from scenet.schema import STRICT_KEYWORDS, strict_schema
from tests.strict_forms import strict_document

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
DOCUMENTS = sorted([*GALLERY.glob("*.panel.yaml"), *GALLERY.glob("*.scene.yaml")])
PROVIDERS: dict[str, dict[str, Any]] = tomllib.loads(
    (ROOT / "tests" / "data" / "structured_outputs.toml").read_text(encoding="utf-8")
)
SCHEMAS = {"panel": strict_schema(), "scene": strict_schema(scene=True)}


def _nodes(node: object, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Every schema node, with where it is; a property's or a definition's name is no keyword."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from _nodes(item, f"{path}/{index}")
        return
    if not isinstance(node, dict):
        return
    yield path, node
    for key, value in node.items():
        if key in ("properties", "$defs") and isinstance(value, dict):
            for name, inner in value.items():
                yield from _nodes(inner, f"{path}/{key}/{name}")
        elif key != "enum":
            yield from _nodes(value, f"{path}/{key}")


def _keywords(schema: dict[str, Any]) -> set[str]:
    return {key for _, node in _nodes(schema) for key in node}


def _depth(schema: dict[str, Any], node: dict[str, Any], seen: frozenset[str] = frozenset()) -> int:
    """How many objects deep a document of this node can go, as OpenAI counts nesting."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[1]
        assert name not in seen, f"{name} is recursive"
        return _depth(schema, schema["$defs"][name], seen | {name})
    inner = [
        *node.get("anyOf", ()),
        *node.get("properties", {}).values(),
        *([node["items"]] if isinstance(node.get("items"), dict) else []),
    ]
    here = 1 if node.get("type") == "object" else 0
    return here + max((_depth(schema, item, seen) for item in inner), default=0)


class TestTheSubset:
    @pytest.mark.parametrize("kind", SCHEMAS)
    def test_it_uses_only_the_strict_keywords(self, kind: str):
        assert _keywords(SCHEMAS[kind]) <= STRICT_KEYWORDS

    @pytest.mark.parametrize("provider", sorted(PROVIDERS))
    @pytest.mark.parametrize("kind", SCHEMAS)
    def test_each_recorded_provider_takes_it(self, provider: str, kind: str):
        rules = PROVIDERS[provider]
        schema = SCHEMAS[kind]
        assert _keywords(schema) <= set(rules["keywords"])
        objects = [(path, node) for path, node in _nodes(schema) if node.get("type") == "object"]
        if rules["closed_objects"]:
            assert [
                path for path, node in objects if node.get("additionalProperties") is not False
            ] == []
        if rules["every_key_required"]:
            assert [
                path
                for path, node in objects
                if node.get("required") != list(node.get("properties", {}))
            ] == []
        if rules["root_is_an_object"]:
            assert schema.get("type") == "object"
            assert "anyOf" not in schema
        if not rules["recursion"] or "max_depth" in rules:
            depth = _depth(schema, schema)
            assert depth <= rules.get("max_depth", depth), depth
        if "max_properties" in rules:
            count = sum(len(node.get("properties", {})) for _, node in objects)
            assert count <= rules["max_properties"], count
        if "max_enum_values" in rules:
            count = sum(len(node["enum"]) for _, node in _nodes(schema) if "enum" in node)
            assert count <= rules["max_enum_values"], count
        if rules.get("union_alone"):
            assert [
                path
                for path, node in _nodes(schema)
                if "anyOf" in node and set(node) - {"anyOf", "description"}
            ] == []

    def test_every_provider_is_recorded_with_its_page(self):
        assert sorted(PROVIDERS) == ["anthropic", "gemini", "openai"]
        text = (ROOT / "docs" / "explanation" / "prior_art.md").read_text(encoding="utf-8")
        for rules in PROVIDERS.values():
            assert rules["page"] in text


class TestTheGallery:
    @pytest.mark.parametrize("path", DOCUMENTS, ids=[path.name for path in DOCUMENTS])
    def test_in_the_strict_shape_it_validates_and_builds_the_same_core(self, path: Path):
        text = path.read_text(encoding="utf-8")
        document = load(text)
        assert isinstance(document, dict)
        schema = SCHEMAS["scene" if "panels" in document else "panel"]
        written = strict_document(document, schema)
        assert [error.message for error in Draft202012Validator(schema).iter_errors(written)] == []
        # Every key of every object is written: the shape is the strict one, not a looser one.
        assert all(value is None or value != {} for value in written.values())
        built, as_written = (
            compile_book(dump(written), source=path),
            compile_book(text, source=path),
        )
        assert [result.core for result in built.panels.values()] == [
            result.core for result in as_written.panels.values()
        ]
        assert built.pages == as_written.pages


class TestTheCommand:
    @pytest.mark.parametrize(("flags", "kind"), [([], "panel"), (["--scene"], "scene")])
    def test_it_writes_the_strict_schema(self, tmp_path: Path, flags: list[str], kind: str):
        target = tmp_path / "strict.json"
        assert main(["schema", "--strict", *flags, "-o", str(target)]) == 0
        assert json.loads(target.read_text(encoding="utf-8")) == SCHEMAS[kind]

    def test_it_takes_no_artwork_or_puppet(self, capsys: pytest.CaptureFixture[str]):
        assert main(["schema", "--strict", "--puppet"]) == 2
        assert "--strict" in capsys.readouterr().err


class TestTheShape:
    def test_a_strict_panel_is_read_as_it_is(self):
        schema = SCHEMAS["panel"]
        document = strict_document({"cast": {"a": {"reference": "alice"}}}, schema)
        assert document["cast"][0]["pose"] is None
        assert document["camera"] is None
        assert compile_book(dump(document)).panels["panel"].core.actors

    def test_a_strict_scene_writes_each_panel_whole(self):
        schema = SCHEMAS["scene"]
        assert "over" not in schema["$defs"]["PanelEntry"]["properties"]
        assert "camera" not in schema["properties"]
        assert "direction" in schema["properties"]
