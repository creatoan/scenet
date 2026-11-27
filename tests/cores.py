"""Helpers for tests that read a Panel Core's actors."""

from scenet.core import CoreActor, CoreMannequin


def drawn(actor: CoreActor) -> CoreMannequin:
    """The mannequin an actor is drawn as, which every compiled puppet is."""
    drawing = actor.mannequin
    assert drawing is not None, f"{actor.id} is not drawn as a mannequin"
    return drawing
