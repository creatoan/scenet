"""Notes: findings that report a house limit rather than a contradiction.

Every finding used to be an error, and any finding made `scenet check` exit 1. Dark
Horse's script format asks for "approximately 25 words per balloon, and about 50 words
per panel, max" -- a limit a letterer works to, not a law a document breaks. A balloon
over it still compiles, and `build` still builds it. So a rule now has a level, `error`
or `note`, and only an error fails a check.
"""

import json
from pathlib import Path

import pytest

from scenet import compile_script
from scenet.cli import main
from scenet.diagnostics import (
    RULES,
    Diagnostic,
    diagnose_file,
    diagnose_script,
    diagnose_source,
    to_sarif,
)
from scenet.pipeline import compile_book_file

CAST = "cast: {bob: {reference: bob}}\n"


def words(count: int, *, word: str = "word") -> str:
    return " ".join([word] * count)


def say(count: int, **words_like: str) -> str:
    return f'  - say: {{by: bob, text: "{words(count, **words_like)}"}}\n'


def yaml_panel(*lines: str) -> str:
    return CAST + "script:\n" + "".join(lines)


def notes(found: list[Diagnostic]) -> list[tuple[str, int]]:
    return [
        (item.rule, item.region.start.line if item.region else 0)
        for item in found
        if item.level == "note"
    ]


class TestLevels:
    def test_every_rule_is_an_error_or_a_note(self):
        assert {rule.level for rule in RULES.values()} <= {"error", "note"}

    def test_the_word_limit_is_a_note(self):
        assert RULES["word-limit"].level == "note"

    def test_a_finding_has_its_rules_level(self):
        assert Diagnostic(rule="word-limit", message="").level == "note"
        assert Diagnostic(rule="unknown-actor", message="").level == "error"


class TestTheWordLimits:
    """Dark Horse: about 25 words a balloon, about 50 a panel. Counted as lettered."""

    def test_a_balloon_of_twenty_five_words_is_within_it(self):
        assert diagnose_source(yaml_panel(say(25))) == []

    def test_a_balloon_of_twenty_six_is_one_note_at_its_text(self):
        (found,) = diagnose_source(yaml_panel(say(26)), source=Path("x.panel.yaml"))
        assert (found.rule, found.level) == ("word-limit", "note")
        assert found.path == ("script", 0, "say", "text")
        assert found.region is not None
        assert found.region.start.line == 3
        assert "26 words" in found.message

    def test_a_caption_has_the_same_limit(self):
        source = CAST + f'script:\n  - caption: {{text: "{words(26)}"}}\n'
        (found,) = diagnose_source(source)
        assert found.path == ("script", 0, "caption", "text")

    @pytest.mark.parametrize("filler", ["--", "...", "—", "!"])
    def test_punctuation_alone_is_not_a_word(self, filler: str):
        text = " ".join(["word"] * 25 + [filler] * 5)
        assert diagnose_source(CAST + f'script:\n  - say: {{by: bob, text: "{text}"}}\n') == []

    def test_emphasis_markers_are_not_counted_as_more_words(self):
        text = " ".join(["_word_"] * 25)
        assert diagnose_source(CAST + f'script:\n  - say: {{by: bob, text: "{text}"}}\n') == []

    def test_a_panel_of_fifty_one_words_is_one_note_at_its_script(self):
        source = yaml_panel(say(17), say(17), say(17))
        (found,) = diagnose_source(source, source=Path("x.panel.yaml"))
        assert (found.rule, found.path) == ("word-limit", ("script",))
        assert found.region is not None
        assert found.region.start.line == 2
        assert "51 words" in found.message

    def test_every_note_is_its_own_finding(self):
        found = diagnose_source(yaml_panel(say(26), say(26)), source=Path("x.panel.yaml"))
        assert notes(found) == [("word-limit", 2), ("word-limit", 3), ("word-limit", 4)]
        fingerprints = {item.fingerprint() for item in found}
        assert len(fingerprints) == 3

    def test_a_scene_reports_each_panel(self):
        line = "    " + say(26)
        source = CAST + f"panels:\n  a:\n    script:\n{line}  b:\n    script:\n{line}"
        found = diagnose_source(source, source=Path("x.scene.yaml"))
        assert [item.path for item in found] == [
            ("panels", "a", "script", 0, "say", "text"),
            ("panels", "b", "script", 0, "say", "text"),
        ]

    def test_an_error_is_reported_before_any_note_is_counted(self):
        """A document with a contradiction in it gets that fixed first."""
        source = CAST + "script:\n" + say(26) + "  - say: {by: nobody, text: Hi}\n"
        assert [item.rule for item in diagnose_source(source)] == ["unknown-actor"]

    def test_a_note_does_not_stop_the_deep_pass(self):
        """`--deep` runs on a document with no errors, notes or not."""
        source = yaml_panel(say(26))
        assert notes(diagnose_source(source, deep=True)) == [("word-limit", 3)]


class TestTheWordLimitsInAScript:
    FRONT = "---\ncast: {BOB: {reference: bob}}\n---\n"

    def test_a_long_speech_is_noted_at_its_cue(self):
        script = f"{self.FRONT}PANEL 1\nBOB\n{words(20)}\n{words(6)}\n"
        (found,) = diagnose_script(script, source=Path("x.script"))
        assert (found.rule, found.level) == ("word-limit", "note")
        assert found.path == ("1", "script", 0, "say", "text")
        assert found.region is not None
        assert found.region.start.line == 5

    def test_a_long_panel_is_noted_at_its_heading(self):
        speech = f"BOB\n{words(17)}\n\n"
        script = f"{self.FRONT}PANEL 1\n{speech * 3}"
        (found,) = diagnose_script(script, source=Path("x.script"))
        assert found.path == ("1", "script")
        assert found.region is not None
        assert found.region.start.line == 4

    def test_a_sound_effect_is_not_lettering_to_be_read(self):
        script = f"{self.FRONT}PANEL 1\nSFX: {words(30, word='BLAM')}\n"
        assert diagnose_script(script) == []


class TestCheck:
    LONG = yaml_panel(say(26))

    @pytest.fixture
    def noted(self, tmp_path: Path) -> Path:
        path = tmp_path / "long.panel.yaml"
        path.write_text(self.LONG, encoding="utf-8")
        return path

    def test_a_document_with_only_notes_passes(
        self, noted: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert main(["check", str(noted)]) == 0
        out, err = capsys.readouterr()
        assert f"{noted}:3:" in err
        assert ": note: word-limit: " in err
        assert out == f"{noted}: ok\n"

    def test_a_note_beside_an_error_still_fails(self, tmp_path: Path):
        path = tmp_path / "both.panel.yaml"
        path.write_text(self.LONG + "  - say: {by: nobody, text: Hi}\n", encoding="utf-8")
        assert main(["check", str(path)]) == 1

    def test_sarif_says_note_for_the_rule_and_the_result(
        self, noted: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert main(["check", "--format", "sarif", str(noted)]) == 0
        (run,) = json.loads(capsys.readouterr().out)["runs"]
        (rule,) = run["tool"]["driver"]["rules"]
        (result,) = run["results"]
        assert rule["defaultConfiguration"] == {"level": "note"}
        assert result["level"] == "note"

    def test_an_error_is_still_an_error_in_sarif(self):
        document = to_sarif([Diagnostic(rule="unknown-actor", message="x")])
        (run,) = document["runs"]
        assert run["results"][0]["level"] == "error"
        assert run["tool"]["driver"]["rules"][0]["defaultConfiguration"] == {"level": "error"}


GALLERY = Path(__file__).resolve().parents[1] / "examples" / "gallery"


@pytest.mark.parametrize(
    "path",
    sorted(path for path in GALLERY.iterdir() if path.name != "manifest.yaml"),
    ids=lambda path: path.name,
)
def test_the_gallery_has_nothing_to_note(path: Path):
    """The examples are what people copy: not even a note, let alone an error."""
    assert diagnose_file(path) == []


class TestOneWayToCompileAScript:
    """A script compiles one way, whoever asks: `build`, `check --deep`, the MCP server
    and the playground used to each assemble it by hand."""

    SCRIPT = "---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1\nALICE\nHello.\n"

    def test_from_text_as_from_a_file(self, tmp_path: Path):
        path = tmp_path / "x.script"
        path.write_text(self.SCRIPT, encoding="utf-8")
        from_text = compile_script(self.SCRIPT, source=path)
        from_file = compile_book_file(path)
        assert [result.core.to_json() for result in from_text.panels.values()] == [
            result.core.to_json() for result in from_file.panels.values()
        ]
        assert from_text.pages == from_file.pages == ()
