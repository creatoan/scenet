"""Properties of the exports for image models (#72), over generated documents.

New properties over the existing strategies, each a module-level function: no strategy draws
anything it did not before, so every example the other properties draw is drawn as it was. A
panel read right to left is compared with its own twin read left to right -- the same drawn
document with `direction` changed, which needs no draw.
"""

import json
from typing import Any

from hypothesis import given

from scenet.core import PanelCore
from scenet.emit.boxes import render_boxes
from scenet.emit.pose import COCO_18, render_pose
from scenet.emit.semantics import render_semantics
from scenet.pipeline import compile_book, compile_script, compile_source
from tests.properties.test_panel_properties import EXPECTED_FAILURES
from tests.strategies import (
    LIBRARY,
    Drawn,
    DrawnScene,
    DrawnScript,
    figure_panels,
    panels,
    scenes,
    scripts,
)


def _compiled(drawn: Drawn) -> PanelCore | None:
    try:
        return compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    except EXPECTED_FAILURES:
        return None


def _exports(core: PanelCore) -> tuple[str, ...]:
    return render_pose(core), render_boxes(core), render_semantics(core)


def _keypoints(core: PanelCore) -> list[dict[str, tuple[float, float, float]]]:
    payload: Any = json.loads(render_pose(core))
    return [
        {
            name: tuple(person["pose_keypoints_2d"][3 * index : 3 * index + 3])
            for index, name in enumerate(COCO_18)
        }
        for person in payload["people"]
    ]


@given(panels())
def test_the_exports_are_the_same_bytes_every_time(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    again = compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    assert _exports(core) == _exports(again)
    assert _exports(PanelCore.from_json(core.to_json())) == _exports(core)


@given(panels())
def test_every_actor_is_eighteen_points_on_the_canvas(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    payload: Any = json.loads(render_pose(core))
    assert len(payload["people"]) == len(core.actors)
    for person in payload["people"]:
        values = person["pose_keypoints_2d"]
        assert len(values) == 3 * len(COCO_18)
        for x, y, confidence in zip(values[0::3], values[1::3], values[2::3], strict=True):
            assert confidence in (0.0, 1.0)
            if confidence == 0.0:
                assert (x, y) == (0.0, 0.0)
            else:
                assert 0.0 <= x <= core.width
                assert 0.0 <= y <= core.height


@given(panels())
def test_the_subject_s_right_is_on_the_reader_s_left(drawn: Drawn):
    """Every body faces the reader, whichever way it is turned."""
    core = _compiled(drawn)
    if core is None:
        return
    for points in _keypoints(core):
        for part in ("shoulder", "hip", "eye"):
            right, left = points[f"right_{part}"], points[f"left_{part}"]
            if right[2] and left[2]:
                assert right[0] < left[0], part


@given(panels())
def test_every_box_is_inside_the_panel(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    payload: Any = json.loads(render_boxes(core))
    ids = [box["id"] for box in payload["boxes"]]
    assert ids == [actor.id for actor in core.actors if actor.id in ids]
    for box in payload["boxes"]:
        xmin, ymin, xmax, ymax = box["box"]
        assert 0.0 <= xmin < xmax <= 1.0
        assert 0.0 <= ymin < ymax <= 1.0
        assert box["phrase"]


@given(panels())
def test_the_lettering_is_listed_in_reading_order(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    payload: Any = json.loads(render_semantics(core))
    lettering = payload["lettering"]
    assert [entry["order"] for entry in lettering] == sorted(entry["order"] for entry in lettering)
    assert len(lettering) == len(core.balloons) + len(core.captions) + len(core.sfx)
    assert payload["description"] == core.description


@given(panels(direction="rtl"))
def test_read_right_to_left_the_pose_and_boxes_are_the_same(drawn: Drawn):
    rtl = _compiled(drawn)
    ltr = _compiled(Drawn({**drawn.document, "direction": "ltr"}, drawn.files))
    if rtl is None or ltr is None:
        return
    assert render_pose(rtl) == render_pose(ltr)
    assert render_boxes(rtl) == render_boxes(ltr)


@given(figure_panels())
def test_a_figure_panel_has_boxes_and_no_pose(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    assert json.loads(render_pose(core))["people"] == []
    semantics: Any = json.loads(render_semantics(core))
    assert semantics["camera"] is None
    assert len(semantics["figures"]) == len(core.figures)
    for box in json.loads(render_boxes(core))["boxes"]:
        assert 0.0 <= box["box"][0] < box["box"][2] <= 1.0


@given(scenes())
def test_every_panel_of_a_scene_exports(drawn: DrawnScene):
    try:
        book = compile_book(drawn.text, library=LIBRARY)
    except EXPECTED_FAILURES:
        return
    for result in book.panels.values():
        assert _exports(result.core) == _exports(PanelCore.from_json(result.core.to_json()))


@given(scripts())
def test_every_panel_of_a_comic_script_exports(drawn: DrawnScript):
    try:
        book = compile_script(drawn.text, library=LIBRARY)
    except EXPECTED_FAILURES:
        return
    for result in book.panels.values():
        people = json.loads(render_pose(result.core))["people"]
        assert len(people) == len(result.core.actors)
