"""How the comic-script front end reads a number written out, and a cue, at their edges (#345).

Panel and page labels may be written out -- `PANEL TWENTY-ONE`, `CASE DIX-SEPT` -- and a cue is
told from a line of prose by its length and its capitals. Each test kills a mutant the
mutation run left alive in `script_front.py`.
"""

from pathlib import Path

import pytest

from scenet.errors import ScriptSyntaxError
from scenet.frontends.script_front import (
    _cue_name,  # pyright: ignore[reportPrivateUsage]
    _is_a_panel_label,  # pyright: ignore[reportPrivateUsage]
    _looks_like_a_cue,  # pyright: ignore[reportPrivateUsage]
    _number_value,  # pyright: ignore[reportPrivateUsage]
    _read_page_heading,  # pyright: ignore[reportPrivateUsage]
    _unquoted,  # pyright: ignore[reportPrivateUsage]
    _unquoted_spoken,  # pyright: ignore[reportPrivateUsage]
    load_script,
)


@pytest.mark.parametrize(
    ("written", "value"),
    [
        ("12", 12),
        ("seven", 7),
        ("twenty", 20),
        ("twenty-one", 21),
        ("twenty nine", 29),
        ("dix-sept", 17),
        ("dix" + chr(0x2019) + "sept", 17),
    ],
)
def test_a_number_written_out_is_read(written: str, value: int):
    assert _number_value(written) == value


@pytest.mark.parametrize("written", ["twenty ten", "twenty zero", "twenty foo", "foo one"])
def test_tens_take_a_unit_from_one_to_nine_and_nothing_else(written: str):
    assert _number_value(written) is None


def test_a_cue_is_forty_characters_at_most():
    assert _looks_like_a_cue("A" * 40)
    assert not _looks_like_a_cue("A" * 41)


class TestAPageHeading:
    @pytest.mark.parametrize("line", ["PAGE THE END", "PLANCHE VERTE"])
    def test_words_that_are_no_number_make_no_heading(self, line: str):
        """Several words, or the French keyword, are a heading only when they are a number."""
        assert _read_page_heading(line) is None

    def test_a_note_that_is_no_count_is_not_kept_as_one(self):
        heading = _read_page_heading("PAGE ONE (flashback)")
        assert heading is not None
        assert (heading.count, heading.count_text) == (None, "")

    def test_a_count_is_kept_as_written(self):
        heading = _read_page_heading("PAGE ONE (three panels)")
        assert heading is not None
        assert (heading.count, heading.count_text) == (3, "three panels")


class TestAPanelLabel:
    def test_any_label_follows_panel(self):
        assert _is_a_panel_label("PANEL", "DEPART")
        assert _is_a_panel_label("panel", "DEPART")

    def test_only_a_number_follows_case(self):
        assert not _is_a_panel_label("CASE", "DEPART")
        assert _is_a_panel_label("CASE", "trois")


class TestACue:
    def test_its_name_is_without_its_parentheticals(self):
        assert _cue_name("ALICE (OP)") == "ALICE"

    def test_a_line_that_is_no_cue_is_its_own_name(self):
        assert _cue_name("42") == "42"


class TestQuotes:
    """Only the spaces a letterer puts inside quotes go with them; a tab is text."""

    def test_a_line_quoted_at_one_end_only_is_kept(self):
        assert _unquoted('Hi"') == 'Hi"'

    def test_quotes_take_their_spaces_and_no_tab(self):
        assert _unquoted('"\tHi"') == "\tHi"

    def test_an_opening_quote_takes_its_spaces_and_no_tab(self):
        assert _unquoted_spoken('"\tHi') == "\tHi"
        assert _unquoted_spoken('"Hi\t"') == "Hi\t"


def test_a_script_file_that_is_not_text_is_refused_as_a_script(tmp_path: Path):
    """Read as any document is, but refused as the comic script it was meant to be."""
    path = tmp_path / "comic.script"
    path.write_bytes(b"PANEL 1\n\xff\xfe\n")
    with pytest.raises(ScriptSyntaxError):
        load_script(path)
