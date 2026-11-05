"""Panels that bleed past the trim (#281): the key, their frames, staging and lettering.

A page placement may write `bleed: true`, for every side of its frame that reaches the page's
margin, or `bleed: [top, left]`, for those sides. A bleeding panel's frame runs out to the
bleed line on those sides. Three boxes follow from that: the **bled frame**, which is the
panel's size and what its art covers; the **visible frame**, out to the trim, where its cast
is staged and framed, so the trim never cuts a shot; and its **lettering box**, the frame as it
was before bleeding and inset by the panel's margin, so the page margin stays the live area.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from scenet.core import Box
from scenet.emit.pdf import print_notes
from scenet.errors import PanelSyntaxError, RuleViolationError
from scenet.frontends.yaml_front import parse_scene, parse_scene_document
from scenet.geom import BBox
from scenet.ir import Direction, PageFormat, PageSpec, PanelPlacement, PanelSpec, Side, StackedPanel
from scenet.pipeline import Book, compile_book, compile_ir
from scenet.schema import scene_schema
from scenet.solve.page import Frame, resolve_frames
from tests.invariants import (
    assert_effects_are_placed,
    assert_frames_are_placed,
    assert_lettering_is_placed,
)

# Usable area 1080 x 1680: `wide` is the top-left corner panel, `tall` the top-right one,
# `last` fills the bottom tier. The bleed adds 30 past the trim.
FORMAT = PageFormat(size=(1200, 1800), margin=60, gutter=30, tier_gutter=40, bleed=30)
SCENE = """\
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40, bleed: 30}
setting: {place: street, time: day}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - {height: 1, panels: [{use: wide, bleed: true}, {use: tall, width: 2}]}
      - {height: 3, panels: [{use: last, bleed: true}]}
panels:
  wide: {camera: {shot: full_shot}, script: [{say: {by: alice, text: "Hello."}}]}
  tall: {over: wide, camera: {shot: medium_shot}}
  last:
    over: wide
    camera: {shot: full_shot}
    script:
      - say: {by: bob, text: "Hi."}
      - sfx: {text: BANG, prefer: bottom_left}
"""
#: The same document with nothing bleeding.
PLAIN = SCENE.replace("{use: wide, bleed: true}", "wide").replace(
    "{use: last, bleed: true}", "last"
)


def _page(**bleeds: object) -> PageSpec:
    """The page `SCENE` lays out, each named panel bleeding as given."""

    def placed(name: str, **extra: object) -> dict[str, object]:
        entry: dict[str, object] = {"use": name, **extra}
        if name in bleeds:
            entry["bleed"] = bleeds[name]
        return entry

    return PageSpec.model_validate(
        {
            "tiers": [
                {"height": 1, "panels": [placed("wide"), placed("tall", width=2)]},
                {"height": 3, "panels": [placed("last")]},
            ]
        }
    )


def _frames(page: PageSpec, *, direction: Direction = Direction.LTR) -> dict[str, Frame]:
    return {frame.panel: frame for frame in resolve_frames(FORMAT, page, direction=direction)}


class TestTheKey:
    def test_true_or_a_list_of_sides(self):
        assert PanelPlacement.model_validate({"use": "a", "bleed": True}).bleed is True
        listed = PanelPlacement.model_validate({"use": "a", "bleed": ["top", "left"]})
        assert listed.bleed == (Side.TOP, Side.LEFT)
        assert StackedPanel.model_validate({"use": "a", "bleed": ["right"]}).bleed == (Side.RIGHT,)

    def test_nothing_bleeds_unless_it_says_so(self):
        assert PanelPlacement(use="a").bleed is False
        assert StackedPanel(use="a").bleed is False

    def test_an_unknown_side_is_refused(self):
        with pytest.raises(ValidationError):
            PanelPlacement.model_validate({"use": "a", "bleed": ["middle"]})

    def test_an_inset_cannot_bleed(self):
        """An inset sits a gutter inside its parent, so it reaches no edge to bleed past."""
        with pytest.raises(ValidationError, match="bleed"):
            PanelPlacement.model_validate(
                {"use": "a", "insets": [{"use": "b", "at": "top_left", "size": 0.3, "bleed": True}]}
            )

    def test_the_schema_offers_it(self):
        """A placement is a panel's name or a mapping; the mapping takes `bleed`."""
        definitions = scene_schema()["$defs"]
        for name in ("PanelPlacement", "StackedPanel"):
            (written,) = [
                branch for branch in definitions[name]["anyOf"] if branch.get("type") == "object"
            ]
            assert "bleed" in written["properties"], name

    def test_a_side_that_cannot_bleed_is_located(self):
        """`scenet check` names the placement's `bleed`, as it does any page-layout finding."""
        text = SCENE.replace("{use: tall, width: 2}", "{use: tall, width: 2, bleed: [left]}")
        with pytest.raises(PanelSyntaxError, match="left") as caught:
            compile_book(text)
        assert caught.value.rule == "page-layout"
        assert tuple(caught.value.loc or ()) == ("pages", 0, "tiers", 0, "panels", 1, "bleed")


class TestTheFrames:
    def test_true_bleeds_on_every_side_that_reaches_the_margin(self):
        wide = _frames(_page(wide=True))["wide"]
        assert (wide.x, wide.y, wide.width, wide.height) == (-30.0, -30.0, 440.0, 500.0)
        assert wide.bleed == (Side.LEFT, Side.TOP)
        assert wide.visible == BBox(0.0, 0.0, 410.0, 470.0)
        assert wide.live == BBox(60.0, 60.0, 350.0, 410.0)

    def test_a_listed_side_bleeds_and_no_other(self):
        last = _frames(_page(last=["bottom"]))["last"]
        assert (last.x, last.y, last.width, last.height) == (60.0, 510.0, 1080.0, 1320.0)
        assert last.bleed == (Side.BOTTOM,)
        assert last.visible == BBox(60.0, 510.0, 1080.0, 1290.0)

    def test_an_empty_list_bleeds_nowhere(self):
        assert _frames(_page(last=[])) == _frames(_page())

    def test_a_panel_that_does_not_bleed_is_as_it_was(self):
        plain = _frames(_page())
        bled = _frames(_page(wide=True))
        assert bled["tall"] == plain["tall"]
        assert bled["tall"].bleed == ()
        assert bled["tall"].visible is None
        assert bled["tall"].live is None

    def test_a_side_that_does_not_reach_the_margin_is_refused(self):
        with pytest.raises(RuleViolationError, match="left") as caught:
            _frames(_page(tall=["left"]))
        assert caught.value.rule == "page-layout"

    def test_a_panel_that_reaches_no_edge_cannot_bleed(self):
        rows = [["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]]
        tiers: list[dict[str, Any]] = [
            {"panels": [{"use": name, "bleed": name == "e"} for name in row]} for row in rows
        ]
        with pytest.raises(RuleViolationError, match="'e'") as caught:
            _frames(PageSpec.model_validate({"tiers": tiers}))
        assert caught.value.rule == "page-layout"

    def test_an_inset_of_a_bleeding_panel_stays_where_it_was(self):
        def page(bleed: bool) -> PageSpec:
            inset = {"use": "small", "at": "top_left", "size": 0.3}
            big = {"use": "big", "insets": [inset], "bleed": bleed}
            return PageSpec.model_validate({"tiers": [{"panels": [big]}]})

        plain = _frames(page(False))
        bled = _frames(page(True))
        assert bled["small"] == plain["small"]
        assert bled["big"].width == plain["big"].width + 2 * 90

    def test_a_slanted_tiers_outline_runs_out_too(self):
        def page(bleed: list[str]) -> PageSpec:
            panels = [{"use": "a", "bleed": bleed}, {"use": "b"}]
            return PageSpec.model_validate({"tiers": [{"slant": 10, "panels": panels}]})

        plain = _frames(page([]))
        a = _frames(page(["left", "top"]))["a"]
        assert a.outline is not None
        assert plain["a"].outline is not None
        assert a.outline[0] == (-30.0, -30.0)
        assert a.outline[3][0] == -30.0
        assert a.outline[1] == (plain["a"].outline[1][0], -30.0)
        assert a.x == -30.0

    def test_a_stacked_panel_bleeds(self):
        stack = {"panels": [{"use": "a", "bleed": True}, {"use": "b"}]}
        beside = {"panels": [{"use": "c"}]}
        page = PageSpec.model_validate({"tiers": [{"columns": [stack, beside]}]})
        assert _frames(page)["a"].bleed == (Side.LEFT, Side.TOP)

    def test_sides_are_the_pages_whichever_way_it_is_read(self):
        """Right to left, the first panel of a tier is at the right: its left side is a
        gutter, so it cannot bleed there."""
        with pytest.raises(RuleViolationError, match="left"):
            _frames(_page(wide=["left"]), direction=Direction.RTL)
        rtl = _frames(_page(wide=["right"]), direction=Direction.RTL)
        assert rtl["wide"].bleed == (Side.RIGHT,)


@pytest.fixture(scope="module")
def book() -> Book:
    return compile_book(SCENE)


class TestTheCompiledPanel:
    def test_it_is_compiled_at_its_bled_frame(self, book: Book):
        assert (book.panels["wide"].core.width, book.panels["wide"].core.height) == (440.0, 500.0)

    def test_it_records_its_open_sides_and_its_lettering_box(self, book: Book):
        core = book.panels["wide"].core
        assert core.open == (Side.LEFT, Side.TOP)
        assert core.lettering == Box(x=90.0, y=90.0, width=350.0, height=410.0)
        (page,) = book.pages
        assert {frame.panel: frame.bleed for frame in page.frames}["wide"] == (Side.LEFT, Side.TOP)

    def test_its_cast_is_staged_in_its_visible_frame(self, book: Book):
        """As the panel alone at the size the reader sees, moved by the bleed.

        `last` reaches the left, right and bottom margins: its visible frame runs to the trim
        on all three, 1200 by 1290, and starts 30 in from its bled frame's left edge.
        """
        (page,) = book.pages
        alone = compile_ir(
            parse_scene(SCENE)["last"].model_copy(
                update={"panel": PanelSpec(size=(1200.0, 1290.0))}
            ),
            lettering_height=page.lettering_height,
        )
        bled = book.panels["last"].core
        assert bled.open == (Side.LEFT, Side.RIGHT, Side.BOTTOM)
        moved = [
            (actor.transform.x - 30.0, actor.transform.y, actor.transform.scale)
            for actor in bled.actors
        ]
        assert moved == [
            pytest.approx((actor.transform.x, actor.transform.y, actor.transform.scale))
            for actor in alone.core.actors
        ]
        assert bled.camera == alone.core.camera

    def test_its_art_covers_the_bleed(self, book: Book):
        core = book.panels["wide"].core
        assert core.backdrop is not None
        right = max(x for mass in core.backdrop.masses for x, _ in mass.polygon)
        bottom = max(y for mass in core.backdrop.masses for _, y in mass.polygon)
        assert (right, bottom) == (core.width, core.height)

    def test_its_lettering_keeps_inside_its_lettering_box(self, book: Book):
        for result in book.panels.values():
            assert_lettering_is_placed(result.core)
            assert_effects_are_placed(result.core)

    def test_the_page_holds_its_frames(self, book: Book):
        (page,) = book.pages
        assert_frames_are_placed(page, margin=60)

    def test_a_panel_that_does_not_bleed_compiles_as_it_did(self, book: Book):
        plain = compile_book(PLAIN)
        assert book.panels["tall"].core.to_json() == plain.panels["tall"].core.to_json()
        assert "open" not in plain.panels["wide"].core.to_json()
        assert "lettering" not in plain.panels["wide"].core.to_json()
        assert '"bleed": [' not in plain.pages[0].to_json()

    def test_the_scene_document_reads_the_key(self):
        layout = parse_scene_document(SCENE).layout
        (page,) = layout.pages
        assert page.tiers[0].panels[0].bleed is True


class TestThePrintNote:
    """A page with no bleed has nothing past the trim for a bleeding panel to run into."""

    def test_a_page_with_no_bleed_is_noted(self):
        book = compile_book(SCENE.replace("bleed: 30}", "bleed: 0}"))
        cores = {name: result.core for name, result in book.panels.items()}
        notes = print_notes(cores, pages=book.pages)
        assert any("page 1" in note and "bleed" in note for note in notes)

    def test_a_page_with_its_bleed_is_not(self, book: Book):
        cores = {name: result.core for name, result in book.panels.items()}
        assert print_notes(cores, pages=book.pages) == []
