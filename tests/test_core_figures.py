"""Figures a picture draws, recorded in Panel Core and drawn by the debug overlay (#71)."""

import json
from pathlib import Path

import pytest

from scenet import compile_source
from scenet.core import CORE_FORMAT_VERSION, CoreFigure, Disc, PanelCore, Speaking
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import render
from tests.images import png

GOLDEN = Path(__file__).resolve().parent / "golden" / "core"

ANA = CoreFigure(
    figure="ana",
    actor="ANA",
    face_exclusion=Disc(cx=300.0, cy=200.0, r=40.0),
    mouth=(305.0, 225.0),
    body=((250.0, 180.0), (350.0, 180.0), (360.0, 600.0), (240.0, 600.0)),
)
BEN = CoreFigure(figure="ben", face_exclusion=Disc(cx=800.0, cy=210.0, r=35.0))
KEEP_OUT = (((20.0, 400.0), (200.0, 400.0), (200.0, 560.0), (20.0, 560.0)),)


def _picture_core() -> PanelCore:
    """A panel over a picture, as #70 compiles it, with nothing of #71 in it."""
    return compile_source(
        "panel: {size: [1200, 600]}\ncast: {a: {reference: alice}}\nsetting: {image: art/a.png}\n",
        base={"art/a.png": png(900, 600)},
    ).core


def _with_figures(core: PanelCore) -> PanelCore:
    assert core.backdrop is not None
    assert core.backdrop.image is not None
    image = core.backdrop.image.model_copy(update={"keep_out": KEEP_OUT})
    backdrop = core.backdrop.model_copy(update={"image": image})
    return core.model_copy(update={"figures": (ANA, BEN), "backdrop": backdrop})


class TestTheShape:
    def test_a_figure_writes_only_what_it_has(self):
        payload = json.loads(_with_figures(_picture_core()).to_json())
        ana, ben = payload["figures"]
        assert ana == {
            "figure": "ana",
            "actor": "ANA",
            "face_exclusion": {"cx": 300.0, "cy": 200.0, "r": 40.0},
            "mouth": [305.0, 225.0],
            "body": [[250.0, 180.0], [350.0, 180.0], [360.0, 600.0], [240.0, 600.0]],
        }
        assert ben == {"figure": "ben", "face_exclusion": {"cx": 800.0, "cy": 210.0, "r": 35.0}}
        assert payload["backdrop"]["image"]["keep_out"] == [
            [[20.0, 400.0], [200.0, 400.0], [200.0, 560.0], [20.0, 560.0]]
        ]

    def test_a_panel_without_them_writes_neither_key(self):
        payload = json.loads(_picture_core().to_json())
        assert "figures" not in payload
        assert "keep_out" not in payload["backdrop"]["image"]

    def test_the_format_version_stays(self):
        assert json.loads(_with_figures(_picture_core()).to_json())["format_version"] == 1
        assert CORE_FORMAT_VERSION == 1

    def test_it_reads_back_byte_for_byte(self):
        core = _with_figures(_picture_core())
        text = core.to_json()
        assert PanelCore.from_json(text) == core
        assert PanelCore.from_json(text).to_json() == text

    @pytest.mark.parametrize(
        "path",
        sorted(path for path in GOLDEN.glob("*.core.json") if ".page-" not in path.name),
        ids=lambda p: p.name,
    )
    def test_every_core_written_before_figures_reads_and_writes_as_it_did(self, path: Path):
        text = path.read_text(encoding="utf-8")
        assert PanelCore.from_json(text).to_json() == text

    def test_an_unknown_key_on_a_figure_is_refused(self):
        payload = json.loads(_with_figures(_picture_core()).to_json())
        payload["figures"][0]["pose"] = "pointing"
        with pytest.raises(ValueError, match="pose"):
            PanelCore.model_validate(payload)


class TestWhoIsInIt:
    def test_every_face_actors_and_figures_alike(self):
        core = _with_figures(_picture_core())
        faces = core.face_exclusions()
        assert faces[0] == core.actors[0].face_exclusion
        assert faces[1:] == (ANA.face_exclusion, BEN.face_exclusion)

    def test_a_speaker_drawn_by_the_picture_is_found_by_the_part_it_plays(self):
        core = _with_figures(_picture_core())
        assert core.speaker("ANA") == Speaking(ANA.face_exclusion, (305.0, 225.0))

    def test_a_puppet_is_found_by_its_id_and_spoken_from_its_mouth(self):
        core = _picture_core()
        actor = core.actors[0]
        assert core.speaker("a") == Speaking(actor.face_exclusion, actor.anchors["mouth"])

    def test_a_figure_with_no_mouth_is_spoken_from_its_face(self):
        core = _picture_core().model_copy(
            update={"figures": (BEN.model_copy(update={"actor": "BEN"}),)}
        )
        assert core.speaker("BEN") == Speaking(BEN.face_exclusion, (800.0, 210.0))

    def test_a_figure_nobody_cast_plays_no_part(self):
        core = _with_figures(_picture_core())
        with pytest.raises(KeyError, match="ben"):
            core.speaker("ben")


class TestDrawing:
    def test_the_svg_draws_no_figure(self):
        """The picture draws them; Scenet draws only what it drew before."""
        core = _picture_core()
        assert render(_with_figures(core)) == render(core)

    def test_the_overlay_draws_each_figure_and_keep_out(self):
        overlay = render_debug(_with_figures(_picture_core()))
        assert '<g id="debug-figure-ana">' in overlay
        assert '<g id="debug-figure-ben">' in overlay
        assert "figure ana as ANA" in overlay
        assert "figure ben (not cast)" in overlay
        assert '<circle cx="300" cy="200" r="40"' in overlay
        assert ">mouth</text>" in overlay
        assert 'class="keep-out" points="20,400 200,400 200,560 20,560"' in overlay
        assert "keep out 0" in overlay

    def test_a_figure_with_no_body_or_mouth_draws_only_its_face(self):
        core = _picture_core().model_copy(update={"figures": (BEN,)})
        overlay = render_debug(core)
        group = overlay.split('<g id="debug-figure-ben">')[1].split("</g>")[0]
        assert "<polygon" not in group
        assert "mouth" not in group
        assert '<circle cx="800" cy="210" r="35"' in group

    def test_the_overlay_without_figures_is_unchanged(self):
        core = _picture_core()
        assert "figure" not in render_debug(core)
        assert "keep-out" not in render_debug(core)

    def test_ids_take_the_prefix(self):
        overlay = render_debug(_with_figures(_picture_core()), id_prefix="p1-")
        assert '<g id="p1-debug-figure-ana">' in overlay
