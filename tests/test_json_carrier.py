"""JSON is a real second carrier for every document (#354).

The language is one data model with two concrete syntaxes. A document that is JSON -- its
file ends in `.json`, or its text opens an object with a quoted key -- is read by a JSON
reader into the same model Scenet YAML reads into, with every position a line and a
column, and a key written twice refused.
"""

import json
import time
from pathlib import Path

import pytest

from scenet.cli import main
from scenet.compose import as_lists
from scenet.diagnostics import diagnose_file, diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.frontends.positions import locate
from scenet.frontends.yaml_front import load_panel, parse_panel, parse_scene_document
from scenet.pipeline import compile_book, compile_source
from scenet.safe_json import (
    MAP_TAG,
    SEQ_TAG,
    STR_TAG,
    JsonSyntaxError,
    compose,
    dump,
    is_json,
    load,
)
from scenet.safe_yaml import (
    BOOL_TAG,
    FLOAT_TAG,
    INT_TAG,
    NULL_TAG,
    DuplicateKeyError,
    WrittenFloat,
    WrittenInt,
)
from scenet.safe_yaml import load as load_yaml

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
DOCUMENTS = sorted([*GALLERY.glob("*.panel.yaml"), *GALLERY.glob("*.scene.yaml")])

PANEL = {
    "cast": {"alice": {"reference": "alice"}},
    "script": [{"say": {"by": "alice", "text": "Hello! \U0001f600"}}],
}


class TestTheEvidence:
    """The five cases of #354's evidence, each a table row."""

    def test_tab_indented_json_compiles(self):
        text = json.dumps(PANEL, indent="\t")
        assert "\t" in text
        assert compile_source(text).core.balloons

    def test_surrogate_escaped_emoji_compiles(self):
        text = json.dumps(PANEL)
        assert "\\ud83d\\ude00" in text
        panel = parse_panel(text)
        assert panel.script[0].text == "Hello! \U0001f600"

    def test_a_key_longer_than_1024_characters_is_read(self):
        """YAML caps an implicit key at 1024 characters; JSON has no such cap. Read, the key
        is refused by the language for what it is, not by the parser."""
        document = {"cast": {"alice": {"reference": "alice"}}, "x-" + "a" * 2000: 1}
        assert compile_source(json.dumps(document)).core.actors

    def test_a_schema_key_is_the_documents(self):
        document = {"$schema": "https://example.org/panel.schema.json", **PANEL}
        assert compile_source(json.dumps(document)).core.actors

    def test_build_takes_a_json_file(self, tmp_path: Path):
        path = tmp_path / "hello.panel.json"
        path.write_text(json.dumps(PANEL, indent=2), encoding="utf-8")
        assert main(["build", str(path), "-o", str(tmp_path / "hello.svg")]) == 0
        assert (tmp_path / "hello.svg").exists()


class TestWhatIsJson:
    @pytest.mark.parametrize(
        ("text", "verdict"),
        [
            ('{"cast": {}}', True),
            ('\ufeff {\n\t"cast": {}}', True),
            ("{}", True),
            ("{ }", True),
            ("{cast: {}}", False),
            ("cast: {}", False),
            ("[1]", False),
            ("", False),
        ],
    )
    def test_an_object_opened_with_a_quoted_key_is_json(self, text: str, verdict: bool):
        assert is_json(text) is verdict

    def test_a_json_file_is_read_as_json_whatever_it_opens_with(self, tmp_path: Path):
        path = tmp_path / "x.panel.json"
        path.write_text("cast: {a: {reference: alice}}\n", encoding="utf-8")
        (found,) = diagnose_file(path)
        assert found.rule == "syntax"
        assert found.message.startswith("invalid JSON: expected a value")
        with pytest.raises(PanelSyntaxError, match="invalid JSON: expected a value"):
            load_panel(path)


class TestTheDataModel:
    def test_a_number_letters_as_written(self):
        text = (
            '{"cast": {"a": {"reference": "alice"}}, '
            '"script": [{"say": {"by": "a", "text": 1.50}}]}'
        )
        assert parse_panel(text).script[0].text == "1.50"

    def test_numbers_remember_their_source(self):
        loaded = load('{"a": 1.50, "b": 10, "c": 1e3, "d": -0}')
        assert isinstance(loaded, dict)
        assert [type(loaded[key]) for key in "abcd"] == [
            WrittenFloat,
            WrittenInt,
            WrittenFloat,
            WrittenInt,
        ]
        assert [loaded[key].source for key in "abcd"] == ["1.50", "10", "1e3", "-0"]

    def test_both_carriers_read_one_model(self):
        yaml_text = "cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: 'No'}}]\n"
        json_text = (
            '{"cast": {"a": {"reference": "alice"}}, '
            '"script": [{"say": {"by": "a", "text": "No"}}]}'
        )
        assert load(json_text) == load_yaml(yaml_text)


class TestMistakes:
    def test_a_key_written_twice_is_one_located_finding(self):
        text = (
            '{\n  "cast": {\n    "a": {"reference": "alice"},\n'
            '    "a": {"reference": "bob"}\n  }\n}\n'
        )
        (found,) = diagnose_source(text)
        assert found.rule == "duplicate-key"
        assert found.region is not None
        assert (found.region.start.line, found.region.start.column) == (4, 5)
        assert "line 3" in found.message
        with pytest.raises(PanelSyntaxError) as caught:
            parse_panel(text)
        assert caught.value.rule == "duplicate-key"

    @pytest.mark.parametrize(
        ("text", "line", "column"),
        [
            ('{"cast": {a: 1}}', 1, 11),
            ('{"cast": {},\n "x-a": 1,\n}', 3, 1),
            ('{"cast": {}', 1, 12),
            ('{"text": "a\tb"}', 1, 12),
            ('{"cast": {}} {}', 1, 14),
        ],
        ids=["unquoted-key", "trailing-comma", "unclosed", "raw-tab-in-string", "two-values"],
    )
    def test_a_syntax_error_is_found_where_it_is(self, text: str, line: int, column: int):
        (found,) = diagnose_source(text)
        assert found.rule == "syntax"
        assert found.region is not None
        assert (found.region.start.line, found.region.start.column) == (line, column)

    def test_a_fault_inside_is_located_in_the_json(self):
        text = (
            '{\n\t"camera": {\n\t\t"shot": "wide"\n\t},\n\t"cast": {"a": {"reference": "alice"}}\n}'
        )
        (found,) = diagnose_source(text)
        assert found.path == ("camera", "shot")
        assert found.region is not None
        assert (found.region.start.line, found.region.start.column) == (3, 11)

    def test_too_deep_is_one_finding(self):
        text = '{"meta": ' + "[" * 5000 + "]" * 5000 + "}"
        (found,) = diagnose_source(text)
        assert found.rule == "syntax"


class TestPositions:
    def test_locate_reads_json(self):
        text = '{\n  "cast": {\n    "alice": {"reference": "alice"}\n  }\n}'
        region = locate(text, ("cast", "alice", "reference"))
        assert region is not None
        assert (region.start.line, region.start.column) == (3, 28)

    def test_the_node_tree_is_marked(self):
        node = compose('{"a": [1, "x"]}')
        ((key, value),) = node.value
        assert key.start_mark.column == 1
        assert [item.start_mark.column for item in value.value] == [7, 10]


class TestTheReader:
    """The node tree, the marks and the messages, as PyYAML's own would be."""

    def test_every_node_is_tagged_and_styled_as_written(self):
        node = compose('{"a": [1, 1.5, 1E5, "x", true, null], "b": {}, "c": []}')
        assert (node.tag, node.flow_style) == (MAP_TAG, True)
        (key, listed), (_, empty_map), (_, empty_list) = node.value
        assert (key.tag, key.style) == (STR_TAG, '"')
        assert (listed.tag, listed.flow_style) == (SEQ_TAG, True)
        assert [item.tag for item in listed.value] == [
            INT_TAG,
            FLOAT_TAG,
            FLOAT_TAG,
            STR_TAG,
            BOOL_TAG,
            NULL_TAG,
        ]
        assert listed.value[3].style == '"'
        assert (empty_map.tag, empty_map.flow_style) == (MAP_TAG, True)
        assert (empty_list.tag, empty_list.flow_style) == (SEQ_TAG, True)

    def test_every_node_spans_what_it_writes_with_no_space_between(self):
        text = '{"a":[1,22],"b":{},"c":[],"d":{"e":3}}'
        node = compose(text)
        spans = [(node.start_mark.index, node.end_mark.index)]
        for key, value in node.value:
            spans.append((key.start_mark.index, key.end_mark.index))
            spans.append((value.start_mark.index, value.end_mark.index))
        listed = node.value[0][1]
        spans.extend((item.start_mark.index, item.end_mark.index) for item in listed.value)
        assert spans == [
            (0, 38),
            (1, 4),
            (5, 11),
            (12, 15),
            (16, 18),
            (19, 22),
            (23, 25),
            (26, 29),
            (30, 37),
            (6, 7),
            (8, 10),
        ]

    def test_a_mark_counts_lines_from_a_leading_break(self):
        text = 'NLNL{"a":NL 1}'.replace("NL", chr(10))
        node = compose(text)
        ((key, value),) = node.value
        assert (key.start_mark.line, key.start_mark.column) == (2, 1)
        assert (value.start_mark.line, value.start_mark.column) == (3, 1)
        mark = value.start_mark
        assert (mark.name, mark.buffer, mark.pointer) == ("<json>", text, mark.index)

    def test_reading_takes_as_long_as_the_text_not_its_square(self):
        """Each mark counted the lines from the start: 300 KB took half a minute."""
        text = "[" + ("," + chr(10)).join(["0"] * 100_000) + "]"
        start = time.perf_counter()
        node = compose(text)
        assert time.perf_counter() - start < 3
        assert node.value[-1].start_mark.line == 99_999

    def test_a_byte_order_mark_is_not_read(self):
        assert load(chr(0xFEFF) + '{"a": 1}') == {"a": 1}

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("", "expected a value, but the document ends"),
            ('{"a": 1', "expected ',' or '}', but the document ends"),
            ("{a: 1}", "expected a key, in double quotes: JSON quotes every key, found 'a'"),
            ('{"a" 1}', "expected ':' after the key, found '1'"),
            ('{"a": 1 "b"}', "expected ',' or '}', found '\"'"),
            ("[1 2]", "expected ',' or ']', found '2'"),
            (
                '{"a": x}',
                "expected a value: an object, a list, a string, a number, true, false or null,"
                " found 'x'",
            ),
            (
                '{"a":' + chr(0xA0) + "1}",
                "expected a value: an object, a list, a string, a number, true, false or null,"
                " found U+00A0",
            ),
            ('{"a": 1} x', "expected the end of the document, after its one value, found 'x'"),
            (
                '{"a": "' + chr(1) + '"}',
                "a string holds U+0001, which JSON writes as an escape: BSn for a line break,"
                " BSt for a tab",
            ),
            ('{"a": "x yBSq"}', "'BSBSq' is no escape JSON has: write BSBS for a backslash"),
            ('{"a": "x', "a string is opened and never closed"),
        ],
        ids=[
            "nothing",
            "ends",
            "unquoted-key",
            "no-colon",
            "no-comma",
            "no-comma-in-list",
            "no-value",
            "unprintable",
            "two-values",
            "control",
            "escape",
            "unclosed",
        ],
    )
    def test_each_fault_says_what_was_expected_and_what_was_found(self, text: str, problem: str):
        with pytest.raises(JsonSyntaxError) as caught:
            compose(text.replace("BS", chr(92)))
        assert caught.value.problem == problem.replace("BS", chr(92))

    def test_a_control_character_is_found_where_it_is(self):
        with pytest.raises(JsonSyntaxError) as caught:
            compose('{"a": "' + chr(1) + '"}')
        assert caught.value.problem_mark is not None
        assert caught.value.problem_mark.column == 7

    def test_a_key_written_twice_names_the_json_reader(self):
        with pytest.raises(DuplicateKeyError) as caught:
            load('{"a": 1, "a": 2}')
        assert caught.value.key == "a"
        assert "key 'a' appears twice" in str(caught.value)
        assert "a JSON reader would keep only the last" in str(caught.value)

    def test_an_exponent_in_capitals_is_a_float(self):
        (value,) = load('{"a": 1E5}').values()  # type: ignore[union-attr]  -- a mapping
        assert isinstance(value, WrittenFloat)
        assert (value, value.source) == (100000.0, "1E5")

    def test_dump_indents_each_level_by_two(self):
        document = {"a": {"b": [1, {"c": []}], "d": {}}}
        lines = [
            "{",
            '  "a": {',
            '    "b": [',
            "      1,",
            "      {",
            '        "c": []',
            "      }",
            "    ],",
            '    "d": {}',
            "  }",
            "}",
            "",
        ]
        assert dump(document) == chr(10).join(lines)

    def test_dump_escapes_a_lone_surrogate_and_nothing_else(self):
        text = dump({"x": "a" + chr(0xD83D) + chr(0xE9)})
        assert '"a' + chr(92) + "ud83d" + chr(0xE9) + '"' in text


def _cores(text: str, source: Path) -> list[tuple[str, str]]:
    book = compile_book(text, source=source)
    return [(name, result.core.model_dump_json()) for name, result in book.panels.items()] + [
        (f"page {index}", page.model_dump_json()) for index, page in enumerate(book.pages)
    ]


class TestTheGallery:
    @pytest.mark.parametrize("path", DOCUMENTS, ids=[path.name for path in DOCUMENTS])
    def test_converted_to_json_it_builds_the_same_core(self, path: Path):
        text = path.read_text(encoding="utf-8")
        converted = dump(load_yaml(text))
        assert is_json(converted)
        assert _cores(converted, path) == _cores(text, path)

    def test_a_json_file_beside_the_art_builds_too(self, tmp_path: Path):
        source = GALLERY / "34-supplied-art.scene.yaml"
        target = GALLERY / "34-supplied-art.scene.json"
        assert not target.exists()
        converted = dump(load_yaml(source.read_text(encoding="utf-8")))
        assert _cores(converted, target) == _cores(source.read_text(encoding="utf-8"), source)


class TestConvert:
    def test_to_json_and_back(self, tmp_path: Path):
        source = GALLERY / "12-sequence.scene.yaml"
        as_json = tmp_path / "sequence.scene.json"
        assert main(["convert", str(source), "--to", "json", "-o", str(as_json)]) == 0
        assert is_json(as_json.read_text(encoding="utf-8"))
        as_yaml = tmp_path / "sequence.scene.yaml"
        assert main(["convert", str(as_json), "--to", "yaml", "-o", str(as_yaml)]) == 0
        assert load_yaml(as_yaml.read_text(encoding="utf-8")) == load_yaml(
            source.read_text(encoding="utf-8")
        )
        assert _cores(as_yaml.read_text(encoding="utf-8"), source) == _cores(
            source.read_text(encoding="utf-8"), source
        )

    def test_lists(self, tmp_path: Path):
        source = GALLERY / "12-sequence.scene.yaml"
        target = tmp_path / "sequence.scene.json"
        assert main(["convert", str(source), "--to", "json", "--lists", "-o", str(target)]) == 0
        written = load(target.read_text(encoding="utf-8"))
        document = load_yaml(source.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        assert written == as_lists(document)

    def test_it_keeps_extensions(self, tmp_path: Path):
        source = tmp_path / "x.panel.yaml"
        source.write_text("x-note: kept\ncast: {a: {reference: alice}}\n", encoding="utf-8")
        target = tmp_path / "x.panel.json"
        assert main(["convert", str(source), "--to", "json", "-o", str(target)]) == 0
        assert load(target.read_text(encoding="utf-8")) == {
            "x-note": "kept",
            "cast": {"a": {"reference": "alice"}},
        }

    def test_it_writes_to_stdout(self, capsys: pytest.CaptureFixture[str]):
        assert main(["convert", str(GALLERY / "01-two-characters.panel.yaml"), "--to", "json"]) == 0
        assert is_json(capsys.readouterr().out)

    def test_a_script_has_no_json_form(self, capsys: pytest.CaptureFixture[str]):
        assert main(["convert", str(GALLERY / "13-comic-script.script"), "--to", "json"]) != 0
        assert "comic script" in capsys.readouterr().err

    def test_a_document_that_does_not_parse_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        source = tmp_path / "x.panel.yaml"
        source.write_text("cast: [\n", encoding="utf-8")
        assert main(["convert", str(source), "--to", "json"]) != 0
        assert "x.panel.yaml" in capsys.readouterr().err


class TestScenes:
    def test_a_json_scene(self):
        text = json.dumps(
            {
                "cast": [{"id": "a", "reference": "alice"}],
                "panels": [
                    {"id": "one"},
                    {"id": "two", "over": "one", "camera": {"shot": "close_up"}},
                ],
            }
        )
        assert list(parse_scene_document(text).panels) == ["one", "two"]


class TestFilesADocumentNames:
    """A puppet file and an artwork contract are documents of the language too."""

    def test_a_puppet_file_in_json(self, tmp_path: Path):
        puppet = load_yaml((GALLERY / "puppets" / "pip.puppet.yaml").read_text(encoding="utf-8"))
        (tmp_path / "puppets").mkdir()
        (tmp_path / "puppets" / "pip.puppet.json").write_text(dump(puppet), encoding="utf-8")
        text = "cast: {pip: {reference: puppets/pip.puppet.json}}\n"
        in_yaml = tmp_path / "yaml"
        (in_yaml / "puppets").mkdir(parents=True)
        (in_yaml / "puppets" / "pip.puppet.yaml").write_bytes(
            (GALLERY / "puppets" / "pip.puppet.yaml").read_bytes()
        )
        # The Core names the puppet by the path written, the one thing that differs.
        in_json = [
            (name, core.replace("pip.puppet.json", "pip.puppet.yaml"))
            for name, core in _cores(text, tmp_path / "x.panel.yaml")
        ]
        assert in_json == _cores(text.replace(".json", ".yaml"), in_yaml / "x.panel.yaml")

    def test_an_artwork_contract_in_json(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "figures.png").write_bytes(
            (GALLERY / "art" / "figures.png").read_bytes()
        )
        contract = load_yaml((GALLERY / "art" / "figures.art.yaml").read_text(encoding="utf-8"))
        (tmp_path / "art" / "figures.art.json").write_text(dump(contract), encoding="utf-8")
        source = GALLERY / "35-figures.scene.yaml"
        text = source.read_text(encoding="utf-8")
        assert _cores(text, tmp_path / source.name) == _cores(text, source)

    def test_a_contract_in_neither_is_named_as_yaml(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "figures.png").write_bytes(
            (GALLERY / "art" / "figures.png").read_bytes()
        )
        text = (GALLERY / "35-figures.scene.yaml").read_text(encoding="utf-8")
        found = diagnose_source(text, source=tmp_path / "x.scene.yaml")
        assert any("figures.art.yaml" in item.message for item in found)
