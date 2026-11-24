"""The published schema and the validator accept the same documents (#353).

A person running `scenet check` and a model decoding against the JSON Schema must see
one language. They did not: `scenet check` read `size: ["1000", "800"]` as numbers and
`hollow: 1` as true, took `camera: null` in a single panel, and both let `text: ' '`
through. Every one of those was a document one side called valid and the other not.

So for every document :func:`tests.strategies.mutants` draws -- valid, or broken in up to
three places by mutations that know nothing about the language -- "passes the shipped
schema" must equal "passes the validator". The shipped schema is the file in
`editor/schemas/`, which is what an editor and a model are given, and the validator is
`scenet check`'s, without the full compile (`deep`), whose rules are about room, not form.

**What a schema cannot say** is listed below by rule, each with the reason. A document
with a finding under one of them is held to half the property only: whatever the schema
refuses, `scenet check` refuses too. A finding under any other rule is one the schema must
make as well.

A scene is held to the same, with three rules more beyond its schema, which checks each
panel as written, before it inherits anything.
"""

import dataclasses
import json
import re
import sys
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hypothesis import event, given, settings
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator
from pydantic import TypeAdapter, ValidationError

from scenet.compose import as_lists
from scenet.diagnostics import RULES, diagnose_source
from scenet.ir import (
    DESCRIPTION_PATTERN,
    HOLDABLE_PATTERN,
    LETTERED_PATTERN,
    WHITE_SPACE,
    Description,
    SvgText,
    Words,
)
from scenet.safe_yaml import load
from tests.strategies import LIBRARY, Drawn, DrawnScene, Mutant, mutants, panels, scenes

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "editor" / "schemas"

#: The rules a JSON Schema cannot express, by name, and why. A schema validates one
#: value at a time against a shape: it cannot compare two values written in different
#: places, do arithmetic, or know what is in a file or a library.
INEXPRESSIBLE: dict[str, str] = {
    "unknown-actor": "an id must be one of the cast's keys, which the document chooses",
    "off-panel-speaker": "a line from off panel must be by somebody not in the cast",
    "reflexive-relation": "the two ids of a relation must differ from each other",
    "ordering-cycle": "the order the relations give must have no cycle, a graph property",
    "panel-geometry": "twice the margin must be less than the panel's shorter side",
    "unknown-puppet": "a reference names a puppet in the library, or a file",
    "puppet-file": "a reference names a puppet file, which must be read",
    "unknown-pose": "a pose must be one the puppet referenced has",
    "unknown-expression": "an expression must be one the puppet referenced has",
    "unknown-figure": "a figure must be one the picture's artwork contract draws",
    "image-file": "a picture must be a file that can be read",
    "artwork-contract": "a picture's contract is a file beside it",
    "font-file": "a font is a file that must be read",
    "duplicate-key": (
        "two items of a list form must not name themselves alike, which a schema checking "
        "one item at a time cannot compare; a key written twice in a mapping never reaches it"
    ),
    "unbalanced-emphasis": (
        "regular, so a pattern could say it, but one spelling Markdown's flanking rules for "
        "an underscore would be no use to anyone it refused"
    ),
}

#: The rules beyond a scene's schema as well. Each panel of a scene is checked as it is
#: written, so a key it inherits may be left out of it -- and what it inherits, and what
#: a page places, are found by following names.
BEYOND_A_SCENE: dict[str, str] = {
    "missing-field": "a panel may leave a required key to the panels it is drawn over",
    "composition": "`over` names another panel of the scene, in a chain with no loop",
    "page-layout": (
        "a page places panels by the names `panels:` gives them, and its margins leave room "
        "for them; what a tier holds, and when it may lean, the schema says"
    ),
}


@dataclass(frozen=True, slots=True)
class _Kind:
    """One kind of document: the file it is checked as, its schema, and what is beyond it."""

    source: Path
    schema: Validator
    beyond: Collection[str]


def _kind(name: str, beyond: Collection[str]) -> _Kind:
    # Loaded once: building a validator compiles every pattern in the schema.
    shipped = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    return _Kind(Path(f"x.{name}.yaml"), Draft202012Validator(shipped), beyond)


PANEL = _kind("panel", INEXPRESSIBLE)
SCENE = _kind("scene", {*INEXPRESSIBLE, *BEYOND_A_SCENE})


def _schema_errors(text: str, kind: _Kind = PANEL) -> list[str]:
    """What the shipped schema says about a document, as `path: message` lines."""
    document: Any = load(text)
    return [
        f"{'/'.join(str(step) for step in error.absolute_path)}: {error.message}"
        for error in kind.schema.iter_errors(document)
    ]


def _check_errors(text: str, kind: _Kind = PANEL) -> list[tuple[str, str]]:
    """What `scenet check` says about a document, its errors only, as (rule, message)."""
    found = diagnose_source(text, source=kind.source, library=LIBRARY)
    return [(item.rule, item.message) for item in found if item.level == "error"]


def _ignore(_: str) -> None:
    """Somewhere to send an event outside a Hypothesis test, which has nowhere to count it."""


def _assert_agree(text: str, kind: _Kind = PANEL, note: Callable[[str], None] = event) -> None:
    by_check = _check_errors(text, kind)
    by_schema = _schema_errors(text, kind)
    said = f"the schema says {by_schema or 'valid'}, and scenet check says {by_check or 'valid'}"
    # What a schema refuses, the validator refuses: always, whatever else is wrong.
    assert by_check or not by_schema, f"{said}, of:\n{text}"
    beyond = sorted({rule for rule, _ in by_check if rule in kind.beyond})
    if beyond:
        note(f"beyond a schema: {', '.join(beyond)}")
        return
    note("both refuse" if by_check else "both accept")
    assert bool(by_schema) == bool(by_check), f"{said}, of:\n{text}"


class TestTheLists:
    @pytest.mark.parametrize("listed", [INEXPRESSIBLE, BEYOND_A_SCENE])
    def test_every_rule_listed_is_an_error(self, listed: dict[str, str]):
        """A note never makes a document invalid, so it has nothing to agree with."""
        assert {RULES[rule].level for rule in listed} == {"error"}

    def test_no_rule_is_listed_twice(self):
        assert not set(INEXPRESSIBLE) & set(BEYOND_A_SCENE)


#: Every code point a pattern's character classes name lies below U+3100. Above it, a
#: sample: a letter, the byte order mark ECMAScript's `\s` has, the noncharacters, and
#: the first and last code points beyond the Basic Multilingual Plane.
_CODE_POINTS = [*range(0x3100), 0xAC00, 0xFEFF, 0xFFFD, 0xFFFE, 0xFFFF, 0x10000, sys.maxunicode]


def _accepts(adapter: TypeAdapter[str], value: str) -> bool:
    try:
        adapter.validate_python(value)
    except ValidationError:
        return False
    return True


class TestThePatterns:
    """Each pattern the schema states accepts exactly what its validator does (#353).

    Character by character, alone and between letters: a pattern and a function agree
    on every string made of those only if they agree on these.
    """

    def test_white_space_is_what_python_strips(self):
        spaces = re.compile(f"[{WHITE_SPACE}]")
        assert [point for point in _CODE_POINTS if spaces.fullmatch(chr(point))] == [
            point for point in _CODE_POINTS if chr(point).isspace()
        ]

    @pytest.mark.parametrize(
        ("pattern", "adapter"),
        [
            (HOLDABLE_PATTERN, TypeAdapter(SvgText)),
            (LETTERED_PATTERN, TypeAdapter(Words)),
            (DESCRIPTION_PATTERN, TypeAdapter(Description)),
        ],
        ids=["holdable", "lettered", "description"],
    )
    def test_a_pattern_is_its_validator(self, pattern: str, adapter: TypeAdapter[str]):
        compiled = re.compile(pattern)
        disagree = [
            text
            for text in (
                written
                for point in _CODE_POINTS
                for written in (chr(point), f"a{chr(point)}", f"{chr(point)}a")
            )
            if bool(compiled.search(text)) != _accepts(adapter, text)
        ]
        assert disagree == []

    def test_text_with_nothing_in_it_is_still_text(self):
        """The holdable pattern alone says nothing of white space: `by: ' '` is a name."""
        assert re.search(HOLDABLE_PATTERN, "")


#: The four rows of #353's evidence and the slips around them, with the verdict both must
#: give. A null in a mapping is a key not written, in a single panel as in a scene: it is
#: what `settle` makes of it, and the schema says so.
_ROWS: dict[str, tuple[str, bool]] = {
    "quoted size": ('panel: {size: ["1000", "800"]}\n', False),
    "quoted margin": ('panel: {margin: "10"}\n', False),
    "a number for a flag": ("script: [{sfx: {text: BANG, hollow: 1}}]\n", False),
    "a quoted flag": ("script: [{sfx: {text: BANG, hollow: 'true'}}]\n", False),
    "camera: null": ("camera: null\n", True),
    "an empty camera": ("camera:\n", True),
    "a null at depth": ("camera: {shot: null}\npanel: {margin: null}\n", True),
    "a null in a list": ("script: [{sfx: {text: BANG, hollow: null}}]\n", True),
    "blank text": ("script: [{caption: {text: ' '}}]\n", False),
    "empty text": ("script: [{caption: {text: ''}}]\n", False),
    "text of white space": ('script: [{caption: {text: "\\t\\n\\u3000"}}]\n', False),
    "a blank line": ("script: [{say: {by: alice, text: ' '}}]\n", False),
    "a blank sound": ("script: [{sfx: {text: ' '}}]\n", False),
    "a blank description": ("description: ' '\n", False),
    # The document's own keys and the extensions (#357).
    "language 1": ("scenet: 1\n", True),
    "a later language": ("scenet: 2\n", False),
    "a quoted language": ("scenet: '1'\n", False),
    "language 0": ("scenet: 0\n", False),
    "a schema and meta": ("$schema: x.json\nmeta: {a: [1]}\n", True),
    "meta a list": ("meta: [1]\n", False),
    "the kind": ("kind: panel\n", True),
    "the kind of a scene": ("kind: scene\n", False),
    "a book": ("kind: book\n", False),
    "an include": ("include: [a.yaml]\n", False),
    "an include of null": ("include: null\n", True),
    "defaults": ("defaults: {}\n", False),
    "extensions at depth": (
        "x-a: 1\ncamera: {x-b: 2}\nscript: [{say: {by: alice, text: Hi., x-c: 3}, x-d: 4}]\n",
        True,
    ),
    "an extension beside the cast": ("x-e: {}\n", True),
    "a capital X": ("X-a: 1\n", False),
}


@pytest.mark.parametrize(("text", "valid"), list(_ROWS.values()), ids=list(_ROWS))
def test_the_evidence_agrees(text: str, valid: bool):
    document = "cast: {alice: {reference: alice}}\n" + text
    _assert_agree(document, note=_ignore)
    assert (not _check_errors(document)) is valid


def test_a_mark_written_twice_agrees():
    """A mark is drawn once, so a list that names one twice is refused by both."""
    document = "cast: {alice: {reference: alice, marks: [plewds, plewds]}}" + chr(10)
    _assert_agree(document, note=_ignore)
    assert _check_errors(document)


@pytest.mark.parametrize(
    ("entry", "path"),
    [
        ("- say: {by: alice, text: ' '}", ("script", 1, "say", "text")),
        ("- caption: {text: ''}", ("script", 1, "caption", "text")),
        ('- sfx: {text: "\\t"}', ("script", 1, "sfx", "text")),
    ],
    ids=["say", "caption", "sfx"],
)
def test_blank_text_is_found_where_it_is_written(entry: str, path: tuple[str | int, ...]):
    text = (
        "cast: {alice: {reference: alice}}\nscript:\n  - say: {by: alice, text: Hi.}\n"
        f"  {entry}\n"
    )
    (found,) = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
    assert (found.rule, found.path) == ("invalid-field", path)
    assert found.message == (
        "the text is empty or only white space, so there is nothing to letter; write the "
        "words, or delete the entry"
    )
    assert found.region is not None
    assert found.region.start.line == 4


def test_a_null_beside_an_unknown_key_is_still_unknown():
    """`settle` takes a null away only where the language has the key (#353)."""
    text = (
        "cast: {alice: {reference: alice}}\ncamera: {shot: long_shot, kind: null}\ncolour: null\n"
    )
    found = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
    assert [(item.rule, item.path) for item in found] == [
        ("unknown-key", ("camera", "kind")),
        ("unknown-key", ("colour",)),
    ]


#: What a scene's schema says that a panel's does not: what a tier holds, when it leans,
#: and that a page lays out panels. Each with the verdict both must give.
_SCENE_ROWS: dict[str, tuple[str, bool]] = {
    "a tier of panels": ("pages: [{tiers: [{panels: [a]}]}]\n", True),
    "a tier of columns": ("pages: [{tiers: [{columns: [{panels: [a]}]}]}]\n", True),
    "a tier of neither": ("pages: [{tiers: [{height: 1}]}]\n", False),
    "a tier of both": (
        "pages: [{tiers: [{panels: [a], columns: [{panels: [a]}]}]}]\n",
        False,
    ),
    "a slant over one panel": ("pages: [{tiers: [{panels: [a], slant: 5}]}]\n", False),
    "no slant over one panel": ("pages: [{tiers: [{panels: [a], slant: 0}]}]\n", True),
    "a slant over columns": (
        "pages: [{tiers: [{columns: [{panels: [a]}, {panels: [b]}], slant: 5}]}]\n",
        False,
    ),
    "a slant beside an inset": (
        "pages: [{tiers: [{slant: 5, panels: [b, {use: a, insets: [{use: c, scale: 0.3}]}]}]}]\n",
        False,
    ),
    # The document's own keys, a script refused as a default, and extensions (#357).
    "a scene of language 1": ("scenet: 1\nkind: scene\nmeta: {}\n", True),
    "a scene that says it is a panel": ("kind: panel\n", False),
    "a script beside panels": ("script: [{say: {by: alice, text: Hi.}}]\n", False),
    "a script of null beside panels": ("script: null\n", False),
    "extensions in a page": ("pages: [{x-a: 1, tiers: [{x-b: 2, panels: [a]}]}]\n", True),
}


@pytest.mark.parametrize(("text", "valid"), list(_SCENE_ROWS.values()), ids=list(_SCENE_ROWS))
def test_a_scene_agrees(text: str, valid: bool):
    document = (
        "cast: {alice: {reference: alice}}\npanels: {a: {}, b: {over: a}, c: {over: a}}\n" + text
    )
    _assert_agree(document, SCENE, _ignore)
    assert (not _check_errors(document, SCENE)) is valid


@pytest.mark.parametrize(
    ("default", "panel"),
    [("camera: ''", "camera: {shot: long_shot}"), ("camera: {kind: x}", "camera: null")],
    ids=["of the wrong shape", "with a key it does not have"],
)
def test_a_default_every_panel_overrides_agrees(default: str, panel: str):
    """A default no panel inherits is written all the same, and the schema reads it."""
    document = (
        f"cast: {{alice: {{reference: alice}}}}\n{default}\n"
        f"panels: {{a: {{{panel}}}, b: {{over: a}}}}\n"
    )
    _assert_agree(document, SCENE, _ignore)
    assert _check_errors(document, SCENE)


def test_a_scene_panel_names_no_puppet_it_inherits():
    """A member's `reference` may be the panel's beneath: the scene's schema asks for none."""
    text = (
        "cast: {alice: {reference: alice}}\n"
        "panels: {a: {}, b: {over: a, cast: {alice: {pose: pointing}}}}\n"
    )
    _assert_agree(text, SCENE, _ignore)
    assert _check_errors(text, SCENE) == []


def test_a_page_needs_panels():
    """Without `panels:`, a document is one panel, which has nothing for a page to lay out."""
    text = "cast: {alice: {reference: alice}}\npage: {margin: 50}\n"
    assert _check_errors(text, SCENE)
    assert _schema_errors(text, SCENE)


def _count(mutant: Mutant) -> None:
    for mutation in mutant.mutations or ("none",):
        event(f"mutation: {mutation}")


@given(mutant=mutants())
@settings(max_examples=400)
def test_a_panel_passes_its_schema_exactly_when_it_passes_check(mutant: Mutant):
    """Checking a document costs a millisecond or two, so this draws many."""
    _count(mutant)
    _assert_agree(mutant.text)


@given(mutant=mutants(scenes()))
@settings(max_examples=200)
def test_a_scene_passes_its_schema_exactly_when_it_passes_check(mutant: Mutant):
    """A scene checks every panel it holds, so this draws half as many."""
    _count(mutant)
    _assert_agree(mutant.text, SCENE)


def _listed[T: (Drawn, DrawnScene)](drawn: T) -> T:
    """The document with its panels and every cast written as lists (#356)."""
    return dataclasses.replace(drawn, document=as_lists(drawn.document))


@given(mutant=mutants(panels(images=False).map(_listed)))
@settings(max_examples=200)
def test_a_list_form_panel_passes_its_schema_exactly_when_it_passes_check(mutant: Mutant):
    """The list form is the same language, and the schema says so of it too (#356)."""
    _count(mutant)
    _assert_agree(mutant.text)


@given(mutant=mutants(scenes().map(_listed)))
@settings(max_examples=100)
def test_a_list_form_scene_passes_its_schema_exactly_when_it_passes_check(mutant: Mutant):
    _count(mutant)
    _assert_agree(mutant.text, SCENE)
