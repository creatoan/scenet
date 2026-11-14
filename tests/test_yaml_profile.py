"""Scenet YAML: a strict profile where ordinary dialogue is never mistyped (#352).

PyYAML reads YAML 1.1, where `No` is false, `1984` a number, `12:30` the sexagesimal 750
and `2024-05-01` a date -- so a line of dialogue was refused, and `01750` silently became
the octal 1000. Scenet YAML types a plain scalar as the YAML 1.2 JSON schema does and
reads every other one as text; where the language expects text, what was written is the
text. Tags, anchors, aliases and merge keys are refused, each as one finding at its span.

The page that states all this is `docs/reference/language/yaml_profile.md`; each row of
its table is a row here.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from scenet import compile_source, parse_panel
from scenet.assets.artwork import ArtworkContract
from scenet.assets.contract import PuppetSpec, load_puppet
from scenet.diagnostics import Diagnostic, diagnose_file, diagnose_source
from scenet.errors import AssetError, PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.common import _say_what_to_write, errors_of
from scenet.frontends.script_front import parse_script
from scenet.ir import PageLayout, PanelIR, SfxEvent
from scenet.safe_yaml import (
    ProfileError,
    WrittenFloat,
    WrittenInt,
    as_written,
    load,
    mistyped,
)
from scenet.schema import artwork_schema, panel_schema

ROOT = Path(__file__).resolve().parents[1]

CAST = "cast: {alice: {reference: alice}}\n"


def _span(text: str, needle: str, occurrence: int = 0) -> tuple[int, int, int]:
    """One-based line, column and end column of the `occurrence`-th `needle` in `text`."""
    index = -1
    for _ in range(occurrence + 1):
        index = text.index(needle, index + 1)
    line = text.count("\n", 0, index) + 1
    column = index - (text.rfind("\n", 0, index) + 1) + 1
    return line, column, column + len(needle)


def _where(found: Diagnostic) -> tuple[int, int, int]:
    assert found.region is not None
    assert found.region.start.line == found.region.end.line
    return found.region.start.line, found.region.start.column, found.region.end.column


# --- Implicit typing -------------------------------------------------------------------

#: (plain scalar, what it loads as). Only the YAML 1.2 JSON schema's spellings are typed;
#: every other plain scalar is text, exactly as written.
TYPING: list[tuple[str, object]] = [
    ("true", True),
    ("false", False),
    ("null", None),
    ("", None),
    ("0", 0),
    ("1984", 1984),
    ("-3", -3),
    ("1.50", 1.5),
    ("-0.25", -0.25),
    ("1e3", 1000.0),
    ("2.5E-1", 0.25),
    ("10.", 10.0),
    # YAML 1.1 booleans, and the capitalised 1.2 core ones: text.
    ("yes", "yes"),
    ("No", "No"),
    ("on", "on"),
    ("OFF", "OFF"),
    ("y", "y"),
    ("n", "n"),
    ("True", "True"),
    ("FALSE", "FALSE"),
    # Nulls other than `null` and an empty value: text.
    ("~", "~"),
    ("Null", "Null"),
    # Numbers no JSON reader would take: text.
    ("01750", "01750"),
    ("0o17", "0o17"),
    ("0x400", "0x400"),
    ("0b101", "0b101"),
    ("1_0", "1_0"),
    ("+5", "+5"),
    (".5", ".5"),
    (".inf", ".inf"),
    ("-.inf", "-.inf"),
    (".nan", ".nan"),
    # Sexagesimal and dates: text.
    ("12:30", "12:30"),
    ("190:20:30", "190:20:30"),
    ("2024-05-01", "2024-05-01"),
    ("2001-12-14t21:59:43.10-05:00", "2001-12-14t21:59:43.10-05:00"),
    # `=` is the YAML 1.1 value key; `<<` is only refused as a key.
    ("=", "="),
    ("<<", "<<"),
]


def _value(written: str) -> object:
    """What `value: <written>` loads as."""
    loaded = load(f"value: {written}\n")
    assert isinstance(loaded, dict)
    return loaded["value"]


class TestImplicitTyping:
    @pytest.mark.parametrize(
        ("written", "expected"), TYPING, ids=[row[0] or "empty" for row in TYPING]
    )
    def test_a_plain_scalar_is_typed_by_the_json_schema_only(self, written: str, expected: object):
        value = _value(written)
        assert value == expected
        assert type(value) is type(expected) or isinstance(value, type(expected))

    @pytest.mark.parametrize("written", ["1984", "-3", "0"])
    def test_an_integer_keeps_what_was_written(self, written: str):
        value = _value(written)
        assert isinstance(value, WrittenInt)
        assert value.source == written

    @pytest.mark.parametrize("written", ["1.50", "1e3", "10.", "-0.0"])
    def test_a_float_keeps_what_was_written(self, written: str):
        value = _value(written)
        assert isinstance(value, WrittenFloat)
        assert value.source == written

    @pytest.mark.parametrize("quoted", ["'1984'", '"true"', "'null'", '"No"'])
    def test_a_quoted_scalar_is_always_text(self, quoted: str):
        assert load(f"value: {quoted}\n") == {"value": quoted[1:-1]}

    def test_a_block_scalar_is_text(self):
        assert load("value: |\n  1984\n") == {"value": "1984\n"}

    def test_an_integer_too_long_to_read_is_a_yaml_error(self):
        """Python refuses to read an integer of more than 4300 digits, with a ValueError
        no caller of a YAML loader expects."""
        with pytest.raises(yaml.YAMLError):
            load(f"value: {'9' * 5000}\n")

    def test_flow_style_comments_and_block_scalars_are_kept(self):
        source = (
            "# a comment\ncast: {alice: {reference: alice}}  # and another\nnote: >\n  folded\n"
        )
        assert load(source) == {"cast": {"alice": {"reference": "alice"}}, "note": "folded\n"}


class TestKeys:
    @pytest.mark.parametrize(
        "key", ["on", "no", "yes", "off", "true", "null", "1984", "1.50", "~", "1_0"]
    )
    def test_a_key_is_text_as_written(self, key: str):
        assert load(f"{{{key}: 1}}\n") == {key: 1}

    def test_keys_that_were_one_value_are_two_keys(self):
        """In YAML 1.1 `1` and `1.0` were one key, and one of them was lost."""
        assert load("{1: a, 1.0: b}\n") == {"1": "a", "1.0": "b"}

    def test_a_key_that_is_not_a_scalar_is_refused(self):
        source = "cast:\n  ? [alice, bob]\n  : {reference: alice}\n"
        with pytest.raises(ProfileError) as caught:
            load(source)
        assert caught.value.rule == "syntax"
        assert "key" in caught.value.summary


class TestAsWritten:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "true"),
            (False, "false"),
            (WrittenInt(7, "007"), "007"),
            (WrittenFloat(1.5, "1.50"), "1.50"),
            (1984, "1984"),
            (2.5, "2.5"),
            ("No", "No"),
            (None, None),
            ([1], [1]),
        ],
    )
    def test_it_gives_the_text_of_a_scalar(self, value: object, expected: object):
        assert as_written(value) == expected


# --- Refusals --------------------------------------------------------------------------

#: (document, the rule of its one finding, the text the finding spans, message fragment).
REFUSALS: list[tuple[str, str, str, str]] = [
    (
        CAST + "script:\n  - say: {by: alice, text: !!binary aGVsbG8=}\n",
        "yaml-tag",
        "!!binary",
        "tag",
    ),
    (CAST + "script:\n  - say: {by: alice, text: !!str 1984}\n", "yaml-tag", "!!str", "quote"),
    ("camera: !shot {shot: wide}\n" + CAST, "yaml-tag", "!shot", "tag"),
    ("panel: {size: !!set {1, 2}}\n" + CAST, "yaml-tag", "!!set", "tag"),
    ("cast: {alice: &a {reference: alice}}\n", "yaml-anchor", "&a", "anchor"),
    (
        "cast: {alice: &a {reference: alice}, bob: *a}\n",
        "yaml-anchor",
        "&a",
        "over:",
    ),
    (CAST + "script:\n  - say: {by: alice, text: *told you}\n", "yaml-anchor", "*told", "_told_"),
    ("camera: {<<: {shot: wide}}\n" + CAST, "yaml-merge-key", "<<", "merge key"),
    ("camera:\n  <<: {shot: wide}\n" + CAST, "yaml-merge-key", "<<", "merge key"),
    ("cast:\n\talice: {reference: alice}\n", "syntax", "\t", "indented with a tab"),
    (CAST + "script:\n  - say:\n    \tby: alice\n", "syntax", "\t", "indented with a tab"),
    ("camera:\t{shot: wide}\n" + CAST, "syntax", "\t", "tab"),
]


class TestRefusals:
    @pytest.mark.parametrize(
        ("source", "rule", "spanned", "says"),
        REFUSALS,
        ids=[f"{row[1]}-{index}" for index, row in enumerate(REFUSALS)],
    )
    def test_check_gives_one_finding_at_the_span(
        self, source: str, rule: str, spanned: str, says: str
    ):
        found = diagnose_source(source)
        assert [finding.rule for finding in found] == [rule]
        assert _where(found[0]) == _span(source, spanned)
        assert says in found[0].message

    @pytest.mark.parametrize(
        ("source", "rule", "spanned", "says"),
        REFUSALS,
        ids=[f"{row[1]}-{index}" for index, row in enumerate(REFUSALS)],
    )
    def test_build_refuses_it_under_the_same_rule(
        self, source: str, rule: str, spanned: str, says: str
    ):
        with pytest.raises(PanelSyntaxError) as caught:
            parse_panel(source)
        assert caught.value.rule == rule
        line, _, _ = _span(source, spanned)
        assert f"line {line}" in str(caught.value)
        assert says in str(caught.value)

    def test_a_tag_is_refused_even_where_safe_load_would_build_an_object(self):
        with pytest.raises(ProfileError) as caught:
            load("!!python/object/apply:os.system ['echo hi']\n")
        assert caught.value.rule == "yaml-tag"

    def test_the_refusal_is_a_yaml_error(self):
        """Every caller already handles `yaml.YAMLError`; a refusal is one."""
        with pytest.raises(yaml.YAMLError):
            load("a: &x 1\n")

    def test_a_tab_inside_a_quoted_or_block_scalar_is_text(self):
        assert load("a: 'x\ty'\nb: |\n  x\ty\n") == {"a": "x\ty", "b": "x\ty\n"}


# --- Where the language expects text, a yes-or-no or a number -------------------------

#: (document, what `alice` says), for text the language takes as written.
LETTERED: list[tuple[str, str]] = [
    ("No", "No"),
    ("no", "no"),
    ("Yes", "Yes"),
    ("on", "on"),
    ("OFF", "OFF"),
    ("y", "y"),
    ("True", "True"),
    ("true", "true"),
    ("false", "false"),
    ("1984", "1984"),
    ("007", "007"),
    ("-3", "-3"),
    ("1.50", "1.50"),
    ("1e3", "1e3"),
    ("12:30", "12:30"),
    ("2024-05-01", "2024-05-01"),
    ("0x400", "0x400"),
    ("1_0", "1_0"),
    ("~", "~"),
    (".inf", ".inf"),
]


class TestTextAsWritten:
    @pytest.mark.parametrize(("written", "said"), LETTERED, ids=[row[0] for row in LETTERED])
    def test_dialogue_is_lettered_as_written(self, written: str, said: str):
        source = CAST + f"script:\n  - say: {{by: alice, text: {written}}}\n"
        assert diagnose_source(source) == []
        core = compile_source(source).core
        assert [balloon.lines for balloon in core.balloons] == [(said,)]

    def test_a_caption_is_lettered_as_written(self):
        source = CAST + "script:\n  - caption: {text: 12:30}\n"
        assert diagnose_source(source) == []
        assert [caption.lines for caption in compile_source(source).core.captions] == [("12:30",)]

    def test_a_sound_effect_is_lettered_as_written(self):
        source = CAST + "script:\n  - sfx: {text: 1984}\n"
        panel = parse_panel(source)
        assert panel.script[0].text == "1984"

    def test_a_cast_keyed_on_and_no_speaks(self):
        source = (
            "cast:\n  on: {reference: alice, at: left_third}\n"
            "  no: {reference: bob, at: right_third}\n"
            "script:\n  - say: {by: on, text: Yes}\n  - say: {by: no, text: No}\n"
        )
        assert diagnose_source(source) == []
        core = compile_source(source).core
        assert [(balloon.speaker, balloon.lines) for balloon in core.balloons] == [
            ("on", ("Yes",)),
            ("no", ("No",)),
        ]

    def test_a_numeric_actor_id_is_the_same_id_as_key_and_as_speaker(self):
        source = "cast: {1984: {reference: alice}}\nscript:\n  - say: {by: 1984, text: Hello.}\n"
        assert diagnose_source(source) == []
        assert set(parse_panel(source).cast) == {"1984"}

    def test_a_description_is_taken_as_written(self):
        source = CAST + "description: 12:30\n"
        assert parse_panel(source).description == "12:30"

    def test_null_is_never_text(self):
        """`null` means no value: to letter the word, quote it."""
        source = CAST + "script:\n  - say: {by: alice, text: null}\n"
        found = diagnose_source(source)
        assert [finding.rule for finding in found] == ["invalid-field"]
        assert (
            parse_panel(CAST + "script:\n  - say: {by: alice, text: 'null'}\n").script[0].text
            == "null"
        )


#: (document, the text of the value its one finding is at, what the message says to write).
MISTYPED: list[tuple[str, str, str]] = [
    (CAST + "script:\n  - sfx: {text: BANG, hollow: yes}\n", "yes", "write true"),
    (CAST + "script:\n  - sfx: {text: BANG, hollow: Off}\n", "Off", "write false"),
    (CAST + "script:\n  - sfx: {text: BANG, hollow: True}\n", "True", "write true"),
    (CAST + "script:\n  - sfx: {text: BANG, hollow: n}\n", "n", "write false"),
    (
        "cast: {alice: {reference: alice}}\nscript:\n  - say: {by: bob, text: Hi, off_panel: on}\n",
        "on",
        "write true",
    ),
    ("panel: {size: [1000, 800], margin: 1_0}\n" + CAST, "1_0", "write 10"),
    ("panel: {size: [1000, 800], margin: .5}\n" + CAST, ".5", "write 0.5"),
    ("panel: {size: [1000, 800], margin: +5}\n" + CAST, "+5", "write 5"),
    ("panel: {size: [1000, 800], margin: 0o17}\n" + CAST, "0o17", "write 15"),
    ("panel: {size: [1000, 800], margin: 0b101}\n" + CAST, "0b101", "write 5"),
    ("panel: {size: [1000, 800], margin: 007}\n" + CAST, "007", "write 7"),
    ("panel: {size: [1000, 800], margin: .inf}\n" + CAST, ".inf", "finite"),
    ("panel: {size: [1000, 800], margin: 1:30}\n" + CAST, "1:30", "number"),
]


class TestMistypedValues:
    @pytest.mark.parametrize(
        ("source", "value", "says"), MISTYPED, ids=[row[1] for row in MISTYPED]
    )
    def test_one_finding_at_the_value_says_what_to_write(self, source: str, value: str, says: str):
        found = diagnose_source(source)
        assert [finding.rule for finding in found] == ["invalid-field"]
        assert _where(found[0]) == _span(source, value, source.count(value) - 1)
        assert says in found[0].message

    @pytest.mark.parametrize(
        ("source", "value", "says"), MISTYPED, ids=[row[1] for row in MISTYPED]
    )
    def test_build_says_the_same(self, source: str, value: str, says: str):
        with pytest.raises(PanelSyntaxError, match=says) as caught:
            parse_panel(source)
        assert caught.value.rule == "invalid-field"

    def test_hexadecimal_and_octal_sizes_give_one_finding_each(self):
        """0.13 compiled this to a 1024 by 1000 panel without a word."""
        source = "panel: {size: [0x400, 01750]}\n" + CAST
        found = diagnose_source(source)
        assert [(finding.rule, _where(finding)) for finding in found] == [
            ("invalid-field", _span(source, "0x400")),
            ("invalid-field", _span(source, "01750")),
        ]
        assert "write 1024" in found[0].message
        assert "write 1750" in found[1].message
        assert "octal" in found[1].message

    def test_a_number_is_never_read_from_quoted_text(self):
        """pydantic would read the string '800' as 800; a number is written as one."""
        source = "panel: {size: ['1000', 800]}\n" + CAST
        assert [finding.rule for finding in diagnose_source(source)] == ["invalid-field"]

    def test_true_is_still_a_yes(self):
        source = CAST + "script:\n  - sfx: {text: BANG, hollow: true}\n"
        (sfx,) = parse_panel(source).script
        assert isinstance(sfx, SfxEvent)
        assert sfx.hollow is True


# --- Every reader of Scenet YAML -------------------------------------------------------


class TestEveryReader:
    def test_a_scripts_front_matter_reads_the_profile(self):
        source = (
            "---\ncast: {NO: {reference: alice}, ON: {reference: bob, at: right_third}}\n---\n\n"
            "PANEL 1\n\nNO\nYes.\n\nON\nNo.\n"
        )
        (panel,) = parse_script(source).values()
        assert set(panel.cast) == {"NO", "ON"}
        assert [event.text for event in panel.script] == ["Yes.", "No."]

    def test_a_tag_in_a_scripts_front_matter_is_one_finding(self, tmp_path: Path):
        source = "---\ncast: {ALICE: {reference: !!str alice}}\n---\n\nPANEL 1\n\nALICE\nHi.\n"
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(source)
        assert caught.value.rule == "yaml-tag"
        path = tmp_path / "tagged.script"
        path.write_text(source, encoding="utf-8")
        found = diagnose_file(path)
        assert [finding.rule for finding in found] == ["yaml-tag"]
        assert _where(found[0]) == _span(source, "!!str")

    def test_an_anchor_in_a_script_directive_is_refused(self):
        source = (
            "---\ncast: {ALICE: {reference: alice}}\n---\n\n"
            "PANEL 1\n@setting: &a {weather: rain}\n\nALICE\nHi.\n"
        )
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(source)
        assert caught.value.rule == "yaml-anchor"

    def test_a_scene_file_is_read_through_the_profile(self):
        source = (
            "panels:\n  one:\n    cast: {no: {reference: alice}}\n"
            "    script: [{say: {by: no, text: No}}]\n"
            "  two: &two\n    cast: {alice: {reference: alice}}\n"
        )
        found = diagnose_source(source)
        assert [(finding.rule, _where(finding)) for finding in found] == [
            ("yaml-anchor", _span(source, "&two"))
        ]

    def test_a_puppet_file_refuses_an_anchor(self, tmp_path: Path):
        text = (ROOT / "src/scenet/assets/library/alice.puppet.yaml").read_text(encoding="utf-8")
        anchored = text.replace("poses:\n", "poses: &poses\n", 1)
        assert anchored != text
        path = tmp_path / "alice.puppet.yaml"
        path.write_text(anchored, encoding="utf-8")
        with pytest.raises(AssetError, match="anchor"):
            load_puppet(path)

    def test_a_named_puppet_file_refuses_a_tag_where_it_is(self, tmp_path: Path):
        puppet = (ROOT / "src/scenet/assets/library/alice.puppet.yaml").read_text(encoding="utf-8")
        tagged = puppet.replace("poses:\n", "poses: !!map\n", 1)
        assert tagged != puppet
        (tmp_path / "pip.puppet.yaml").write_text(tagged, encoding="utf-8")
        panel = tmp_path / "a.panel.yaml"
        panel.write_text("cast: {pip: {reference: pip.puppet.yaml}}\n", encoding="utf-8")
        found = diagnose_file(panel)
        assert [finding.rule for finding in found] == ["puppet-file"]
        assert "tag" in found[0].message


# --- The models take text as written, and never read a number or a yes from text ------

#: Every model a document's YAML is validated against.
ROOTS: tuple[type[BaseModel], ...] = (PanelIR, PageLayout, PuppetSpec, ArtworkContract)


def _scalars(schema: object, inside_text: bool, found: list[tuple[str, bool, bool]]) -> None:
    """Every str, bool, int and float in a core schema: its type, whether it is strict, and
    whether it is wrapped in `as_written`."""
    if isinstance(schema, list):
        for item in schema:
            _scalars(item, inside_text, found)
        return
    if not isinstance(schema, dict):
        return
    kind = schema.get("type")
    if kind in {"str", "bool", "int", "float"}:
        found.append((str(kind), bool(schema.get("strict")), inside_text))
    function: Any = schema.get("function")
    wraps = (
        kind == "function-before"
        and isinstance(function, dict)
        and function.get("function") is as_written
    )
    for key, value in schema.items():
        if key in {
            "function",
            "serialization",
            "metadata",
            "keys_schema",
            "json_schema_input_schema",
        }:
            continue
        _scalars(value, inside_text or wraps, found)


class TestTheModels:
    @pytest.mark.parametrize("model", ROOTS, ids=lambda model: model.__name__)
    def test_every_scalar_is_strict_or_taken_as_written(self, model: type[BaseModel]):
        """A `bool` field reads `yes` as true and a `float` field reads '01750' as 1750,
        as pydantic does unless it is told not to: every one of them is strict, and every
        `str` is wrapped in `as_written`, so `text: 1984` is the text it looks like."""
        found: list[tuple[str, bool, bool]] = []
        _scalars(model.__pydantic_core_schema__, False, found)
        assert found
        loose = sorted({kind for kind, strict, _ in found if kind != "str" and not strict})
        unwritten = [kind for kind, _, written in found if kind == "str" and not written]
        assert (loose, len(unwritten)) == ([], 0)

    def test_the_schema_says_a_text_field_takes_a_number_and_a_boolean(self):
        """So an editor validating `text: 1984` with it agrees with the compiler -- and a
        text field keeps its other constraints."""
        text = panel_schema()["$defs"]["CaptionEvent"]["properties"]["text"]
        assert text["type"] == ["string", "number", "boolean"]
        assert text["minLength"] == 1

    def test_a_key_stays_a_string_in_the_schema(self):
        figures = artwork_schema()["properties"]["figures"]
        assert figures["propertyNames"] == {"minLength": 1}


# --- What to write instead ---------------------------------------------------------------

#: (text, the field it was given to, what the message ends with, or None for no message).
WHAT_TO_WRITE: list[tuple[str, str, str | None]] = [
    ("yes", "bool", "as a yes or a no: write true"),
    ("NO", "bool", "as a yes or a no: write false"),
    ("On", "bool", "write true"),
    ("off", "bool", "write false"),
    ("Y", "bool", "write true"),
    ("n", "bool", "write false"),
    ("TRUE", "bool", "write true"),
    ("False", "bool", "write false"),
    ("true", "bool", "is quoted, so it is text: write true, without the quotes"),
    ("false", "bool", "is quoted, so it is text: write false, without the quotes"),
    ("maybe", "bool", None),
    ("0x400", "number", "in decimal: write 1024"),
    ("-0x10", "number", "in decimal: write -16"),
    ("+0X1f", "number", "in decimal: write 31"),
    ("0o17", "number", "in decimal: write 15"),
    ("0b101", "number", "in decimal: write 5"),
    ("0x1_0", "number", "in decimal: write 16"),
    ("0b102", "number", None),
    ("0xZZ", "number", None),
    ("01750", "number", "in decimal: write 1750 (YAML 1.1 read it as the octal 1000)"),
    ("-012", "number", "in decimal: write -12 (YAML 1.1 read it as the octal 10)"),
    ("007", "number", "in decimal: write 7"),
    ("00", "number", "in decimal: write 0"),
    ("09", "number", "in decimal: write 9"),
    ("01.5", "number", "in decimal: write 1.5"),
    ("1_000", "number", "in decimal: write 1000"),
    ("1_0.5", "number", "in decimal: write 10.5"),
    ("+5", "number", "in decimal: write 5"),
    (".5", "number", "in decimal: write 0.5"),
    ("-.5", "number", "in decimal: write -0.5"),
    (".5e3", "number", "in decimal: write 0.5e3"),
    ("+1.5E2", "number", "in decimal: write 1.5E2"),
    ("800", "number", "is quoted, so it is text: write 800, without the quotes"),
    ("-0.25", "number", "is quoted, so it is text: write -0.25, without the quotes"),
    (".inf", "number", "and a number here is finite: write one"),
    ("-.INF", "number", "finite: write one"),
    ("+.Inf", "number", "finite: write one"),
    (".NaN", "number", "finite: write one"),
    ("1:30", "number", None),
    ("e5", "number", None),
    ("_", "number", None),
    (".", "number", None),
    (".e5", "number", None),
    ("-", "number", None),
    ("1e", "number", None),
    ("abc", "number", None),
    ("inf", "number", None),
]


class TestWhatToWrite:
    @pytest.mark.parametrize(
        ("written", "expected", "ends"), WHAT_TO_WRITE, ids=[row[0] for row in WHAT_TO_WRITE]
    )
    def test_it_says_what_to_write(self, written: str, expected: str, ends: str | None):
        said = mistyped(written, expected)
        if ends is None:
            assert said is None
            return
        assert said is not None
        assert said.startswith(f"'{written}' is ")
        assert said.endswith(ends)
        assert ("octal" in said) == ("octal" in ends)

    def test_a_yes_in_a_number_field_says_nothing_of_a_yes(self):
        assert mistyped("yes", "number") is None

    def test_a_number_in_a_yes_or_no_field_says_nothing_of_a_number(self):
        assert mistyped("0x1", "bool") is None


def _error(kind: str, loc: tuple[str | int, ...], value: object) -> ErrorDetails:
    return {"type": kind, "loc": loc, "msg": f"pydantic's {kind}", "input": value}


class TestTheFindingSaysWhatToWrite:
    def test_each_error_is_rewritten_or_kept(self):
        errors = [
            _error("bool_type", ("a", "bool"), "yes"),
            _error("enum", ("a", "str-enum[Side]"), "yes"),
            _error("tuple_type", ("a", "tuple[str-enum[Side], ...]"), "yes"),
            _error("enum", ("b", "str-enum[Side]"), "yes"),
            _error("enum", ("a", "x", "y"), "yes"),
            _error("float_type", ("c",), "1_0"),
            _error("float_type", ("d", "float"), "0x10"),
            _error("int", ("d", "x"), "0x10"),
            _error("int_type", ("e", 0), "+3"),
            _error("bool_type", ("f",), 1),
            _error("float_type", ("g",), "abc"),
            _error("missing", ("h",), {}),
            _error("bool_type", (), "on"),
        ]
        said = _say_what_to_write(errors)
        assert [(error["loc"], error["msg"]) for error in said] == [
            (("a",), mistyped("yes", "bool")),
            (("b", "str-enum[Side]"), "pydantic's enum"),
            (("a", "x", "y"), "pydantic's enum"),
            (("c",), mistyped("1_0", "number")),
            (("d",), mistyped("0x10", "number")),
            (("e", 0), mistyped("+3", "number")),
            (("f",), "pydantic's bool_type"),
            (("g",), "pydantic's float_type"),
            (("h",), "pydantic's missing"),
            ((), mistyped("on", "bool")),
        ]
        assert errors[0]["loc"] == ("a", "bool"), "the errors given are not changed"

    def test_errors_of_says_what_to_write_for_a_real_validation(self):
        with pytest.raises(ValidationError) as caught:
            PanelIR.model_validate(
                {"cast": {"a": {"reference": "alice"}}, "panel": {"margin": "1_0"}}
            )
        (error,) = errors_of(caught.value)
        assert error["loc"] == ("panel", "margin")
        assert error["msg"] == mistyped("1_0", "number")

    def test_a_placement_that_bleeds_yes_is_one_finding_at_bleed(self):
        source = (
            "cast: {alice: {reference: alice}}\npanels:\n  a: {}\n"
            "pages:\n  - tiers:\n      - panels: [{use: a, bleed: yes}]\n"
        )
        (found,) = diagnose_source(source)
        assert (found.rule, found.path[-1]) == ("invalid-field", "bleed")
        assert _where(found) == _span(source, "yes")
        assert found.message.endswith("write true")
