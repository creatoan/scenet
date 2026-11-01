"""Every note the compiler gives has a name (#240).

A compile note is a sentence: something the compiler decided that the source did not
literally ask for -- a camera that retreated, a tail that bent, a face an inset covers. A
gallery example that shows one declares it in the manifest's `notes:`, as an example that
shows a check's note declares its rule. So each kind of sentence has a stable name too, as
each rule has, and the sentences themselves are free to be reworded.
"""

import re
from pathlib import Path
from typing import get_args

from scenet import CompileNote, compile_source
from scenet.diagnostics import RULES
from scenet.pipeline import CompileNoteRule

DEBUG = Path(__file__).resolve().parents[1] / "docs" / "howto" / "debug_a_layout.md"

#: Two characters at a close-up in a panel too small for them: the camera retreats.
CROWDED = (
    "{panel: {size: [600.0, 400.0]}, camera: {shot: close_up},"
    " cast: {a: {reference: alice}, b: {reference: bob}}, staging: [a left_of b]}"
)


class TestTheNames:
    def test_each_is_lowercase_words_joined_by_hyphens(self):
        """Spelled as a check's rules are, since a manifest lists both side by side."""
        names = get_args(CompileNoteRule)
        assert names
        assert [name for name in names if not re.fullmatch(r"[a-z]+(-[a-z]+)*", name)] == []

    def test_none_is_also_a_checks_rule(self):
        """One name in `notes:` is one thing."""
        assert sorted(set(get_args(CompileNoteRule)) & set(RULES)) == []

    def test_each_is_explained_where_the_notes_are(self):
        page = DEBUG.read_text(encoding="utf-8")
        assert [name for name in get_args(CompileNoteRule) if f"`{name}`" not in page] == []


class TestTheNotes:
    def test_the_sentences_are_the_notes_in_order(self):
        result = compile_source(CROWDED)
        assert result.notes
        assert result.notes == tuple(note.message for note in result.compile_notes)

    def test_a_note_carries_its_name(self):
        (note,) = compile_source(CROWDED).compile_notes
        assert note == CompileNote(rule="camera-retreated", message=note.message)
        assert note.message.startswith("camera retreated to ")

    def test_a_panel_with_nothing_to_say_has_no_note(self):
        assert compile_source("cast: {a: {reference: alice}}").compile_notes == ()
