"""Panels whose people a supplied picture draws, declared in an artwork contract (#71).

The checklist #71 set: a balloon never touches a declared face, a tail ends at the
declared mouth, a keep-out costs but does not forbid, staging on a figure is a finding, and
the output is byte-identical -- with each fault a single finding, where the author can
see it, in `scenet check` and in `build` alike.
"""

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scenet import compile_source
from scenet.core import PanelCore
from scenet.diagnostics import Diagnostic, diagnose_file, diagnose_script, diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import render
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_panel
from scenet.geom import BBox
from scenet.pipeline import compile_ir, compile_script
from tests.images import contract, png
from tests.invariants import assert_effects_are_placed, assert_lettering_is_placed

FIGURES = {
    "ana": {
        "face": {"center": [250, 180], "radius": 50},
        "mouth": [255, 210],
        "body": [[180, 140], [320, 140], [340, 600], [160, 600]],
    },
    "ben": {"face": {"center": [650, 170], "radius": 45}, "mouth": [645, 200]},
    "carl": {"face": {"center": [450, 300], "radius": 30}},
}
KEEP_OUT = [[(380, 420), (520, 420), (520, 560), (380, 560)]]
#: Figures that fit on a smaller export, for a contract measured on one.
SMALL = {"ana": {"face": {"center": [100, 100], "radius": 20}}}


def _files(
    figures: Mapping[str, Mapping[str, object]] | None = None,
    keep_out: Sequence[Sequence[tuple[float, float]]] | None = None,
    size: tuple[int, int] = (900, 600),
) -> dict[str, bytes]:
    return {
        "art/p.png": png(900, 600),
        "art/p.art.yaml": contract(
            size,
            FIGURES if figures is None else figures,
            KEEP_OUT if keep_out is None else keep_out,
        ),
    }


PANEL = """panel: {size: [1200, 600]}
cast:
  ANA: {figure: ana}
  BEN: {figure: ben}
setting: {image: art/p.png}
script:
  - caption: {text: "Later that night.", kind: locale}
  - say: {by: ANA, text: "Where are we?"}
  - say: {by: BEN, text: "Somewhere they won't look."}
"""


def _core(
    source: str = PANEL,
    *,
    figures: Mapping[str, Mapping[str, object]] | None = None,
    keep_out: Sequence[Sequence[tuple[float, float]]] | None = None,
) -> PanelCore:
    return compile_source(source, base=_files(figures, keep_out)).core


def _one(found: list[Diagnostic], rule: str) -> Diagnostic:
    assert [item.rule for item in found] == [rule], [(item.rule, item.message) for item in found]
    return found[0]


def _line(text: str, found: Diagnostic) -> str:
    assert found.region is not None
    return text.splitlines()[found.region.start.line - 1]


class TestTheLetteringKeepsItsPromises:
    def test_no_box_touches_a_declared_face_cast_or_not(self):
        core = _core(PANEL + '  - sfx: {text: "KRAK", from: BEN}\n')
        assert len(core.face_exclusions()) == 3
        assert_lettering_is_placed(core)
        assert_effects_are_placed(core)
        assert core.sfx

    def test_every_tail_is_aimed_at_its_speakers_declared_mouth(self):
        core = _core()
        for balloon in core.balloons:
            face, mouth = core.speaker(balloon.speaker)
            (sx, sy), (ex, ey) = balloon.tail.start, balloon.tail.end
            # On the face's edge, on the line from where it starts to the mouth.
            assert math.hypot(ex - face.cx, ey - face.cy) == pytest.approx(face.r, abs=0.02)
            cross = (ex - sx) * (mouth[1] - sy) - (ey - sy) * (mouth[0] - sx)
            assert abs(cross) < 0.05 * math.hypot(mouth[0] - sx, mouth[1] - sy) * 2

    def test_a_tail_ends_exactly_at_a_mouth_outside_the_face(self):
        figures = {"ana": {"face": {"center": [250, 180], "radius": 50}, "mouth": [250, 320]}}
        core = _core(
            "panel: {size: [1200, 600]}\ncast: {ANA: {figure: ana}}\n"
            "setting: {image: art/p.png}\nscript: [{say: {by: ANA, text: Hello.}}]\n",
            figures=figures,
            keep_out=[],
        )
        assert core.balloons[0].tail.end == core.speaker("ANA").mouth

    def test_a_keep_out_costs_and_moves_a_balloon_off_it(self):
        free = _core(keep_out=[])
        balloon = free.balloons[0].box
        # Its box, in the picture's pixels: the fit scales by 4/3 and crops 100 off the top.
        region = [
            ((x - 0.0) * 0.75, (y + 100.0) * 0.75)
            for x, y in (
                (balloon.x, balloon.y),
                (balloon.right, balloon.y),
                (balloon.right, balloon.bottom),
                (balloon.x, balloon.bottom),
            )
        ]
        kept = _core(keep_out=[region])
        assert kept.balloons[0].box.as_bbox().overlap_area(balloon.as_bbox()) == 0

    def test_a_keep_out_never_forbids(self):
        whole = [[(0, 0), (900, 0), (900, 600), (0, 600)]]
        core = _core(keep_out=whole)
        assert len(core.balloons) == 2
        assert_lettering_is_placed(core)


class TestNothingIsStagedAndNobodyIsPosed:
    def test_no_camera_and_no_actor(self):
        result = compile_source(PANEL, base=_files())
        assert result.camera is None
        assert result.placements == ()
        assert result.core.actors == ()

    def test_the_figures_are_recorded_with_the_parts_they_play(self):
        core = _core()
        assert [(figure.figure, figure.actor) for figure in core.figures] == [
            ("ana", "ANA"),
            ("ben", "BEN"),
            ("carl", None),
        ]
        payload = json.loads(core.to_json())
        assert "actor" not in payload["figures"][2]
        assert payload["backdrop"]["image"]["keep_out"][0][0] == [506.67, 460.0]

    def test_the_description_names_who_is_drawn_and_no_shot(self):
        assert _core().description == "ANA, left; BEN, right."

    def test_the_svg_draws_the_picture_and_nobody_else(self):
        core = _core()
        svg = render(core)
        assert 'xlink:href="art/p.png"' in svg
        assert "figure" not in svg.lower().replace("figures", "")
        assert "debug-figure-ana" in render_debug(core)

    def test_a_cast_member_the_picture_does_not_draw_is_simply_not_there(self):
        source = PANEL.replace(
            "  BEN: {figure: ben}\n", "  BEN: {figure: ben}\n  DOT: {figure: dot}\n"
        )
        core = _core(source)
        assert {figure.actor for figure in core.figures} == {"ANA", "BEN", None}
        assert "DOT" not in (core.description or "")


class TestEachFaultIsOneFinding:
    """Located where the author can see it, and the same in `check` as in `build`."""

    def _agree(self, source: str, files: dict[str, bytes], rule: str) -> Diagnostic:
        """`check` reports one finding, and `build` refuses the panel for the same reason.

        A fault the IR's own validators find reaches `build` inside pydantic's summary,
        "invalid panel: at ...", as every such fault always has; its sentence is the same.
        """
        found = _one(diagnose_source(source, base=files), rule)
        with pytest.raises(PanelSyntaxError) as caught:
            compile_source(source, base=files)
        assert caught.value.rule in (rule, None)
        assert found.message.split(";")[0] in str(caught.value)
        return found

    def test_staging_on_a_figure(self):
        source = PANEL.replace("setting:", "staging: [ANA left_of BEN]\nsetting:")
        found = self._agree(source, _files(), "figure-staging")
        assert found.path == ("staging", 0)
        assert "ANA left_of BEN" in _line(source, found)

    def test_a_camera_over_figures(self):
        source = "camera: {shot: close_up}\n" + PANEL
        found = self._agree(source, _files(), "figure-staging")
        assert found.path == ("camera", "shot")

    @pytest.mark.parametrize(
        "key",
        [
            "reference: alice",
            "pose: pointing",
            "facing: right",
            "at: center",
            "marks: [plewds]",
            "expression: angry",
        ],
    )
    def test_a_puppets_key_on_a_figure(self, key: str):
        source = PANEL.replace("ANA: {figure: ana}", f"ANA: {{figure: ana, {key}}}")
        found = self._agree(source, _files(), "conflicting-cast")
        assert found.path == ("cast", "ANA", key.split(":", maxsplit=1)[0])

    def test_a_mixed_cast(self):
        source = PANEL.replace("BEN: {figure: ben}", "BEN: {reference: bob}")
        found = self._agree(source, _files(), "conflicting-cast")
        assert found.path == ("cast", "BEN", "reference")

    def test_two_parts_for_one_figure(self):
        source = PANEL.replace("BEN: {figure: ben}", "BEN: {figure: ana}")
        assert self._agree(source, _files(), "conflicting-cast").path == ("cast", "BEN", "figure")

    def test_a_figure_with_no_picture(self):
        source = "cast: {ANA: {figure: ana}}\n"
        found = self._agree(source, {}, "unknown-figure")
        assert found.path == ("cast", "ANA", "figure")

    def test_a_line_spoken_by_a_figure_the_picture_does_not_draw(self):
        source = PANEL.replace("BEN: {figure: ben}", "BEN: {figure: bne}")
        found = self._agree(source, _files(), "unknown-figure")
        assert found.path == ("script", 2, "say", "by")
        assert "ana, ben, carl" in found.message
        assert "by: BEN" in _line(source, found)

    def test_a_missing_contract_is_reported_where_the_picture_is_named(self):
        files = {"art/p.png": png(900, 600)}
        found = self._agree(PANEL, files, "artwork-contract")
        assert found.path == ("setting", "image")
        assert "art/p.art.yaml" in found.message

    def test_a_fault_inside_the_contract_names_its_line_when_checked_as_text(self):
        found = self._agree(PANEL, _files(SMALL, [], size=(600, 400)), "artwork-contract")
        assert found.path == ("setting", "image")
        assert "'art/p.art.yaml', line 1" in found.message
        assert "image" in _line(PANEL, found)


class TestCheckedAsAFile:
    """A fault inside a contract is reported in the contract, which the author can open."""

    def _write(self, folder: Path, *, size: tuple[int, int] = (600, 400)) -> Path:
        (folder / "art").mkdir()
        (folder / "art" / "p.png").write_bytes(png(900, 600))
        figures = FIGURES if size == (900, 600) else SMALL
        (folder / "art" / "p.art.yaml").write_bytes(contract(size, figures))
        document = folder / "p.panel.yaml"
        document.write_text(PANEL, encoding="utf-8")
        return document

    def test_in_the_contract_at_its_line(self, tmp_path: Path):
        document = self._write(tmp_path)
        found = _one(diagnose_file(document), "artwork-contract")
        assert found.source == tmp_path / "art" / "p.art.yaml"
        assert found.path == ("size",)
        assert found.region is not None
        assert found.region.start.line == 1

    def test_once_however_many_panels_read_it(self, tmp_path: Path):
        self._write(tmp_path)
        scene = tmp_path / "s.scene.yaml"
        scene.write_text(
            "cast: {ANA: {figure: ana}}\nsetting: {image: art/p.png}\n"
            "panels:\n  one: {panel: {size: [1200, 600]}}\n  two: {panel: {size: [600, 600]}}\n",
            encoding="utf-8",
        )
        found = _one(diagnose_file(scene), "artwork-contract")
        assert found.source == tmp_path / "art" / "p.art.yaml"

    def test_a_valid_file_compiles_and_checks_clean(self, tmp_path: Path):
        document = self._write(tmp_path, size=(900, 600))
        assert diagnose_file(document, deep=True) == []


class TestInAComicScript:
    SCRIPT = """---
cast:
  ANA: {figure: ana}
  BEN: {figure: ben}
---

PAGE ONE

PANEL 1
@setting: {image: art/p.png}

ANA: Where are we?

PANEL 2
@setting: {image: art/q.png}

ANA: Over here.

BEN: Wait.
"""

    def _files(self) -> dict[str, bytes]:
        only_ana = {"ana": FIGURES["ana"]}
        return {
            **_files(),
            "art/q.png": png(900, 600),
            "art/q.art.yaml": contract((900, 600), only_ana),
        }

    def test_a_panel_holds_the_figures_its_picture_draws(self):
        script = self.SCRIPT.replace("\nBEN: Wait.\n", "")
        book = compile_script(script, base=self._files())
        first, second = book.panels.values()
        assert {f.actor for f in first.core.figures} == {"ANA", "BEN", None}
        assert {f.actor for f in second.core.figures} == {"ANA"}

    def test_a_line_by_a_figure_its_panels_picture_does_not_draw_is_found_at_its_line(self):
        found = _one(diagnose_script(self.SCRIPT, base=self._files()), "unknown-figure")
        assert found.path == ("2", "script", 1, "say", "by")
        assert _line(self.SCRIPT, found) == "BEN: Wait."


class TestInAScene:
    def test_over_turns_a_puppet_into_a_figure_only_with_reference_null(self):
        scene = (
            "cast: {ANA: {reference: alice}}\n"
            "panels:\n"
            "  one: {panel: {size: [600, 600]}}\n"
            "  two:\n"
            "    over: one\n"
            "    panel: {size: [1200, 600]}\n"
            "    cast: {ANA: {figure: ana}}\n"
            "    setting: {image: art/p.png}\n"
        )
        found = _one(diagnose_source(scene, base=_files()), "conflicting-cast")
        # The puppet was written in the scene's defaults, so that is where it is reported.
        assert found.path == ("cast", "ANA", "reference")
        fixed = scene.replace("{figure: ana}", "{figure: ana, reference: null}")
        assert diagnose_source(fixed, base=_files()) == []


class TestDeterminism:
    def test_the_same_bytes_twice_and_from_a_folder(self, tmp_path: Path):
        first = _core()
        assert _core().to_json() == first.to_json()
        for name, data in _files().items():
            (tmp_path / name).parent.mkdir(exist_ok=True)
            (tmp_path / name).write_bytes(data)
        from_folder = compile_source(PANEL, base=tmp_path).core
        assert from_folder.to_json() == first.to_json()
        assert render(from_folder) == render(first)


class TestACoverCropAndAnInset:
    def test_a_mouth_cropped_out_of_the_panel_gets_a_tail_to_the_frame_and_a_note(self):
        # A wide panel crops the picture top and bottom; this mouth is in the cropped band.
        figures = {"ana": {"face": {"center": [450, 40], "radius": 30}, "mouth": [450, 5]}}
        source = (
            "panel: {size: [1200, 400]}\ncast: {ANA: {figure: ana}}\n"
            "setting: {image: art/p.png}\nscript: [{say: {by: ANA, text: Up here.}}]\n"
        )
        result = compile_source(source, base=_files(figures=figures, keep_out=[]))
        tail = result.core.balloons[0].tail
        assert tail.end[1] == pytest.approx(0.0, abs=0.01)
        assert any("mouth is outside the panel" in note for note in result.notes)

    def test_an_inset_over_a_figures_face_is_noted(self):
        panel = parse_panel(PANEL)
        face = _core().figures[2].face_exclusion  # carl, whom nobody cast
        inset = BBox(face.cx - 10, face.cy - 10, 20, 20)
        result = compile_ir(panel, base=_files(), exclusions=[inset])
        assert any("an inset covers carl's face" in note for note in result.notes)
