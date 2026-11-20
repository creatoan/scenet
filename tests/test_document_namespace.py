"""The document-level namespace: a version key, `$schema`, `meta`, `kind` and `x-` keys (#357).

In a scene every key beside `panels:` was a default for each panel, so no key could ever say
something of the document itself, and nothing told a document of one language from one of the
next. `script:` beside `panels:` gave every panel the same lines without a word, `$schema` was
an unknown key, and so was any key a tool wrote to annotate a document.

Now the top of a document has keys of its own -- `scenet`, `$schema`, `meta`, `kind`, and
`include` and `defaults`, kept for later -- which are nobody's default; any key that starts with
`x-` is an extension, ignored at every level; and `script` is refused beside `panels:`, as
`description` is. Each row below runs through what `scenet check` says and what `scenet build`
reads, and, for a YAML document, the schema an editor is given.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator

from scenet import compile_source, parse_scene_document, render
from scenet.assets.artwork import ContractError, load_contract
from scenet.assets.contract import (
    DEFAULT_LIBRARY_PATH,
    PuppetFileError,
    load_puppet,
    load_puppet_file,
)
from scenet.diagnostics import RULES, Diagnostic, diagnose_script, diagnose_source
from scenet.errors import MalformedAssetError, PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.script_front import parse_script_document
from scenet.identifiers import GRAMMAR
from scenet.images import load_image
from scenet.ir import IDENTIFIER_PATTERN, IDENTIFIERS
from scenet.namespace import (
    DOCUMENT_KEYS,
    EXTENSION_PREFIX,
    LANGUAGE,
    NOT_YET_KEYS,
    is_extension,
    without_extensions,
)
from scenet.safe_yaml import load
from scenet.schema import artwork_schema, panel_schema, puppet_schema, scene_schema
from tests.images import png
from tests.puppets import KID_PATH, kid
from tests.strategies import LIBRARY

REPO = Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "editor" / "schemas"

CAST = "cast: {alice: {reference: alice}}\n"
SCENE = CAST + "panels: {one: {}, two: {over: one}}\n"
SCRIPT_BODY = "PANEL 1\nALICE\nHello.\n"
SCRIPT_CAST = "cast: {ALICE: {reference: alice}}\n"


def _shipped(name: str) -> Validator:
    return Draft202012Validator(
        json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    )


PANEL_SCHEMA = _shipped("panel")
SCENE_SCHEMA = _shipped("scene")
PUPPET_SCHEMA = _shipped("puppet")
ARTWORK_SCHEMA = _shipped("artwork")


def _check(text: str, kind: str = "panel") -> list[Diagnostic]:
    found = diagnose_source(text, source=Path(f"x.{kind}.yaml"), library=LIBRARY)
    return [item for item in found if item.level == "error"]


def _said(found: list[Diagnostic]) -> list[tuple[str, tuple[str | int, ...]]]:
    return [(item.rule, item.path) for item in found]


def _schema_accepts(schema: Validator, text: str) -> bool:
    document: Any = load(text)
    return not list(schema.iter_errors(document))


def _build_fault(text: str) -> PanelSyntaxError:
    with pytest.raises(PanelSyntaxError) as raised:
        parse_scene_document(text)
    return raised.value


def _script(front: str, body: str = SCRIPT_BODY) -> str:
    return f"---\n{SCRIPT_CAST}{front}---\n{body}"


def _script_check(text: str) -> list[Diagnostic]:
    return [item for item in diagnose_script(text, library=LIBRARY) if item.level == "error"]


def _line(item: Diagnostic) -> int:
    assert item.region is not None
    return item.region.start.line


# --- The version key ------------------------------------------------------------------------

#: A document of each YAML kind, with `{head}` where the version key goes.
KINDS = {
    "panel": (CAST, "panel"),
    "scene": (SCENE, "scene"),
}

#: The version key's value, and the rule `scenet check` gives it, or None.
VERSIONS: dict[str, tuple[str, str | None]] = {
    "language 1": ("1", None),
    "left out, as null": ("null", None),
    "with a point, as JSON has it": ("1.0", None),
    "a later language with a point": ("2.0", "language-version"),
    "a later language": ("2", "language-version"),
    "a much later language": ("46", "language-version"),
    "quoted": ("'1'", "invalid-field"),
    "a decimal": ("1.5", "invalid-field"),
    "zero": ("0", "invalid-field"),
    "negative": ("-1", "invalid-field"),
    "a flag": ("true", "invalid-field"),
    "a mapping": ("{major: 1}", "invalid-field"),
}


class TestTheVersionKey:
    def test_the_language_is_1(self):
        assert LANGUAGE == 1

    @pytest.mark.parametrize("kind", list(KINDS))
    @pytest.mark.parametrize(("value", "rule"), list(VERSIONS.values()), ids=list(VERSIONS))
    def test_check_build_and_the_schema_agree(self, kind: str, value: str, rule: str | None):
        body, suffix = KINDS[kind]
        text = f"scenet: {value}\n{body}"
        found = _check(text, suffix)
        schema = PANEL_SCHEMA if kind == "panel" else SCENE_SCHEMA
        assert _schema_accepts(schema, text) is (rule is None)
        if rule is None:
            assert found == []
            parse_scene_document(text)
            return
        assert _said(found) == [(rule, ("scenet",))]
        assert _line(found[0]) == 1
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == (rule, ("scenet",))

    def test_absent_means_language_1(self):
        assert _check(CAST) == []
        assert render(compile_source(CAST).core) == render(
            compile_source(f"scenet: 1\n{CAST}").core
        )

    def test_a_later_language_is_one_finding_that_says_so(self):
        """Whatever else a later language's document holds, it is not read as this one."""
        text = "scenet: 2\ncast: {alice: {reference: alice, hat: tall}}\nfuture: {key: 1}\n"
        (found,) = _check(text)
        assert found.rule == "language-version"
        assert found.message.startswith("written for Scenet language 2; this is language 1")
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == ("language-version", ("scenet",))
        assert "future" not in str(fault)
        assert "tall" not in str(fault)

    def test_a_later_language_in_a_scene_is_found_before_its_panels(self):
        text = "scenet: 3\npanels: {one: {cast: {a: {reference: nobody}}}}\n"
        assert _said(_check(text, "scene")) == [("language-version", ("scenet",))]

    def test_written_in_the_middle_it_is_found_where_it_is(self):
        text = f"{CAST}scenet: 2\n"
        (found,) = _check(text)
        assert _line(found) == 2

    def test_its_rule_is_in_the_catalogue(self):
        assert RULES["language-version"].level == "error"


class TestTheVersionKeyInAComicScript:
    @pytest.mark.parametrize(("value", "rule"), list(VERSIONS.values()), ids=list(VERSIONS))
    def test_check_and_build_agree(self, value: str, rule: str | None):
        text = _script(f"scenet: {value}\n")
        found = _script_check(text)
        if rule is None:
            assert found == []
            parse_script_document(text)
            return
        assert [item.rule for item in found] == [rule]
        # The front matter's own line: `---`, the cast, then the key.
        assert _line(found[0]) == 3
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text)
        assert (raised.value.rule, raised.value.line) == (rule, 3)

    def test_a_later_language_says_so_and_nothing_else(self):
        text = _script("scenet: 2\nfuture: 1\n", "PANEL 1\nNOBODY\nHi.\n")
        (found,) = _script_check(text)
        assert found.rule == "language-version"
        assert found.message.startswith("line 3: written for Scenet language 2; this is language 1")

    def test_in_a_flow_style_front_matter_it_is_found_on_its_line(self):
        text = "---\n{cast: {ALICE: {reference: alice}},\n scenet: 2}\n---\n" + SCRIPT_BODY
        (found,) = _script_check(text)
        assert (found.rule, _line(found)) == ("language-version", 3)


def _puppet_fault(text: str) -> PuppetFileError:
    with pytest.raises(PuppetFileError) as raised:
        load_puppet_file(KID_PATH, {KID_PATH: text.encode("utf-8")})
    return raised.value


def _contract(text: str) -> bytes:
    return text.encode("utf-8")


def _artwork(text: str):
    picture = "art/a.png"
    image = load_image(picture, {picture: png(300, 200)}, loc=("setting", "image"))
    return load_contract(image, {"art/a.art.yaml": _contract(text)}, loc=("setting", "image"))


class TestTheVersionKeyInAPuppetAndAContract:
    """A puppet file and an artwork contract are documents too, and carry the same key."""

    def test_a_puppet_of_language_1(self):
        assert (
            load_puppet_file(
                KID_PATH, {KID_PATH: kid("name: kid\n", "scenet: 1\nname: kid\n").encode()}
            ).name
            == "kid"
        )

    @pytest.mark.parametrize(
        ("value", "said"),
        [
            ("2", "written for Scenet language 2; this is language 1"),
            ("'1'", "scenet"),
        ],
        ids=["a later language", "quoted"],
    )
    def test_a_puppet_file_is_refused_at_the_key(self, value: str, said: str):
        fault = _puppet_fault(kid("name: kid\n", f"name: kid\nscenet: {value}\n"))
        assert said in str(fault)
        assert fault.inner == ("scenet",)
        assert fault.region is not None
        assert fault.region.start.line == 3

    def test_a_puppet_in_a_library_folder(self, tmp_path: Path):
        path = tmp_path / "kid.puppet.yaml"
        path.write_text(kid("name: kid\n", "scenet: 2\nname: kid\n"), encoding="utf-8")
        with pytest.raises(MalformedAssetError) as raised:
            load_puppet(path)
        assert "written for Scenet language 2; this is language 1" in str(raised.value)
        path.write_text(kid("name: kid\n", "scenet: 1\nname: kid\n"), encoding="utf-8")
        assert load_puppet(path).name == "kid"

    def test_an_artwork_contract(self):
        assert _artwork("scenet: 1\nsize: [300, 200]\n").contract.size == (300, 200)
        with pytest.raises(ContractError) as raised:
            _artwork("size: [300, 200]\nscenet: 2\n")
        assert "written for Scenet language 2; this is language 1" in str(raised.value)
        assert raised.value.inner == ("scenet",)

    def test_the_schemas_agree(self):
        puppet = kid("name: kid\n", "scenet: 1\nname: kid\n")
        assert _schema_accepts(PUPPET_SCHEMA, puppet)
        assert not _schema_accepts(PUPPET_SCHEMA, puppet.replace("scenet: 1", "scenet: 2"))
        assert _schema_accepts(ARTWORK_SCHEMA, "scenet: 1\nsize: [300, 200]\n")
        assert not _schema_accepts(ARTWORK_SCHEMA, "scenet: '1'\nsize: [300, 200]\n")


# --- The reserved keys ------------------------------------------------------------------------

#: Head keys every document takes, each with a value that is accepted.
ACCEPTED_HEADS = {
    "$schema": "'$schema': https://example.org/scenet/panel.schema.json\n",
    "meta": "meta: {title: The Wait, tags: [one, two], nested: {deep: {deeper: 1}}}\n",
    "an empty meta": "meta: {}\n",
    "meta as null": "meta: null\n",
    "every one": (
        "scenet: 1\n'$schema': ../editor/schemas/panel.schema.json\nmeta: {by: Scenet}\n"
    ),
}


class TestTheReservedKeys:
    def test_they_are_the_issues(self):
        assert set(DOCUMENT_KEYS) >= {"scenet", "$schema", "meta", "kind", "include", "defaults"}
        assert NOT_YET_KEYS == ("include", "defaults")

    @pytest.mark.parametrize("kind", list(KINDS))
    @pytest.mark.parametrize("head", list(ACCEPTED_HEADS.values()), ids=list(ACCEPTED_HEADS))
    def test_they_are_accepted(self, kind: str, head: str):
        body, suffix = KINDS[kind]
        text = head + body
        assert _check(text, suffix) == []
        parse_scene_document(text)
        assert _schema_accepts(PANEL_SCHEMA if kind == "panel" else SCENE_SCHEMA, text)

    @pytest.mark.parametrize("head", list(ACCEPTED_HEADS.values()), ids=list(ACCEPTED_HEADS))
    def test_a_comic_script_takes_them(self, head: str):
        text = _script(head)
        assert _script_check(text) == []
        parse_script_document(text)

    def test_they_change_nothing_drawn(self):
        plain = render(compile_source(CAST).core)
        assert render(compile_source(ACCEPTED_HEADS["every one"] + CAST).core) == plain

    @pytest.mark.parametrize(
        ("head", "path"),
        [
            ("meta: 3\n", ("meta",)),
            ("meta: [a, b]\n", ("meta",)),
            ("'$schema': [a]\n", ("$schema",)),
        ],
        ids=["meta a number", "meta a list", "$schema a list"],
    )
    def test_a_head_of_the_wrong_shape(self, head: str, path: tuple[str, ...]):
        text = head + CAST
        assert _said(_check(text)) == [("invalid-field", path)]
        assert _build_fault(text).loc == path
        assert not _schema_accepts(PANEL_SCHEMA, text)

    def test_beside_panels_they_are_no_default(self):
        """`meta` and the rest say something of the document, so no panel inherits them."""
        text = "scenet: 1\nmeta: {title: Two}\nkind: scene\n" + SCENE
        document = parse_scene_document(text)
        assert list(document.panels) == ["one", "two"]
        assert _check(text, "scene") == []
        assert _schema_accepts(SCENE_SCHEMA, text)

    @pytest.mark.parametrize("key", ["scenet: 1", "meta: {}", "kind: panel", "include: [a]"])
    def test_a_panel_of_a_scene_cannot_have_one(self, key: str):
        name = key.split(":", maxsplit=1)[0]
        text = CAST + f"panels: {{one: {{}}, two: {{{key}}}}}\n"
        found = _check(text, "scene")
        assert _said(found) == [("unknown-key", ("panels", "two", name))]
        assert "the whole document" in found[0].message
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == ("unknown-key", ("panels", "two", name))
        assert not _schema_accepts(SCENE_SCHEMA, text)

    @pytest.mark.parametrize("key", ["scenet", "meta", "kind", "include", "defaults"])
    def test_a_script_panel_cannot_have_one(self, key: str):
        text = _script("", f"PANEL 1\n@{key}: 1\nALICE\nHello.\n")
        (found,) = _script_check(text)
        assert (found.rule, _line(found)) == ("unknown-key", 5)
        assert "the whole document" in found.message


class TestTheKind:
    @pytest.mark.parametrize(
        ("text", "kind", "rule"),
        [
            ("kind: panel\n" + CAST, "panel", None),
            ("kind: scene\n" + SCENE, "scene", None),
            ("kind: null\n" + CAST, "panel", None),
            ("kind: scene\n" + CAST, "panel", "document-kind"),
            ("kind: panel\n" + SCENE, "scene", "document-kind"),
            ("kind: book\n" + SCENE, "scene", "not-yet"),
            ("kind: book\n" + CAST, "panel", "not-yet"),
            ("kind: comic\n" + CAST, "panel", "invalid-field"),
            ("kind: Panel\n" + CAST, "panel", "invalid-field"),
        ],
        ids=[
            "a panel",
            "a scene",
            "null",
            "a scene with no panels",
            "a panel with panels",
            "a book of panels",
            "a book of one",
            "no kind at all",
            "in capitals",
        ],
    )
    def test_check_build_and_the_schema_agree(self, text: str, kind: str, rule: str | None):
        found = _check(text, kind)
        schema = PANEL_SCHEMA if kind == "panel" else SCENE_SCHEMA
        assert _schema_accepts(schema, text) is (rule is None)
        if rule is None:
            assert found == []
            parse_scene_document(text)
            return
        assert _said(found) == [(rule, ("kind",))]
        assert _line(found[0]) == 1
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == (rule, ("kind",))

    def test_a_scene_with_no_panels_says_what_to_write(self):
        (found,) = _check("kind: scene\n" + CAST)
        assert "`panels:`" in found.message
        assert "kind: panel" in found.message

    def test_a_panel_with_panels_says_what_to_write(self):
        (found,) = _check("kind: panel\n" + SCENE, "scene")
        assert "kind: scene" in found.message

    def test_a_book_is_not_yet(self):
        (found,) = _check("kind: book\n" + SCENE, "scene")
        assert "not yet" in found.message
        assert RULES["not-yet"].level == "error"
        assert RULES["document-kind"].level == "error"

    @pytest.mark.parametrize(
        ("kind", "rule"),
        [("scene", None), ("null", None), ("panel", "document-kind"), ("book", "not-yet")],
    )
    def test_a_comic_script_is_a_scene(self, kind: str, rule: str | None):
        text = _script(f"kind: {kind}\n")
        found = _script_check(text)
        if rule is None:
            assert found == []
            return
        assert [(item.rule, _line(item)) for item in found] == [(rule, 3)]

    def test_the_kind_never_changes_how_a_document_is_read(self):
        """Shape-sniffing stays the default: `kind` only confirms what the shape says."""
        assert parse_scene_document("kind: scene\n" + SCENE).panels.keys() == {"one", "two"}
        assert list(parse_scene_document("kind: panel\n" + CAST).panels) == ["panel"]


class TestNotYet:
    @pytest.mark.parametrize("key", ["include", "defaults"])
    @pytest.mark.parametrize("kind", list(KINDS))
    def test_one_finding_where_it_is_written(self, key: str, kind: str):
        body, suffix = KINDS[kind]
        text = f"{body}{key}: [chapter-1.scene.yaml]\n"
        found = _check(text, suffix)
        assert _said(found) == [("not-yet", (key,))]
        assert _line(found[0]) == body.count("\n") + 1
        assert f"'{key}'" in found[0].message
        assert "not yet" in found[0].message
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == ("not-yet", (key,))
        schema = PANEL_SCHEMA if kind == "panel" else SCENE_SCHEMA
        assert not _schema_accepts(schema, text)

    @pytest.mark.parametrize("key", ["include", "defaults"])
    def test_as_null_it_is_not_written(self, key: str):
        text = f"{key}: null\n{CAST}"
        assert _check(text) == []
        assert _schema_accepts(PANEL_SCHEMA, text)

    @pytest.mark.parametrize("key", ["include", "defaults"])
    def test_in_a_comic_script(self, key: str):
        (found,) = _script_check(_script(f"{key}: {{}}\n"))
        assert (found.rule, _line(found)) == ("not-yet", 3)


# --- Extension keys ---------------------------------------------------------------------------

#: A document with an `x-` key at each level the issue names, and more.
EXTENSIONS = {
    "at the top": "x-generator: a tool\n" + CAST,
    "in a panel's mapping": CAST + "camera: {shot: close_up, x-note: tighter}\n",
    "in a cast entry": "cast: {alice: {reference: alice, x-id: 7}}\n",
    "beside the cast": "cast: {alice: {reference: alice}, x-cast-note: {anything: [1, 2]}}\n",
    "in a script event": CAST + "script: [{say: {by: alice, text: Hi.}, x-take: 2}]\n",
    "in what a script event says": CAST + "script: [{say: {by: alice, text: Hi., x-take: 2}}]\n",
    "in a setting": CAST + "setting: {time: night, x-mood: {a: b}}\n",
    "holding nothing": "x-empty: null\n" + CAST,
    "holding a list": "x-list: [1, {b: c}]\n" + CAST,
    "in a staging relation": (
        "cast: {alice: {reference: alice}, bob: {reference: bob}}\n"
        "staging: [{subject: alice, predicate: left_of, object: bob, x-why: blocking}]\n"
    ),
    "in a font": CAST + "lettering: {font: {regular: x.ttf, x-licence: OFL}}\n",
}


class TestExtensionKeys:
    def test_the_prefix(self):
        assert EXTENSION_PREFIX == "x-"
        assert is_extension("x-a")
        assert is_extension("x-")
        assert not is_extension("X-a")
        assert not is_extension("xa")
        assert not is_extension(7)

    def test_they_are_taken_out_at_every_level(self):
        written = {"a": [{"x-b": 1, "c": {"x-d": 2, "e": 3}}], "x-f": {"g": 4}, 5: "h"}
        assert without_extensions(written) == {"a": [{"c": {"e": 3}}], 5: "h"}
        assert without_extensions([{"x-a": 1}, "x-b"]) == [{}, "x-b"]
        assert without_extensions("x-c") == "x-c"

    @pytest.mark.parametrize("text", list(EXTENSIONS.values()), ids=list(EXTENSIONS))
    def test_check_build_and_the_schema_accept_them(self, text: str):
        if "x.ttf" in text:
            # A font file is read; only the key is in question here.
            found = [item for item in _check(text) if item.rule != "font-file"]
        else:
            found = _check(text)
            parse_scene_document(text)
        assert found == []
        assert _schema_accepts(PANEL_SCHEMA, text)

    @pytest.mark.parametrize(
        "text", [value for value in EXTENSIONS.values() if "x.ttf" not in value]
    )
    def test_they_change_nothing_drawn(self, text: str):
        """The same document with every extension taken out, written as JSON, draws the same."""
        plain = json.dumps(_loaded(text))
        assert render(compile_source(text).core) == render(compile_source(plain).core)

    def test_in_a_capital_it_is_an_unknown_key(self):
        """`x-` is the prefix, as OpenAPI spells it: `X-note` is a typo, and said to be."""
        assert _said(_check("X-note: 1\n" + CAST)) == [("unknown-key", ("X-note",))]
        assert not _schema_accepts(PANEL_SCHEMA, "X-note: 1\n" + CAST)

    def test_in_a_scene_at_every_level(self):
        text = (
            "x-tool: {name: t}\n"
            "cast: {alice: {reference: alice, x-a: 1}}\n"
            "panels:\n"
            "  x-draft: {anything: [goes, here]}\n"
            "  one: {x-b: 2}\n"
            "  two: {over: one, camera: {x-c: 3}}\n"
            "page: {x-d: 4}\n"
            "pages: [{x-e: 5, tiers: [{x-f: 6, panels: [one, {use: two, x-g: 7}]}]}]\n"
        )
        assert _check(text, "scene") == []
        assert _schema_accepts(SCENE_SCHEMA, text)
        document = parse_scene_document(text)
        # An `x-` key under `panels:` is an extension, never a panel.
        assert list(document.panels) == ["one", "two"]

    def test_an_extension_under_panels_is_no_panel_to_place(self):
        text = SCENE + "x-z: 1\npages: [{tiers: [{panels: [x-draft]}]}]\n"
        text = text.replace("panels: {one: {}", "panels: {x-draft: {}, one: {}")
        found = _check(text, "scene")
        assert [item.rule for item in found] == ["page-layout"]

    def test_an_extension_under_cast_is_nobody(self):
        text = "cast: {x-ray: {reference: alice}}\nscript: [{say: {by: alice, text: Hi.}}]\n"
        assert [item.rule for item in _check(text)] == ["unknown-actor"]

    def test_in_a_comic_script(self):
        text = (
            "---\nx-tool: t\ncast: {ALICE: {reference: alice, x-a: 1}}\n---\n"
            "PANEL 1\n@x-note: tighter here\n@camera: {shot: close_up, x-b: 2}\nALICE\nHello.\n"
        )
        assert _script_check(text) == []
        document = parse_script_document(text)
        # The directive is no prose: the panel has no description of its own.
        assert document.descriptions["1"] == ()

    def test_an_extension_in_a_panels_cast_is_nobody_who_speaks(self):
        """`x-ray: Hello.` is a line only if somebody called `x-ray` is cast, and nobody is."""
        text = "PANEL 1\n@cast: {x-ray: {reference: alice}, BOB: {reference: bob}}\n"
        document = parse_script_document(text + "x-ray: Hello.\nBOB\nHi.\n")
        assert document.descriptions["1"] == ("x-ray: Hello.",)
        assert [event.text for event in document.panels["1"].script] == ["Hi."]
        assert list(document.panels["1"].cast) == ["BOB"]

    def test_in_a_puppet_file(self):
        text = kid("name: kid\n", "x-tool: t\nname: kid\n")
        text = text.replace("  head_top: 0\n", "  head_top: 0\n  x-where: crown\n")
        assert load_puppet_file(KID_PATH, {KID_PATH: text.encode()}).name == "kid"
        assert _schema_accepts(PUPPET_SCHEMA, text)

    def test_in_a_shipped_puppet_folder(self, tmp_path: Path):
        text = (DEFAULT_LIBRARY_PATH / "alice.puppet.yaml").read_text(encoding="utf-8")
        path = tmp_path / "alice.puppet.yaml"
        path.write_text("x-tool: t\n" + text, encoding="utf-8")
        assert load_puppet(path) == load_puppet(DEFAULT_LIBRARY_PATH / "alice.puppet.yaml")

    def test_in_an_artwork_contract(self):
        text = "x-tool: t\nsize: [300, 200]\nfigures: {x-ghost: {face: {center: [1, 2]}}}\n"
        assert _artwork(text).contract.figures == {}
        assert _schema_accepts(ARTWORK_SCHEMA, text)


def _loaded(text: str) -> dict[str, Any]:
    loaded = without_extensions(load(text))
    assert isinstance(loaded, dict)
    return loaded


class TestAnIdIsNoExtension:
    """A key that starts with `x-` is an extension wherever it is, so no id can be one (#355)."""

    @pytest.mark.parametrize("name", ["x-ray", "x-", "x-1"])
    def test_the_grammar_refuses_it(self, name: str):
        problem = IDENTIFIERS.problem(name)
        assert problem is not None
        assert "extension" in problem
        assert GRAMMAR in problem
        assert re.search(IDENTIFIER_PATTERN, name) is None

    @pytest.mark.parametrize("name", ["X-ray", "xray", "ax-b", "x_ray", "x"])
    def test_the_grammar_takes_one_that_only_looks_like_it(self, name: str):
        assert IDENTIFIERS.problem(name) is None

    def test_a_line_by_it_says_why(self):
        text = CAST + "script: [{say: {by: x-ray, text: Hi., off_panel: true}}]\n"
        (found,) = _check(text)
        assert found.rule == "invalid-identifier"
        assert "extension" in found.message
        assert not _schema_accepts(PANEL_SCHEMA, text)

    def test_the_grammar_says_so(self):
        assert "'x-'" in GRAMMAR


# --- `script` is no scene default --------------------------------------------------------------


class TestScriptIsNoDefault:
    def test_beside_panels_it_is_one_finding_saying_where_to_put_it(self):
        text = CAST + "script: [{say: {by: alice, text: Hello.}}]\npanels: {one: {}, two: {}}\n"
        found = _check(text, "scene")
        assert _said(found) == [("unknown-key", ("script",))]
        assert _line(found[0]) == 2
        assert "write it on the panel" in found[0].message
        fault = _build_fault(text)
        assert (fault.rule, fault.loc) == ("unknown-key", ("script",))
        assert not _schema_accepts(SCENE_SCHEMA, text)

    def test_its_panels_are_checked_all_the_same(self):
        text = (
            CAST
            + "script: [{say: {by: alice, text: Hello.}}]\n"
            + "panels: {one: {cast: {bob: {reference: nobody}}}}\n"
        )
        assert [item.rule for item in _check(text, "scene")] == ["unknown-key", "unknown-puppet"]

    def test_as_null_it_is_refused_too(self):
        """A scene has no `script` to leave out, as it has no `description`: no key there."""
        text = CAST + "script: null\npanels: {one: {}}\n"
        assert _said(_check(text, "scene")) == [("unknown-key", ("script",))]
        assert not _schema_accepts(SCENE_SCHEMA, text)

    def test_on_a_panel_it_is_the_panels(self):
        text = CAST + "panels: {one: {script: [{say: {by: alice, text: Hi.}}]}, two: {over: one}}\n"
        document = parse_scene_document(text)
        assert [len(panel.script) for panel in document.panels.values()] == [1, 1]

    def test_in_a_single_panel_it_is_the_panels(self):
        assert _check(CAST + "script: [{say: {by: alice, text: Hi.}}]\n") == []

    def test_in_a_comic_scripts_front_matter(self):
        text = _script("script: [{say: {by: ALICE, text: Hi.}}]\n")
        (found,) = _script_check(text)
        assert (found.rule, _line(found)) == ("unknown-key", 3)
        assert "PANEL" in found.message


# --- The schemas say it -----------------------------------------------------------------------


class TestTheSchemas:
    @pytest.mark.parametrize(
        "schema",
        [panel_schema, scene_schema, puppet_schema, artwork_schema],
        ids=lambda f: f.__name__,
    )
    def test_every_document_takes_the_version_and_the_head(self, schema: Any):
        properties = schema()["properties"]
        assert {"scenet", "$schema", "meta"} <= set(properties)

    def test_the_version_is_an_integer_up_to_this_language(self):
        version = panel_schema()["properties"]["scenet"]
        (integer,) = [branch for branch in version["anyOf"] if branch.get("type") == "integer"]
        assert (integer["minimum"], integer["maximum"]) == (1, LANGUAGE)

    def test_a_panel_and_a_scene_take_a_kind_and_keep_two_keys(self):
        for schema in (panel_schema(), scene_schema()):
            assert {"kind", "include", "defaults"} <= set(schema["properties"])

    @pytest.mark.parametrize(
        "schema",
        [panel_schema, scene_schema, puppet_schema, artwork_schema],
        ids=lambda f: f.__name__,
    )
    def test_every_object_takes_an_extension(self, schema: Any):
        objects: list[dict[str, Any]] = []

        def visit(node: object) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    objects.append(node)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(schema())
        assert objects
        assert [node for node in objects if "^x-" not in node.get("patternProperties", {})] == []

    def test_a_scene_offers_no_script_and_no_head_as_a_default(self):
        scene = scene_schema()
        member = scene["properties"]["panels"]["additionalProperties"]
        assert "script" not in scene["properties"]
        assert "script" in member["properties"]
        assert not {"scenet", "$schema", "meta", "kind"} & set(member["properties"])
