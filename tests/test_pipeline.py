"""End-to-end compilation, and the invariants a compiled panel must satisfy.

The invariant tests are the important ones. A solver has an enormous space of possible
outputs and no obvious "correct" coordinate to assert against, so what can be checked
is that certain things are *never* true: no balloon over a face, none outside the
panel, none out of reading order. Those hold for every input or the compiler is wrong.
"""

import re
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml

from scenet.assets.contract import default_library
from scenet.core import PanelCore
from scenet.emit.debug_svg import render_debug
from scenet.emit.strip import render_strip
from scenet.emit.svg import fmt, render
from scenet.geom import BBox, Circle
from scenet.pipeline import compile_file, compile_scene, compile_source
from scenet.solve.text import load_metrics
from tests.invariants import assert_lettering_is_placed, assert_svg_is_sound

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

PANELS = [
    # A minimal panel: one actor, nothing said.
    "cast:\n  a: {reference: alice}\n",
    # Dialogue between two actors.
    """
camera: {shot: medium_shot}
cast:
  alice: {reference: alice, at: left_third, facing: right}
  bob:   {reference: bob,   at: right_third, facing: left}
staging:
  - alice left_of bob
  - alice ground_shared_with bob
script:
  - say: {by: alice, text: "You forgot your umbrella!", prefer: top_left}
  - say: {by: bob,   text: "I know."}
""",
    # A crowd, which forces the camera to retreat.
    """
camera: {shot: close_up}
cast:
  a: {reference: alice}
  b: {reference: bob}
  c: {reference: alice, pose: hands_on_hips}
script:
  - say: {by: a, text: "Everyone is here."}
  - say: {by: c, text: "So it seems."}
""",
    # Every balloon kind, and a wide shot.
    """
camera: {shot: full_shot, angle: high}
cast:
  a: {reference: alice, at: left_third}
  b: {reference: bob, at: right_third}
script:
  - say: {by: a, text: "Psst.", kind: whisper}
  - say: {by: b, text: "WHAT?!", kind: shout}
  - say: {by: a, text: "I wonder about him.", kind: thought}
""",
    # A tall narrow panel, to catch anything assuming a square.
    """
panel: {size: [500, 1100], margin: 20}
camera: {shot: medium_close_up}
cast:
  a: {reference: bob}
script:
  - say: {by: a, text: "Tight quarters in here."}
""",
]


@pytest.fixture(scope="module")
def compiled() -> list[PanelCore]:
    library = default_library()
    return [compile_source(source, library=library).core for source in PANELS]


class TestInvariants:
    """Properties that must hold for every panel the compiler accepts."""

    def test_lettering_is_placed_as_promised(self, compiled: list[PanelCore]):
        """No box over a face or outside the margin, none overlapping, every one in
        reading order, every tail from its balloon to its speaker.

        The checks live in `tests/invariants.py`, shared with the generated panels in
        `tests/properties/`, so the two can never disagree about what a correct panel is.
        """
        for source, core in zip(PANELS, compiled, strict=True):
            panel = (yaml.safe_load(source) or {}).get("panel", {})
            assert_lettering_is_placed(core, margin=panel.get("margin", 0.0))

    def test_actors_never_overlap(self, compiled: list[PanelCore]):
        for index, core in enumerate(compiled):
            boxes = sorted((actor.bounds for actor in core.actors), key=lambda b: b.x)
            for first, second in pairwise(boxes):
                assert first.right <= second.x + 0.5, f"panel {index}: actors overlap"

    def test_every_actor_is_at_least_partly_visible(self, compiled: list[PanelCore]):
        """Bleeding off an edge is normal comics practice; vanishing entirely is not."""
        for index, core in enumerate(compiled):
            for actor in core.actors:
                assert actor.bounds.overlap_area(core.bounds) > 0, (
                    f"panel {index}: actor {actor.id} is entirely off-panel"
                )


class TestDeterminism:
    def test_recompiling_gives_byte_identical_core(self):
        library = default_library()
        for source in PANELS:
            first = compile_source(source, library=library).core.to_json()
            second = compile_source(source, library=library).core.to_json()
            assert first == second

    def test_recompiling_gives_byte_identical_svg(self):
        library = default_library()
        for source in PANELS:
            core = compile_source(source, library=library).core
            assert render(core) == render(compile_source(source, library=library).core)

    def test_a_contested_layout_compiles_to_the_same_bytes_every_time(self):
        """The weekly Hypothesis exploration's find: the solver's last-bit noise reached
        the Core whenever a coordinate sat on a rounding boundary -- 247.95 one compile,
        247.96 the next, in the same process."""
        source = (
            "panel: {size: [1399, 1196]}\n"
            "camera: {shot: medium_shot}\n"
            "cast:\n"
            "  a: {reference: alice, facing: left}\n"
            "  z: {reference: alice, facing: left}\n"
            "script:\n"
            "  - caption: {text: '0'}\n"
            "  - caption: {text: '0'}\n"
        )
        library = default_library()
        compiled = {compile_source(source, library=library).core.to_json() for _ in range(12)}
        assert len(compiled) == 1

    def test_core_survives_a_json_round_trip(self, compiled: list[PanelCore]):
        """Panel Core is a real writable format, not a private data structure, so it
        must reload exactly."""
        for core in compiled:
            assert PanelCore.from_json(core.to_json()) == core

    def test_negative_zero_is_normalised(self):
        """-0.0 and 0.0 are equal but format differently, which would produce phantom
        golden-file diffs."""
        assert fmt(-0.0) == "0"
        assert fmt(-0.001) == "0"


class TestEmitters:
    def test_svg_is_sound(self, compiled: list[PanelCore]):
        """It parses, its ids are unique and resolve, and every glyph is drawn at the
        size it was measured at."""
        for core in compiled:
            sizes = [box.font_size for box in (*core.balloons, *core.captions)]
            for live_text in (False, True):
                svg = render(core, live_text=live_text)
                assert_svg_is_sound(svg, size=(core.width, core.height), font_sizes=sizes)

    def test_debug_svg_is_well_formed(self, compiled: list[PanelCore]):
        for core in compiled:
            ElementTree.fromstring(render_debug(core))

    def test_dialogue_is_never_emitted_as_raw_text_by_default(self, compiled: list[PanelCore]):
        """Lettering goes out as glyph outlines so the file depends on no installed
        font and renders exactly what was measured."""
        core = compiled[1]
        assert "<text" not in render(core)
        assert "<text" in render(core, live_text=True)

    def test_glyphs_are_drawn_at_the_size_they_were_measured(self, compiled: list[PanelCore]):
        """A balloon is sized from the lettering's measured width, and each glyph is
        advanced by its measured width. A glyph drawn at a rounded scale is a different
        size from the one measured: at size 35 the scale is 0.035, and two decimals
        wrote 0.04 -- every letter 14% too large, crowding the next."""
        units_per_em = load_metrics().units_per_em
        for core in compiled:
            measured = {
                round(item.font_size / units_per_em, 9) for item in (*core.balloons, *core.captions)
            }
            if not measured:
                continue
            drawn = re.findall(r"scale\(([-\d.]+) -[\d.]+\)", render(core))
            assert drawn
            for scale in drawn:
                assert any(abs(float(scale) - expected) < 1e-6 for expected in measured), (
                    f"a glyph drawn at scale {scale}, measured at {sorted(measured)}"
                )

    def test_live_text_escapes_markup(self):
        core = compile_source(
            'cast:\n  a: {reference: alice}\nscript:\n  - say: {by: a, text: "<b>&</b>"}\n'
        ).core
        rendered = render(core, live_text=True)
        assert "<b>" not in rendered
        assert "&lt;b&gt;" in rendered

    def test_svg_declares_the_panel_size(self):
        core = compile_source("panel: {size: [640, 480]}\ncast:\n  a: {reference: alice}\n").core
        rendered = render(core)
        assert 'width="640"' in rendered
        assert 'viewBox="0 0 640 480"' in rendered


class TestDebugStrip:
    """A scene's overlay: each panel's working geometry, laid out exactly as the strip is.

    Without it a scene has no overlay at all, and the playground's Overlay tab used to
    show the plain strip a second time.
    """

    SOURCE = (
        "panels:\n  one: {cast: {a: {reference: alice}}}\n  two: {cast: {b: {reference: bob}}}\n"
    )
    G = "{http://www.w3.org/2000/svg}g"

    @pytest.fixture
    def pairs(self) -> list[tuple[str, PanelCore]]:
        return [(name, result.core) for name, result in compile_scene(self.SOURCE).items()]

    def test_each_panel_carries_its_own_overlay(self, pairs: list[tuple[str, PanelCore]]):
        root = ElementTree.fromstring(render_strip(pairs, debug=True))
        panels = {
            g.get("id"): g for g in root.iter(self.G) if (g.get("id") or "").startswith("panel-")
        }
        assert set(panels) == {"panel-one", "panel-two"}
        assert any(g.get("id") == "p1-debug-a" for g in panels["panel-one"].iter(self.G))
        assert any(g.get("id") == "p2-debug-b" for g in panels["panel-two"].iter(self.G))

    def test_it_has_the_geometry_of_the_plain_strip(self, pairs: list[tuple[str, PanelCore]]):
        """Toggling between the two views must not move anything."""
        plain = ElementTree.fromstring(render_strip(pairs))
        debug = ElementTree.fromstring(render_strip(pairs, debug=True))
        assert debug.get("viewBox") == plain.get("viewBox")

        def placements(root: ElementTree.Element) -> list[str | None]:
            return [
                g.get("transform")
                for g in root.iter(self.G)
                if (g.get("id") or "").startswith("panel-")
            ]

        assert placements(debug) == placements(plain)

    def test_the_plain_strip_is_unchanged(self, pairs: list[tuple[str, PanelCore]]):
        assert "debug-" not in render_strip(pairs)


class TestStripIsOneDocument:
    """A strip is one SVG document holding several panels (#64).

    Each panel used to be pasted in exactly as it rendered alone, so every id repeated
    once per panel. And nothing clipped: a shot crops the body at the frame, a panel on
    its own hides the rest behind its `viewBox`, and in a strip the rest of the figure
    drew straight into the gutter -- and, once panels stack, into the tier below.
    """

    SVG = "{http://www.w3.org/2000/svg}"

    # Two panels with the same setting share a seed, so they used to define the same
    # fog filter twice.
    FOGGY = (
        "panels:\n"
        "  one: {setting: {place: docks, weather: fog}, cast: {a: {reference: alice}}}\n"
        "  two: {over: one, camera: {shot: close_up}}\n"
    )

    @pytest.fixture(params=["gallery-sequence", "shared-fog"])
    def pairs(self, request: pytest.FixtureRequest) -> list[tuple[str, PanelCore]]:
        source = (
            (EXAMPLES / "gallery" / "12-sequence.scene.yaml").read_text(encoding="utf-8")
            if request.param == "gallery-sequence"
            else self.FOGGY
        )
        return [(name, result.core) for name, result in compile_scene(source).items()]

    @pytest.mark.parametrize("debug", [False, True], ids=["plain", "overlay"])
    def test_no_id_repeats(self, pairs: list[tuple[str, PanelCore]], debug: bool):
        root = ElementTree.fromstring(render_strip(pairs, debug=debug))
        ids = [id_ for element in root.iter() if (id_ := element.get("id")) is not None]
        assert ids
        assert sorted({id_ for id_ in ids if ids.count(id_) > 1}) == []

    @pytest.mark.parametrize("debug", [False, True], ids=["plain", "overlay"])
    def test_every_reference_resolves(self, pairs: list[tuple[str, PanelCore]], debug: bool):
        strip = render_strip(pairs, debug=debug)
        ids = set(re.findall(r' id="([^"]+)"', strip))
        referenced = re.findall(r"url\(#([^)]+)\)", strip) + re.findall(r'href="#([^"]+)"', strip)
        assert referenced, "every panel's clip, at least"
        assert set(referenced) <= ids

    @pytest.mark.parametrize("debug", [False, True], ids=["plain", "overlay"])
    def test_each_panel_is_clipped_to_its_own_frame(
        self, pairs: list[tuple[str, PanelCore]], debug: bool
    ):
        """In the panel's own coordinates, on a group with no transform of its own:
        `userSpaceOnUse` is the referencing element's user space, which is ambiguous on
        an element that also carries a `transform`."""
        root = ElementTree.fromstring(render_strip(pairs, debug=debug))
        groups = [g for g in root.iter(f"{self.SVG}g") if (g.get("id") or "").startswith("panel-")]
        assert len(groups) == len(pairs)
        for group, (_, core) in zip(groups, pairs, strict=True):
            (clip,) = group.findall(f"{self.SVG}clipPath")
            (rect,) = clip.findall(f"{self.SVG}rect")
            frame = (rect.get("x"), rect.get("y"), rect.get("width"), rect.get("height"))
            assert frame == ("0", "0", fmt(core.width), fmt(core.height))
            (clipped,) = (
                g
                for g in group.findall(f"{self.SVG}g")
                if g.get("clip-path") == f"url(#{clip.get('id')})"
            )
            assert clipped.get("transform") is None
            assert len(list(clipped)) > 0

    def test_fog_in_each_panel_comes_from_that_panel(self):
        pairs = [(name, r.core) for name, r in compile_scene(self.FOGGY).items()]
        root = ElementTree.fromstring(render_strip(pairs))
        groups = [g for g in root.iter(f"{self.SVG}g") if (g.get("id") or "").startswith("panel-")]
        for group in groups:
            filters = {f.get("id") for f in group.iter(f"{self.SVG}filter")}
            veils = [veil for e in group.iter(f"{self.SVG}rect") if (veil := e.get("filter"))]
            assert veils
            assert {veil.removeprefix("url(#").removesuffix(")") for veil in veils} <= filters

    def test_a_panel_on_its_own_keeps_its_bare_ids(self):
        """Prefixing is the strip's business. A single panel's SVG is unchanged."""
        core = compile_source("cast: {a: {reference: alice}}").core
        assert 'id="actor-a"' in render(core)
        assert 'id="debug-a"' in render_debug(core)


class TestExample:
    def test_shipped_example_compiles(self):
        result = compile_file(EXAMPLES / "duel.panel.yaml")
        assert len(result.core.actors) == 2
        assert len(result.core.balloons) == 2

    def test_a_retreating_camera_is_reported(self):
        """Diagnostics are part of the result, not log noise, so tooling can surface
        that the requested framing was loosened."""
        result = compile_file(EXAMPLES / "duel.panel.yaml")
        assert any("retreated" in note for note in result.notes)


class TestGeometryHelpers:
    def test_circle_box_intersection_uses_nearest_point(self):
        box = BBox(0, 0, 10, 10)
        assert box.intersects_circle(Circle(12, 5, 3))
        assert not box.intersects_circle(Circle(14, 5, 3))

    def test_diagonal_near_miss_is_not_an_intersection(self):
        """A naive centre-distance test would wrongly report a hit here."""
        box = BBox(0, 0, 10, 10)
        assert not box.intersects_circle(Circle(13, 13, 4))


class TestIdentifiersCannotInjectMarkup:
    """Identifiers come from user documents and end up in SVG attributes.

    The output is injected into the page with `innerHTML` by the browser playground, so
    an identifier that can close its own attribute is a scripting vector and not merely
    malformed XML. `xml.sax.saxutils.escape` does not escape quotation marks, which is
    exactly the gap this covers.
    """

    HOSTILE = 'x" onload=alert(1) y="'

    def test_actor_id_stays_inside_its_attribute(self):
        source = f"cast:\n  '{self.HOSTILE}': {{reference: alice}}\n"
        svg = render(compile_source(source).core)

        assert "onload" in svg, "the identifier should survive, escaped"
        root = ElementTree.fromstring(svg)
        groups = root.iter("{http://www.w3.org/2000/svg}g")
        assert any(g.get("id") == f"actor-{self.HOSTILE}" for g in groups)
        # No element anywhere gained an attribute called `onload`.
        assert all("onload" not in element.attrib for element in root.iter())

    def test_actor_id_stays_inside_its_attribute_in_the_overlay(self):
        """The overlay goes through `innerHTML` too, from the playground's Overlay tab."""
        source = f"cast:\n  '{self.HOSTILE}': {{reference: alice}}\n"
        svg = render_debug(compile_source(source).core)

        root = ElementTree.fromstring(svg)
        groups = root.iter("{http://www.w3.org/2000/svg}g")
        assert any(g.get("id") == f"debug-{self.HOSTILE}" for g in groups)
        assert all("onload" not in element.attrib for element in root.iter())

    def test_actor_id_stays_inside_its_label_in_the_overlay(self):
        """The overlay labels actors and speakers in text, which needs escaping too."""
        hostile = "</text><script/>"
        source = (
            f"cast:\n  '{hostile}': {{reference: alice}}\n"
            f"script:\n  - say: {{by: '{hostile}', text: Hi}}\n"
        )
        root = ElementTree.fromstring(render_debug(compile_source(source).core))

        assert not list(root.iter("{http://www.w3.org/2000/svg}script"))
        texts = "".join(t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text"))
        assert hostile in texts

    def test_panel_name_stays_inside_its_attribute(self):
        source = f"panels:\n  '{self.HOSTILE}': {{cast: {{a: {{reference: alice}}}}}}\n"
        panels = compile_scene(source)
        strip = render_strip([(name, result.core) for name, result in panels.items()])

        root = ElementTree.fromstring(strip)
        groups = root.iter("{http://www.w3.org/2000/svg}g")
        assert any(g.get("id") == f"panel-{self.HOSTILE}" for g in groups)

    def test_panel_name_never_reaches_a_reference(self):
        """Ids inside a strip are prefixed by position, not by name. Attribute escaping
        keeps a name inside its quotes, but nothing would keep it inside `url(#...)`."""
        source = f"panels:\n  '{self.HOSTILE}': {{cast: {{a: {{reference: alice}}}}}}\n"
        panels = compile_scene(source)
        strip = render_strip([(name, result.core) for name, result in panels.items()])

        assert 'clip-path="url(#p1-frame)"' in strip
        assert all("onload" not in ref for ref in re.findall(r"url\(#[^)]*\)", strip))

    def test_dialogue_stays_inside_its_element(self):
        source = 'cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: "</text><script/>"}}]'
        svg = render(compile_source(source).core, live_text=True)

        root = ElementTree.fromstring(svg)
        assert not list(root.iter("{http://www.w3.org/2000/svg}script"))
        texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
        assert "</text><script/>" in texts
