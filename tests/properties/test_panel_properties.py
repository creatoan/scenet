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
from scenet.errors import BalloonPlacementError, LayoutError, SfxPlacementError
from scenet.pipeline import CompileResult, compile_source
from tests.invariants import (
    assert_accessible,
    assert_effects_are_placed,
    assert_lettering_is_placed,
    assert_svg_is_sound,
    assert_words_are_carried,
    without_access,
)
from tests.strategies import LIBRARY, Drawn, panels

#: The only ways a valid panel may fail to compile: it has no layout, or no room for its
#: lettering. Anything else escaping the compiler is a bug.
EXPECTED_FAILURES = (BalloonPlacementError, LayoutError, SfxPlacementError)

#: What `scenet check --deep` reports for each of them: one finding, its rule.
ONE_FAILURE = (["balloon-placement"], ["layout"], ["sfx-placement"])


def _result(drawn: Drawn) -> CompileResult | None:
    """The compiled panel, or `None` when it fails in one of the expected ways."""
    try:
        result = compile_source(drawn.text, library=LIBRARY, base=drawn.base)
    except EXPECTED_FAILURES as exc:
        event(f"failed: {type(exc).__name__}")
        return None
    event("compiled")
    event("over a picture" if result.images else "no picture")
    event(f"lettered boxes: {len(result.core.balloons) + len(result.core.captions)}")
    return result


def _compile(drawn: Drawn) -> PanelCore | None:
    """The compiled panel's Core, or `None` when it fails in one of the expected ways."""
    result = _result(drawn)
    return None if result is None else result.core


def _font_sizes(core: PanelCore) -> list[float]:
    return [box.font_size for box in (*core.balloons, *core.captions, *core.sfx)]


@given(panels())
def test_compiling_twice_gives_the_same_bytes(drawn: Drawn):
    """Every output, compiled twice in one process, is byte-identical."""
    compiled = _result(drawn)
    if compiled is None:
        return
    first = compiled.core
    again = compile_source(drawn.text, library=LIBRARY, base=drawn.base)
    second = again.core
    assert first.to_json() == second.to_json()
    assert render(first) == render(second)
    assert render(first, embed=compiled.images) == render(second, embed=again.images)
    assert render(first, live_text=True) == render(second, live_text=True)
    assert render(first, aria=False) == render(second, aria=False)
    assert render_debug(first) == render_debug(second)


@given(panels())
def test_without_aria_it_is_the_same_svg_less_what_aria_adds(drawn: Drawn):
    """The opt-out writes nothing accessible output adds, and nothing else differs."""
    core = _compile(drawn)
    if core is None:
        return
    for live_text in (False, True):
        bare = render(core, aria=False, live_text=live_text)
        assert bare == without_access(render(core, live_text=live_text))
        assert not any(written in bare for written in ("role=", "aria-", "<title", "<desc"))


@given(panels())
def test_a_compiled_panel_keeps_every_promise(drawn: Drawn):
    """Lettering is placed where the language says, and the SVG holds together."""
    core = _compile(drawn)
    if core is None:
        return
    assert_lettering_is_placed(core, margin=drawn.margin)
    assert_effects_are_placed(core, margin=drawn.margin)
    assert_words_are_carried(core, description=drawn.document.get("description"))
    sizes = _font_sizes(core)
    assert_svg_is_sound(render(core), size=drawn.size, font_sizes=sizes)
    assert_svg_is_sound(
        render(core, embed=drawn.files_by_digest), size=drawn.size, font_sizes=sizes
    )
    assert_svg_is_sound(render(core, live_text=True), size=drawn.size, font_sizes=sizes)
    assert_svg_is_sound(render_debug(core), size=drawn.size)
    assert_accessible(render(core), core)
    assert_accessible(render(core, live_text=True), core)


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
    so anything but the three expected failures escapes and fails the test.
    """
    findings = diagnose_source(drawn.text, library=LIBRARY, deep=True, base=drawn.base)
    try:
        compile_source(drawn.text, library=LIBRARY, base=drawn.base)
    except BalloonPlacementError:
        assert [finding.rule for finding in findings] == ["balloon-placement"]
    except LayoutError:
        assert [finding.rule for finding in findings] == ["layout"]
    except SfxPlacementError:
        # A sound effect with nowhere to go; this property did not expect one before.
        assert [finding.rule for finding in findings] == ["sfx-placement"]
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


@given(panels(direction="rtl"))
def test_read_right_to_left_every_property_still_holds(drawn: Drawn):
    """Determinism, the invariants, the round trip and the oracle, for panels read right to
    left (#68), the reading-order invariant among them read the other way.

    A property of its own rather than a direction drawn into `panels`: every example the
    properties above draw stays the one they drew before directions existed.
    """
    findings = diagnose_source(drawn.text, library=LIBRARY, deep=True, base=drawn.base)
    core = _compile(drawn)
    if core is None:
        assert [item.rule for item in findings] in ONE_FAILURE
        return
    assert findings == []
    assert (
        core.to_json()
        == compile_source(drawn.text, library=LIBRARY, base=drawn.base).core.to_json()
    )
    assert_lettering_is_placed(core, margin=drawn.margin)
    assert_effects_are_placed(core, margin=drawn.margin)
    assert_words_are_carried(core, description=drawn.document.get("description"))
    assert_svg_is_sound(render(core), size=drawn.size, font_sizes=_font_sizes(core))
    assert_accessible(render(core), core)
    text = core.to_json()
    assert '"direction": "rtl"' in text
    restored = PanelCore.from_json(text)
    assert restored == core
    assert restored.to_json() == text
