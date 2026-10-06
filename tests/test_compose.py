"""Sparse override between panels, and the comic-script frontend.

The `over` arc is what makes a sequence writable: consecutive panels in a scene share
nearly all their staging, and restating it per panel is where continuity errors get
in.
"""

from pathlib import Path

import pytest

from scenet.compose import CompositionError, merge, resolve_overrides
from scenet.diagnostics import diagnose_source
from scenet.frontends.script_front import ScriptSyntaxError, load_script, parse_script
from scenet.frontends.yaml_front import PanelSyntaxError, load_scene, parse_panel, parse_scene
from scenet.ir import BalloonKind, CaptionEvent, CaptionKind, SayEvent, ShotType
from scenet.pipeline import compile_document

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class TestMerge:
    def test_override_wins_on_scalars(self):
        assert merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_mappings_merge_recursively(self):
        """Changing one actor's pose must leave the rest of the cast alone."""
        base = {
            "cast": {"alice": {"pose": "standing", "at": "left_third"}, "bob": {"pose": "idle"}}
        }
        result = merge(base, {"cast": {"alice": {"pose": "pointing"}}})
        assert result["cast"]["alice"] == {"pose": "pointing", "at": "left_third"}
        assert result["cast"]["bob"] == {"pose": "idle"}

    def test_lists_replace_rather_than_append(self):
        """Script and staging are ordered wholes. Appending to an inherited script
        would make it impossible to write a panel where somebody says less."""
        assert merge({"script": [1, 2, 3]}, {"script": [9]}) == {"script": [9]}

    def test_the_base_is_not_mutated(self):
        base = {"cast": {"alice": {"pose": "standing"}}}
        merge(base, {"cast": {"alice": {"pose": "pointing"}}})
        assert base["cast"]["alice"]["pose"] == "standing"


class TestResolveOverrides:
    def test_a_panel_without_over_is_unchanged(self):
        assert resolve_overrides({"p": {"camera": {"shot": "close_up"}}}) == {
            "p": {"camera": {"shot": "close_up"}}
        }

    def test_inheritance_chains_compose(self):
        resolved = resolve_overrides(
            {
                "a": {"camera": {"shot": "wide"}, "cast": {"x": {"pose": "idle"}}},
                "b": {"over": "a", "camera": {"shot": "close_up"}},
                "c": {"over": "b", "cast": {"x": {"pose": "pointing"}}},
            }
        )
        assert resolved["c"]["camera"]["shot"] == "close_up"
        assert resolved["c"]["cast"]["x"]["pose"] == "pointing"

    def test_a_panel_may_inherit_from_one_declared_later(self):
        """Resolution is lazy, so declaration order carries no meaning."""
        resolved = resolve_overrides({"b": {"over": "a"}, "a": {"camera": {"shot": "wide"}}})
        assert resolved["b"]["camera"]["shot"] == "wide"

    def test_the_over_key_is_consumed(self):
        resolved = resolve_overrides({"a": {"camera": {}}, "b": {"over": "a"}})
        assert "over" not in resolved["b"]

    def test_declaration_order_is_preserved(self):
        resolved = resolve_overrides({"z": {}, "a": {"over": "z"}, "m": {}})
        assert list(resolved) == ["z", "a", "m"]

    def test_a_cycle_is_reported_with_the_chain(self):
        with pytest.raises(CompositionError, match="cyclic"):
            resolve_overrides({"a": {"over": "b"}, "b": {"over": "a"}})

    def test_self_reference_is_a_cycle(self):
        with pytest.raises(CompositionError, match="cyclic"):
            resolve_overrides({"a": {"over": "a"}})

    def test_an_unknown_parent_names_what_exists(self):
        with pytest.raises(CompositionError, match="does not exist"):
            resolve_overrides({"a": {"over": "nowhere"}})


class TestSceneDocuments:
    def test_a_single_panel_document_needs_no_ceremony(self):
        scene = parse_scene("cast:\n  a: {reference: alice}\n")
        assert list(scene) == ["panel"]

    def test_panels_inherit_document_level_defaults(self):
        scene = parse_scene("""
panel: {size: [640, 480]}
panels:
  one:
    cast: {a: {reference: alice}}
  two:
    cast: {a: {reference: bob}}
""")
        assert all(ir.panel.size == (640.0, 480.0) for ir in scene.values())

    def test_over_is_resolved_before_validation(self):
        """A panel that inherits its cast is valid even though it declares none."""
        scene = parse_scene("""
panels:
  one:
    camera: {shot: full_shot}
    cast: {alice: {reference: alice}}
    script: [{say: {by: alice, text: "Here."}}]
  two:
    over: one
    camera: {shot: close_up}
""")
        assert list(scene["two"].cast) == ["alice"]
        assert scene["two"].camera.shot is ShotType.CLOSE_UP
        assert scene["two"].script[0].text == "Here."

    def test_a_bad_panel_is_named_in_the_error(self):
        with pytest.raises(PanelSyntaxError, match="in panel 'two'"):
            parse_scene("""
panels:
  one: {cast: {a: {reference: alice}}}
  two: {cast: {a: {reference: alice}}, staging: ["a left_of ghost"]}
""")

    def test_shipped_sequence_example_parses(self):
        scene = load_scene(EXAMPLES / "sequence.scene.yaml")
        assert list(scene) == ["establishing", "reaction", "closer"]
        # Only Alice's pose was overridden in the last panel; Bob is untouched.
        assert scene["closer"].cast["alice"].pose == "pointing"
        assert scene["closer"].cast["bob"].pose == scene["establishing"].cast["bob"].pose


class TestComicScript:
    def test_cues_and_dialogue_are_paired(self):
        panels = parse_script("""
---
cast: {ALICE: {reference: alice}}
---
PANEL 1
ALICE
Hello there.
""")
        assert panels["1"].script[0].by == "ALICE"
        assert panels["1"].script[0].text == "Hello there."

    def test_parentheticals_select_the_balloon_kind(self):
        """A regression guard: testing the whole line for capitals rejects
        `BOB (whisper)`, silently dropping every piece of modified dialogue."""
        panels = parse_script("""
---
cast: {BOB: {reference: bob}}
---
PANEL 1
BOB (whisper)
Quietly now.
BOB (shouting)
NOT LIKE THAT!
""")
        kinds = [event.kind for event in panels["1"].script]
        assert kinds == [BalloonKind.WHISPER, BalloonKind.SHOUT]

    def test_caption_lines_become_captions(self):
        """`CAPTION:` is the convention writers already use, recorded in prior_art.md
        alongside PAGE ONE and PANEL 1."""
        panels = parse_script("""
---
cast: {ALICE: {reference: alice}}
---
PANEL 1
CAPTION: Midnight. The docks.
ALICE
Hello there.
""")
        caption, dialogue = panels["1"].script
        assert isinstance(caption, CaptionEvent)
        assert caption.text == "Midnight. The docks."
        assert caption.kind is CaptionKind.LOCALE
        assert isinstance(dialogue, SayEvent)

    def test_a_parenthetical_selects_the_caption_kind(self):
        panels = parse_script("""
---
cast: {ALICE: {reference: alice}}
---
PANEL 1
CAPTION (monologue): I should have brought an umbrella.
""")
        assert panels["1"].script[0].kind is CaptionKind.MONOLOGUE

    def test_a_bare_caption_line_is_not_read_as_a_cue(self):
        """`CAPTION` on its own matches the character-cue pattern, so it has to be
        ruled out before cue detection or the next line becomes its dialogue."""
        with pytest.raises(ScriptSyntaxError, match="CAPTION"):
            parse_script("""
---
cast: {ALICE: {reference: alice}}
---
PANEL 1
CAPTION
Midnight. The docks.
""")

    def test_prose_descriptions_are_not_interpreted(self):
        """Turning prose into staging needs language understanding, and guessing
        would produce panels that are confidently wrong."""
        panels = parse_script("""
---
cast: {ALICE: {reference: alice}}
---
PANEL 1
Alice stands on a rainy street corner looking furious.
ALICE
Hello.
""")
        assert len(panels["1"].script) == 1

    def test_directives_set_camera_properties(self):
        panels = parse_script("""
---
cast: {A: {reference: alice}}
---
PANEL 1
@shot: close_up
@angle: low
""")
        assert panels["1"].camera.shot is ShotType.CLOSE_UP

    def test_page_headings_leave_unrepeated_panel_names_alone(self):
        """Pages only qualify a panel's name when its number repeats, so a script that
        numbers panels straight through keeps the names it always had."""
        panels = parse_script("""
---
cast: {A: {reference: alice}}
---
PAGE ONE
PANEL 1
PAGE TWO
PANEL 2
""")
        assert list(panels) == ["1", "2"]

    def test_content_before_the_first_panel_is_rejected(self):
        with pytest.raises(ScriptSyntaxError, match="before the first PANEL"):
            parse_script("---\ncast: {A: {reference: alice}}\n---\nstray text\nPANEL 1\n")

    def test_a_script_with_no_panels_is_rejected(self):
        with pytest.raises(ScriptSyntaxError, match="no PANEL headings"):
            parse_script("---\ncast: {}\n---\n")

    def test_leading_blank_lines_do_not_break_front_matter(self):
        """A script pasted out of an editor very often starts with a blank line, and
        failing on that would look identical to a working file."""
        panels = parse_script("\n\n---\ncast: {A: {reference: alice}}\n---\nPANEL 1\n")
        assert list(panels) == ["1"]

    @pytest.mark.parametrize(
        ("text", "line"),
        [
            # No front matter: the body is the file.
            ("\n\nstray prose\nPANEL 1\n", 3),
            # Front matter occupies lines 1-4, so the stray line is the file's line 6.
            ("---\ncast: {A: {reference: alice}}\nscene: x\n---\n\nstray prose\nPANEL 1\n", 6),
            # Blank lines before the opening fence count too.
            ("\n\n---\ncast: {A: {reference: alice}}\n---\nstray prose\nPANEL 1\n", 6),
        ],
        ids=["no-front-matter", "after-front-matter", "after-leading-blank-lines"],
    )
    def test_a_line_number_counts_from_the_top_of_the_file(self, text: str, line: int):
        """Not from the end of the front matter: an editor jumping to "line 2" of a
        script whose first five lines are YAML lands on the cast, not the fault."""
        with pytest.raises(ScriptSyntaxError, match=f"line {line}:") as caught:
            parse_script(text)
        assert caught.value.line == line

    def test_a_directive_fault_is_located_in_the_file(self):
        text = "---\ncast: {A: {reference: alice}}\n---\nPANEL 1\n@weather: [unclosed\n"
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(text)
        assert caught.value.line == 5

    def test_a_panel_that_does_not_validate_is_located_at_its_heading(self):
        """It used to carry no line at all, so `scenet check` pointed at line 1 -- the
        front-matter fence -- whichever panel was wrong."""
        text = (
            "---\ncast: {A: {reference: alice}}\n---\n"
            "PANEL 1\nA\nHello.\n\n"
            "PANEL 2\n@shot: extremely_wide\n"
        )
        with pytest.raises(ScriptSyntaxError, match="in PANEL 2") as caught:
            parse_script(text)
        assert caught.value.line == 8

    def test_shipped_script_example_parses(self):
        panels = load_script(EXAMPLES / "umbrella.script")
        assert list(panels) == ["1", "2"]
        assert [event.kind for event in panels["2"].script] == [
            BalloonKind.WHISPER,
            BalloonKind.SHOUT,
        ]


class TestNothingTypedIsLost:
    """Three ways a script used to drop what its writer typed, without a word (#63).

    Each was silent: no error, no note, no `scenet check` finding. A writer found out by
    counting balloons.
    """

    # Five lines, so the body starts on line 6 of the file.
    CAST = "---\ncast:\n  ALICE: {reference: alice}\n  BOB: {reference: bob}\n---\n"

    def test_panel_numbers_restarting_on_each_page_keep_every_panel(self):
        """Publishers number panels per page -- Dark Horse's script format guide heads
        each page `PAGE ONE` and starts again at `Panel 1.`. Keyed by number alone, the
        second page's PANEL 1 replaced the first page's."""
        panels = parse_script(
            self.CAST + "PAGE ONE\n\nPANEL 1\nALICE\nFirst.\n\nPANEL 2\nBOB\nSecond.\n\n"
            "PAGE TWO\n\nPANEL 1\nALICE\nThird.\n"
        )
        assert list(panels) == ["1-1", "1-2", "2-1"]
        assert [panel.script[0].text for panel in panels.values()] == [
            "First.",
            "Second.",
            "Third.",
        ]

    @pytest.mark.parametrize(
        ("heading", "label"),
        [
            ("PAGE TWO", "2"),
            ("Page Two", "2"),
            ("PAGE TWENTY-ONE", "21"),
            ("PAGE 7", "7"),
            ("PAGE 07", "7"),
            ("PAGE 3A", "3A"),
        ],
    )
    def test_a_page_is_named_as_written_with_number_words_as_digits(self, heading: str, label: str):
        """So an excerpt that starts at page 7 names its panels from page 7, and a script
        that spells its pages out still gets `2-1` rather than `TWO-1`."""
        panels = parse_script(self.CAST + f"PAGE ONE\nPANEL 1\n{heading}\nPANEL 1\n")
        assert list(panels) == ["1-1", f"{label}-1"]

    def test_a_panel_repeated_on_one_page_is_reported_where_it_repeats(self):
        with pytest.raises(ScriptSyntaxError, match="PANEL 1") as caught:
            parse_script(self.CAST + "PAGE ONE\nPANEL 1\nPANEL 1\n")
        assert caught.value.rule == "duplicate-panel"
        assert caught.value.line == 8

    def test_a_repeated_panel_with_no_page_headings_is_reported(self):
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(self.CAST + "PANEL 1\nALICE\nHi.\n\nPANEL 1\nBOB\nHi.\n")
        assert caught.value.rule == "duplicate-panel"
        assert caught.value.line == 10

    def test_a_panel_before_the_first_page_cannot_be_told_apart(self):
        """Once numbers repeat, every panel is named by its page. One that comes before
        any PAGE heading has no page to be named by, so it is reported rather than
        guessed at."""
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(self.CAST + "PANEL 1\nPAGE TWO\nPANEL 1\n")
        assert caught.value.rule == "duplicate-panel"

    def test_dialogue_runs_on_until_a_blank_line(self):
        """Writers wrap long speeches by hand, and so do models writing a script. The
        second line used to be filed as prose and thrown away."""
        panels = parse_script(
            self.CAST + "PANEL 1\nALICE\nFirst line of dialogue,\nand a second line.\n"
            "\nThe rain keeps falling.\n"
        )
        (speech,) = panels["1"].script
        assert speech.text == "First line of dialogue, and a second line."

    def test_a_cue_caption_or_directive_still_ends_a_speech(self):
        """Back-to-back speeches with no blank line between them already worked, and
        must keep working: a line that looks like a cue starts a new speech."""
        panels = parse_script(
            self.CAST + "PANEL 1\nALICE\nHello.\nBOB (whisper)\nHi.\nCAPTION: Later.\n"
            "@shot: close_up\n"
        )
        first, second, caption = panels["1"].script
        assert (first.text, second.text) == ("Hello.", "Hi.")
        assert isinstance(caption, CaptionEvent)
        assert panels["1"].camera.shot is ShotType.CLOSE_UP

    def test_a_repeated_key_in_the_front_matter_is_reported_on_its_line(self):
        """The cast lives in the front matter, and YAML kept only the last of two
        characters with one name (#83). The line is the file's, not the block's."""
        text = "---\ncast:\n  ALICE: {reference: alice}\n  ALICE: {reference: bob}\n---\nPANEL 1\n"
        with pytest.raises(ScriptSyntaxError, match="ALICE") as caught:
            parse_script(text)
        assert caught.value.rule == "duplicate-key"
        assert caught.value.line == 4

    def test_a_repeated_key_in_a_directive_is_reported_on_its_line(self):
        with pytest.raises(ScriptSyntaxError, match="place") as caught:
            parse_script(self.CAST + "PANEL 1\n@setting: {place: docks, place: street}\n")
        assert caught.value.rule == "duplicate-key"
        assert caught.value.line == 7

    @pytest.mark.parametrize("heading", ["PANEL 1:", "PANEL 1.", "PANEL 1 :", "Panel 1:"])
    def test_punctuation_after_the_number_is_not_part_of_the_name(self, heading: str):
        """`\\S+` took the colon, so the panel was called `1:` and `scenet build` wrote
        `name.1:.svg` -- not a legal file name on Windows."""
        assert list(parse_script(self.CAST + f"{heading}\n")) == ["1"]


class TestFrontendDispatch:
    def test_extension_selects_the_frontend(self):
        """Every frontend produces the same IR, so adding a syntax is one line."""
        assert len(compile_document(EXAMPLES / "umbrella.script")) == 2
        assert len(compile_document(EXAMPLES / "sequence.scene.yaml")) == 3
        assert len(compile_document(EXAMPLES / "duel.panel.yaml")) == 1

    def test_an_unsupported_extension_is_rejected(self, tmp_path: Path):
        stray = tmp_path / "panel.txt"
        stray.write_text("cast: {}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported extension"):
            compile_document(stray)

    def test_the_two_frontends_agree(self):
        """The same panel written as YAML and as script must compile identically --
        that is what makes them frontends onto one language rather than two."""
        common_cast = "{reference: alice, at: left_third}"
        yaml_ir = parse_panel(
            f"camera: {{shot: close_up}}\ncast:\n  A: {common_cast}\n"
            'script:\n  - say: {by: A, text: "Same words."}\n'
        )
        script_ir = parse_script(
            f"---\ncast: {{A: {common_cast}}}\n---\nPANEL 1\n@shot: close_up\nA\nSame words.\n"
        )["1"]
        assert yaml_ir == script_ir


class TestLineEndings:
    """Source arrives as a string, and not every string came from a file.

    Python's text mode normalises CRLF on read, which hides this everywhere the tests
    look. The browser playground does not: it hands over exactly the bytes it was given,
    so a script written by a Windows editor -- or pasted out of one -- reaches the parser
    with CRLF intact. It took running the gallery in a browser to notice.
    """

    SCRIPT = "---\ncast:\n  ALICE: {reference: alice}\n---\n\nPANEL 1\n\nALICE\nHello.\n"

    def test_crlf_script_parses(self):
        panels = parse_script(self.SCRIPT.replace("\n", "\r\n"))
        assert list(panels) == ["1"]
        assert panels["1"].script[0].text == "Hello."

    def test_cr_only_script_parses(self):
        """Classic Mac line endings. Rare, free to support, and free to get wrong."""
        panels = parse_script(self.SCRIPT.replace("\n", "\r"))
        assert list(panels) == ["1"]

    def test_line_endings_do_not_change_the_result(self):
        lf = parse_script(self.SCRIPT)
        crlf = parse_script(self.SCRIPT.replace("\n", "\r\n"))
        assert lf == crlf

    def test_crlf_panel_documents_parse(self):
        """PyYAML already handles this, but nothing said so."""
        source = "cast:\n  a: {reference: alice}\n"
        assert parse_panel(source) == parse_panel(source.replace("\n", "\r\n"))


class TestPanelNamesAreText:
    """A panel's name is text, as a cast member's id is. YAML reads `1:` as a number and
    `null:` as nothing, and a scene mixing one with a named panel could not even sort its
    names: `check` and `build` both ended in a `TypeError` traceback. A page could not
    name such a panel either, since `use:` takes text."""

    MIXED = "cast: {a: {reference: alice}}\npanels:\n  1: {}\n  b: {}\n"

    def test_a_number_beside_a_name_is_one_finding_at_the_number(self):
        (finding,) = diagnose_source(self.MIXED)
        assert finding.rule == "invalid-field"
        assert finding.path == ("panels", 1)
        assert finding.region is not None
        assert finding.region.start.line == 3
        assert "'1'" in finding.message

    def test_build_refuses_it_as_a_syntax_error(self):
        with pytest.raises(PanelSyntaxError, match="panel name"):
            compile_document(self.MIXED)

    def test_every_name_that_is_not_text_is_its_own_finding(self):
        found = diagnose_source("cast: {a: {reference: alice}}\npanels:\n  1: {}\n  2: {}\n")
        assert [(item.rule, item.path) for item in found] == [
            ("invalid-field", ("panels", 1)),
            ("invalid-field", ("panels", 2)),
        ]

    def test_a_null_name_is_refused_too(self):
        (finding,) = diagnose_source(
            "cast: {a: {reference: alice}}\npanels:\n  null: {}\n  b: {}\n"
        )
        assert finding.rule == "invalid-field"

    def test_a_quoted_number_is_a_name(self):
        assert diagnose_source("cast: {a: {reference: alice}}\npanels:\n  '1': {}\n  b: {}\n") == []
