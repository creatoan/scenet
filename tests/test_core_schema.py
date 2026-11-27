"""The JSON Schema of a Panel Core and of a Page Core, published beside the language's (#365).

A Core is a format people edit, share and read with other tools, so it has a schema as the
documents people write do: generated from the models that read it back, so the two cannot
disagree, and checked here against every Core the gallery compiles to.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scenet.cli import main
from scenet.schema import core_schema, page_core_schema

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = sorted((ROOT / "tests" / "golden" / "core").glob("*.core.json"))
SHIPPED = {
    "core": ROOT / "editor" / "schemas" / "core.schema.json",
    "page-core": ROOT / "editor" / "schemas" / "page-core.schema.json",
}


def _written(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _is_page(path: Path) -> bool:
    return "frames" in json.loads(path.read_text(encoding="utf-8"))


def test_the_gallery_compiled_cores_to_check():
    assert len(GOLDEN) > 100
    assert any(_is_page(path) for path in GOLDEN)
    assert not all(_is_page(path) for path in GOLDEN)


@pytest.mark.parametrize("make", [core_schema, page_core_schema])
def test_it_is_a_valid_schema(make: Any):
    Draft202012Validator.check_schema(make())


@pytest.mark.parametrize("path", GOLDEN, ids=lambda path: path.name)
def test_every_golden_core_validates_against_its_schema(path: Path):
    schema = page_core_schema() if _is_page(path) else core_schema()
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = [
        f"{'/'.join(str(part) for part in error.absolute_path)}: {error.message[:120]}"
        for error in Draft202012Validator(schema).iter_errors(document)
    ]
    assert not errors


def _a_panel(name: str = "30-sound-effects") -> dict[str, Any]:
    return json.loads((ROOT / "tests" / "golden" / "core" / f"{name}.core.json").read_text())


@pytest.mark.parametrize(
    ("name", "path", "value"),
    [
        ("30-sound-effects", ("sfx", 0, "fill"), 'x" onload="alert(1)'),
        ("21-atmosphere.midnight", ("backdrop", "masses", 0, "tone"), "red"),
        ("30-sound-effects", ("actors", 0, "id"), "a b"),
        ("30-sound-effects", ("width",), "wide"),
    ],
)
def test_a_hostile_core_does_not_validate(name: str, path: tuple[str | int, ...], value: object):
    document = copy.deepcopy(_a_panel(name))
    node: Any = document
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    assert not Draft202012Validator(core_schema()).is_valid(document)


def test_an_unknown_key_is_refused_as_the_reader_refuses_it():
    document = _a_panel()
    document["extra_key"] = 1
    assert not Draft202012Validator(core_schema()).is_valid(document)


def test_the_schema_says_what_it_describes():
    assert core_schema()["title"] == "Scenet Panel Core"
    assert page_core_schema()["title"] == "Scenet Page Core"
    assert core_schema()["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_an_identifier_is_written_once():
    """Its pattern is some twelve thousand characters; every id refers to the one definition."""
    text = _written(core_schema())
    assert text.count('"pattern": "^(?!') == 1
    assert len(text) < 400_000


@pytest.mark.parametrize(("flag", "kind"), [("--core", "core"), ("--page-core", "page-core")])
def test_the_command_writes_it(tmp_path: Path, flag: str, kind: str):
    target = tmp_path / "out.json"
    assert main(["schema", flag, "-o", str(target)]) == 0
    expected = {"core": core_schema, "page-core": page_core_schema}[kind]()
    assert target.read_text(encoding="utf-8") == _written(expected)


def test_it_is_one_schema_at_a_time(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit):
        main(["schema", "--core", "--scene"])
    assert "not allowed with" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["core", "page-core"])
def test_the_shipped_schema_is_up_to_date(kind: str):
    make = {"core": core_schema, "page-core": page_core_schema}[kind]
    path = SHIPPED[kind]
    assert path.exists(), f"{path} is missing; run `npm run schemas` in editor/"
    assert path.read_text(encoding="utf-8") == _written(make()), (
        f"{path} is stale; run `npm run schemas` in editor/"
    )
