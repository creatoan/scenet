"""The boxes export: each figure's extent with a phrase, GLIGEN style (#72).

"This entity, here": a phrase and a box per actor and per figure a picture draws, the box as
`[xmin, ymin, xmax, ymax]` fractions of the panel -- what diffusers' GLIGEN pipeline takes.
The phrase is templated from Panel Core with the description's own words, so a figure is never
said one way to a reader and another way to a model.
"""

import json
from typing import Any

from scenet.core import PanelCore
from scenet.emit.boxes import render_boxes
from scenet.pipeline import compile_source
from tests.images import contract, png

DUEL = """\
panel: {size: [1000, 800]}
camera: {shot: full_shot}
cast:
  alice: {reference: alice, pose: pointing, expression: angry, marks: [plewds]}
  bob: {reference: bob, facing: left}
staging: [alice left_of bob]
"""


def _boxes(core: PanelCore) -> list[dict[str, Any]]:
    return json.loads(render_boxes(core))["boxes"]


def _fractions(core: PanelCore, points: tuple[tuple[float, float], ...]) -> list[float]:
    xs = [min(max(x, 0.0), core.width) / core.width for x, _ in points]
    ys = [min(max(y, 0.0), core.height) / core.height for _, y in points]
    return [round(value, 4) for value in (min(xs), min(ys), max(xs), max(ys))]


class TestActors:
    def test_one_box_per_actor_in_panel_core_s_order(self):
        core = compile_source(DUEL).core
        assert [box["id"] for box in _boxes(core)] == [actor.id for actor in core.actors]

    def test_the_box_is_the_hull_s_bounds_as_fractions_of_the_panel(self):
        core = compile_source(DUEL).core
        for actor, box in zip(core.actors, _boxes(core), strict=True):
            assert box["box"] == _fractions(core, actor.hull)

    def test_the_phrase_says_what_the_description_says(self):
        """Name, pose, expression and marks, in the description's words; left and right are
        the box's to say."""
        core = compile_source(DUEL).core
        phrases = {box["id"]: box["phrase"] for box in _boxes(core)}
        assert phrases == {"alice": "Alice, pointing, angry, sweating", "bob": "Bob"}
        assert core.description is not None
        assert "Alice, left, pointing, angry, sweating" in core.description

    def test_a_box_is_clipped_to_the_panel(self):
        """A close-up's body runs off the bottom; the box stops at the frame."""
        core = compile_source(DUEL.replace("full_shot", "close_up")).core
        assert max(y for _, y in core.actors[0].hull) > core.height
        for box in _boxes(core):
            xmin, ymin, xmax, ymax = box["box"]
            assert 0.0 <= xmin < xmax <= 1.0
            assert 0.0 <= ymin < ymax <= 1.0
        assert _boxes(core)[0]["box"][3] == 1.0

    def test_an_actor_wholly_outside_the_panel_has_no_box(self):
        core = compile_source(DUEL).core
        alice = core.actor("alice")
        gone = alice.model_copy(update={"hull": tuple((x, y + 2000.0) for x, y in alice.hull)})
        core = core.model_copy(update={"actors": (gone, *core.actors[1:])})
        assert [box["id"] for box in _boxes(core)] == ["bob"]

    def test_marks_and_sound_effects_are_not_in_the_box(self):
        """The hull leaves emanata out so a sweating figure never moves; the box follows it."""
        plain = compile_source(DUEL.replace(", marks: [plewds]", "")).core
        sweating = compile_source(DUEL).core
        assert [box["box"] for box in _boxes(plain)] == [box["box"] for box in _boxes(sweating)]


FIGURES = {
    "ana": {
        "face": {"center": [250, 180], "radius": 50},
        "body": [[180, 140], [320, 140], [340, 600], [160, 600]],
    },
    "ben": {"face": {"center": [650, 170], "radius": 45}},
}


def _figures() -> PanelCore:
    return compile_source(
        "panel: {size: [900, 600]}\nsetting: {image: art/p.png, fit: contain}\n"
        "cast: {ANA: {figure: ana}}\n",
        base={"art/p.png": png(900, 600), "art/p.art.yaml": contract((900, 600), FIGURES)},
    ).core


class TestFiguresAPictureDraws:
    def test_every_figure_has_a_box_cast_or_not(self):
        core = _figures()
        assert [box["id"] for box in _boxes(core)] == ["ana", "ben"]

    def test_the_box_holds_its_body_and_its_face(self):
        core = _figures()
        ana, ben = core.figures
        face = ana.face_exclusion
        corners = (
            *ana.body,
            (face.cx - face.r, face.cy - face.r),
            (face.cx + face.r, face.cy + face.r),
        )
        assert _boxes(core)[0]["box"] == _fractions(core, corners)
        disc = ben.face_exclusion
        assert _boxes(core)[1]["box"] == _fractions(
            core, ((disc.cx - disc.r, disc.cy - disc.r), (disc.cx + disc.r, disc.cy + disc.r))
        )

    def test_a_figure_is_called_by_its_part_or_its_own_name(self):
        phrases = [box["phrase"] for box in _boxes(_figures())]
        assert phrases == ["ANA", "Ben"]


class TestTheDocument:
    def test_it_names_the_canvas_and_nothing_but_boxes(self):
        payload = json.loads(render_boxes(compile_source(DUEL).core))
        assert sorted(payload) == ["boxes", "canvas_height", "canvas_width"]
        assert (payload["canvas_width"], payload["canvas_height"]) == (1000, 800)
        assert all(sorted(box) == ["box", "id", "phrase"] for box in payload["boxes"])

    def test_it_is_written_as_panel_core_is(self):
        text = render_boxes(compile_source(DUEL).core)
        assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"

    def test_a_panel_read_right_to_left_has_the_same_boxes(self):
        source = DUEL + "script:\n  - say: {by: alice, text: Hi.}\n  - say: {by: bob, text: Yes.}\n"
        ltr = compile_source(source).core
        rtl = compile_source("direction: rtl\n" + source).core
        assert render_boxes(rtl) == render_boxes(ltr)


class TestWhatIsDrawn:
    """A box bounds what of the figure the panel draws: inside its frame, or its outline."""

    def test_a_slanted_edge_crops_the_box(self):
        core = compile_source(DUEL).core
        alice = core.actor("alice")
        xs = [x for x, _ in alice.hull]
        cut = (min(xs) + max(xs)) / 2
        outline = ((0.0, 0.0), (cut, 0.0), (cut, core.height), (0.0, core.height))
        box = _boxes(core.model_copy(update={"outline": outline}))[0]["box"]
        assert box[2] == round(cut / core.width, 4)
        assert box[0] == _boxes(core)[0]["box"][0]

    def test_a_figure_round_a_corner_outside_the_panel_has_no_box(self):
        """Its bounds overlap the frame; nothing of it is inside."""
        core = compile_source(DUEL).core
        alice = core.actor("alice")
        corner = alice.model_copy(update={"hull": ((-10.0, 5.0), (5.0, -10.0), (-10.0, -10.0))})
        core = core.model_copy(update={"actors": (corner, *core.actors[1:])})
        assert [box["id"] for box in _boxes(core)] == ["bob"]

    def test_a_body_wider_below_the_frame_is_bounded_where_it_is_cut(self):
        core = compile_source(DUEL).core
        alice = core.actor("alice")
        flared = ((400.0, 700.0), (500.0, 700.0), (900.0, 1200.0), (0.0, 1200.0))
        core = core.model_copy(
            update={"actors": (alice.model_copy(update={"hull": flared}), *core.actors[1:])}
        )
        # At the frame's bottom edge, y = 800, the sides are at x = 320 and 580.
        assert _boxes(core)[0]["box"] == [0.32, 0.875, 0.58, 1.0]


def test_a_negative_zero_is_written_as_zero():
    """A hand-edited Core may say `-0.0`; a fraction of the panel never does."""
    core = compile_source(DUEL).core
    alice = core.actor("alice")
    hull = ((-0.0, alice.hull[0][1]), *alice.hull[1:])
    core = core.model_copy(
        update={"actors": (alice.model_copy(update={"hull": hull}), *core.actors[1:])}
    )
    text = render_boxes(core)
    assert "-0.0" not in text
    assert _boxes(core)[0]["box"][0] == 0.0


def test_a_box_smaller_than_a_unit_is_still_a_box():
    """Area, not size, decides: half a square unit inside the panel is something there."""
    core = compile_source(DUEL).core
    alice = core.actor("alice")
    tiny = alice.model_copy(update={"hull": ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))})
    core = core.model_copy(update={"actors": (tiny, *core.actors[1:])})
    assert [box["id"] for box in _boxes(core)] == ["alice", "bob"]
