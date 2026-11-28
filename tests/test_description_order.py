"""Where a panel's description says people stand (#447).

A reader meets the figures left to right -- right to left for a comic read that way -- and
each figure in a different place has a different word for it. The words come from where the
figure was resolved to stand, never from where the author put it, and never from the
alphabet: three figures were once "Aiko, centre; Grandmother, centre; Ryo, centre".
"""

import itertools
import re

from hypothesis import given

from scenet import compile_source
from scenet.core import PanelCore
from scenet.errors import BalloonPlacementError, LayoutError, SfxPlacementError
from scenet.frontends.yaml_front import parse_panel
from scenet.solve.describe import describe, name
from tests.strategies import LIBRARY, Drawn, panels

THREE = """\
camera: {shot: medium_shot}
cast:
  aiko: {reference: alice}
  grandmother: {reference: alice, pose: pointing}
  ryo: {reference: alice}
staging:
  - ryo left_of grandmother
  - grandmother left_of aiko
"""


def _said(core: PanelCore) -> str:
    assert core.description is not None
    return core.description


def _figures(description: str) -> list[tuple[str, str]]:
    """Each figure of a generated description, in the order it is read: (name, place)."""
    body = description.rsplit(". ", 1)[-1].removesuffix(".")
    pairs = [part.split(", ")[:2] for part in body.split("; ")]
    return [(who, where) for who, where in pairs]


def _described(faces: dict[str, float]) -> str:
    return describe(parse_panel(THREE), faces, 1000.0)


class TestThreeFigures:
    def test_the_compiled_panel_is_read_left_to_right_each_in_its_own_place(self):
        said = _said(compile_source(THREE, library=LIBRARY).core)
        figures = _figures(said)
        assert [who for who, _ in figures] == ["Ryo", "Grandmother", "Aiko"]
        assert len({where for _, where in figures}) == 3

    def test_three_in_a_row_are_left_centre_right(self):
        said = _described({"ryo": 100.0, "grandmother": 500.0, "aiko": 900.0})
        assert _figures(said) == [("Ryo", "left"), ("Grandmother", "centre"), ("Aiko", "right")]

    def test_two_in_one_third_are_told_apart(self):
        said = _described({"ryo": 100.0, "grandmother": 300.0, "aiko": 900.0})
        assert _figures(said) == [
            ("Ryo", "far left"),
            ("Grandmother", "left of centre"),
            ("Aiko", "right"),
        ]

    def test_three_in_one_third_are_told_apart(self):
        said = _described({"ryo": 50.0, "grandmother": 150.0, "aiko": 250.0})
        assert [where for _, where in _figures(said)] == ["far left", "left", "left of centre"]

    def test_three_in_the_middle_are_told_apart(self):
        said = _described({"ryo": 400.0, "grandmother": 500.0, "aiko": 600.0})
        assert [where for _, where in _figures(said)] == [
            "centre left",
            "centre",
            "centre right",
        ]

    def test_the_right_side_mirrors_the_left(self):
        said = _described({"ryo": 700.0, "grandmother": 800.0, "aiko": 900.0})
        assert [where for _, where in _figures(said)] == ["right of centre", "right", "far right"]

    def test_four_in_one_third_are_numbered(self):
        source = THREE.replace("  ryo:", "  zed: {reference: alice}\n  ryo:")
        faces = {"zed": 10.0, "ryo": 60.0, "grandmother": 110.0, "aiko": 160.0}
        said = describe(parse_panel(source), faces, 1000.0)
        assert [where for _, where in _figures(said)] == [
            "left (1 of 4)",
            "left (2 of 4)",
            "left (3 of 4)",
            "left (4 of 4)",
        ]

    def test_figures_in_the_same_place_share_a_word_and_a_tie_is_broken_by_id(self):
        said = _described({"ryo": 500.0, "grandmother": 500.0, "aiko": 500.0})
        assert _figures(said) == [
            ("Aiko", "centre"),
            ("Grandmother", "centre"),
            ("Ryo", "centre"),
        ]

    def test_right_to_left_reads_the_far_side_first_but_says_where_they_stand(self):
        panel = parse_panel(f"direction: rtl\n{THREE}")
        said = describe(panel, {"ryo": 100.0, "grandmother": 300.0, "aiko": 900.0}, 1000.0)
        assert _figures(said) == [
            ("Aiko", "right"),
            ("Grandmother", "left of centre"),
            ("Ryo", "far left"),
        ]


def _order_in(description: str, actors: list[str]) -> list[str]:
    """The actors in the order the description names them."""
    found: list[tuple[int, str]] = []
    for actor in actors:
        hit = re.search(rf"(?:^|\. |; ){re.escape(name(actor))}, ", description)
        assert hit is not None, (actor, description)
        found.append((hit.start(), actor))
    return [actor for _, actor in sorted(found)]


def _generated(core: PanelCore, drawn: Drawn) -> bool:
    """Whether the description is generated, not the author's."""
    return "description" not in drawn.document and bool(core.actors)


def _check(drawn: Drawn, direction: str) -> None:
    try:
        core = compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    except (BalloonPlacementError, LayoutError, SfxPlacementError):
        return
    if not _generated(core, drawn):
        return
    sign = -1 if direction == "rtl" else 1
    ids = [actor.id for actor in core.actors]
    expected = sorted(ids, key=lambda a: (sign * _face_x(core, a), a))
    assert _order_in(_said(core), ids) == expected


def _face_x(core: PanelCore, actor: str) -> float:
    return next(item.face_exclusion.cx for item in core.actors if item.id == actor)


@given(panels(images=False))
def test_the_names_are_in_the_order_of_the_resolved_x_positions(drawn: Drawn):
    _check(drawn, "ltr")


@given(panels(images=False, direction="rtl"))
def test_the_names_are_in_the_mirrored_order_under_rtl(drawn: Drawn):
    _check(drawn, "rtl")


@given(panels(images=False))
def test_figures_in_different_places_are_in_different_words(drawn: Drawn):
    try:
        core = compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    except (BalloonPlacementError, LayoutError, SfxPlacementError):
        return
    if not _generated(core, drawn):
        return
    said = dict(_figures(_said(core)))
    where = {name(item.id): item.face_exclusion.cx for item in core.actors}
    for a, b in itertools.combinations(where, 2):
        assert (where[a] == where[b]) == (said[a] == said[b])
