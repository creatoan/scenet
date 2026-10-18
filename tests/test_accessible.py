"""Accessible output: a screen reader can read the panel (#76).

Each panel is one image, named with what it shows and then everything said in it, in the
one reading order Panel Core keeps: an explicit `role="img"` named by one `<title>`, its
first child. The words are in the *name*, because a description alone is often not spoken
(Lembree's NVDA and JAWS results; NVDA's own guide) -- and in nothing else, because NVDA
2026.2 with Edge 155, moving by graphic, read a `<desc>` named through `aria-labelledby`
a second time as the description. One title is read once, needs no id, and so cannot be
confused with another panel's in a page that inlines several.

Children of an image are presentational, so nothing inside a panel is named: the panel is
read whole, sound effects in their place in the order whatever order they are painted in.

Lettering stays outlined. `aria=False` is exactly the SVG written before any of this.
"""

from pathlib import Path
from xml.etree import ElementTree

import pytest

from scenet import compile_book, compile_source
from scenet.cli import main
from scenet.core import PanelCore
from scenet.emit.debug_svg import render_debug
from scenet.emit.page import render_page, render_pages
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.pipeline import Book
from tests.invariants import (
    accessible_name,
    assert_accessible,
    assert_svg_is_sound,
    without_access,
)

SVG = "{http://www.w3.org/2000/svg}"

SPOKEN = """\
setting: {place: street, time: night, weather: rain}
cast:
  alice: {reference: alice, pose: pointing, expression: angry, at: left_third}
  bob: {reference: bob, pose: arms_crossed, marks: [plewds], at: right_third, facing: left}
staging: [alice left_of bob, alice looking_at bob]
script:
  - caption: {text: Midnight.}
  - say: {by: alice, text: You forgot your umbrella!}
  - sfx: {text: BLAM, from: bob}
  - say: {by: bob, text: I know., kind: whisper}
"""

SILENT = "cast: {alice: {reference: alice}}\n"

TWO_PAGES = """
cast: {a: {reference: alice}}
script: [{say: {by: a, text: Over here.}}]
page: {size: [1000, 1500]}
pages:
  - tiers: [{panels: [one, two]}]
  - tiers: [{panels: [three]}]
panels: {one: {}, two: {}, three: {}}
"""


@pytest.fixture(scope="module")
def core() -> PanelCore:
    return compile_source(SPOKEN).core


def _root(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


class TestAPanel:
    def test_it_is_one_image(self, core: PanelCore):
        root = _root(render(core))
        assert root.get("role") == "img"

    def test_its_name_is_what_it_shows_then_everything_said_in_order(self, core: PanelCore):
        """The caption, Alice, the sound Bob's side makes, then Bob -- the one order, though
        the sound effect is painted under every balloon."""
        assert accessible_name(_root(render(core))) == (
            "Medium shot. A street at night, in the rain. "
            "Alice, left, pointing, angry, looking at Bob; Bob, right, arms crossed, sweating. "
            "Caption: Midnight. Alice: You forgot your umbrella! "
            "Sound effect, from Bob: BLAM. Bob, whispering: I know."
        )

    def test_it_is_named_by_one_title_its_first_child(self, core: PanelCore):
        children = list(_root(render(core)))
        assert children[0].tag == f"{SVG}title"
        assert (children[0].text or "").startswith(core.description or "")
        assert [child for child in children if child.tag == f"{SVG}title"] == children[:1]

    def test_nothing_is_there_to_be_read_twice(self, core: PanelCore):
        """No `<desc>`, no `aria-labelledby`, no `aria-describedby`: with them, NVDA read
        the words once in the name and again as the description."""
        root = _root(render(core))
        assert root.find(f".//{SVG}desc") is None
        for attribute in ("aria-labelledby", "aria-describedby", "aria-description"):
            assert root.get(attribute) is None
        assert root.find(f"{SVG}title") is not None
        assert root.find(f"{SVG}title").get("id") is None

    def test_it_keeps_every_promise(self, core: PanelCore):
        svg = render(core)
        assert_accessible(svg, core)
        sizes = [item.font_size for item in (*core.balloons, *core.captions, *core.sfx)]
        assert_svg_is_sound(svg, size=(core.width, core.height), font_sizes=sizes)

    def test_the_lettering_is_still_outlines(self, core: PanelCore):
        svg = render(core)
        assert "<text" not in svg
        assert 'id="balloon-b0"' in svg

    def test_live_text_is_inside_the_image_and_so_not_read_twice(self, core: PanelCore):
        root = _root(render(core, live_text=True))
        assert root.get("role") == "img"
        assert root.find(f".//{SVG}text") is not None

    def test_nothing_inside_is_named(self, core: PanelCore):
        """An image's children are presentational: a name in there would never be read."""
        for element in list(_root(render(core)).iter())[1:]:
            assert element.get("role") is None
            assert element.get("aria-label") is None

    def test_words_that_look_like_markup_stay_words(self):
        source = SILENT + 'script: [{say: {by: alice, text: "a < b & \\"c\\" > d"}}]\n'
        root = _root(render(compile_source(source).core))
        assert accessible_name(root).endswith('Alice: a < b & "c" > d.')


class TestInlinedTogether:
    """A page holding several inlined SVGs -- the VS Code preview, any web comic -- has one
    set of ids, and `getElementById` returns the first. A name that needs none cannot be
    taken from the wrong panel."""

    def test_each_panel_is_named_by_its_own_words(self, core: PanelCore):
        other = compile_source(SPOKEN.replace("Midnight.", "Noon.")).core
        body = "".join(render(item).split("\n", 1)[1] for item in (core, other, core))
        page = ElementTree.fromstring(f"<html>{body}</html>")
        names = [accessible_name(svg) for svg in page.findall(f"{SVG}svg")]
        assert names[0] == names[2]
        assert "Caption: Noon." in names[1]
        assert "Caption: Midnight." in names[0]

    def test_a_strip_of_the_same_panel_twice_holds_together(self, core: PanelCore):
        strip = render_strip([("one", core), ("two", core)])
        sizes = [item.font_size for item in (*core.balloons, *core.captions, *core.sfx)]
        assert_svg_is_sound(strip, font_sizes=sizes)


class TestAPanelWithNoWords:
    def test_it_is_named_by_its_description_alone(self):
        root = _root(render(compile_source(SILENT).core))
        assert root.get("role") == "img"
        assert accessible_name(root) == "Medium shot. Alice, centre."

    def test_a_core_without_words_has_no_accessible_markup(self, core: PanelCore):
        """A Core written before descriptions existed: an image with no name is worse than
        none, so it is drawn as it always was."""
        bare = core.model_copy(
            update={
                "description": None,
                "balloons": tuple(b.model_copy(update={"label": None}) for b in core.balloons),
                "captions": tuple(c.model_copy(update={"label": None}) for c in core.captions),
                "sfx": tuple(s.model_copy(update={"label": None}) for s in core.sfx),
            }
        )
        assert render(bare) == render(core, aria=False)


class TestTheOptOut:
    def test_it_writes_none_of_it(self, core: PanelCore):
        svg = render(core, aria=False)
        for written in ("role=", "aria-", "<title", "<desc"):
            assert written not in svg

    def test_it_is_the_accessible_svg_with_that_taken_out(self, core: PanelCore):
        assert render(core, aria=False) == without_access(render(core))
        assert render(core, aria=False, live_text=True) == without_access(
            render(core, live_text=True)
        )

    def test_in_a_strip_and_on_a_page(self, core: PanelCore):
        strip = [("one", core), ("two", core)]
        assert render_strip(strip, aria=False) == without_access(render_strip(strip))
        book = compile_book(TWO_PAGES)
        cores = {name: result.core for name, result in book.panels.items()}
        page = book.pages[0]
        assert render_page(page, cores, aria=False) == without_access(render_page(page, cores))
        assert render_pages(book.pages, cores, aria=False) == without_access(
            render_pages(book.pages, cores)
        )

    def test_from_the_command_line(self, tmp_path: Path):
        source = tmp_path / "spoken.panel.yaml"
        source.write_text(SPOKEN, encoding="utf-8")
        assert main(["build", str(source), "-o", str(tmp_path / "with.svg"), "--quiet"]) == 0
        argv = ["build", str(source), "-o", str(tmp_path / "without.svg"), "--no-aria"]
        assert main([*argv, "--quiet"]) == 0
        with_access = (tmp_path / "with.svg").read_text(encoding="utf-8")
        without = (tmp_path / "without.svg").read_text(encoding="utf-8")
        assert 'role="img"' in with_access
        assert without == without_access(with_access)


@pytest.fixture(scope="module")
def root() -> ElementTree.Element:
    """A strip of a spoken panel and a silent one."""
    one = compile_source(SPOKEN).core
    two = compile_source(SILENT).core
    return _root(render_strip([("one", one), ("two", two)]))


@pytest.fixture(scope="module")
def book() -> Book:
    return compile_book(TWO_PAGES)


class TestAStrip:
    def test_it_is_a_named_group(self, root: ElementTree.Element):
        assert root.get("role") == "group"
        assert accessible_name(root) == "A strip of 2 panels."

    def test_each_panel_is_an_image_in_reading_order(self, root: ElementTree.Element):
        panels = [g for g in root.findall(f"{SVG}g") if (g.get("id") or "").startswith("panel-")]
        assert [g.get("id") for g in panels] == ["panel-one", "panel-two"]
        assert [g.get("role") for g in panels] == ["img", "img"]
        assert accessible_name(panels[0]).endswith("Bob, whispering: I know.")
        assert accessible_name(panels[1]) == "Medium shot. Alice, centre."

    def test_the_background_is_hidden(self, root: ElementTree.Element):
        background = root.find(f"{SVG}rect")
        assert background is not None
        assert background.get("aria-hidden") == "true"

    def test_one_panel_is_a_strip_of_one(self):
        root = _root(render_strip([("one", compile_source(SILENT).core)]))
        assert accessible_name(root) == "A strip of 1 panel."


class TestAPage:
    def test_it_is_a_named_group_of_images(self, book: Book):
        cores = {name: result.core for name, result in book.panels.items()}
        root = _root(render_page(book.pages[0], cores))
        assert root.get("role") == "group"
        assert accessible_name(root) == "A page of 2 panels."
        panels = [g for g in root.findall(f"{SVG}g") if (g.get("id") or "").startswith("panel-")]
        assert [(g.get("id"), g.get("role")) for g in panels] == [
            ("panel-one", "img"),
            ("panel-two", "img"),
        ]

    def test_pages_side_by_side_are_each_a_group(self, book: Book):
        cores = {name: result.core for name, result in book.panels.items()}
        root = _root(render_pages(book.pages, cores))
        assert root.get("role") == "group"
        assert accessible_name(root) == "2 pages."
        pages = [g for g in root.findall(f"{SVG}g") if (g.get("id") or "").startswith("page-")]
        assert [(g.get("role"), accessible_name(g)) for g in pages] == [
            ("group", "Page 1 of 2, 2 panels."),
            ("group", "Page 2 of 2, 1 panel."),
        ]
        # The background, and each page's sheet: shapes of the document's own, outside any
        # panel. What is inside a panel is an image's, and presentational already.
        sheets = [*root.findall(f"{SVG}rect"), *(page.find(f"{SVG}rect") for page in pages)]
        assert [rect.get("aria-hidden") for rect in sheets if rect is not None] == ["true"] * 3

    def test_an_insets_ring_is_hidden(self):
        book = compile_book(
            "cast: {a: {reference: alice}}\npage: {size: [1000, 1500]}\n"
            "pages: [{tiers: [{panels: [{use: one, insets: [{use: two, at: top_left, "
            "size: 0.3}]}]}]}]\npanels: {one: {}, two: {}}\n"
        )
        cores = {name: result.core for name, result in book.panels.items()}
        root = _root(render_page(book.pages[0], cores))
        rings = root.findall(f"{SVG}rect")[1:]
        assert rings
        assert {ring.get("aria-hidden") for ring in rings} == {"true"}


class TestTheOverlay:
    """A diagnostic, not a publication: its labels are live text already."""

    def test_it_says_nothing_more(self, core: PanelCore):
        svg = render_debug(core)
        assert "role=" not in svg
        assert "<title" not in svg

    def test_nor_does_a_strip_or_a_page_of_overlays(self, core: PanelCore):
        assert "role=" not in render_strip([("one", core)], debug=True)
        book = compile_book(TWO_PAGES)
        cores = {name: result.core for name, result in book.panels.items()}
        assert "role=" not in render_page(book.pages[0], cores, debug=True)
        assert "role=" not in render_pages(book.pages, cores, debug=True)
