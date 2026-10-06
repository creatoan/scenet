"""Slanted tiers: the gutters between a tier's panels lean (#67).

A tier's `slant` tilts every gutter inside it by that many degrees, about the gutter's
centre at the tier's mid-height. Neighbours share one cut, so every frame is a convex
quadrilateral by construction, and a gutter stays a gutter wide measured across the cut,
as a letterer's paneling tools keep it. The outer edges of the tier stay vertical.

A slanted panel compiles at its bounding box, and is clipped to its outline: the slanted
edge crops it the way a margin would. Its lettering stays inside the outline.
"""

import json
import math
import re
from collections.abc import Iterable
from xml.etree import ElementTree

import pytest
from shapely.geometry import Polygon, box

from scenet.core import PageCore, PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.page import render_page
from scenet.emit.svg import render
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_scene_document
from scenet.pipeline import compile_book

SVG = "{http://www.w3.org/2000/svg}"

# Usable area 1000 x 600 from (30, 30). Two equal panels share 1000 - 40 = 960, so on the
# centre line the gutter between them is centred on x = 530, at mid-height y = 330.
SCENE = """\
page: {size: [1060, 660], margin: 30, gutter: 40, tier_gutter: 40}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging: [alice left_of bob]
pages:
  - tiers:
      - {slant: 10, panels: [punch, impact]}
panels:
  punch:
    camera: {shot: full_shot}
    script: [{say: {by: alice, text: "Take that!", kind: shout}}]
  impact:
    over: punch
    camera: {shot: medium_shot}
    script: [{say: {by: bob, text: "Oof."}}]
"""

TAN = math.tan(math.radians(10))
SHIFT = 300 * TAN  # how far the cut moves from mid-height to the top or bottom
OFFSET = 40 / (2 * math.cos(math.radians(10)))  # half a gutter, measured across


def scene(tier: str, *, page: str = "{size: [1060, 660], margin: 30, gutter: 40}") -> str:
    names = sorted(set(re.findall(r"\b[a-z]\b", tier)))
    return (
        f"page: {page}\ncast: {{x: {{reference: alice}}}}\n"
        f"pages: [{{tiers: [{tier}]}}]\n"
        f"panels: {{{', '.join(f'{name}: {{}}' for name in names)}}}\n"
    )


@pytest.fixture(scope="module")
def page() -> PageCore:
    (only,) = compile_book(SCENE).pages
    return only


def flat(points: Iterable[tuple[float, float]]) -> list[float]:
    """Corners as one flat list, which `pytest.approx` can compare; it does not nest."""
    return [value for point in points for value in point]


def outline(page: PageCore, name: str) -> list[tuple[float, float]]:
    frame = next(f for f in page.frames if f.panel == name)
    assert frame.outline is not None
    return list(frame.outline)


class TestTheCut:
    def test_outlines_run_clockwise_from_the_top_left(self, page: PageCore):
        punch = outline(page, "punch")
        assert flat(punch) == pytest.approx(
            flat([(30, 30), (530 + SHIFT - OFFSET, 30), (530 - SHIFT - OFFSET, 630), (30, 630)]),
            abs=0.01,
        )
        impact = outline(page, "impact")
        assert flat(impact) == pytest.approx(
            flat(
                [(530 + SHIFT + OFFSET, 30), (1030, 30), (1030, 630), (530 - SHIFT + OFFSET, 630)]
            ),
            abs=0.01,
        )

    def test_neighbours_share_one_cut_a_gutter_wide(self, page: PageCore):
        """Both edges are parallel, and a gutter apart measured across, not along x."""
        (_, top_right, bottom_right, _) = outline(page, "punch")
        (top_left, _, _, bottom_left) = outline(page, "impact")
        right = Polygon([top_right, bottom_right, bottom_left, top_left])
        # The band between the two edges is a parallelogram one gutter across.
        length = math.dist(top_right, bottom_right)
        assert math.dist(top_left, bottom_left) == pytest.approx(length, abs=0.01)
        assert right.area / length == pytest.approx(40, abs=0.05)

    def test_the_cut_is_centred_on_the_gutter_at_mid_height(self, page: PageCore):
        (_, top_right, bottom_right, _) = outline(page, "punch")
        (top_left, _, _, bottom_left) = outline(page, "impact")
        left_mid = ((top_right[0] + bottom_right[0]) / 2, 330)
        right_mid = ((top_left[0] + bottom_left[0]) / 2, 330)
        assert (left_mid[0] + right_mid[0]) / 2 == pytest.approx(530, abs=0.01)

    def test_a_positive_slant_leans_the_top_to_the_right(self, page: PageCore):
        (_, top_right, bottom_right, _) = outline(page, "punch")
        assert top_right[0] > bottom_right[0]

    def test_a_frame_is_the_outline_s_bounding_box(self, page: PageCore):
        for frame in page.frames:
            assert frame.outline is not None
            xs = [x for x, _ in frame.outline]
            ys = [y for _, y in frame.outline]
            assert (frame.x, frame.y) == (min(xs), min(ys))
            assert frame.width == round(max(xs) - min(xs), 2)
            assert frame.height == round(max(ys) - min(ys), 2)

    def test_a_negative_slant_mirrors_it(self):
        (page,) = compile_book(SCENE.replace("slant: 10", "slant: -10")).pages
        (_, top_right, bottom_right, _) = outline(page, "punch")
        assert top_right[0] < bottom_right[0]

    def test_every_gutter_in_the_tier_leans(self):
        (page,) = compile_book(scene("{slant: 8, panels: [a, b, c]}")).pages
        assert all(frame.outline is not None for frame in page.frames)
        assert [f.panel for f in page.frames] == ["a", "b", "c"]

    def test_a_tier_with_no_slant_is_unchanged(self):
        (page,) = compile_book(SCENE.replace("slant: 10, ", "")).pages
        assert all(frame.outline is None for frame in page.frames)
        assert "outline" not in page.to_json()


@pytest.fixture(scope="module")
def punch() -> PanelCore:
    return compile_book(SCENE).panels["punch"].core


class TestTheSlantedPanel:
    def test_it_compiles_at_its_bounding_box(self, punch: PanelCore):
        assert (punch.width, punch.height) == pytest.approx(
            (530 + SHIFT - OFFSET - 30, 600), abs=0.01
        )

    def test_its_core_holds_its_outline_in_its_own_units(self, punch: PanelCore):
        assert punch.outline is not None
        assert flat(punch.outline) == pytest.approx(
            flat([(0, 0), (500 + SHIFT - OFFSET, 0), (500 - SHIFT - OFFSET, 600), (0, 600)]),
            abs=0.01,
        )

    def test_its_lettering_stays_inside_the_outline(self, punch: PanelCore):
        assert punch.outline is not None
        shape = Polygon(punch.outline)
        for balloon in punch.balloons:
            b = balloon.box
            assert shape.contains(box(b.x, b.y, b.right, b.bottom)), balloon.id

    def test_its_outline_never_leaves_its_bounds(self):
        """Corners are rounded one by one, so the bounds are taken from them, not beside."""
        # The second tier runs from y = 748.125 to 1501.875: its height rounds to 753.75,
        # and its rounded corners are 753.76 apart.
        source = scene(
            "{panels: [a]}, {height: 1.2, slant: 12, panels: [b, c]}",
            page="{size: [1500, 2250], margin: 75, gutter: 30, tier_gutter: 45}",
        )
        book = compile_book(source)
        for name in ("b", "c"):
            core = book.panels[name].core
            assert core.outline is not None
            assert all(0 <= x <= core.width and 0 <= y <= core.height for x, y in core.outline)

    def test_its_core_survives_a_json_round_trip(self, punch: PanelCore):
        assert PanelCore.from_json(punch.to_json()) == punch

    def test_a_rectangular_panel_writes_no_outline(self):
        core = compile_book(SCENE.replace("slant: 10, ", "")).panels["punch"].core
        assert "outline" not in json.loads(core.to_json())

    def test_alone_it_is_drawn_and_bordered_as_its_outline(self, punch: PanelCore):
        svg = ElementTree.fromstring(render(punch))
        (clip,) = svg.iter(f"{SVG}clipPath")
        (shape,) = clip.findall(f"{SVG}polygon")
        border = [p for p in svg.findall(f"{SVG}polygon") if p.get("fill") == "none"]
        assert len(border) == 1
        assert border[0].get("points") == shape.get("points")

    def test_a_rectangular_panel_is_drawn_as_it_always_was(self):
        core = compile_book(SCENE.replace("slant: 10, ", "")).panels["punch"].core
        assert "clipPath" not in render(core)

    def test_the_debug_overlay_draws_the_outline(self, punch: PanelCore):
        svg = ElementTree.fromstring(render_debug(punch))
        assert [p for p in svg.iter(f"{SVG}polygon") if p.get("class") == "outline"]

    def test_a_cut_across_a_face_is_noted(self):
        source = SCENE.replace("slant: 10", "slant: 30").replace(
            "camera: {shot: medium_shot}", "camera: {shot: close_up}"
        )
        notes = compile_book(source).panels["impact"].notes
        assert any("slanted edge" in note for note in notes)


class TestThePageSvg:
    def test_each_slanted_panel_is_clipped_to_its_outline(self, page: PageCore):
        book = compile_book(SCENE)
        cores = {name: result.core for name, result in book.panels.items()}
        svg = ElementTree.fromstring(render_page(page, cores))
        groups = {
            g.get("id"): g
            for g in svg.findall(f"{SVG}g")
            if (g.get("id") or "").startswith("panel-")
        }
        (clip,) = groups["panel-impact"].findall(f"{SVG}clipPath")
        assert clip.findall(f"{SVG}rect") == []
        (shape,) = clip.findall(f"{SVG}polygon")
        assert shape.get("points")


class TestMistakes:
    @pytest.mark.parametrize(
        ("tier", "said"),
        [
            ("{slant: 31, panels: [a, b]}", None),
            ("{slant: -31, panels: [a, b]}", None),
            ("{slant: 10, columns: [{panels: [a]}, {panels: [b]}]}", "column"),
            ("{slant: 10, panels: [a]}", "one panel"),
            (
                "{slant: 10, panels: [{use: a, insets: [{use: b, at: top_left, size: 0.2}]}, c]}",
                "inset",
            ),
        ],
        ids=["too-far-right", "too-far-left", "columns", "one-panel", "inset"],
    )
    def test_it_is_refused(self, tier: str, said: str | None):
        with pytest.raises(PanelSyntaxError, match=said) as caught:
            parse_scene_document(scene(tier))
        if said is not None:
            assert caught.value.rule == "page-layout"

    def test_a_slant_too_steep_for_its_panels_is_refused(self):
        """Three narrow, tall panels: the cut would cross a panel's whole width."""
        source = scene(
            "{slant: 30, panels: [a, b, c]}",
            page="{size: [400, 1000], margin: 20, gutter: 20}",
        )
        with pytest.raises(PanelSyntaxError, match="steep") as caught:
            compile_book(source)
        assert caught.value.rule == "page-layout"

    def test_scenet_check_points_at_the_tier(self):
        source = (
            "page: {size: [400, 1000], margin: 20, gutter: 20}\n"
            "pages:\n"
            "  - tiers:\n"
            "      - {slant: 30, panels: [a, b, c]}\n"
            "panels: {a: {}, b: {}, c: {}}\n"
        )
        (finding,) = diagnose_source(source)
        assert finding.rule == "page-layout"
        assert finding.path == ("pages", 0, "tiers", 0, "slant")
        assert finding.region is not None
        assert finding.region.start.line == 4
