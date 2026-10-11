"""Type size: the one lettering measurement an author sets.

Balloon type has always been a fixed fraction of the height the panel letters against:
3.5% for dialogue and 3% for captions, of the panel's own height alone and of one tier of
a three-tier page on a page. That is a good default and a bad only choice. A page set in
tight panels wants smaller type, a children's comic larger, and neither is a layout
decision the compiler should be guessing.

`lettering: {size: N}` sets the dialogue size in panel units -- the same abstract units as
`panel.size` and `page.size`, which on a page are one unit, since a panel there is
compiled at its frame's size. Captions keep their proportion to it. Set beside `panels:`
it is a default every panel inherits, which is how a page letters at one size the author
chose; set on one panel, it letters that panel alone.

What these tests pin down: the number reaches measurement exactly, captions follow it,
the page's own type size yields to it, and nothing changes for a document that does not
say it.
"""

from pathlib import Path

import pytest

from scenet.diagnostics import diagnose_source
from scenet.emit.svg import render
from scenet.errors import BalloonPlacementError, PanelSyntaxError
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_panel
from scenet.pipeline import compile_book, compile_source
from scenet.solve.balloons import CAPTION_FONT_SIZE_FRACTION, FONT_SIZE_FRACTION
from tests.invariants import assert_svg_is_sound

CAST = "cast: {alice: {reference: alice}}\n"
SCRIPT = "script:\n  - caption: {text: Later.}\n  - say: {by: alice, text: Hello.}\n"
CAPTION_RATIO = CAPTION_FONT_SIZE_FRACTION / FONT_SIZE_FRACTION


def _sizes(source: str) -> tuple[float, float]:
    """The dialogue and caption type sizes a one-panel document letters at."""
    core = compile_source(source).core
    return core.balloons[0].font_size, core.captions[0].font_size


class TestTheDefault:
    def test_a_panel_that_says_nothing_letters_as_it_always_did(self):
        dialogue, caption = _sizes(f"panel: {{size: [1000, 800]}}\n{CAST}{SCRIPT}")
        assert dialogue == pytest.approx(800 * FONT_SIZE_FRACTION)
        assert caption == pytest.approx(800 * CAPTION_FONT_SIZE_FRACTION)

    def test_the_language_has_the_key(self):
        assert parse_panel("{}").lettering.size is None


class TestSettingIt:
    def test_the_dialogue_is_set_at_exactly_that_size(self):
        dialogue, _ = _sizes(f"lettering: {{size: 30}}\n{CAST}{SCRIPT}")
        assert dialogue == 30.0

    def test_captions_keep_their_proportion_to_it(self):
        _, caption = _sizes(f"lettering: {{size: 30}}\n{CAST}{SCRIPT}")
        assert caption == pytest.approx(30 * CAPTION_RATIO, abs=0.01)

    def test_it_does_not_depend_on_the_panel_height(self):
        short = _sizes(f"panel: {{size: [1000, 600]}}\nlettering: {{size: 30}}\n{CAST}{SCRIPT}")
        tall = _sizes(f"panel: {{size: [1000, 1200]}}\nlettering: {{size: 30}}\n{CAST}{SCRIPT}")
        assert short == tall

    def test_larger_type_makes_a_larger_balloon(self):
        small = compile_source(f"lettering: {{size: 24}}\n{CAST}{SCRIPT}").core.balloons[0]
        large = compile_source(f"lettering: {{size: 48}}\n{CAST}{SCRIPT}").core.balloons[0]
        assert large.box.width > small.box.width
        assert large.box.height > small.box.height

    def test_the_drawing_is_at_the_size_measured(self):
        core = compile_source(f"lettering: {{size: 30}}\n{CAST}{SCRIPT}").core
        sizes = [core.balloons[0].font_size, core.captions[0].font_size]
        assert_svg_is_sound(render(core), size=(core.width, core.height), font_sizes=sizes)
        assert_svg_is_sound(
            render(core, live_text=True), size=(core.width, core.height), font_sizes=sizes
        )

    def test_type_too_large_for_the_panel_has_nowhere_to_go(self):
        with pytest.raises(BalloonPlacementError):
            compile_source(f"lettering: {{size: 400}}\n{CAST}{SCRIPT}")


class TestOnAPage:
    PAGE = (
        "pages: [{tiers: [{panels: [wide]}, {height: 2, panels: [tall]}]}]\n"
        "panels:\n"
        "  wide: {cast: {a: {reference: alice}}, script: [{say: {by: a, text: Hi.}}]}\n"
        "  tall: {cast: {b: {reference: bob}}, script: [{say: {by: b, text: Hi.}}]}\n"
    )

    def test_set_beside_the_panels_it_letters_every_panel_on_the_page(self):
        book = compile_book(f"lettering: {{size: 40}}\n{self.PAGE}")
        sizes = {name: result.core.balloons[0].font_size for name, result in book.panels.items()}
        assert sizes == {"wide": 40.0, "tall": 40.0}

    def test_it_takes_the_place_of_the_pages_own_type_size(self):
        default = compile_book(self.PAGE)
        page_size = default.pages[0].lettering_height * FONT_SIZE_FRACTION
        assert default.panels["wide"].core.balloons[0].font_size == pytest.approx(
            page_size, abs=0.01
        )
        assert page_size != pytest.approx(40.0)

    def test_set_on_one_panel_it_letters_that_panel_alone(self):
        source = self.PAGE.replace("wide: {cast", "wide: {lettering: {size: 40}, cast")
        book = compile_book(source)
        assert book.panels["wide"].core.balloons[0].font_size == 40.0
        assert book.panels["tall"].core.balloons[0].font_size != 40.0

    def test_a_panel_inherits_it_through_over(self):
        source = (
            "panels:\n"
            "  first: {lettering: {size: 40}, cast: {a: {reference: alice}},"
            " script: [{say: {by: a, text: Hi.}}]}\n"
            "  second: {over: first}\n"
        )
        book = compile_book(source)
        assert book.panels["second"].core.balloons[0].font_size == 40.0


class TestInAComicScript:
    SCRIPT = "PANEL 1\n\nALICE\nHello.\n\nPANEL 2\n{directive}\nALICE\nAgain.\n"

    def test_front_matter_sets_it_for_every_panel(self):
        text = "---\ncast: {ALICE: {reference: alice}}\nlettering: {size: 30}\n---\n"
        panels = parse_script(text + self.SCRIPT.format(directive=""))
        assert [panel.lettering.size for panel in panels.values()] == [30.0, 30.0]

    def test_a_directive_sets_it_for_one_panel(self):
        text = "---\ncast: {ALICE: {reference: alice}}\n---\n"
        panels = parse_script(text + self.SCRIPT.format(directive="@lettering: {size: 30}"))
        assert [panel.lettering.size for panel in panels.values()] == [None, 30.0]


class TestMistakes:
    @pytest.mark.parametrize("size", ["0", "-12", ".nan", "big"])
    def test_a_size_must_be_a_positive_number(self, size: str):
        with pytest.raises(PanelSyntaxError, match=r"lettering\.size"):
            parse_panel(f"lettering: {{size: {size}}}")

    def test_a_bad_size_is_a_located_finding(self):
        source = f"lettering: {{size: 0}}\n{CAST}"
        (found,) = diagnose_source(source, source=Path("size.panel.yaml"))
        assert found.rule == "invalid-field"
        assert found.path == ("lettering", "size")

    def test_an_unknown_key_is_refused(self):
        (found,) = diagnose_source(f"lettering: {{sise: 30}}\n{CAST}")
        assert found.rule == "unknown-key"
        assert found.path == ("lettering", "sise")
