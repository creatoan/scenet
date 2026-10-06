"""Pages: panels laid out in tiers (#66).

A page decides the size of each panel's frame; each panel is still compiled on its own,
inside that frame, exactly as it would be alone at that size. That keeps the property the
whole pipeline rests on -- a panel's composition does not depend on what sits beside it --
while letting a page be designed as a page.
"""

import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scenet.cli import main
from scenet.core import PageCore
from scenet.diagnostics import diagnose_source
from scenet.emit.page import render_page, render_pages
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_scene, parse_scene_document
from scenet.ir import PanelSpec
from scenet.pipeline import compile_book, compile_ir
from scenet.solve.balloons import FONT_SIZE_FRACTION

SVG = "{http://www.w3.org/2000/svg}"

# Usable area 1080 x 1680. Two tiers weighted 1 and 3 share 1680 - 40 = 1640, so they are
# 410 and 1230 tall; the first tier's 1080 - 30 = 1050 is split 1 : 2.
SCENE = """\
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - {height: 1, panels: [wide, {use: tall, width: 2}]}
      - {height: 3, panels: [last]}
panels:
  wide: {camera: {shot: full_shot}, script: [{say: {by: alice, text: "Hello."}}]}
  tall: {over: wide, camera: {shot: medium_shot}}
  last: {over: wide, camera: {shot: close_up}, script: [{say: {by: bob, text: "Hi."}}]}
  unused: {over: wide}
"""


def frames(page: PageCore) -> list[tuple[str, float, float, float, float]]:
    return [(f.panel, f.x, f.y, f.width, f.height) for f in page.frames]


class TestTheLayout:
    def test_frames_follow_the_weights_the_gutters_and_the_margin(self):
        (page,) = compile_book(SCENE).pages
        assert (page.width, page.height) == (1200.0, 1800.0)
        assert frames(page) == [
            ("wide", 60.0, 60.0, 350.0, 410.0),
            ("tall", 440.0, 60.0, 700.0, 410.0),
            ("last", 60.0, 510.0, 1080.0, 1230.0),
        ]

    def test_frames_are_listed_in_reading_order(self):
        """Tier by tier, left to right within a tier: the Z-path, by construction."""
        (page,) = compile_book(SCENE).pages
        assert [f.panel for f in page.frames] == ["wide", "tall", "last"]

    def test_a_page_with_no_format_uses_the_defaults(self):
        source = (
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [one]}]}]\n"
            "panels: {one: {}}\n"
        )
        (page,) = compile_book(source).pages
        assert (page.width, page.height) == (2000.0, 3000.0)
        assert frames(page) == [("one", 100.0, 100.0, 1800.0, 2800.0)]

    def test_several_pages(self):
        source = (
            "cast: {x: {reference: alice}}\n"
            "pages:\n  - tiers: [{panels: [a]}]\n  - tiers: [{panels: [b]}]\n"
            "panels: {a: {}, b: {}}\n"
        )
        first, second = compile_book(source).pages
        assert [f.panel for f in first.frames] == ["a"]
        assert [f.panel for f in second.frames] == ["b"]


class TestPanelsOnAPage:
    def test_a_placed_panel_is_compiled_at_its_frame(self):
        core = compile_book(SCENE).panels["tall"].core
        assert (core.width, core.height) == (700.0, 410.0)

    def test_it_is_exactly_that_panel_compiled_alone_at_that_size(self):
        """The page decides the frame and the type size, and nothing else."""
        book = compile_book(SCENE)
        (page,) = book.pages
        panel = parse_scene(SCENE)["tall"]
        alone = compile_ir(
            panel.model_copy(update={"panel": PanelSpec(size=(700.0, 410.0))}),
            lettering_height=page.lettering_height,
        )
        assert book.panels["tall"].core.to_json() == alone.core.to_json()

    def test_every_panel_on_a_page_letters_at_one_size(self):
        """A short panel and a tall one used to letter at different sizes, since type was
        a fraction of each panel's own height. No letterer does that."""
        book = compile_book(SCENE)
        (page,) = book.pages
        wide = book.panels["wide"].core.balloons[0].font_size
        last = book.panels["last"].core.balloons[0].font_size
        assert wide == last == pytest.approx(page.lettering_height * FONT_SIZE_FRACTION, abs=0.01)

    def test_the_type_size_is_a_third_of_the_usable_height(self):
        (page,) = compile_book(SCENE).pages
        assert page.lettering_height == 560.0

    def test_a_panel_on_no_page_compiles_as_it_always_did(self):
        """A panel may exist only to be inherited from, through `over:`."""
        unused = compile_book(SCENE).panels["unused"].core
        assert (unused.width, unused.height) == (1000.0, 1000.0)
        assert unused.to_json() == compile_ir(parse_scene(SCENE)["unused"]).core.to_json()

    def test_a_scene_without_pages_is_unchanged(self):
        source = "panels: {a: {cast: {x: {reference: alice}}}, b: {over: a}}\n"
        book = compile_book(source)
        assert book.pages == ()
        assert {name: r.core.to_json() for name, r in book.panels.items()} == {
            name: compile_ir(panel).core.to_json() for name, panel in parse_scene(source).items()
        }

    def test_parse_scene_still_returns_only_panels(self):
        assert list(parse_scene(SCENE)) == ["wide", "tall", "last", "unused"]


class TestMistakesArePageLayoutFindings:
    @pytest.mark.parametrize(
        ("source", "said"),
        [
            ("pages: [{tiers: [{panels: [ghost]}]}]\npanels: {one: {}}\n", "ghost"),
            ("pages: [{tiers: [{panels: [one, one]}]}]\npanels: {one: {}}\n", "twice"),
            (
                "pages:\n  - tiers: [{panels: [one]}]\n  - tiers: [{panels: [one]}]\n"
                "panels: {one: {}}\n",
                "twice",
            ),
            ("pages: [{tiers: [{panels: [one]}]}]\ncast: {a: {reference: alice}}\n", "panels"),
            (
                "page: {size: [400, 400], margin: 150, gutter: 200}\n"
                "pages: [{tiers: [{panels: [a, b]}]}]\npanels: {a: {}, b: {}}\n",
                "room",
            ),
        ],
        ids=["unknown-panel", "twice-in-a-tier", "twice-on-two-pages", "no-panels", "no-room"],
    )
    def test_it_is_refused_under_the_page_layout_rule(self, source: str, said: str):
        with pytest.raises(PanelSyntaxError, match=said) as caught:
            parse_scene_document(source)
        assert caught.value.rule == "page-layout"

    def test_a_weight_must_be_positive(self):
        with pytest.raises(PanelSyntaxError):
            parse_scene_document("pages: [{tiers: [{height: 0, panels: [a]}]}]\npanels: {a: {}}\n")

    def test_scenet_check_points_at_the_placement(self):
        source = "pages:\n  - tiers:\n      - panels: [one, ghost]\npanels: {one: {}}\n"
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.region is not None
        assert finding.region.start.line == 3
        assert "ghost" in finding.message


class TestPageCore:
    def test_it_survives_a_json_round_trip(self):
        (page,) = compile_book(SCENE).pages
        assert PageCore.from_json(page.to_json()) == page

    def test_it_is_deterministic(self):
        assert compile_book(SCENE).pages[0].to_json() == compile_book(SCENE).pages[0].to_json()


class TestThePageSvg:
    @pytest.fixture
    def svg(self) -> ElementTree.Element:
        book = compile_book(SCENE)
        cores = {name: result.core for name, result in book.panels.items()}
        return ElementTree.fromstring(render_page(book.pages[0], cores))

    def test_it_is_the_page_size(self, svg: ElementTree.Element):
        assert svg.get("viewBox") == "0 0 1200 1800"

    def test_each_panel_sits_at_its_frame_clipped_to_it(self, svg: ElementTree.Element):
        groups = {
            g.get("id"): g for g in svg.iter(f"{SVG}g") if (g.get("id") or "").startswith("panel-")
        }
        assert list(groups) == ["panel-wide", "panel-tall", "panel-last"]
        assert groups["panel-tall"].get("transform") == "translate(440 60)"
        (clip,) = groups["panel-tall"].findall(f"{SVG}clipPath")
        (rect,) = clip.findall(f"{SVG}rect")
        assert (rect.get("width"), rect.get("height")) == ("700", "410")

    def test_ids_are_unique(self, svg: ElementTree.Element):
        ids = [i for element in svg.iter() if (i := element.get("id")) is not None]
        assert sorted({i for i in ids if ids.count(i) > 1}) == []

    def test_several_pages_side_by_side_keep_ids_unique(self):
        source = (
            "cast: {a: {reference: alice}}\n"
            "pages:\n  - tiers: [{panels: [one]}]\n  - tiers: [{panels: [two]}]\n"
            "panels: {one: {}, two: {}}\n"
        )
        book = compile_book(source)
        cores = {name: result.core for name, result in book.panels.items()}
        for debug in (False, True):
            text = render_pages(book.pages, cores, debug=debug)
            ids = re.findall(r' id="([^"]+)"', text)
            assert sorted({i for i in ids if ids.count(i) > 1}) == []
            assert set(re.findall(r"url\(#([^)]+)\)", text)) <= set(ids)


class TestBuild:
    def test_it_writes_each_page(self, tmp_path: Path):
        source = tmp_path / "story.scene.yaml"
        source.write_text(SCENE, encoding="utf-8")
        assert main(["build", str(source), "--core", "--quiet"]) == 0
        assert (tmp_path / "story.page-1.svg").exists()
        assert (tmp_path / "story.page-1.core.json").exists()
        assert (tmp_path / "story.tall.svg").exists()

    def test_a_page_never_overwrites_a_panel(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        source = tmp_path / "clash.scene.yaml"
        source.write_text(
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [page-1]}]}]\n"
            "panels: {page-1: {}}\n",
            encoding="utf-8",
        )
        assert main(["build", str(source)]) == 2
        assert "page-1" in capsys.readouterr().err
