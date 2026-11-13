"""How far down a path `locate` walks before it stops, at the edges of the document (#345).

A finding's path is pydantic's, and may name a field of a value that is not the shape the
schema expected, or an index a list does not have. `locate` then stops at the deepest node it
reached. Each test kills a mutant the mutation run left alive in `positions.py`.
"""

from scenet.frontends.positions import Position, Region, locate


def test_an_index_into_text_stops_at_the_text():
    """A scalar has no items, whatever the index: the region is the scalar's."""
    assert locate("a: hello\n", ("a", 0)) == Region(Position(1, 4), Position(1, 9))


def test_an_index_one_past_the_end_stops_at_the_list():
    assert locate("a: [x, y]\n", ("a", 2)) == Region(Position(1, 4), Position(1, 10))


def test_the_last_index_is_reached():
    assert locate("a: [x, y]\n", ("a", 1)) == Region(Position(1, 8), Position(1, 9))
