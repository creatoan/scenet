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
from scenet.diagnostics import Diagnostic, diagnose_script, diagnose_source
from scenet.errors import ScriptSyntaxError
from scenet.frontends.script_front import parse_script, parse_script_document
from scenet.ir import CaptionEvent, PanelIR, SayEvent, Side

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


# Typographic quotes, spelled as code points so no editor mistakes one for another.
LEFT, RIGHT = chr(0x201C), chr(0x201D)
GUILLEMET_OPEN, GUILLEMET_CLOSE, NBSP = chr(0x00AB), chr(0x00BB), chr(0x00A0)


def events(panel: PanelIR) -> list[tuple[str, str | None, str, str]]:
    """What a panel says, as `(verb, speaker, kind, text)`."""
    said: list[tuple[str, str | None, str, str]] = []
    for event in panel.script:
        if isinstance(event, SayEvent):
            said.append(("say", event.by, event.kind.value, event.text))
        elif isinstance(event, CaptionEvent):
            said.append(("caption", event.by, event.kind.value, event.text))
    return said


def only(body: str) -> list[tuple[str, str | None, str, str]]:
    """What the one panel of a script says."""
    (panel,) = panels(body).values()
    return events(panel)


class TestCaptions:
    """Dark Horse: `CAP:` is "indicated the same way" as dialogue -- the text under it."""

    @pytest.mark.parametrize(
        "body",
        ["CAP: Later.", "CAP:\nLater.", "CAPTION\nLater.", "CAPTION:\nLater.", "**CAP:** Later."],
    )
    def test_a_caption_on_its_line_or_under_it(self, body: str):
        assert only(f"PANEL 1\n{body}\n") == [("caption", None, "locale", "Later.")]

    def test_its_text_runs_to_a_blank_line_when_under_it(self):
        said = only("PANEL 1\nCAP:\nLater that night,\nby the docks.\n\nRain.\n")
        assert said == [("caption", None, "locale", "Later that night, by the docks.")]

    def test_its_first_line_is_its_text_whatever_it_looks_like(self):
        assert only("PANEL 1\nCAPTION\nMIDNIGHT.\n") == [("caption", None, "locale", "MIDNIGHT.")]

    def test_a_kind_works_either_way(self):
        said = only("PANEL 1\nCAPTION (monologue)\nShe never forgot.\nCAP (editorial): See #4.\n")
        assert [kind for _, _, kind, _ in said] == ["monologue", "editorial"]

    def test_with_no_text_it_is_an_error_at_its_line(self):
        assert found("PANEL 1\nCAP:\n\nRain.\n") == [("error", "invalid-field", 5)]

    def test_a_name_that_starts_with_cap_is_a_cue(self):
        said = only("PANEL 1\n@cast: {CAPTAIN: {reference: bob}}\nCAPTAIN: Hi.\n")
        assert said == [("say", "CAPTAIN", "speech", "Hi.")]


class TestCaptionsThatCarrySpeech:
    """Dark Horse's `CAP/CHARACTER`, "placing the speech in quotation marks" -- marks the
    compiler adds itself, so the writer's are taken off rather than doubled."""

    def test_cap_slash_name_is_a_spoken_caption_by_them(self):
        said = only(f"PANEL 1\nCAP/ALICE\n{LEFT}-- a caption can carry the speech.{RIGHT}\n")
        assert said == [("caption", "ALICE", "spoken", "-- a caption can carry the speech.")]

    def test_inline_and_with_straight_quotes(self):
        said = only('PANEL 1\nCAPTION/BOB: "Get down!"\n')
        assert said == [("caption", "BOB", "spoken", "Get down!")]

    def test_a_run_opens_each_box_with_a_quote_and_closes_only_the_last(self):
        """Blambot's run: the writer's opening quote on each box is the writer's, too."""
        body = f"PANEL 1\nCAP/ALICE: {LEFT}Get down,\n\nCAP/ALICE: {LEFT}all of you!{RIGHT}\n"
        assert [text for *_, text in only(body)] == ["Get down,", "all of you!"]

    def test_a_kind_that_cannot_have_a_speaker_is_the_existing_rule(self):
        assert found("PANEL 1\nCAP/ALICE (monologue): Hm.\n") == [("error", "caption-speaker", 5)]

    @pytest.mark.parametrize("words", ["voice over", "V.O.", "VO", "voice-over"])
    def test_a_voice_over_caption_is_spoken(self, words: str):
        assert only(f"PANEL 1\nCAPTION ({words}): Hello.\n") == [
            ("caption", None, "spoken", "Hello.")
        ]


class TestVoiceOver:
    """Blambot: a voice over is "the character is speaking, but is not in the location
    shown" -- a spoken caption by them, not a balloon tailed to somebody drawn."""

    def test_a_cue_marked_voice_over_is_a_spoken_caption(self):
        said = only("PANEL 1\nALICE (V.O.)\nI never came back.\n")
        assert said == [("caption", "ALICE", "spoken", "I never came back.")]

    def test_inline_too(self):
        assert only("PANEL 1\nALICE (VO): Never.\n") == [("caption", "ALICE", "spoken", "Never.")]

    def test_nor_small_type(self):
        with pytest.raises(ScriptSyntaxError, match="voice over"):
            panels("PANEL 1\nALICE (V.O., small)\nHm.\n")

    def test_a_voice_over_has_no_balloon_to_whisper_in(self):
        with pytest.raises(ScriptSyntaxError, match="voice over") as raised:
            panels("PANEL 1\nALICE (V.O., whisper)\nHm.\n")
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 5)


class TestInlineCues:
    def test_a_name_and_its_line_on_one_line(self):
        assert only("PANEL 1\nALICE: Hello.\n") == [("say", "ALICE", "speech", "Hello.")]

    @pytest.mark.parametrize("line", ["ALICE (whisper): Psst.", "**ALICE (whisper):** Psst."])
    def test_with_a_parenthetical_or_in_bold(self, line: str):
        assert only(f"PANEL 1\n{line}\n") == [("say", "ALICE", "whisper", "Psst.")]

    def test_a_wrapped_line_belongs_to_it(self):
        assert only("PANEL 1\nALICE: Hello\nthere.\n") == [
            ("say", "ALICE", "speech", "Hello there.")
        ]

    def test_the_panels_whole_cast_decides(self):
        """A cast member the panel adds after the line still makes it dialogue."""
        said = only("PANEL 1\nCARL: Who?\n@cast: {CARL: {reference: bob}}\n")
        assert said == [("say", "CARL", "speech", "Who?")]

    def test_a_name_not_in_the_cast_is_prose_and_a_note(self):
        document = parse_script_document(FRONT + "PANEL 1\nNOTE: redraw the rain.\n")
        assert events(document.panels["1"]) == []
        assert document.descriptions["1"] == ("NOTE: redraw the rain.",)
        assert found("PANEL 1\nNOTE: redraw the rain.\n") == [("note", "looks-like-dialogue", 5)]

    def test_a_name_in_lower_case_is_dialogue_only_when_it_is_a_cast_member(self):
        junior = "PANEL 1\n@cast: {Junior: {reference: bob}}\nJunior: Die, you dirty rat!\n"
        assert only(junior) == [("say", "Junior", "speech", "Die, you dirty rat!")]
        assert only("PANEL 1\nLater: they meet.\n") == []
        assert found("PANEL 1\nLater: they meet.\n") == []

    def test_one_ends_the_speech_before_it(self):
        """It used to be joined onto the balloon above: "Hi. BOB: Hello."."""
        said = only("PANEL 1\nALICE\nHi.\nBOB: Hello.\n")
        assert said == [("say", "ALICE", "speech", "Hi."), ("say", "BOB", "speech", "Hello.")]

    def test_one_not_in_the_cast_continues_the_speech(self):
        said = only("PANEL 1\nALICE\nListen.\nRULE ONE: never lie.\n")
        assert said == [("say", "ALICE", "speech", "Listen. RULE ONE: never lie.")]

    def test_the_line_under_a_cue_is_its_line_unless_a_cast_member_speaks(self):
        assert only("PANEL 1\nBOB\nNOTE: this is what he says.\n") == [
            ("say", "BOB", "speech", "NOTE: this is what he says.")
        ]


class TestModifiers:
    def test_burst_is_a_shout(self):
        """Blambot: "(BURST), meaning the dialogue is shouted"."""
        assert only("PANEL 1\nALICE (burst)\nNo!\n") == [("say", "ALICE", "shout", "No!")]

    @pytest.mark.parametrize("cue", ["ALICE (whisper, burst)", "ALICE (whisper) (thinking)"])
    def test_two_kinds_of_balloon_is_an_error(self, cue: str):
        with pytest.raises(ScriptSyntaxError) as raised:
            panels(f"PANEL 1\n{cue}\nNo!\n")
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 5)

    def test_a_performance_note_beside_a_kind_is_still_ignored(self):
        assert only("PANEL 1\nALICE (quietly) (whisper)\nNo.\n") == [
            ("say", "ALICE", "whisper", "No.")
        ]


class TestBalloonNumbers:
    """Blambot: "Each item in the lettering area should be numbered"."""

    @pytest.mark.parametrize("body", ["1. ALICE:\nHi.", "1) ALICE: Hi.", "12 ALICE\nHi."])
    def test_a_numbered_cue(self, body: str):
        assert only(f"PANEL 1\n{body}\n") == [("say", "ALICE", "speech", "Hi.")]

    def test_a_numbered_caption(self):
        assert only("PANEL 1\n2. CAP: Later.\n") == [("caption", None, "locale", "Later.")]

    def test_a_wrapped_line_that_starts_with_a_number_stays_wrapped(self):
        said = only("PANEL 1\nALICE\nJust\n1 MORE TIME\n")
        assert said == [("say", "ALICE", "speech", "Just 1 MORE TIME")]


class TestQuotationMarks:
    @pytest.mark.parametrize(
        "line",
        [
            '"Hello."',
            f"{LEFT}Hello.{RIGHT}",
            f"{GUILLEMET_OPEN}{NBSP}Hello.{NBSP}{GUILLEMET_CLOSE}",
            f"{GUILLEMET_OPEN} Hello. {GUILLEMET_CLOSE}",
        ],
    )
    def test_a_balloons_enclosing_marks_are_taken_off(self, line: str):
        assert only(f"PANEL 1\nALICE\n{line}\n") == [("say", "ALICE", "speech", "Hello.")]

    def test_a_quotation_inside_is_kept(self):
        line = '"He said "no", twice."'
        assert only(f"PANEL 1\nALICE\n{line}\n") == [("say", "ALICE", "speech", line)]

    def test_a_double_dash_is_kept_at_either_end(self):
        said = only("PANEL 1\nALICE:\nWait --\n\nBOB:\n-- no.\n")
        assert [text for *_, text in said] == ["Wait --", "-- no."]


class TestReservedNames:
    @pytest.mark.parametrize("name", ["CAP", "CAPTION", "SFX", "Sfx"])
    def test_a_label_cannot_be_a_cast_member(self, name: str):
        with pytest.raises(ScriptSyntaxError, match="reserved") as raised:
            parse_script(f"---\ncast: {{{name}: {{reference: alice}}}}\n---\nPANEL 1\n")
        assert raised.value.rule == "invalid-field"

    def test_nor_in_a_panels_own_cast(self):
        with pytest.raises(ScriptSyntaxError, match="reserved") as raised:
            panels("PANEL 1\n@cast: {CAP: {reference: bob}}\n")
        assert raised.value.line == 5


class TestOver:
    """`@over:` writes a panel as a sparse change to another, as `over:` does in YAML."""

    BASE = "PANEL 1\n@shot: close_up\n@setting: {weather: rain}\nALICE\nHello.\n\n"

    def test_a_panel_inherits_the_directives_of_the_one_it_is_over(self):
        result = panels(self.BASE + "PANEL 2\n@over: 1\n@angle: low\n")
        assert result["2"].camera.shot == result["1"].camera.shot
        assert result["2"].setting == result["1"].setting
        assert result["2"].camera.angle.value == "low"

    def test_never_the_dialogue(self):
        assert events(panels(self.BASE + "PANEL 2\n@over: 1\n")["2"]) == []

    def test_it_may_change_what_it_inherits(self):
        result = panels(self.BASE + "PANEL 2\n@over: 1\n@shot: full_shot\n")
        assert result["2"].camera.shot.value == "full_shot"

    def test_it_may_name_a_panel_further_down(self):
        result = panels("PANEL 1\n@over: 2\n\n" + self.BASE.replace("PANEL 1", "PANEL 2"))
        assert result["1"].camera.shot == result["2"].camera.shot

    def test_a_label_is_looked_up_on_the_same_page_first(self):
        script = (
            "PAGE ONE\n" + self.BASE + "PAGE TWO\nPANEL 1\n@shot: full_shot\n\nPANEL 2\n@over: 1\n"
        )
        result = panels(script)
        assert result["2-2"].camera.shot.value == "full_shot"

    def test_then_as_a_panels_whole_name(self):
        script = "PAGE ONE\n" + self.BASE + "PAGE TWO\nPANEL 1\n@over: 1-1\n"
        assert panels(script)["2-1"].setting == panels(script)["1-1"].setting

    def test_a_label_is_a_label_not_a_number(self):
        """YAML would read `07` as the number 7; a script names the panel `07` is."""
        result = panels("PANEL 07\n@shot: close_up\n\nPANEL 8\n@over: 07\n")
        assert result["8"].camera.shot.value == "close_up"

    def test_a_cast_member_it_inherits_may_speak(self):
        script = "PANEL 1\n@cast: {CARL: {reference: bob}}\n\nPANEL 2\n@over: 1\nCARL: Who?\n"
        assert events(panels(script)["2"]) == [("say", "CARL", "speech", "Who?")]

    @pytest.mark.parametrize(
        ("body", "line", "says"),
        [
            ("PANEL 1\n@over: 9\n", 5, "does not exist"),
            # At the `@over:` that closes the cycle, as YAML reports one.
            ("PANEL 1\n@over: 2\n\nPANEL 2\n@over: 1\n", 8, "cyclic"),
            ("PANEL 1\n@over: 1\n", 5, "names its own panel"),
        ],
    )
    def test_a_fault_is_one_composition_finding_at_its_line(self, body: str, line: int, says: str):
        (finding,) = diagnose_script(FRONT + body, source=Path("x.script"))
        assert (finding.rule, finding.level) == ("composition", "error")
        assert finding.region is not None
        assert finding.region.start.line == line
        assert says in finding.message

    def test_written_twice_it_is_a_repeated_directive(self):
        assert found("PANEL 1\n\nPANEL 2\n@over: 1\n@over: 1\n") == [("error", "duplicate-key", 8)]


class TestOffPanelCues:
    """Dark Horse: `CHARACTER (OP):` -- "Characters speaking from off-panel are indicated
    this way." Off panel means in the scene, not in the frame: the front matter is the
    scene's cast, so the speaker is left out of that one panel, and the tail ends on the
    frame on their side."""

    STAGED = (
        "---\n"
        "cast:\n"
        "  ALICE: {reference: alice, at: left_third}\n"
        "  BOB: {reference: bob, at: right_third}\n"
        "staging: [ALICE left_of BOB, BOB looking_at ALICE]\n"
        "---\n"
    )

    def read(self, body: str) -> dict[str, PanelIR]:
        return parse_script(self.STAGED + body)

    def test_the_speaker_is_left_out_of_that_panel_only(self):
        result = self.read("PANEL 1\nALICE (OP)\nHey!\n\nPANEL 2\nALICE\nHi.\n")
        assert set(result["1"].cast) == {"BOB"}
        assert result["1"].staging == ()
        assert set(result["2"].cast) == {"ALICE", "BOB"}

    def test_their_tail_ends_on_the_side_they_stood(self):
        (line,) = self.read("PANEL 1\nALICE (OP)\nHey!\n")["1"].script
        assert isinstance(line, SayEvent)
        assert (line.by, line.off_panel) == ("ALICE", Side.LEFT)

    def test_each_relation_left_out_is_a_note(self):
        script = self.STAGED + "PANEL 1\nALICE (OP)\nHey!\n"
        found_here = diagnose_script(script, source=Path("x.script"))
        assert [(item.rule, item.level) for item in found_here] == [
            ("dropped-relation", "note"),
            ("dropped-relation", "note"),
        ]
        assert all(item.region is not None and item.region.start.line == 8 for item in found_here)

    @pytest.mark.parametrize(
        "marker", ["(OFF)", "(O.S.)", "(O.C.)", "(off-panel)", "(OP, whisper)"]
    )
    def test_every_spelling(self, marker: str):
        (line,) = panels(f"PANEL 1\nCARL {marker}\nHey!\n")["1"].script
        assert isinstance(line, SayEvent)
        assert line.off_panel is True

    def test_a_side_may_be_named(self):
        (line,) = self.read("PANEL 1\nALICE (OP, right)\nHey!\n")["1"].script
        assert isinstance(line, SayEvent)
        assert line.off_panel == Side.RIGHT

    def test_a_side_word_without_a_marker_is_a_performance_note(self):
        (line,) = panels("PANEL 1\nALICE (left)\nHey!\n")["1"].script
        assert isinstance(line, SayEvent)
        assert line.off_panel is False

    def test_somebody_never_cast_speaks_too(self):
        said = panels("PANEL 1\nPHONE (OP)\nRing.\nPHONE (OP): Ring.\n")["1"].script
        assert [(line.by, line.off_panel) for line in said if isinstance(line, SayEvent)] == [
            ("PHONE", True),
            ("PHONE", True),
        ]

    def test_a_panels_own_cast_cannot_name_them(self):
        with pytest.raises(ScriptSyntaxError) as raised:
            panels("PANEL 1\n@cast: {CARL: {reference: bob}}\nCARL (OP)\nHey!\n")
        assert (raised.value.rule, raised.value.line) == ("off-panel-speaker", 6)

    def test_nor_can_one_speaker_be_on_and_off_panel_in_one_panel(self):
        with pytest.raises(ScriptSyntaxError) as raised:
            self.read("PANEL 1\nALICE\nHi.\n\nALICE (OP)\nBye.\n")
        assert (raised.value.rule, raised.value.line) == ("off-panel-speaker", 11)

    def test_a_panel_over_it_does_not_inherit_the_absence(self):
        result = self.read("PANEL 1\nALICE (OP)\nHey!\n\nPANEL 2\n@over: 1\n")
        assert set(result["2"].cast) == {"ALICE", "BOB"}

    def test_a_fault_in_a_member_off_panel_everywhere_is_still_found(self):
        script = (
            "---\ncast: {ALICE: {reference: alicee}, BOB: {reference: bob}}\n---\n"
            "PANEL 1\nALICE (OP)\nHey!\n"
        )
        assert [item.rule for item in diagnose_script(script)] == ["unknown-puppet"]


class TestFrench:
    """Franco-Belgian scripts: *planche*, *case* or *vignette*, *récitatif* or *cartouche*,
    *onomatopée* (Cité internationale de la bande dessinée, lexique), and the *échelle des
    plans* for shots."""

    FRONT = "---\ncast: {LÉA: {reference: alice}, Léa: {reference: bob}}\n---\n"

    def read(self, body: str) -> dict[str, PanelIR]:
        return parse_script(self.FRONT + body)

    @pytest.mark.parametrize(
        ("heading", "names"),
        [
            ("PLANCHE 1\nCASE 1\nCASE 2\nPLANCHE 2\nCASE 1\n", ["1-1", "1-2", "2-1"]),
            ("PLANCHE UNE\nVIGNETTE 1\n", ["1"]),
            ("Planche 3 (2 cases)\nCase 1 : La plage.\nCase 2.\n", ["1", "2"]),
        ],
    )
    def test_pages_and_panels(self, heading: str, names: list[str]):
        assert list(self.read(heading)) == names

    def test_a_panel_heading_comes_before_a_cue(self):
        """`CASE 2` is a name in capitals as far as a cue goes."""
        document = parse_script_document(self.FRONT + "CASE 1 : Le port.\nLÉA\nBonjour.\n")
        assert document.descriptions["1"] == ("Le port.",)

    def test_a_case_with_no_number_is_still_a_cue(self):
        script = "---\ncast: {CASE: {reference: bob}}\n---\nCASE 1\nCASE\nEnquête close.\n"
        (line,) = parse_script(script)["1"].script
        assert isinstance(line, SayEvent)
        assert line.by == "CASE"

    @pytest.mark.parametrize("count", ["(six cases)", "(6 vignettes)", "(SIX CASES)", "(une case)"])
    def test_the_count_in_french(self, count: str):
        cases = 1 if "une" in count else 6
        body = f"PLANCHE 1 {count}\n" + "".join(f"CASE {n}\n" for n in range(1, cases + 1))
        assert diagnose_script(self.FRONT + body) == []

    @pytest.mark.parametrize(
        "label", ["RÉCITATIF", "RECITATIF", "Récitatif", "NARRATIF", "CARTOUCHE"]
    )
    def test_a_caption_by_its_french_names(self, label: str):
        (line,) = self.read(f"CASE 1\n{label} : Dimanche soir.\n")["1"].script
        assert isinstance(line, CaptionEvent)
        assert (line.text, line.kind.value) == ("Dimanche soir.", "locale")

    def test_a_caption_carrying_speech(self):
        quoted = f"{GUILLEMET_OPEN}{NBSP}Je reviendrai.{NBSP}{GUILLEMET_CLOSE}"
        (line,) = self.read(f"CASE 1\nCARTOUCHE/LÉA : {quoted}\n")["1"].script
        assert isinstance(line, CaptionEvent)
        assert (line.by, line.kind.value, line.text) == ("LÉA", "spoken", "Je reviendrai.")

    @pytest.mark.parametrize("label", ["ONOMATOPÉE", "ONOMATOPEE", "Onomatopée"])
    def test_a_sound_effect(self, label: str):
        quoted = f"{GUILLEMET_OPEN} FLOP ! {GUILLEMET_CLOSE}"
        (effect,) = self.read(f"CASE 1\n{label} : {quoted}\n")["1"].script
        assert effect.verb == "sfx"

    @pytest.mark.parametrize("space", [" ", NBSP, chr(0x202F)])
    def test_a_space_before_the_colon(self, space: str):
        (line,) = self.read(f"CASE 1\nLÉA{space}: Bonjour.\n")["1"].script
        assert isinstance(line, SayEvent)
        assert (line.by, line.text) == ("LÉA", "Bonjour.")

    def test_a_name_in_lower_case_that_is_cast(self):
        quoted = f"{GUILLEMET_OPEN} Plus qu'une heure ! {GUILLEMET_CLOSE}"
        (line,) = self.read(f"CASE 1\nLéa : {quoted}\n")["1"].script
        assert isinstance(line, SayEvent)
        assert (line.by, line.text) == ("Léa", "Plus qu'une heure !")

    @pytest.mark.parametrize(
        ("modifier", "kind", "off_panel"),
        [
            ("(pensée)", "thought", False),
            ("(off)", "speech", True),
            ("(hors champ)", "speech", True),
        ],
    )
    def test_french_modifiers(self, modifier: str, kind: str, off_panel: bool):
        (line,) = self.read(f"CASE 1\nLÉA {modifier}\nHm.\n")["1"].script
        assert isinstance(line, SayEvent)
        assert (line.kind.value, line.off_panel is not False) == (kind, off_panel)

    @pytest.mark.parametrize(
        ("written", "shot"),
        [
            ("plan d'ensemble", "long_shot"),
            ("PE", "long_shot"),
            ("plan moyen", "full_shot"),
            ("plan américain", "cowboy"),
            ("P.A.", "cowboy"),
            ("plan rapproché taille", "medium_shot"),
            ("plan mi-moyen", "medium_shot"),
            ("plan rapproché poitrine", "medium_close_up"),
            ("plan rapproché", "medium_close_up"),
            ("plan rapproché épaule", "close_up"),
            ("gros plan", "big_close_up"),
            ("Gros Plan", "big_close_up"),
            ("GP", "big_close_up"),
            ("très gros plan", "extreme_close_up"),
            ("tres gros plan", "extreme_close_up"),
        ],
    )
    def test_a_shot_by_its_french_name(self, written: str, shot: str):
        assert self.read(f"CASE 1\n@shot: {written}\n")["1"].camera.shot.value == shot

    @pytest.mark.parametrize(
        ("written", "angle"),
        [
            ("plongée", "high"),
            ("contre-plongée", "low"),
            ("contre plongee", "low"),
            ("angle normal", "eye_level"),
        ],
    )
    def test_an_angle_by_its_french_name(self, written: str, angle: str):
        assert self.read(f"CASE 1\n@angle: {written}\n")["1"].camera.angle.value == angle

    def test_an_unknown_shot_names_the_french_ones_too(self):
        with pytest.raises(ScriptSyntaxError, match="gros plan") as raised:
            self.read("CASE 1\n@shot: plan général\n")
        assert (raised.value.rule, raised.value.line) == ("invalid-field", 5)

    def test_yaml_stays_english(self):
        (found,) = diagnose_source("camera: {shot: gros plan}\ncast: {a: {reference: alice}}\n")
        assert found.rule == "invalid-field"

    @pytest.mark.parametrize("name", ["RÉCITATIF", "CARTOUCHE", "ONOMATOPÉE"])
    def test_a_french_label_is_reserved_too(self, name: str):
        with pytest.raises(ScriptSyntaxError, match="reserved"):
            parse_script(f"---\ncast: {{{name}: {{reference: alice}}}}\n---\nCASE 1\n")
