"""Properties every single-panel compile must have, checked against generated panels.

The invariants in `tests/invariants.py` were checked against five hand-written panels.
Here they are checked against every panel `tests.strategies.panels` can draw, along with
the four kinds of property that have found real bugs in numerical code: determinism,
invariants, round trips and an oracle (*Falsify your Software*, SciPy 2020).

The profile in `tests/conftest.py` fixes the examples, so a failure replays exactly:
re-run the test and the same panel comes back.
"""

import pytest
from hypothesis import event, given

from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.emit.debug_svg import render_debug
from scenet.emit.svg import render
from scenet.errors import BalloonPlacementError, LayoutError
from scenet.pipeline import compile_source
from tests.invariants import assert_lettering_is_placed, assert_svg_is_sound
from tests.strategies import LIBRARY, Drawn, panels

#: The only ways a valid panel may fail to compile: it has no layout, or no room for its
#: lettering. Anything else escaping the compiler is a bug.
EXPECTED_FAILURES = (BalloonPlacementError, LayoutError)


def _compile(drawn: Drawn) -> PanelCore | None:
    """The compiled panel, or `None` when it fails in one of the expected ways."""
    try:
        core = compile_source(drawn.text, library=LIBRARY).core
    except EXPECTED_FAILURES as exc:
        event(f"failed: {type(exc).__name__}")
        return None
    event("compiled")
    event(f"lettered boxes: {len(core.balloons) + len(core.captions)}")
    return core


def _font_sizes(core: PanelCore) -> list[float]:
    return [box.font_size for box in (*core.balloons, *core.captions)]


@given(panels())
def test_compiling_twice_gives_the_same_bytes(drawn: Drawn):
    """Every output, compiled twice in one process, is byte-identical."""
    first = _compile(drawn)
    if first is None:
        return
    second = compile_source(drawn.text, library=LIBRARY).core
    assert first.to_json() == second.to_json()
    assert render(first) == render(second)
    assert render(first, live_text=True) == render(second, live_text=True)
    assert render_debug(first) == render_debug(second)


@given(panels())
def test_a_compiled_panel_keeps_every_promise(drawn: Drawn):
    """Lettering is placed where the language says, and the SVG holds together."""
    core = _compile(drawn)
    if core is None:
        return
    assert_lettering_is_placed(core, margin=drawn.margin)
    sizes = _font_sizes(core)
    assert_svg_is_sound(render(core), size=drawn.size, font_sizes=sizes)
    assert_svg_is_sound(render(core, live_text=True), size=drawn.size, font_sizes=sizes)
    assert_svg_is_sound(render_debug(core), size=drawn.size)


@given(panels())
def test_panel_core_survives_a_round_trip(drawn: Drawn):
    """Panel Core is a real format: it reads back equal, and writes back the same bytes."""
    core = _compile(drawn)
    if core is None:
        return
    text = core.to_json()
    restored = PanelCore.from_json(text)
    assert restored == core
    assert restored.to_json() == text


@given(panels())
def test_check_agrees_with_the_compiler(drawn: Drawn):
    """`scenet check --deep` is clean exactly when the panel compiles, and otherwise
    reports the one finding whose rule names how it failed.

    This is also the failure property: `compile_source` is called without a safety net,
    so anything but the two expected failures escapes and fails the test.
    """
    findings = diagnose_source(drawn.text, library=LIBRARY, deep=True)
    try:
        compile_source(drawn.text, library=LIBRARY)
    except BalloonPlacementError:
        assert [finding.rule for finding in findings] == ["balloon-placement"]
    except LayoutError:
        assert [finding.rule for finding in findings] == ["layout"]
    else:
        assert findings == []


@pytest.mark.parametrize(
    "document",
    [
        # A margin of a tenth of the shorter side, the most the strategy draws.
        {
            "panel": {"size": [360, 360], "margin": 36},
            "cast": {"a": {"reference": "alice"}},
            "script": [{"say": {"by": "a", "text": "Hello."}}],
        },
    ],
)
def test_the_invariants_hold_for_a_pinned_example(document: dict[str, object]):
    """A fixed example beside the generated ones, so the shared checks always run on at
    least one panel with lettering even if the strategy changes."""
    drawn = Drawn(document)
    core = compile_source(drawn.text, library=LIBRARY).core
    assert_lettering_is_placed(core, margin=drawn.margin)
    assert_svg_is_sound(render(core), size=drawn.size, font_sizes=_font_sizes(core))
