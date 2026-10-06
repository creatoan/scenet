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
import yaml
from jsonschema import Draft202012Validator

from scenet.cli import main
from scenet.core import PageCore
from scenet.diagnostics import diagnose_source
from scenet.emit.page import render_page, render_pages
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_scene, parse_scene_document
from scenet.ir import PanelSpec
from scenet.pipeline import compile_book, compile_ir
from scenet.schema import scene_schema
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

    def test_a_bad_tier_is_one_finding(self):
        """Not two: pydantic also calls a tuple whose item failed too short, which is no
        fault of its own."""
        source = "pages:\n  - tiers:\n      - {height: 0, panels: [a]}\npanels: {a: {}}\n"
        (finding,) = diagnose_source(source)
        assert finding.path == ("pages", 0, "tiers", 0, "height")

    def test_an_empty_tier_list_is_still_refused(self):
        (finding,) = diagnose_source("pages: [{tiers: []}]\npanels: {a: {}}\n")
        assert finding.path == ("pages", 0, "tiers")

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


# Columns (#67). The second tier is a stack beside a tall panel: Cohn's *blockage*, after
# which about nine readers in ten go down the stack before across (Cohn 2013).
#
# Tiers weighted 1 and 3 share 1640, so the second is 1230 tall from y = 510. Its 1050 of
# width is split 2 : 1 into 700 and 350; the stack's 1230 - 40 = 1190 is split 1 : 2.
COLUMNS = """\
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - panels: [top]
      - height: 3
        columns:
          - {width: 2, panels: [above, {use: below, height: 2}]}
          - {width: 1, panels: [falling]}
panels:
  top: {camera: {shot: full_shot}, script: [{say: {by: alice, text: "Look out!"}}]}
  above: {over: top, camera: {shot: medium_shot}}
  below: {over: top, camera: {shot: close_up}}
  falling: {over: top, camera: {shot: long_shot}}
"""


def columns(*specs: str) -> str:
    """A one-tier page whose tier is the given columns, each a YAML flow mapping."""
    names = sorted(set(re.findall(r"\b[a-z]\b", " ".join(specs))))
    body = ", ".join(f"{name}: {{}}" for name in names)
    return (
        "cast: {x: {reference: alice}}\n"
        f"pages: [{{tiers: [{{columns: [{', '.join(specs)}]}}]}}]\n"
        f"panels: {{{body}}}\n"
    )


class TestColumns:
    def test_frames_split_the_tier_by_column_and_each_column_by_panel(self):
        (page,) = compile_book(COLUMNS).pages
        assert frames(page) == [
            ("top", 60.0, 60.0, 1080.0, 410.0),
            ("above", 60.0, 510.0, 700.0, 396.67),
            ("below", 60.0, 946.67, 700.0, 793.33),
            ("falling", 790.0, 510.0, 350.0, 1230.0),
        ]

    def test_a_stack_is_read_down_before_across(self):
        """The order written is column by column, top to bottom in each: blockage."""
        (page,) = compile_book(COLUMNS).pages
        assert [f.panel for f in page.frames] == ["top", "above", "below", "falling"]

    def test_a_panel_in_a_column_is_compiled_at_its_frame(self):
        core = compile_book(COLUMNS).panels["below"].core
        assert (core.width, core.height) == (700.0, 793.33)

    def test_a_tall_panel_may_come_first(self):
        """Tall, then down the stack: the order the Z-path would give anyway."""
        (page,) = compile_book(columns("{panels: [t]}", "{panels: [a, b]}")).pages
        assert [f.panel for f in page.frames] == ["t", "a", "b"]

    def test_a_stack_between_two_tall_panels(self):
        (page,) = compile_book(columns("{panels: [t]}", "{panels: [a, b]}", "{panels: [u]}")).pages
        assert [f.panel for f in page.frames] == ["t", "a", "b", "u"]

    def test_it_survives_a_json_round_trip(self):
        (page,) = compile_book(COLUMNS).pages
        assert PageCore.from_json(page.to_json()) == page


class TestColumnMistakes:
    @pytest.mark.parametrize(
        ("source", "said"),
        [
            (
                "pages: [{tiers: [{panels: [a], columns: [{panels: [b]}]}]}]\n"
                "panels: {a: {}, b: {}}\n",
                "either",
            ),
            ("pages: [{tiers: [{height: 2}]}]\npanels: {a: {}}\n", "either"),
            (columns("{panels: [a]}", "{panels: [b, a]}"), "twice"),
            (columns("{panels: [a]}", "{panels: [b, ghost]}"), "ghost"),
            # Two stacks side by side are staggered, or a grid; most readers go across
            # those (Cohn 2013), so reading down them would be the wrong order.
            (columns("{panels: [a, b]}", "{panels: [c, d]}"), "across"),
            (columns("{panels: [t]}", "{panels: [a, b]}", "{panels: [c, d]}"), "across"),
            (
                "page: {size: [400, 400], margin: 50, tier_gutter: 300}\n"
                + columns("{panels: [a]}", "{panels: [b, c]}").replace("cast", "cast", 1),
                "room",
            ),
            (
                "page: {size: [400, 400], margin: 50, gutter: 300}\n"
                + columns("{panels: [a]}", "{panels: [b]}"),
                "room",
            ),
        ],
        ids=[
            "panels-and-columns",
            "neither",
            "twice-across-columns",
            "unknown-panel",
            "two-stacks",
            "two-stacks-after-a-tall-one",
            "no-room-in-a-column",
            "no-room-for-columns",
        ],
    )
    def test_it_is_refused_under_the_page_layout_rule(self, source: str, said: str):
        with pytest.raises(PanelSyntaxError, match=said) as caught:
            parse_scene_document(source)
        assert caught.value.rule == "page-layout"

    def test_scenet_check_points_at_the_panel_in_its_column(self):
        source = (
            "pages:\n"
            "  - tiers:\n"
            "      - columns:\n"
            "          - panels: [one]\n"
            "          - panels: [two, ghost]\n"
            "panels: {one: {}, two: {}}\n"
        )
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.path == ("pages", 0, "tiers", 0, "columns", 1, "panels", 1)
        assert finding.region is not None
        assert finding.region.start.line == 5

    def test_scenet_check_points_at_the_second_of_two_stacks(self):
        source = (
            "pages:\n"
            "  - tiers:\n"
            "      - columns:\n"
            "          - panels: [a, b]\n"
            "          - panels: [c, d]\n"
            "panels: {a: {}, b: {}, c: {}, d: {}}\n"
        )
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.path == ("pages", 0, "tiers", 0, "columns", 1)
        assert finding.region is not None
        assert finding.region.start.line == 5

    def test_the_editor_schema_accepts_columns(self):
        document = yaml.safe_load(COLUMNS)
        assert list(Draft202012Validator(scene_schema()).iter_errors(document)) == []

    def test_the_editor_schema_refuses_a_misspelt_column_key(self):
        document = yaml.safe_load(columns("{panel: [a]}"))
        assert list(Draft202012Validator(scene_schema()).iter_errors(document)) != []

    def test_a_tier_with_neither_is_located_at_the_tier(self):
        source = "pages:\n  - tiers:\n      - {height: 2}\npanels: {a: {}}\n"
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.region is not None
        assert finding.region.start.line == 3
