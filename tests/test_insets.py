"""Insets: a small panel set into the corner of another (#67).

An inset is the layout where readers agree least on what comes next. In Cohn's 2013
experiments, overlap split them about evenly between the inset and the panel it sits in,
so an inset never guesses: it is read right after its parent unless it says `read: before`.

It sits on top of its parent's art, which therefore never moves for it. Only the parent's
lettering does, because a balloon under an inset could not be read.
"""

import json
from enum import StrEnum
from xml.etree import ElementTree

import pytest
import yaml
from jsonschema import Draft202012Validator

from scenet.core import PageCore, PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.page import render_page
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_scene, parse_scene_document
from scenet.geom import BBox
from scenet.ir import Corner, InsetOrder, PanelSpec
from scenet.pipeline import compile_book, compile_ir
from scenet.schema import scene_schema

SVG = "{http://www.w3.org/2000/svg}"

# One tier holding one panel, so `street` fills the usable area: (60, 60, 1080, 1680).
#   clock, top left, 0.2 of it:     216 x 336 at (60 + 30, 60 + 30) = (90, 90)
#   face, bottom right, 0.3 of it:  324 x 504 at (60 + 1080 - 30 - 324, 60 + 1680 - 30 - 504)
#                                              = (786, 1206)
# Each inset is ringed by a gutter's width of white, so what the street's lettering must
# keep clear of is the inset grown by 30 on every side, in the street's own coordinates.
SCENE = """\
page: {size: [1200, 1800], margin: 60, gutter: 30, tier_gutter: 40}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - panels:
          - use: street
            insets:
              - {use: face, at: bottom_right, size: 0.3}
              - {use: clock, at: top_left, size: 0.2, read: before}
panels:
  street:
    camera: {shot: long_shot}
    script:
      - caption: {text: "Nine o'clock."}
      - say: {by: alice, text: "We're late. We are so very late, and it is all your fault."}
      - say: {by: bob, text: "Mine?"}
  face: {over: street, camera: {shot: close_up}, script: []}
  clock: {over: street, camera: {shot: close_up}, script: []}
"""

CLOCK_CLEARANCE = BBox(0.0, 0.0, 276.0, 396.0)
FACE_CLEARANCE = BBox(696.0, 1116.0, 384.0, 564.0)


def frames(page: PageCore) -> list[tuple[str, float, float, float, float, str | None]]:
    return [(f.panel, f.x, f.y, f.width, f.height, f.inset_of) for f in page.frames]


def scene(insets: str, *, panels: str = "street: {}, a: {}, b: {}") -> str:
    """A one-panel page whose panel `street` carries the given insets (a YAML flow list)."""
    return (
        "cast: {x: {reference: alice}}\n"
        f"pages: [{{tiers: [{{panels: [{{use: street, insets: {insets}}}]}}]}}]\n"
        f"panels: {{{panels}}}\n"
    )


class TestTheLayout:
    def test_an_inset_sits_a_gutter_in_from_its_corner(self):
        (page,) = compile_book(SCENE).pages
        assert frames(page) == [
            ("clock", 90.0, 90.0, 216.0, 336.0, "street"),
            ("street", 60.0, 60.0, 1080.0, 1680.0, None),
            ("face", 786.0, 1206.0, 324.0, 504.0, "street"),
        ]

    def test_it_is_read_after_its_parent_unless_it_says_before(self):
        """Readers split about evenly over an inset (Cohn 2013), so the order is written."""
        (page,) = compile_book(SCENE).pages
        assert [f.panel for f in page.frames] == ["clock", "street", "face"]

    def test_after_is_the_default(self):
        (page,) = compile_book(scene("[{use: a, at: top_right, size: 0.25}]")).pages
        assert [f.panel for f in page.frames] == ["street", "a"]

    def test_an_inset_is_compiled_at_its_frame(self):
        core = compile_book(SCENE).panels["face"].core
        assert (core.width, core.height) == (324.0, 504.0)

    def test_a_panel_in_a_column_can_have_an_inset(self):
        source = (
            "cast: {x: {reference: alice}}\n"
            "pages:\n"
            "  - tiers:\n"
            "      - columns:\n"
            "          - panels: [{use: t, insets: [{use: i, at: top_left, size: 0.25}]}]\n"
            "          - panels: [a, b]\n"
            "panels: {t: {}, i: {}, a: {}, b: {}}\n"
        )
        (page,) = compile_book(source).pages
        assert [(f.panel, f.inset_of) for f in page.frames] == [
            ("t", None),
            ("i", "t"),
            ("a", None),
            ("b", None),
        ]


@pytest.fixture(scope="module")
def street() -> PanelCore:
    return compile_book(SCENE).panels["street"].core


@pytest.fixture(scope="module")
def svg() -> ElementTree.Element:
    book = compile_book(SCENE)
    cores = {name: result.core for name, result in book.panels.items()}
    return ElementTree.fromstring(render_page(book.pages[0], cores))


class TestTheParent:
    def test_its_core_records_what_its_lettering_kept_clear_of(self, street: PanelCore):
        assert [box.as_bbox() for box in street.exclusions] == [CLOCK_CLEARANCE, FACE_CLEARANCE]

    def test_no_lettering_sits_under_an_inset(self, street: PanelCore):
        for box in (*street.balloons, *street.captions):
            for clearance in (CLOCK_CLEARANCE, FACE_CLEARANCE):
                assert box.box.as_bbox().overlap_area(clearance) == 0, box.id

    def test_the_inset_is_what_moved_the_caption(self):
        """Without its insets, the street puts its caption in the corner the clock takes."""
        alone = compile_ir(
            parse_scene(SCENE)["street"].model_copy(
                update={"panel": PanelSpec(size=(1080.0, 1680.0))}
            ),
            lettering_height=560.0,
        ).core
        assert alone.captions[0].box.as_bbox().overlap_area(CLOCK_CLEARANCE) > 0

    def test_its_art_does_not_move(self, street: PanelCore):
        """An inset is drawn over the art, so the cast stays exactly where it was."""
        alone = compile_ir(
            parse_scene(SCENE)["street"].model_copy(
                update={"panel": PanelSpec(size=(1080.0, 1680.0))}
            ),
            lettering_height=560.0,
        ).core
        assert street.actors == alone.actors
        assert street.backdrop == alone.backdrop

    def test_its_core_survives_a_json_round_trip(self, street: PanelCore):
        assert PanelCore.from_json(street.to_json()) == street

    def test_a_panel_with_no_inset_writes_no_exclusions(self):
        """So every Core written before insets existed reads, and writes, the same."""
        core = compile_book(SCENE).panels["face"].core
        assert "exclusions" not in json.loads(core.to_json())

    def test_an_inset_over_a_face_is_noted(self):
        source = SCENE.replace("at: top_left, size: 0.2", "at: top_left, size: 0.5")
        notes = compile_book(source).panels["street"].notes
        assert any("inset" in note and "alice" in note for note in notes)


class TestPageCore:
    def test_it_survives_a_json_round_trip(self):
        (page,) = compile_book(SCENE).pages
        assert PageCore.from_json(page.to_json()) == page

    def test_a_frame_that_is_no_inset_says_nothing_about_it(self):
        (page,) = compile_book(SCENE).pages
        street = json.loads(page.to_json())["frames"][1]
        assert street["panel"] == "street"
        assert "inset_of" not in street


class TestThePageSvg:
    def test_insets_are_painted_over_their_parent_whatever_their_order(
        self, svg: ElementTree.Element
    ):
        groups = [
            g.get("id") for g in svg.findall(f"{SVG}g") if (g.get("id") or "").startswith("panel-")
        ]
        assert groups == ["panel-street", "panel-clock", "panel-face"]

    def test_each_inset_is_ringed_in_white(self, svg: ElementTree.Element):
        children = list(svg)
        clock = next(i for i, e in enumerate(children) if e.get("id") == "panel-clock")
        ring = children[clock - 1]
        assert ring.tag == f"{SVG}rect"
        assert ring.get("fill") == "#ffffff"
        assert [ring.get(k) for k in ("x", "y", "width", "height")] == ["60", "60", "276", "396"]

    def test_ids_are_unique(self, svg: ElementTree.Element):
        ids = [i for element in svg.iter() if (i := element.get("id")) is not None]
        assert sorted({i for i in ids if ids.count(i) > 1}) == []


class TestMistakes:
    @pytest.mark.parametrize(
        ("source", "said"),
        [
            (scene("[{use: ghost, at: top_left, size: 0.2}]"), "ghost"),
            (scene("[{use: street, at: top_left, size: 0.2}]"), "twice"),
            (
                "cast: {x: {reference: alice}}\n"
                "pages: [{tiers: [{panels: [{use: street, insets: "
                "[{use: a, at: top_left, size: 0.2}]}, a]}]}]\n"
                "panels: {street: {}, a: {}}\n",
                "twice",
            ),
            (
                scene("[{use: a, at: top_left, size: 0.2}, {use: b, at: top_left, size: 0.1}]"),
                "overlap",
            ),
            (
                scene("[{use: a, at: top_left, size: 0.5}, {use: b, at: top_right, size: 0.5}]"),
                "overlap",
            ),
        ],
        ids=["unknown", "its-own-parent", "also-a-panel", "same-corner", "too-big-together"],
    )
    def test_it_is_refused_under_the_page_layout_rule(self, source: str, said: str):
        with pytest.raises(PanelSyntaxError, match=said) as caught:
            compile_book(source)
        assert caught.value.rule == "page-layout"

    @pytest.mark.parametrize("size", [0, -0.1, 0.51, 1])
    def test_a_size_is_more_than_nothing_and_at_most_half(self, size: float):
        with pytest.raises(PanelSyntaxError):
            parse_scene_document(scene(f"[{{use: a, at: top_left, size: {size}}}]"))

    @pytest.mark.parametrize(
        ("field", "value"), [("at", "middle"), ("read", "during")], ids=["corner", "read"]
    )
    def test_a_corner_and_an_order_are_named(self, field: str, value: str):
        base = {"use": "a", "at": "top_left", "size": 0.2, field: value}
        inset = "{" + ", ".join(f"{k}: {v}" for k, v in base.items()) + "}"
        with pytest.raises(PanelSyntaxError):
            parse_scene_document(scene(f"[{inset}]"))

    def test_scenet_check_points_at_the_inset(self):
        source = (
            "pages:\n"
            "  - tiers:\n"
            "      - panels:\n"
            "          - use: street\n"
            "            insets:\n"
            "              - {use: ghost, at: top_left, size: 0.2}\n"
            "panels: {street: {}}\n"
        )
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.path == ("pages", 0, "tiers", 0, "panels", 0, "insets", 0)
        assert finding.region is not None
        assert finding.region.start.line == 6

    def test_scenet_check_finds_insets_that_overlap(self):
        """Found where the frames are worked out, which `check` runs too."""
        source = (
            "pages:\n"
            "  - tiers:\n"
            "      - panels:\n"
            "          - use: street\n"
            "            insets:\n"
            "              - {use: a, at: top_left, size: 0.2}\n"
            "              - {use: b, at: top_left, size: 0.3}\n"
            "panels: {street: {}, a: {}, b: {}}\n"
        )
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.path == ("pages", 0, "tiers", 0, "panels", 0, "insets", 1)
        assert finding.region is not None
        assert finding.region.start.line == 7


class TestTheEditorSchema:
    def test_it_accepts_insets(self):
        document = yaml.safe_load(SCENE)
        assert list(Draft202012Validator(scene_schema()).iter_errors(document)) == []

    @pytest.mark.parametrize("enum", [Corner, InsetOrder])
    def test_it_offers_every_corner_and_order(self, enum: type[StrEnum]):
        text = json.dumps(scene_schema())
        for member in enum:
            assert f'"{member.value}"' in text, member

    def test_it_refuses_an_inset_without_a_corner(self):
        document = yaml.safe_load(scene("[{use: a, size: 0.2}]"))
        assert list(Draft202012Validator(scene_schema()).iter_errors(document)) != []


class TestTheDebugOverlay:
    def test_it_draws_what_each_inset_covers(self, street: PanelCore):
        svg = ElementTree.fromstring(render_debug(street))
        drawn = [
            [rect.get(k) for k in ("x", "y", "width", "height")]
            for rect in svg.iter(f"{SVG}rect")
            if rect.get("class") == "exclusion"
        ]
        assert drawn == [["0", "0", "276", "396"], ["696", "1116", "384", "564"]]


class TestAnInsetFitsInsideItsParent:
    """An inset sits a gutter in from its corner, so in a parent narrower or shorter than
    that, it was drawn partly or wholly outside the panel it is set into -- over the next
    panel or the page margin -- and nothing said so. Found while planning #92."""

    NARROW = (
        "cast: {a: {reference: alice}}\n"
        "page: {size: [600, 800], margin: 20, gutter: 40}\n"
        "panels: {big: {}, thin: {}, wee: {}, more: {}}\n"
        "pages:\n"
        "  - tiers:\n"
        "      - panels:\n"
        "          - {use: big, width: 10}\n"
        "          - use: thin\n"
        "            width: 0.5\n"
        "            insets: [{use: wee, at: top_left, size: 0.5}]\n"
        "          - {use: more, width: 10}\n"
    )
    SHORT = (
        "cast: {a: {reference: alice}}\n"
        "page: {size: [800, 600], margin: 20, gutter: 40, tier_gutter: 40}\n"
        "panels: {tall: {}, low: {}, wee: {}, rest: {}}\n"
        "pages:\n"
        "  - tiers:\n"
        "      - {height: 10, panels: [tall]}\n"
        "      - height: 0.5\n"
        "        panels: [{use: low, insets: [{use: wee, at: bottom_right, size: 0.5}]}]\n"
        "      - {height: 10, panels: [rest]}\n"
    )

    @pytest.mark.parametrize("source", [NARROW, SHORT], ids=["narrow", "short"])
    def test_it_is_refused_under_the_page_layout_rule(self, source: str):
        with pytest.raises(PanelSyntaxError, match="does not fit") as caught:
            compile_book(source)
        assert caught.value.rule == "page-layout"

    @pytest.mark.parametrize("source", [NARROW, SHORT], ids=["narrow", "short"])
    def test_scenet_check_reports_it_once_at_the_inset(self, source: str):
        (found,) = diagnose_source(source)
        assert found.rule == "page-layout"
        assert "wee" in found.message
        assert found.path[-2:] == ("insets", 0)

    def test_an_inset_that_fits_is_inside_its_parent(self):
        book = compile_book(self.NARROW.replace("width: 0.5", "width: 4"))
        frames = {frame.panel: frame for frame in book.pages[0].frames}
        parent, inset = frames["thin"], frames["wee"]
        assert parent.x <= inset.x
        assert inset.x + inset.width <= parent.x + parent.width
        assert parent.y <= inset.y
        assert inset.y + inset.height <= parent.y + parent.height
