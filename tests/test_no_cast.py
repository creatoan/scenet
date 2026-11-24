"""A panel may have no cast: establishing shots and inserts (#364).

A comic opens on a place. A panel with nobody in it used to fail with "panel has no cast;
there is nothing to place", with no file, no line and no fix. Now its setting is drawn,
its captions and sounds are placed, and its description says what is shown.

In a comic script, a panel draws who speaks in it and whom its `@cast:` names, and the
panels it is drawn `@over` -- not the whole front matter's cast -- so a panel of
description, captions or sounds only is cast-less.
"""

import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.emit.page import render_page
from scenet.emit.pdf import render_pdf
from scenet.emit.svg import render
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.pipeline import compile_book, compile_source

ESTABLISHING = (
    "panel: {size: [800, 500]}\n"
    "camera: {shot: long_shot}\n"
    "setting: {place: street, time: night, weather: rain}\n"
    "script:\n"
    "  - caption: {kind: locale, text: 'Rue des Martyrs, 2 a.m.'}\n"
    "  - sfx: {text: SHHHH, size: small}\n"
)

#: A scene whose first panel has only a setting and a caption, between ordinary ones.
SCENE = (
    "panel: {size: [700, 500]}\n"
    "panels:\n"
    "  - id: street\n"
    "    camera: {shot: long_shot}\n"
    "    setting: {place: street, time: night}\n"
    "    script: [{caption: {kind: locale, text: 'Night, the street.'}}]\n"
    "  - id: talk\n"
    "    cast: [{id: alice, reference: alice, at: left_third}]\n"
    "    script: [{say: {by: alice, text: 'Anyone there?'}}]\n"
    "  - id: empty\n"
    "    setting: {place: street, time: night}\n"
    "    script: [{say: {by: voice, text: 'Over here.', off_panel: right}}]\n"
    "  - id: answer\n"
    "    cast: [{id: alice, reference: alice}]\n"
    "    script: [{say: {by: alice, text: 'Who said that?'}}]\n"
    "pages:\n"
    "  - tiers:\n"
    "      - panels: [street, talk]\n"
    "      - panels: [empty, answer]\n"
)


class TestAPanelWithNobody:
    def test_it_compiles(self):
        core = compile_source(ESTABLISHING).core
        assert core.actors == ()
        assert core.camera is None
        assert [" ".join(caption.lines) for caption in core.captions] == ["Rue des Martyrs, 2 a.m."]
        assert core.sfx

    def test_its_setting_is_drawn(self):
        result = compile_source(ESTABLISHING)
        assert result.core.backdrop is not None
        assert result.core.backdrop.masses

    def test_it_renders_to_svg_and_pdf(self):
        result = compile_source(ESTABLISHING)
        assert ElementTree.fromstring(render(result.core))
        book = compile_book(SCENE)
        cores = {name: panel.core for name, panel in book.panels.items()}
        assert render_pdf(book.pages, cores).startswith(b"%PDF-")
        assert ElementTree.fromstring(render_page(book.pages[0], cores))

    def test_its_description_says_what_is_shown(self):
        core = compile_source(ESTABLISHING).core
        assert core.description is not None
        assert core.description.startswith("Long shot. ")
        assert "night" in core.description
        assert "rain" in core.description

    def test_check_finds_nothing(self):
        assert diagnose_source(ESTABLISHING) == []
        assert diagnose_source(ESTABLISHING, deep=True) == []

    def test_an_empty_cast_is_no_cast(self):
        assert compile_source("cast: {}\nsetting: {place: docks}\n").core.actors == ()
        assert compile_source("cast: []\nsetting: {place: docks}\n").core.actors == ()


class TestLinesInIt:
    def test_a_line_needs_off_panel(self):
        with pytest.raises(PanelSyntaxError) as caught:
            compile_source("script: [{say: {by: carol, text: 'Hello?'}}]\n")
        assert caught.value.rule == "unknown-actor"
        (found,) = diagnose_source("script: [{say: {by: carol, text: 'Hello?'}}]\n")
        assert found.rule == "unknown-actor"

    def test_a_line_from_off_panel_is_lettered(self):
        core = compile_source(
            "script: [{say: {by: carol, text: 'Hello?', off_panel: left}}]\n"
        ).core
        assert [balloon.lines for balloon in core.balloons] == [("Hello?",)]


class TestBetweenOrdinaryPanels:
    def test_the_page_reads_in_order(self):
        book = compile_book(SCENE)
        assert list(book.panels) == ["street", "talk", "empty", "answer"]
        (page,) = book.pages
        assert [frame.panel for frame in page.frames] == ["street", "talk", "empty", "answer"]

    def test_balloons_are_placed_in_each(self):
        book = compile_book(SCENE)
        assert book.panels["street"].core.captions
        assert book.panels["empty"].core.balloons
        assert book.panels["talk"].core.balloons
        assert book.panels["empty"].core.actors == ()

    def test_check_finds_nothing(self):
        assert diagnose_source(SCENE, deep=True) == []


class TestAScript:
    FRONT = "---\ncast:\n  ALICE: {reference: alice}\n  BOB: {reference: bob}\n---\n"
    CAROL = "  CAROL: {reference: alice}\n"
    WITH_CAROL = FRONT.removesuffix("---\n") + CAROL + "---\n"

    def _cast(self, body: str) -> dict[str, list[str]]:
        panels = parse_script(self.FRONT + body)
        return {name: list(panel.cast) for name, panel in panels.items()}

    def test_a_panel_of_description_and_captions_is_cast_less(self):
        body = "PANEL 1\nA street at night, in the rain.\nCAPTION: Later.\n"
        assert self._cast(body) == {"1": []}
        assert diagnose_script(self.FRONT + body) == []

    def test_a_panel_draws_who_speaks_in_it(self):
        body = "PANEL 1\nALICE\nHi.\n\nPANEL 2\nBOB\nHello.\n"
        assert self._cast(body) == {"1": ["ALICE"], "2": ["BOB"]}

    def test_a_silent_panel_draws_whom_its_cast_names(self):
        body = "PANEL 1\nMaya runs.\n@cast: {ALICE: {pose: pointing}}\n"
        assert self._cast(body) == {"1": ["ALICE"]}

    def test_a_panel_over_another_draws_whom_it_drew(self):
        body = "PANEL 1\nALICE\nHi.\n\nPANEL 2\n@over: 1\nSFX: BANG\n"
        assert self._cast(body) == {"1": ["ALICE"], "2": ["ALICE"]}

    def test_a_voice_from_off_panel_is_not_drawn(self):
        body = "PANEL 1\nBOB (OP)\nWho's there?\n"
        assert self._cast(body) == {"1": []}

    def test_a_panel_draws_whom_its_staging_names_beside_who_speaks(self):
        body = "PANEL 1\n@staging: [ALICE left_of BOB]\nCAROL\nHi.\n"
        panels = parse_script(self.WITH_CAROL + body)
        assert list(panels["1"].cast) == ["ALICE", "BOB", "CAROL"]

    def test_a_staging_relation_written_as_a_mapping_names_both(self):
        body = "PANEL 1\nA room.\n@staging: [{subject: ALICE, predicate: left_of, object: BOB}]\n"
        assert self._cast(body) == {"1": ["ALICE", "BOB"]}

    def test_a_panel_over_one_over_another_draws_whom_the_first_drew(self):
        body = (
            "PANEL 1\n@cast: {BOB: {}}\nALICE\nHi.\n\n"
            "PANEL 2\n@over: 1\nA beat.\n\nPANEL 3\n@over: 2\nA beat.\n"
        )
        assert self._cast(body)["3"] == ["ALICE", "BOB"]

    @pytest.mark.parametrize(
        ("body", "said"),
        [
            (
                "PANEL 1\n@over: 2\nALICE\nHi.\n\nPANEL 2\n@over: 1\nBOB\nHi.\n",
                "'over' chain is cyclic: 1 -> 2 -> 1",
            ),
            ("PANEL 1\n@over: 9\nALICE\nHi.\n", "panel '1' is over '9', which does not exist"),
        ],
        ids=["a-cycle", "no-such-panel"],
    )
    def test_an_over_that_draws_nobody_is_a_composition_fault(self, body: str, said: str):
        with pytest.raises(ScriptSyntaxError, match=re.escape(said)) as caught:
            parse_script(self.FRONT + body)
        assert caught.value.rule == "composition"

    def test_a_member_no_panel_draws_is_checked_where_it_is_written(self):
        """In the front matter, once: no panel draws them, so no panel checks them."""
        script = (
            self.WITH_CAROL.replace(
                "CAROL: {reference: alice}", "CAROL: {reference: alice, marks: [plewds, plewds]}"
            )
            + "PANEL 1\nALICE\nHi.\n"
        )
        said = "line 5: in the front matter, at cast.CAROL.marks: mark listed more than once"
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(script, source=Path("x.script.md"))
        error = caught.value
        assert (error.rule, error.line, error.source) == ("invalid-field", 5, Path("x.script.md"))
        assert said in str(error)
        (found,) = diagnose_script(script)
        assert found.message.startswith(said)
        assert found.region is not None
        assert found.region.start.line == 5

    def test_front_matter_staging_keeps_what_names_only_who_is_drawn(self):
        staging = "staging: [ALICE left_of BOB, ALICE left_of CAROL]\n"
        front = self.WITH_CAROL.removesuffix("---\n") + staging + "---\n"
        panels = parse_script(front + "PANEL 1\nALICE\nHi.\nBOB\nHey.\n")
        ((subject, predicate, object_),) = [
            (relation.subject, relation.predicate.value, relation.object)
            for relation in panels["1"].staging
        ]
        assert (subject, predicate, object_) == ("ALICE", "left_of", "BOB")

    def test_front_matter_staging_keeps_to_who_is_drawn(self):
        front = (
            "---\ncast:\n  ALICE: {reference: alice}\n  BOB: {reference: bob}\n"
            "staging: [ALICE left_of BOB]\n---\n"
        )
        panels = parse_script(front + "PANEL 1\nALICE\nHi.\n\nPANEL 2\nALICE\nHi.\nBOB\nHey.\n")
        assert panels["1"].staging == ()
        assert len(panels["2"].staging) == 1
