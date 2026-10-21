"""The panel properties again, for panels whose people a supplied picture draws (#71).

The same four kinds -- determinism, invariants, round trips and the check-agrees-with-build
oracle -- against `tests.strategies.figure_panels`, which draws a picture and its artwork
contract into `Drawn.files`. A separate strategy, rather than a branch of `panels`, so every
panel those properties drew before figures existed is still drawn as it was.
"""

from hypothesis import event, given

from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import render
from scenet.errors import BalloonPlacementError, LayoutError, SfxPlacementError
from scenet.pipeline import compile_source
from tests.invariants import (
    assert_accessible,
    assert_effects_are_placed,
    assert_lettering_is_placed,
    assert_svg_is_sound,
    assert_words_are_carried,
)
from tests.properties.test_panel_properties import EXPECTED_FAILURES, _font_sizes
from tests.strategies import LIBRARY, Drawn, figure_panels


def _core(drawn: Drawn) -> tuple[PanelCore, dict[str, bytes]] | None:
    try:
        result = compile_source(drawn.text, library=LIBRARY, base=drawn.base)
    except EXPECTED_FAILURES as exc:
        event(f"failed: {type(exc).__name__}")
        return None
    event(f"figures: {len(result.core.figures)}, cast: {len(drawn.document['cast'])}")
    event(f"lettered boxes: {len(result.core.balloons) + len(result.core.captions)}")
    return result.core, result.images


@given(figure_panels())
def test_compiling_twice_gives_the_same_bytes(drawn: Drawn):
    compiled = _core(drawn)
    if compiled is None:
        return
    first, images = compiled
    second = compile_source(drawn.text, library=LIBRARY, base=drawn.base).core
    assert first.to_json() == second.to_json()
    assert render(first) == render(second)
    assert render(first, embed=images) == render(second, embed=images)
    assert render_debug(first) == render_debug(second)


@given(figure_panels())
def test_a_compiled_panel_keeps_every_promise(drawn: Drawn):
    """No lettering over any declared face, cast or not; every tail at its speaker."""
    compiled = _core(drawn)
    if compiled is None:
        return
    core, _ = compiled
    assert core.actors == ()
    assert len(core.face_exclusions()) == len(core.figures) >= 1
    assert_lettering_is_placed(core, margin=drawn.margin)
    assert_effects_are_placed(core, margin=drawn.margin)
    assert_words_are_carried(core, description=drawn.document.get("description"))
    sizes = _font_sizes(core)
    assert_svg_is_sound(render(core), size=drawn.size, font_sizes=sizes)
    assert_svg_is_sound(
        render(core, embed=drawn.files_by_digest), size=drawn.size, font_sizes=sizes
    )
    assert_svg_is_sound(render_debug(core), size=drawn.size)
    assert_accessible(render(core), core)


@given(figure_panels())
def test_panel_core_survives_a_round_trip(drawn: Drawn):
    compiled = _core(drawn)
    if compiled is None:
        return
    core, _ = compiled
    text = core.to_json()
    restored = PanelCore.from_json(text)
    assert restored == core
    assert restored.to_json() == text


@given(figure_panels())
def test_check_agrees_with_the_compiler(drawn: Drawn):
    findings = diagnose_source(drawn.text, library=LIBRARY, deep=True, base=drawn.base)
    try:
        compile_source(drawn.text, library=LIBRARY, base=drawn.base)
    except BalloonPlacementError:
        assert [finding.rule for finding in findings] == ["balloon-placement"]
    except LayoutError:
        assert [finding.rule for finding in findings] == ["layout"]
    except SfxPlacementError:
        assert [finding.rule for finding in findings] == ["sfx-placement"]
    else:
        assert findings == []
