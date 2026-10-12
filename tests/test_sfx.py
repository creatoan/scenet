"""Sound effects: lettering that is part of the picture.

`BLAM` is not dialogue. Comics letter sound as art -- big, angled, outlined, near its
source -- and a writer already puts it in the script. `- sfx: {text: BLAM, from: bob}`
places one, lettered in the display face (Bangers), and these tests pin down what the
issue asked of it:

- **It never covers a face**, the same hard rule every balloon obeys.
- **It sits near its source**, or in its `prefer:` zone, chosen by candidate scoring as
  everything else is, never by a coordinate.
- **Balloons pay to cover it**, as they pay to cover emanata: a balloon over a sound
  effect deletes what the panel was saying. Never forbidden, so a crowded panel still
  compiles.
- **Nobody moves.** An effect is placed after the cast and changes no figure and no
  framing, and a panel without one compiles exactly as it did before effects existed.
- **It takes its place in the script's order** -- the `order` every box shares -- without
  the geometric reading-order rule, which a sound would break wherever it is drawn.
"""

import math
from pathlib import Path

import fonts.ttf
import pytest
from jsonschema import Draft202012Validator
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon, box

from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import render
from scenet.errors import PanelSyntaxError, SfxPlacementError
from scenet.frontends.yaml_front import parse_panel
from scenet.ir import Face, SfxEvent, SfxSize
from scenet.pipeline import compile_file, compile_source
from scenet.safe_yaml import load
from scenet.schema import panel_schema
from scenet.solve.sfx import SIZE_FACTORS, layout_effect
from scenet.solve.text import DISPLAY_FONT_PATH, Typeface
from tests.invariants import assert_effects_are_placed, assert_svg_is_sound

SEMIBOLD = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]

PANEL = (
    "panel: {size: [1200, 800], margin: 20}\n"
    "camera: {shot: full_shot}\n"
    "cast:\n"
    "  alice: {reference: alice, at: left_third}\n"
    "  bob:   {reference: bob,   at: right_third, facing: left}\n"
    "staging: [alice left_of bob]\n"
)


def _core(script: str, *, head: str = PANEL) -> PanelCore:
    return compile_source(f"{head}script:\n{script}").core


def _zone(core: PanelCore, index: int = 0) -> Polygon:
    return Polygon(core.sfx[index].zone)


def _faces(core: PanelCore) -> list:
    return [
        ShapelyPoint(a.face_exclusion.cx, a.face_exclusion.cy).buffer(a.face_exclusion.r)
        for a in core.actors
    ]


class TestTheLanguage:
    def test_an_effect_is_written_as_a_script_verb(self):
        panel = parse_panel(f"{PANEL}script:\n  - sfx: {{text: BLAM, from: bob}}\n")
        (event,) = panel.script
        assert isinstance(event, SfxEvent)
        assert (event.text, event.source) == ("BLAM", "bob")

    def test_the_defaults(self):
        (event,) = parse_panel(f"{PANEL}script:\n  - sfx: {{text: tok}}\n").script
        assert isinstance(event, SfxEvent)
        assert event.source is None
        assert event.prefer is None
        assert event.size is SfxSize.MEDIUM
        assert (event.rotate, event.arc, event.hollow) == (0.0, 0.0, False)

    def test_from_must_name_a_cast_member(self):
        source = f"{PANEL}script:\n  - sfx: {{text: BLAM, from: carol}}\n"
        with pytest.raises(PanelSyntaxError, match="carol"):
            parse_panel(source)
        (found,) = diagnose_source(source)
        assert found.rule == "unknown-actor"
        assert found.path == ("script", 0, "sfx", "from")

    @pytest.mark.parametrize("field", ["rotate: 60", "arc: -200", "size: huge", "loud: true"])
    def test_a_bad_field_is_refused(self, field: str):
        with pytest.raises(PanelSyntaxError):
            parse_panel(f"{PANEL}script:\n  - sfx: {{text: BLAM, {field}}}\n")

    def test_the_text_is_lettered_as_written(self):
        """No exclamation mark the author did not write -- Comicraft's rule -- and no
        emphasis: an underscore in a sound effect is just an underscore."""
        core = _core("  - sfx: {text: k_thunk, from: bob}\n")
        assert core.sfx[0].text == "k_thunk"
        assert "".join(glyph.char for glyph in core.sfx[0].glyphs) == "k_thunk"

    def test_the_published_schema_accepts_it(self):
        document = load(
            f"{PANEL}script:\n  - sfx: {{text: BLAM, from: bob, size: large, hollow: true}}\n"
        )
        assert list(Draft202012Validator(panel_schema()).iter_errors(document)) == []


class TestWhereItGoes:
    @pytest.mark.parametrize(
        "effect",
        [
            "{text: BLAM, from: bob}",
            "{text: BLAM, from: alice, size: large}",
            "{text: KRAKA-THOOM, size: large, rotate: -20}",
            "{text: tok tok tok, prefer: top_right, size: small}",
            "{text: WHOOOSH, from: alice, arc: 60}",
            "{text: SPLAT, from: bob, arc: -90, rotate: 30, hollow: true}",
        ],
    )
    def test_it_never_covers_a_face_and_stays_in_the_panel(self, effect: str):
        core = _core(f"  - sfx: {effect}\n  - say: {{by: alice, text: Look out!}}\n")
        assert_effects_are_placed(core, margin=20)
        for face in _faces(core):
            assert not _zone(core).intersects(face)

    def test_it_sits_near_its_source(self):
        core = _core("  - sfx: {text: BLAM, from: bob}\n")
        centre = _zone(core).centroid
        alice, bob = (core.actor(name).bounds.centre for name in ("alice", "bob"))
        assert centre.distance(ShapelyPoint(bob.x, bob.y)) < centre.distance(
            ShapelyPoint(alice.x, alice.y)
        )

    def test_without_a_source_it_goes_where_it_prefers(self):
        core = _core("  - sfx: {text: tok, prefer: top_right, size: small}\n")
        centre = _zone(core).centroid
        assert centre.x > core.width / 2
        assert centre.y < core.height / 2

    def test_two_effects_never_overlap(self):
        core = _core("  - sfx: {text: BLAM, from: bob}\n  - sfx: {text: BLAM, from: bob}\n")
        assert _zone(core, 0).intersection(_zone(core, 1)).area == pytest.approx(0, abs=0.5)

    def test_an_effect_with_nowhere_to_go_says_so(self):
        source = (
            "panel: {size: [300, 200]}\ncast: {a: {reference: alice}}\n"
            "script:\n  - sfx: {text: KRAKA-THOOOOOOOOOOOOOOOOOOOOOOOOOM, size: large}\n"
        )
        with pytest.raises(SfxPlacementError, match="sound effect"):
            compile_source(source)
        (found,) = diagnose_source(source, deep=True)
        assert found.rule == "sfx-placement"


class TestNobodyMoves:
    def test_an_effect_moves_no_figure_and_changes_no_framing(self):
        plain = compile_source(f"{PANEL}script:\n  - say: {{by: alice, text: Hi.}}\n")
        loud = compile_source(
            f"{PANEL}script:\n  - sfx: {{text: BLAM, from: bob, size: large}}\n"
            "  - say: {by: alice, text: Hi.}\n"
        )
        assert loud.core.actors == plain.core.actors
        assert loud.camera == plain.camera

    def test_a_panel_without_one_records_none(self):
        assert '"sfx"' not in _core("  - say: {by: alice, text: Hi.}\n").to_json()


class TestBalloonsPayToCoverIt:
    def test_a_balloon_moves_off_an_effect_beside_its_speaker(self):
        say = "  - say: {by: bob, text: 'Did you hear that?'}\n"
        alone = _core(say).balloons[0].box
        core = _core("  - sfx: {text: BLAM, from: bob, size: large}\n" + say)
        zone = _zone(core)

        def covered(b) -> float:
            return box(b.x, b.y, b.right, b.bottom).intersection(zone).area

        assert covered(core.balloons[0].box) <= covered(alone)
        if covered(alone) > 0:
            assert covered(core.balloons[0].box) < covered(alone)

    def test_it_is_never_forbidden_to(self):
        """A panel too crowded to keep balloons off an effect still compiles."""
        crowded = "".join(
            f"  - say: {{by: {who}, text: 'Words, words, and more words here.'}}\n"
            for who in ("alice", "bob", "alice", "bob")
        )
        core = _core("  - sfx: {text: KRAKA-THOOM, size: large}\n" + crowded)
        assert len(core.balloons) == 4


class TestOrder:
    def test_it_takes_its_turn_in_the_one_sequence(self):
        core = _core(
            "  - say: {by: alice, text: Hi.}\n"
            "  - sfx: {text: BLAM, from: bob}\n"
            "  - say: {by: bob, text: Ow.}\n"
        )
        assert [core.balloons[0].order, core.sfx[0].order, core.balloons[1].order] == [0, 1, 2]
        assert core.sfx[0].id == "s0"


class TestTheShape:
    FAMILY = Typeface()

    def test_sizes_are_multiples_of_the_dialogue_size(self):
        assert (
            SIZE_FACTORS[SfxSize.SMALL] < SIZE_FACTORS[SfxSize.MEDIUM] < SIZE_FACTORS[SfxSize.LARGE]
        )
        shape = layout_effect(
            SfxEvent(text="BLAM", size=SfxSize.LARGE), dialogue_size=30, typeface=self.FAMILY
        )
        assert shape.font_size == pytest.approx(30 * SIZE_FACTORS[SfxSize.LARGE])

    def test_it_is_lettered_in_the_display_face(self):
        shape = layout_effect(SfxEvent(text="BLAM"), dialogue_size=30, typeface=self.FAMILY)
        assert shape.metrics.path == DISPLAY_FONT_PATH

    def test_rotation_turns_every_letter(self):
        flat = layout_effect(SfxEvent(text="BLAM"), dialogue_size=30, typeface=self.FAMILY)
        turned = layout_effect(
            SfxEvent(text="BLAM", rotate=20), dialogue_size=30, typeface=self.FAMILY
        )
        assert [g.angle for g in flat.glyphs] == [0.0] * 4
        assert all(g.angle == pytest.approx(20) for g in turned.glyphs)

    def test_a_positive_arc_bows_the_middle_upward(self):
        shape = layout_effect(
            SfxEvent(text="WHOOOSH", arc=90), dialogue_size=30, typeface=self.FAMILY
        )
        ys = [glyph.origin.y for glyph in shape.glyphs]
        angles = [glyph.angle for glyph in shape.glyphs]
        assert min(ys[2:5]) < ys[0]
        assert min(ys[2:5]) < ys[-1]
        assert angles[0] < 0 < angles[-1]

    def test_a_negative_arc_bows_it_downward(self):
        shape = layout_effect(
            SfxEvent(text="WHOOOSH", arc=-90), dialogue_size=30, typeface=self.FAMILY
        )
        ys = [glyph.origin.y for glyph in shape.glyphs]
        assert max(ys[2:5]) > ys[0]
        assert max(ys[2:5]) > ys[-1]

    def test_the_footprint_holds_every_letter(self):
        shape = layout_effect(
            SfxEvent(text="SPLAT", arc=-60, rotate=30), dialogue_size=30, typeface=self.FAMILY
        )
        for glyph in shape.glyphs:
            assert shape.footprint.buffer(1).contains(ShapelyPoint(glyph.origin.x, glyph.origin.y))

    def test_it_is_centred_on_its_own_origin(self):
        shape = layout_effect(SfxEvent(text="BLAM"), dialogue_size=30, typeface=self.FAMILY)
        centre = shape.footprint.centroid
        assert math.hypot(centre.x, centre.y) < shape.font_size * 0.2


class TestCoreAndDrawing:
    SCRIPT = (
        "  - sfx: {text: BLAM, from: bob, rotate: -12}\n  - say: {by: alice, text: Get down!}\n"
    )

    def test_it_survives_a_round_trip(self):
        core = _core(self.SCRIPT)
        assert PanelCore.from_json(core.to_json()) == core

    def test_it_is_deterministic(self):
        assert _core(self.SCRIPT).to_json() == _core(self.SCRIPT).to_json()
        assert render(_core(self.SCRIPT)) == render(_core(self.SCRIPT))

    def test_it_is_drawn_as_outlines_under_the_balloons(self):
        core = _core(self.SCRIPT)
        svg = render(core)
        assert svg.index('id="sfx-s0"') < svg.index('id="balloon-b0"')
        group = svg[svg.index('id="sfx-s0"') : svg.index("</g>", svg.index('id="sfx-s0"'))]
        assert group.count("<path") == 4
        assert 'paint-order="stroke"' in group
        assert_svg_is_sound(
            svg,
            size=(core.width, core.height),
            font_sizes=[core.balloons[0].font_size, core.sfx[0].font_size],
        )

    def test_a_solid_effect_is_ink_with_a_paper_halo(self):
        effect = _core(self.SCRIPT).sfx[0]
        assert (effect.fill, effect.stroke, effect.hollow) == ("#111111", "#ffffff", False)

    def test_a_hollow_effect_is_all_outline_and_no_fill(self):
        core = _core("  - sfx: {text: BLAM, from: bob, hollow: true}\n")
        assert (core.sfx[0].fill, core.sfx[0].stroke) == ("none", "#111111")
        assert 'fill="none"' in render(core)

    def test_live_text_still_draws_it_as_outlines(self):
        svg = render(_core(self.SCRIPT), live_text=True)
        assert ">BLAM<" not in svg
        assert 'id="sfx-s0"' in svg

    def test_the_overlay_shows_the_zone_balloons_paid_to_avoid(self):
        assert 'class="sfx-zone"' in render_debug(_core(self.SCRIPT))

    def test_an_authors_display_face_is_used(self, tmp_path: Path):
        """Source Sans Semibold stands in for an author's own display face."""
        folder = tmp_path / "fonts"
        folder.mkdir()
        (folder / "Shout.ttf").write_bytes(SEMIBOLD.read_bytes())
        document = tmp_path / "loud.panel.yaml"
        document.write_text(
            f"lettering: {{font: {{regular: fonts/Shout.ttf, display: fonts/Shout.ttf}}}}\n"
            f"{PANEL}script:\n  - sfx: {{text: BLAM, from: bob}}\n",
            encoding="utf-8",
        )
        result = compile_file(document)
        assert result.core.fonts[Face.DISPLAY].family == "Source Sans Pro Semibold"
        assert render(result.core, fonts=result.fonts)
