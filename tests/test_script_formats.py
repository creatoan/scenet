"""Comic scripts as publishers ask for them (#75).

Dark Horse's *Script Format and Specifications* is the reference house format: a title
block, then `PAGE ONE (five panels)`, then `Panel 1.` with the description on the same
line. Writers also keep scripts in Markdown, so heading markers and bold labels are
tolerated -- stripped, then the convention parsed, never a second format. Each test here
is one row of the issue's table, or one edge of it.
"""

from pathlib import Path

import pytest

from scenet import compile_script
from scenet.cli import main
from scenet.diagnostics import Diagnostic, diagnose_script
from scenet.errors import ScriptSyntaxError
from scenet.frontends.script_front import parse_script, parse_script_document
from scenet.ir import CaptionEvent, PanelIR, SayEvent

FRONT = "---\ncast: {ALICE: {reference: alice}, BOB: {reference: bob}}\n---\n"


def panels(body: str) -> dict[str, PanelIR]:
    return parse_script(FRONT + body)


def found(body: str) -> list[tuple[str, str, int]]:
    """Every finding, as `(level, rule, line)`, the line counted in the whole script."""
    return [
        (item.level, item.rule, item.region.start.line if item.region else 0)
        for item in diagnose_script(FRONT + body, source=Path("x.script"))
    ]


def lines(panel: PanelIR) -> list[tuple[str, str]]:
    """What a panel says, as `(speaker, text)`, a caption's speaker being `CAPTION`."""
    said: list[tuple[str, str]] = []
    for event in panel.script:
        if isinstance(event, SayEvent):
            said.append((event.by, event.text))
        elif isinstance(event, CaptionEvent):
            said.append(("CAPTION", event.text))
    return said


class TestPageHeadings:
    def test_dark_horse_page_heading_as_the_first_line(self):
        script = "PAGE ONE (two panels)\n\nPANEL 1\n\nPANEL 2\n"
        assert list(panels(script)) == ["1", "2"]

    def test_it_names_the_page_when_panel_numbers_start_again(self):
        script = "PAGE ONE (one panel)\nPANEL 1\nPAGE TWO (two panels)\nPANEL 1\nPANEL 2\n"
        assert list(panels(script)) == ["1-1", "2-1", "2-2"]

    @pytest.mark.parametrize(
        ("heading", "page"),
        [
            ("Page Six (five panels)", "6"),
            ("PAGE TWENTY ONE", "21"),
            ("PAGE TWENTY-ONE (one panel)", "21"),
            ("PAGE 7:", "7"),
            ("PAGE 3A", "3A"),
            ("PAGE ONE (splash)", "1"),
        ],
    )
    def test_a_page_is_named_by_its_number(self, heading: str, page: str):
        script = f"PAGE ZERO\nPANEL 1\n{heading}\nPANEL 1\n"
        assert list(panels(script)) == ["0-1", f"{page}-1"]


class TestPanelHeadings:
    @pytest.mark.parametrize(
        "heading",
        [
            "Panel 1. Alice and Bob on a corner.",
            "Panel 1: Alice and Bob on a corner.",
            "Panel 1 — Alice and Bob on a corner.",
            "PANEL 1 - Alice and Bob on a corner.",
        ],
    )
    def test_the_description_may_follow_on_the_same_line(self, heading: str):
        document = parse_script_document(FRONT + f"{heading}\nALICE\nHi.\n")
        assert list(document.panels) == ["1"]
        assert lines(document.panels["1"]) == [("ALICE", "Hi.")]
        assert document.descriptions["1"][0] == "Alice and Bob on a corner."

    @pytest.mark.parametrize(
        ("heading", "label"),
        [
            ("Panel One", "1"),
            ("PANEL TWO:", "2"),
            ("Panel Twelve. A corner.", "12"),
            ("PANEL 4B", "4B"),
        ],
    )
    def test_a_panel_is_named_by_its_number(self, heading: str, label: str):
        assert list(panels(f"{heading}\n")) == [label]

    @pytest.mark.parametrize("line", ["Panel shows Alice.", "Panel borders are thick here."])
    def test_a_sentence_that_starts_with_panel_stays_prose(self, line: str):
        document = parse_script_document(FRONT + f"PANEL 1\n{line}\n")
        assert list(document.panels) == ["1"]
        assert document.descriptions["1"] == (line,)


class TestMarkdown:
    """Strip the markers, then parse the convention. Text is never rewritten."""

    @pytest.mark.parametrize(
        "heading",
        [
            "## PANEL 2",
            "# PANEL 2",
            "###### Panel 2.",
            "**PANEL 2**",
            "__PANEL 2__",
            "## **PANEL 2**",
        ],
    )
    def test_a_marked_heading_is_a_heading(self, heading: str):
        script = f"PANEL 1\nALICE\nHi.\n\n{heading}\nBOB\nHello.\n"
        said = {name: lines(panel) for name, panel in panels(script).items()}
        assert said == {"1": [("ALICE", "Hi.")], "2": [("BOB", "Hello.")]}

    def test_a_marked_page_heading_is_a_heading(self):
        assert list(panels("# PAGE ONE\n## PANEL 1\n# PAGE TWO\n## PANEL 1\n")) == ["1-1", "2-1"]

    @pytest.mark.parametrize("rule", ["---", "***", "___", "- - -"])
    def test_a_horizontal_rule_ends_a_speech(self, rule: str):
        document = parse_script_document(FRONT + f"PANEL 1\nALICE\nHi.\n{rule}\nRain falls.\n")
        assert lines(document.panels["1"]) == [("ALICE", "Hi.")]
        assert document.descriptions["1"] == ("Rain falls.",)

    def test_a_double_dash_is_kept_in_the_speech(self):
        """Dark Horse: `--` carries a speech over to the next balloon, or cuts it off."""
        said = lines(panels("PANEL 1\nALICE\nWait --\n-- no.\n")["1"])
        assert said == [("ALICE", "Wait -- -- no.")]


class TestTheTitlePage:
    """Dark Horse's format opens with the writer's name and address, before page one."""

    TITLE = "JOHN SMITH\n123 Main Street\nSpringfield\n\nThe Umbrella, Issue 1\n\n"

    def test_a_title_block_compiles(self):
        document = parse_script_document(
            FRONT + self.TITLE + "PAGE ONE (one panel)\nPanel 1. Rain.\n"
        )
        assert list(document.panels) == ["1"]
        assert document.title_page == (
            "JOHN SMITH",
            "123 Main Street",
            "Springfield",
            "The Umbrella, Issue 1",
        )

    def test_a_name_in_capitals_there_is_one_note(self):
        assert found(self.TITLE + "PANEL 1\n") == [("note", "looks-like-dialogue", 4)]

    def test_a_cast_member_there_is_an_error(self):
        """A forgotten heading, not a title page: ALICE is in the cast."""
        assert found("ALICE\nHi.\n\nPANEL 1\n") == [("error", "invalid-field", 4)]

    @pytest.mark.parametrize("line", ["@shot: close_up", "CAPTION: Midnight.", "SFX: BLAM"])
    def test_a_directive_caption_or_sound_there_is_an_error(self, line: str):
        with pytest.raises(ScriptSyntaxError, match="before the first PANEL"):
            panels(f"{line}\nPANEL 1\n")


class TestBetweenAPageAndItsFirstPanel:
    """Lines under a PAGE heading belong to the page, not to the last panel before it."""

    def test_prose_there_is_not_the_previous_panels(self):
        document = parse_script_document(
            FRONT + "PAGE ONE\nPANEL 1\nRain.\nPAGE TWO\nThe storm breaks.\nPANEL 1\n"
        )
        assert document.descriptions["1-1"] == ("Rain.",)
        assert document.descriptions["2-1"] == ()

    def test_dialogue_there_is_an_error_not_the_previous_panels(self):
        script = "PAGE ONE\nPANEL 1\nPAGE TWO\nALICE\nHi.\nPANEL 1\n"
        with pytest.raises(ScriptSyntaxError, match="belongs to no panel"):
            panels(script)


class TestAnEmptyCue:
    def test_a_cue_with_nothing_to_say_is_a_note(self):
        assert found("PANEL 1\nALICE\n\nBOB\nHello.\n") == [("note", "looks-like-dialogue", 5)]

    def test_the_rest_of_the_panel_is_read_as_before(self):
        assert lines(panels("PANEL 1\nALICE\n\nBOB\nHello.\n")["1"]) == [("BOB", "Hello.")]

    def test_one_at_the_end_of_the_script_too(self):
        assert found("PANEL 1\nALICE\n") == [("note", "looks-like-dialogue", 5)]


class TestThePanelCount:
    """`PAGE ONE (five panels)` is often the only sign a panel heading was misread."""

    @pytest.mark.parametrize(
        "heading",
        [
            "PAGE ONE (two panels)",
            "PAGE ONE (2 panels)",
            "Page One (Two Panels)",
            "PAGE 1 (two panels):",
        ],
    )
    def test_a_count_that_agrees_is_silent(self, heading: str):
        assert found(f"{heading}\nPANEL 1\nPANEL 2\n") == []

    def test_one_that_does_not_is_one_note_at_the_page(self):
        script = (
            "PAGE ONE (five panels)\nPANEL 1\nPANEL 2\nPANEL 3\nPANEL 4\n"
            "PAGE TWO (one panel)\nPANEL 1\n"
        )
        assert found(script) == [("note", "panel-count", 4)]
        (note,) = diagnose_script(FRONT + script)
        assert "five" in note.message
        assert "4" in note.message

    def test_a_singular_panel_is_counted_too(self):
        assert found("PAGE ONE (one panel)\nPANEL 1\nPANEL 2\n") == [("note", "panel-count", 4)]

    def test_a_page_note_that_is_not_a_count_is_not_read_as_one(self):
        assert found("PAGE ONE (splash)\nPANEL 1\nPANEL 2\n") == []


class TestNotesReachTheBuild:
    def test_compile_script_carries_the_frontends_notes(self):
        book = compile_script(FRONT + "PAGE ONE (two panels)\nPANEL 1\n")
        (note,) = book.notes
        assert "line 4" in note
        assert "two" in note

    def test_scenet_build_prints_them(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        path = tmp_path / "x.script"
        path.write_text(FRONT + "PAGE ONE (two panels)\nPANEL 1\n", encoding="utf-8")
        assert main(["build", str(path)]) == 0
        assert "note: line 4:" in capsys.readouterr().out


def test_every_note_has_a_rule_the_catalogue_knows():
    """Notes found by the frontend become findings like any other."""
    for item in diagnose_script(
        FRONT + "JOHN SMITH\nAddress\nPAGE ONE (two panels)\nPANEL 1\nALICE\n"
    ):
        assert isinstance(item, Diagnostic)
        assert item.level == "note"
