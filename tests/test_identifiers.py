"""One grammar for actor ids and panel names, with separators reserved (#355).

An id had no grammar. `scenet check` passed a cast keyed `""`, `a/b` and `left_of`, staged
as `left_of left_of a/b`; an actor called `old man` could not be written in a staging
sentence; a panel called `../../evil` was clean in `check` and refused only by `build`. Now
there is one definition, in :mod:`scenet.identifiers`, which the JSON Schema states as a
pattern, the validator holds every key to, and the comic-script frontend reads the same.

The table below is run through all three, and each must give the same verdict.
"""

import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator

from scenet import parse_scene_document
from scenet.diagnostics import RULES, diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.script_front import parse_script_document
from scenet.identifier_tables import CASES, UNICODE_VERSION
from scenet.identifiers import (
    GRAMMAR,
    LABEL_WORDS,
    MAX_LENGTH,
    RESERVED_CHARACTERS,
    Grammar,
)
from scenet.ir import IDENTIFIER_PATTERN, IDENTIFIERS, RESERVED_WORDS, Predicate
from scenet.safe_yaml import load
from tests.strategies import LIBRARY

REPO = Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "editor" / "schemas"
RULE = "invalid-identifier"

#: Each identifier, and a few words of what its refusal says, or None for one accepted.
TABLE: dict[str, tuple[str, str | None]] = {
    "a word": ("alice", None),
    "in capitals": ("ALICE", None),
    "accented": ("Zoé", None),
    "accented, decomposed": ("Zoe\u0301", None),
    "Han": ("健", None),
    "beyond the BMP": ("\U00020000", None),
    "Devanagari with its vowel signs": ("\u0939\u093f\u0928\u094d\u0926\u0940", None),
    "Arabic-Indic digits": ("\u0661\u0662", None),
    "a number": ("7", None),
    "a page and a panel": ("2-1", None),
    "a panel and a letter": ("4B", None),
    "with an underscore": ("old_man", None),
    "with a hyphen": ("mary-jane", None),
    "the longest": ("a" * MAX_LENGTH, None),
    "a reserved word and more": ("left_ofs", None),
    "a reserved word inside": ("caps", None),
    "empty": ("", "empty"),
    "too long": ("a" * (MAX_LENGTH + 1), "65 characters long"),
    "a slash": ("a/b", "'/' is reserved"),
    "a full stop": ("x.debug", "'.' is reserved"),
    "a colon": ("a:b", "':' is reserved"),
    "a hash": ("a#b", "'#' is reserved"),
    "an at sign": ("a@b", "'@' is reserved"),
    "climbing out": ("../../evil", "'.' is reserved"),
    "a space": ("old man", "' ' (U+0020)"),
    "a tab": ("a\tb", "U+0009"),
    "a backslash": ("a\\b", "U+005C"),
    "a trailing line break": ("a\n", "U+000A"),
    "an apostrophe": ("o'neil", "U+0027"),
    "an emoji": ("\U0001f600", "U+1F600"),
    "a joiner": ("a\u200db", "U+200D"),
    "a roman numeral": ("\u216b", "U+216B"),
    "a superscript": ("a\u00b2", "U+00B2"),
    "a leading hyphen": ("-a", "starts with '-'"),
    "a leading underscore": ("_a", "starts with '_'"),
    "a leading mark": ("\u0301a", "starts with"),
    "a relation word": ("left_of", "reserved word"),
    "a relation word in capitals": ("LOOKING_AT", "reserved word"),
    "a relation word with a Kelvin sign": ("loo\u212aing_at", "reserved word"),
    "a caption label": ("CAP", "reserved word"),
    "a caption label, mixed case": ("Caption", "reserved word"),
    "a sound effect label": ("sfx", "reserved word"),
    "a sound effect label with a long s": ("\u017ffx", "reserved word"),
    "a French label": ("RÉCITATIF", "reserved word"),
}

PANEL_SCHEMA = Draft202012Validator(
    json.loads((SCHEMAS / "panel.schema.json").read_text(encoding="utf-8"))
)
SCENE_SCHEMA = Draft202012Validator(
    json.loads((SCHEMAS / "scene.schema.json").read_text(encoding="utf-8"))
)


def _quoted(name: str) -> str:
    """A YAML scalar that is `name`, whatever it holds."""
    return json.dumps(name, ensure_ascii=False)


def _schema_accepts(schema: Validator, text: str) -> bool:
    document: Any = load(text)
    return not list(schema.iter_errors(document))


def _errors(text: str, kind: str) -> list[tuple[str, str]]:
    found = diagnose_source(text, source=Path(f"x.{kind}.yaml"), library=LIBRARY)
    return [(item.rule, item.message) for item in found if item.level == "error"]


def _script_errors(text: str) -> list[tuple[str, str]]:
    found = diagnose_script(text, library=LIBRARY)
    return [(item.rule, item.message) for item in found if item.level == "error"]


def _verdict(errors: list[tuple[str, str]], said: str | None) -> None:
    if said is None:
        assert errors == []
        return
    assert [rule for rule, _ in errors] == [RULE], errors
    (message,) = [message for _, message in errors]
    assert said in message
    assert GRAMMAR in message


_IDS = list(TABLE)
_ROWS = list(TABLE.values())


@pytest.mark.parametrize(("name", "said"), _ROWS, ids=_IDS)
class TestEveryLayerAgrees:
    """The schema, `scenet check` and the comic-script frontend, on every row."""

    def test_an_actor_id(self, name: str, said: str | None):
        text = f"cast: {{{_quoted(name)}: {{reference: alice}}}}\n"
        assert _schema_accepts(PANEL_SCHEMA, text) is (said is None)
        _verdict(_errors(text, "panel"), said)

    def test_a_panel_name(self, name: str, said: str | None):
        text = f"cast: {{alice: {{reference: alice}}}}\npanels: {{{_quoted(name)}: {{}}}}\n"
        assert _schema_accepts(SCENE_SCHEMA, text) is (said is None)
        _verdict(_errors(text, "scene"), said)

    def test_somebody_heard_from_off_panel(self, name: str, said: str | None):
        text = f"script: [{{say: {{by: {_quoted(name)}, text: Hi., off_panel: true}}}}]\n"
        assert _schema_accepts(PANEL_SCHEMA, text) is (said is None)
        _verdict(_errors(text, "panel"), said)

    def test_a_script_cast_member(self, name: str, said: str | None):
        text = f"---\ncast: {{{_quoted(name)}: {{reference: alice}}}}\n---\nPANEL 1\n"
        _verdict(_script_errors(text), said)

    @pytest.mark.parametrize(
        "written",
        [
            "cast: {{{name}: {{reference: alice}}}}\n",
            "cast: {{alice: {{reference: alice}}}}\npanels: {{{name}: {{}}}}\n",
            "script: [{{say: {{by: {name}, text: Hi., off_panel: true}}}}]\n",
        ],
        ids=["actor", "panel", "off-panel"],
    )
    def test_build_reads_it_as_check_does(self, name: str, said: str | None, written: str):
        """What `scenet build` and the Python API read a document with refuses the same."""
        text = written.format(name=_quoted(name))
        if said is None:
            parse_scene_document(text)
            return
        with pytest.raises(PanelSyntaxError) as raised:
            parse_scene_document(text)
        assert raised.value.rule == RULE
        assert said in str(raised.value)

    def test_the_pattern(self, name: str, said: str | None):
        """What an editor reads: the pattern, in the dialect both engines share."""
        assert (re.search(IDENTIFIER_PATTERN, name) is not None) is (said is None)
        assert (IDENTIFIERS.problem(name) is None) is (said is None)


class TestTheEvidence:
    """The three documents of #355's evidence each give located findings that state it."""

    def test_an_empty_id_a_slash_and_a_relation_word(self):
        text = (
            'cast: {"": {reference: alice}, "a/b": {reference: bob}, '
            '"left_of": {reference: alice}}\n'
            "staging: [left_of left_of a/b]\n"
        )
        found = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
        assert [(item.rule, item.path) for item in found] == [
            (RULE, ("cast", "", "[key]")),
            (RULE, ("cast", "a/b", "[key]")),
            (RULE, ("cast", "left_of", "[key]")),
        ]
        # Each at its own key, on the line all three are written on.
        columns = [item.region.start.column for item in found if item.region]
        assert [item.region.start.line for item in found if item.region] == [1, 1, 1]
        assert columns == sorted(columns)
        assert len(set(columns)) == 3
        assert all(GRAMMAR in item.message for item in found)

    def test_an_id_with_a_space_staged_in_a_sentence(self):
        text = (
            "cast:\n  old man: {reference: alice}\n  bob: {reference: bob}\n"
            "staging:\n  - old man left_of bob\n"
        )
        found = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
        assert [(item.rule, item.path) for item in found] == [
            (RULE, ("cast", "old man", "[key]")),
            ("invalid-field", ("staging", 0)),
        ]
        key, sentence = found
        assert key.region is not None
        assert (key.region.start.line, key.region.start.column) == (2, 3)
        assert (key.region.end.line, key.region.end.column) == (2, 10)
        assert GRAMMAR in key.message
        assert "one word" in sentence.message

    def test_panel_names_that_are_paths(self):
        text = "cast: {alice: {reference: alice}}\npanels: {'../../evil': {}, '': {}, 'a b': {}}\n"
        found = diagnose_source(text, source=Path("x.scene.yaml"), library=LIBRARY)
        assert [(item.rule, item.path) for item in found] == [
            (RULE, ("panels", "../../evil", "[key]")),
            (RULE, ("panels", "", "[key]")),
            (RULE, ("panels", "a b", "[key]")),
        ]
        assert [item.region.start.line for item in found if item.region] == [2, 2, 2]
        assert all(GRAMMAR in item.message for item in found)


class TestTheGrammar:
    def test_the_rule_is_in_the_catalogue(self):
        assert RULES[RULE].level == "error"

    def test_the_reserved_words_are_the_relations_and_a_scripts_labels(self):
        assert (*(predicate.value for predicate in Predicate), *LABEL_WORDS) == RESERVED_WORDS
        assert {"cap", "caption", "sfx"} <= set(LABEL_WORDS)

    def test_the_reserved_characters(self):
        assert RESERVED_CHARACTERS == "./:#@"

    def test_a_reserved_word_is_refused_in_every_case_it_folds_from(self):
        """`str.casefold` is the comparison, and the pattern spells it out letter by letter."""
        for word in RESERVED_WORDS:
            for index, letter in enumerate(word):
                variants = re.findall(f"[{CASES[letter]}]", "".join(map(chr, range(0x3000))))
                variants += [chr(0x212A)] if letter == "k" else []
                for variant in variants:
                    spelled = word[:index] + variant + word[index + 1 :]
                    assert spelled.casefold() == word
                    assert IDENTIFIERS.problem(spelled) is not None, spelled
            assert IDENTIFIERS.problem(f"{word}x") is None

    def test_no_character_folds_into_part_of_a_reserved_word(self):
        """Folding one character into two is the one way the pattern could miss a word."""
        for point in range(sys.maxunicode + 1):
            folded = chr(point).casefold()
            if len(folded) > 1:
                assert not any(folded in word for word in RESERVED_WORDS), hex(point)

    def test_every_letter_of_a_reserved_word_has_its_cases(self):
        assert {letter for word in RESERVED_WORDS for letter in word} <= set(CASES)

    def test_a_grammar_of_other_words(self):
        grammar = Grammar(("spam",))
        assert grammar.problem("SPAM") is not None
        assert grammar.problem("left_of") is None

    @pytest.mark.parametrize(
        ("name", "said"),
        [
            ("", "'' is not an id: it is empty"),
            (
                "a b",
                "'a b' is not an id: ' ' (U+0020) is not a letter, a digit, a mark, '_' or '-'",
            ),
            (
                f"a{chr(9)}b",
                "'a<U+0009>b' is not an id: U+0009 is not a letter, a digit, a mark, '_' or '-'",
            ),
            (
                f"a{chr(0x1F600)}",
                "'a<U+1F600>' is not an id: U+1F600 is not a letter, a digit, a mark, '_' or '-'",
            ),
            (
                "-a",
                "'-a' is not an id: it starts with '-' (U+002D), which is not a letter or a digit",
            ),
            (
                f"{chr(0x301)}a",
                f"'{chr(0x301)}a' is not an id: it starts with U+0301, which is not a letter or a "
                "digit",
            ),
            ("a" * 65, f"'{'a' * 65}' is not an id: it is 65 characters long, more than 64"),
            ("Left_Of", "'Left_Of' is not an id: it is a reserved word"),
        ],
        ids=["empty", "space", "tab", "emoji", "hyphen", "mark", "long", "word"],
    )
    def test_a_refusal_says_exactly_what_is_wrong(self, name: str, said: str):
        """A character shown as itself is printable ASCII or one an id may hold; any other
        is its code point alone, so a message never carries a control character."""
        assert IDENTIFIERS.problem(name) == f"{said}. {GRAMMAR}"

    @pytest.mark.parametrize("after", ["a", ""], ids=["between", "alone"])
    def test_the_pattern_is_the_validator_on_every_character(self, after: str):
        """Every refusal the pattern makes, the validator explains, and the other way."""
        points = [*range(0x10000), 0x1F600, 0x20000, 0x2A6DF, 0xE0001, 0xE0100, sys.maxunicode]
        compiled = re.compile(IDENTIFIER_PATTERN)
        disagree = [
            hex(point)
            for point in points
            for written in (f"a{chr(point)}{after}", f"{chr(point)}{after}")
            if (compiled.search(written) is None) != (IDENTIFIERS.problem(written) is not None)
        ]
        assert disagree == []

    @pytest.mark.skipif(
        unicodedata.unidata_version != UNICODE_VERSION,
        reason=f"the table is read from Unicode {UNICODE_VERSION}",
    )
    def test_the_table_is_current(self):
        path = REPO / "scripts" / "build_identifier_tables.py"
        spec = importlib.util.spec_from_file_location("build_identifier_tables", path)
        assert spec is not None
        assert spec.loader is not None
        build_identifier_tables = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_identifier_tables)
        committed = (REPO / "src" / "scenet" / "identifier_tables.py").read_text(encoding="utf-8")
        assert build_identifier_tables.render() == committed


class TestAnIdWrittenAsAValue:
    """`by:` names an actor where a number is a number, so an id there is quoted."""

    def test_a_number_is_quoted(self):
        text = "cast: {1984: {reference: alice}}\nscript:\n  - say: {by: 1984, text: Hello.}\n"
        assert not _schema_accepts(PANEL_SCHEMA, text)
        (found,) = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
        assert (found.rule, found.path) == (RULE, ("script", 0, "say", "by"))
        assert "'1984'" in found.message

    @pytest.mark.parametrize(
        ("written", "said"),
        [
            ("1984", "1984 unquoted is a number; write '1984'"),
            ("1.50", "1.50 unquoted is a number; write '1.50'"),
            ("true", "true unquoted is a yes-or-no; write 'true'"),
        ],
        ids=["integer", "float", "yes"],
    )
    def test_it_says_what_the_value_was_read_as(self, written: str, said: str):
        text = f"script:\n  - say: {{by: {written}, text: Hello., off_panel: true}}\n"
        (found,) = diagnose_source(text, source=Path("x.panel.yaml"), library=LIBRARY)
        assert found.message == f"an actor id is a name, and {said}, in quotes"

    def test_quoted_it_names_the_actor(self):
        text = "cast: {1984: {reference: alice}}\nscript:\n  - say: {by: '1984', text: Hello.}\n"
        assert _schema_accepts(PANEL_SCHEMA, text)
        assert _errors(text, "panel") == []


class TestBuild:
    def test_a_panel_name_is_refused_at_its_key_in_its_file(self):
        """What `scenet build` reports names the file and the key, as `check` does."""
        source = Path("x.scene.yaml")
        with pytest.raises(PanelSyntaxError) as raised:
            parse_scene_document("panels: {one: {}, 'a b': {}}\n", source=source)
        assert raised.value.rule == RULE
        assert raised.value.loc == ("panels", "a b", "[key]")
        assert raised.value.source == source


class TestAScriptsRefusal:
    """Where a comic script's refusal points, and in which file."""

    SOURCE = Path("x.script")

    def _refused(self, text: str) -> ScriptSyntaxError:
        with pytest.raises(ScriptSyntaxError) as raised:
            parse_script_document(text, source=self.SOURCE)
        assert raised.value.rule == RULE
        assert raised.value.source == self.SOURCE
        return raised.value

    def test_a_panel_name_is_refused_in_its_file(self):
        found = self._refused("PANEL 1.5\nALICE\nHi.\n")
        assert found.line == 1

    def test_a_front_matter_key_is_refused_at_its_columns(self):
        found = self._refused(
            "---\ncast: {ALICE: {reference: alice}, a/b: {reference: bob}}\n---\n"
        )
        assert (found.line, found.columns) == (2, (35, 38))
        assert str(found).startswith("x.script: line 2: 'a/b' is not an id")

    def test_a_key_written_over_two_lines_has_no_columns(self):
        found = self._refused('---\ncast:\n  ? "DR.\n    NO"\n  : {reference: alice}\n---\n')
        assert (found.line, found.columns) == (3, None)

    def test_only_a_cast_directive_names_actors(self):
        """`@setting:` keys are the language's keys, refused as unknown, not as ids."""
        text = "PANEL 1\n@setting: {place: docks, time of day: night}\n"
        (found,) = diagnose_script(text, library=LIBRARY)
        assert found.rule == "unknown-key"


class TestAScript:
    def test_a_panel_name_with_a_full_stop_is_found_at_its_heading(self):
        text = "---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1.5\nALICE\nHi.\n"
        (found,) = diagnose_script(text, library=LIBRARY)
        assert found.rule == RULE
        assert found.region is not None
        assert found.region.start.line == 4
        assert "'1.5'" in found.message
        assert GRAMMAR in found.message

    def test_a_page_with_a_full_stop_names_its_panels_with_one(self):
        text = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PAGE 3.5\nPANEL 1\nALICE\nHi.\n\nPAGE 4\nPANEL 1\nALICE\nBye.\n"
        )
        (found,) = diagnose_script(text, library=LIBRARY)
        assert found.rule == RULE
        assert found.region is not None
        assert found.region.start.line == 5
        assert "'3.5-1'" in found.message

    def test_a_cast_member_in_a_directive(self):
        text = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n"
            "PANEL 1\n@cast: {DR. NO: {reference: bob}}\nALICE\nHi.\n"
        )
        (found,) = diagnose_script(text, library=LIBRARY)
        assert found.rule == RULE
        assert found.region is not None
        assert found.region.start.line == 5

    def test_somebody_off_panel_whose_name_is_no_id(self):
        text = "---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1\nDR. NO (OP)\nHi.\n"
        (found,) = diagnose_script(text, library=LIBRARY)
        assert found.rule == RULE
        assert found.region is not None
        assert found.region.start.line == 5
        assert "'.' is reserved" in found.message


class TestTheReference:
    """The grammar, its reserved characters and its reserved words are one section."""

    PAGE = REPO / "docs" / "reference" / "language" / "identifiers.md"

    def test_it_names_every_reserved_character_and_word(self):
        text = self.PAGE.read_text(encoding="utf-8")
        for character in RESERVED_CHARACTERS:
            assert f"`{character}`" in text
        for word in RESERVED_WORDS:
            assert f"`{word}`" in text.lower()
        assert f"{MAX_LENGTH} characters" in text
        assert UNICODE_VERSION in text

    def test_it_reserves_the_qualified_reference(self):
        text = self.PAGE.read_text(encoding="utf-8")
        assert "`chapter/panel`" in text
        assert "`file#panel`" in text
