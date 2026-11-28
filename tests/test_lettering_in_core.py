"""Lettering is placed in Panel Core, and an emitter only looks glyphs up (#434).

Core is "resolved, numeric, ready to emit", and for text it was not: it stored the lines, and
every emitter laid the glyphs out again, with Scenet's kerning reader, a baseline constant and
a centring rule. These tests hold the other arrangement: the solver writes down where every
line and every letter sits, and an emitter draws what it was told.
"""

import ast
import itertools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scenet.core import CoreLine, PageCore, PanelCore
from scenet.emit.debug_svg import render_debug
from scenet.emit.pdf import render_pdf
from scenet.emit.svg import render
from scenet.errors import CoreSyntaxError
from scenet.pipeline import compile_source
from scenet.solve.text import FontMetrics, load_metrics
from tests.under_mutmut import reads_the_source

ROOT = Path(__file__).parent.parent
EMIT = ROOT / "src" / "scenet" / "emit"
GOLDEN = ROOT / "tests" / "golden" / "core"

PANEL = (
    "cast: {alice: {reference: alice}}\n"
    "script:\n"
    "  - say: {by: alice, text: 'Hello _there_, friend. AVAST, the Tower!'}\n"
    "  - caption: {text: 'Later that day.'}\n"
)


def _core() -> PanelCore:
    return compile_source(PANEL).core


class TestNothingUnderEmitMeasuresText:
    """The layering: layout arithmetic is the solver's, and no emitter can redo it."""

    @staticmethod
    def _modules() -> list[Path]:
        return sorted(EMIT.glob("*.py"))

    @reads_the_source
    def test_no_emitter_imports_text_measurement_from_the_solver(self):
        # A face handle, to look outlines up in, is all an emitter takes from `solve.text`.
        allowed = {"FontMetrics"}
        found: list[str] = []
        for path in self._modules():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module == "scenet.solve.text":
                    found += [
                        f"{path.name}: {alias.name}"
                        for alias in node.names
                        if alias.name not in allowed
                    ]
                if isinstance(node, ast.Import):
                    found += [
                        f"{path.name}: {alias.name}"
                        for alias in node.names
                        if alias.name == "scenet.solve.text"
                    ]
        assert found == []

    @reads_the_source
    def test_no_emitter_asks_a_face_for_a_step_a_kerning_or_a_width_of_text(self):
        forbidden = {"step", "kerning", "measure", "glyph_outlines"}
        found = [
            f"{path.name}:{node.lineno} .{node.func.attr}()"
            for path in self._modules()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden
        ]
        assert found == []

    @reads_the_source
    def test_geometry_is_shape_geometry_only(self):
        tree = ast.parse((EMIT / "geometry.py").read_text(encoding="utf-8"))
        defined = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.ClassDef)
        }
        assert not defined & {"baselines", "line_width", "centred", "glyph_walk", "PlacedRun"}
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "scenet.solve.text"
            for node in ast.walk(tree)
        )


def _broken(*_arguments: object, **_keywords: object) -> Any:
    raise AssertionError("an emitter read the kerning of a face")


def _golden_panels() -> list[Path]:
    return [
        path
        for path in sorted(GOLDEN.glob("*.core.json"))
        if json.loads(path.read_text(encoding="utf-8")).get("format") == "scenet.panel"
    ]


def _rendered(core: PanelCore) -> tuple[object, ...]:
    # A print PDF of a panel over a picture needs the picture's bytes, which a Core does not hold.
    drawn = core.backdrop is not None and core.backdrop.image is not None
    return (
        render(core),
        render(core, live_text=True),
        render_debug(core),
        None if drawn else render_pdf([], {"panel": core}),
        None if drawn else render_pdf([], {"panel": core}, live_text=True),
    )


class TestAnEmitterNeedsNoKerningReader:
    """What is drawn does not depend on how Scenet reads a font's pair adjustments."""

    def test_every_golden_core_is_drawn_the_same_with_a_kerning_reader_that_cannot_be_used(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        panels = _golden_panels()
        assert len(panels) > 100
        cores = [PanelCore.from_json(path.read_text(encoding="utf-8")) for path in panels]
        # A Core lettered in a font of its own is drawn from the font handed back with it,
        # which a golden file does not carry.
        cores = [core for core in cores if not core.fonts]
        assert len(cores) > 100
        before = [_rendered(core) for core in cores]
        for name in ("step", "kerning", "measure", "glyph_outlines", "_pair"):
            monkeypatch.setattr(FontMetrics, name, _broken)
        after = [_rendered(core) for core in cores]
        assert after == before

    def test_the_letters_sit_where_the_core_says_not_where_the_font_would_put_them(self):
        core = _core()
        payload = json.loads(core.to_json())
        payload["balloons"][0]["setting"][0]["offsets"][0][1] += 40.0
        moved = PanelCore.from_json(json.dumps(payload))
        assert render(moved) != render(core)


def _shifted(core: PanelCore, how: Callable[[dict[str, Any]], None]) -> str:
    payload = json.loads(core.to_json())
    how(payload)
    return json.dumps(payload)


class TestCoreSaysWhereEveryLetterIs:
    def test_a_line_has_an_origin_a_width_and_an_offset_for_every_character(self):
        core = _core()
        balloon = core.balloons[0]
        assert len(balloon.setting) == len(balloon.lines)
        for text, line, cut in zip(balloon.lines, balloon.setting, balloon.runs, strict=True):
            assert len(line.offsets) == len(cut)
            for run, offsets in zip(cut, line.offsets, strict=True):
                assert len(offsets) == len(run.text)
            assert line.offsets[0][0] == 0.0
            assert line.width > 0.0
            assert "".join(run.text for run in cut) == text

    def test_a_line_without_emphasis_has_one_run_of_all_its_characters(self):
        caption = _core().captions[0]
        for text, line in zip(caption.lines, caption.setting, strict=True):
            assert [len(offsets) for offsets in line.offsets] == [len(text)]

    def test_the_offsets_are_what_the_font_measured_to_a_hundredth(self):
        metrics = load_metrics()
        balloon = _core().balloons[0]
        line = balloon.setting[0]
        text = "".join(run.text for run in balloon.runs[0])
        if len(balloon.runs[0]) == 1:
            cursor = 0.0
            for index, character in enumerate(text):
                assert line.offsets[0][index] == pytest.approx(cursor, abs=0.011)
                cursor += (
                    metrics.step(character, text[index + 1] if index + 1 < len(text) else None)
                    * balloon.font_size
                )

    def test_a_balloons_line_is_centred_and_a_captions_is_flush_left_inside_its_padding(self):
        core = _core()
        balloon = core.balloons[0]
        for line in balloon.setting:
            left = line.origin[0] - balloon.box.x
            right = balloon.box.x + balloon.box.width - (line.origin[0] + line.width)
            assert left == pytest.approx(right, abs=0.011)
        caption = core.captions[0]
        padding = (caption.box.height - len(caption.lines) * caption.line_height) / 2
        assert caption.setting[0].origin[0] == pytest.approx(caption.box.x + padding, abs=0.011)

    def test_the_inner_margin_of_a_balloon_is_read_from_core_alone(self):
        balloon = _core().balloons[0]
        margins = [
            min(
                line.origin[0] - balloon.box.x,
                balloon.box.x + balloon.box.width - line.origin[0] - line.width,
            )
            for line in balloon.setting
        ]
        assert all(margin > 0 for margin in margins)

    def test_baselines_are_a_line_height_apart(self):
        balloon = _core().balloons[0]
        ys = [line.origin[1] for line in balloon.setting]
        for upper, lower in itertools.pairwise(ys):
            assert lower - upper == pytest.approx(balloon.line_height, abs=0.011)

    def test_what_is_stored_is_rounded_and_survives_a_round_trip(self):
        core = _core()
        again = PanelCore.from_json(core.to_json())
        assert again == core
        assert again.to_json() == core.to_json()
        for line in core.balloons[0].setting:
            for value in (*line.origin, line.width, *(o for run in line.offsets for o in run)):
                assert value == round(value, 2)

    def test_glyph_ids_are_left_out_until_text_is_shaped(self):
        text = _core().to_json()
        assert "glyph_ids" not in text
        line = CoreLine(origin=(1.0, 2.0), width=3.0, offsets=((0.0, 1.0),), glyph_ids=((4, 5),))
        assert json.loads(line.model_dump_json())["glyph_ids"] == [[4, 5]]

    def test_every_golden_core_names_the_setting_of_every_line(self):
        for path in _golden_panels():
            core = PanelCore.from_json(path.read_text(encoding="utf-8"))
            for lettered in (*core.balloons, *core.captions):
                assert len(lettered.setting) == len(lettered.lines), path.name

    def test_a_page_core_is_not_a_panel_core_and_still_reads(self):
        pages = [
            path
            for path in sorted(GOLDEN.glob("*.core.json"))
            if json.loads(path.read_text(encoding="utf-8")).get("format") == "scenet.page"
        ]
        assert pages
        assert PageCore.from_json(pages[0].read_text(encoding="utf-8"))


class TestACoreThatDoesNotAddUp:
    def test_a_line_without_its_setting_is_refused(self):
        def how(payload: dict[str, Any]) -> None:
            payload["balloons"][0]["setting"].pop()

        with pytest.raises(CoreSyntaxError, match="setting"):
            PanelCore.from_json(_shifted(_core(), how))

    def test_an_offset_missing_for_a_character_is_refused(self):
        def how(payload: dict[str, Any]) -> None:
            payload["balloons"][0]["setting"][0]["offsets"][0].pop()

        with pytest.raises(CoreSyntaxError, match="offsets"):
            PanelCore.from_json(_shifted(_core(), how))

    def test_glyph_ids_that_do_not_pair_with_the_offsets_are_refused(self):
        def how(payload: dict[str, Any]) -> None:
            payload["balloons"][0]["setting"][0]["glyph_ids"] = [[1]]

        with pytest.raises(CoreSyntaxError, match="glyph_ids"):
            PanelCore.from_json(_shifted(_core(), how))
