"""What a YAML syntax error says, and where (#261).

Most syntax errors a person makes by hand are a line indented one space too far or too
short, and PyYAML says so as "expected <block end>, but found '<block sequence start>'".
So when the parser stops at a line that lines up with no line above it, the message says
how far in it is, and how far in the line it most likely goes with is.

A comic script's front matter is YAML too, and a syntax error in it used to be reported on
line 1, as `invalid-field`, with line numbers counted from the front matter's first line.
"""

import pytest
import yaml

from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.errors import ScriptSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.safe_yaml import describe, load


def said(text: str) -> str:
    with pytest.raises(yaml.YAMLError) as caught:
        load(text)
    return describe(caught.value)


class TestTheHint:
    def test_a_list_item_one_space_too_deep(self):
        text = "cast: {a: {reference: alice}}\nscript:\n  - say: {by: a, text: Hi.}\n\n   - x: 1\n"
        assert "line 5 is indented 3 spaces" in said(text)
        assert "if it goes with line 3, indent it 2 spaces" in said(text)

    def test_a_list_item_one_space_short(self):
        text = "script:\n  - say: {by: a, text: Hi.}\n - say: {by: a, text: Bye.}\n"
        assert "line 3 is indented 1 space," in said(text)
        assert "if it goes with line 2, indent it 2 spaces" in said(text)

    def test_a_key_one_space_too_deep(self):
        text = "cast:\n  a: {reference: alice}\n   b: {reference: bob}\n"
        assert "if it goes with line 2, indent it 2 spaces" in said(text)

    def test_a_key_that_belongs_at_the_top(self):
        text = "panel: {size: [9, 9]}\n camera: {shot: close_up}\n"
        assert "if it goes with line 1, do not indent it" in said(text)

    def test_a_comment_or_a_blank_line_is_no_line_to_go_with(self):
        text = "cast:\n  a: {reference: alice}\n\n     # a comment\n   b: {reference: bob}\n"
        assert "if it goes with line 2, indent it 2 spaces" in said(text)

    def test_parsers_own_words_are_kept(self):
        text = "cast:\n  a: {reference: alice}\n   b: {reference: bob}\n"
        assert "expected <block end>" in said(text)

    @pytest.mark.parametrize(
        "text",
        [
            "cast: {a: [1, 2}\n",  # a bracket never closed
            "cast:\n  a: 1\n- x\n",  # lines up with `cast:`, and is still wrong
            "a: b: c\n",
        ],
    )
    def test_nothing_is_said_of_a_line_that_lines_up(self, text: str):
        assert "indent" not in said(text)


class TestTheHintReachesTheChecker:
    def test_scenet_check_says_it_on_that_line(self):
        text = "cast: {a: {reference: alice}}\nscript:\n  - say: {by: a, text: Hi.}\n   - x: 1\n"
        (found,) = diagnose_source(text)
        assert found.rule == "syntax"
        assert found.region is not None
        assert found.region.start.line == 4
        assert "indent it 2 spaces" in found.message


class TestAFrontMatterSyntaxError:
    SCRIPT = (
        "---\ncast:\n  ALICE: {reference: alice}\n   BOB: {reference: bob}\n---\n"
        "PANEL 1\nALICE\nHi.\n"
    )

    def test_it_is_a_syntax_error_on_its_line_of_the_file(self):
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(self.SCRIPT)
        assert caught.value.rule == "syntax"
        assert caught.value.line == 4

    def test_its_message_counts_lines_as_the_file_does(self):
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(self.SCRIPT)
        message = str(caught.value)
        assert "line 4" in message
        assert "if it goes with line 3, indent it 2 spaces" in message

    def test_scenet_check_reports_it_there(self):
        (found,) = diagnose_script(self.SCRIPT)
        assert found.rule == "syntax"
        assert found.region is not None
        assert found.region.start.line == 4

    def test_a_repeated_key_is_still_reported_on_its_line(self):
        text = "---\ncast:\n  ALICE: {reference: alice}\n  ALICE: {reference: bob}\n---\nPANEL 1\n"
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(text)
        assert (caught.value.rule, caught.value.line) == ("duplicate-key", 4)
