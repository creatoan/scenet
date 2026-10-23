"""A Core written before the staging keys (#72) still reads and writes back byte for byte.

New properties over the existing strategies, so every example the other properties draw is
drawn as it was. The keys a panel gained are deleted from its document, which leaves exactly
what the compiler wrote before them; reading that back must give the same bytes.
"""

import json
from typing import Any

from hypothesis import given

from scenet.core import PanelCore
from scenet.pipeline import compile_source
from tests.properties.test_panel_properties import EXPECTED_FAILURES
from tests.strategies import LIBRARY, Drawn, figure_panels, panels

#: What #72 added to each part of a Panel Core.
ACTOR_KEYS = ("joints", "features", "looking_at")
BACKDROP_KEYS = ("place", "time")


def _without_staging(core: PanelCore) -> str:
    payload: Any = json.loads(core.to_json())
    payload.pop("camera", None)
    for actor in payload["actors"]:
        for key in ACTOR_KEYS:
            actor.pop(key, None)
    if payload.get("backdrop") is not None:
        for key in BACKDROP_KEYS:
            payload["backdrop"].pop(key, None)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _compiled(drawn: Drawn) -> PanelCore | None:
    try:
        return compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    except EXPECTED_FAILURES:
        return None


@given(panels())
def test_a_core_without_the_staging_keys_writes_back_unchanged(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    old = _without_staging(core)
    assert PanelCore.from_json(old).to_json() == old
    assert PanelCore.from_json(core.to_json()) == core


@given(figure_panels())
def test_a_figure_panel_without_the_staging_keys_writes_back_unchanged(drawn: Drawn):
    core = _compiled(drawn)
    if core is None:
        return
    assert core.camera is None
    old = _without_staging(core)
    assert PanelCore.from_json(old).to_json() == old
