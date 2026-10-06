"""Broken documents: exactly one located finding per mistake, and never a traceback.

`scenet check` is how a person or an agent repairs a document, so what matters is not
that *a* finding appears -- the old tests checked only that -- but that each mistake
gives **exactly one**, under the right rule, pointing at the line to change. Two
findings for one mistake send whoever is repairing it after a fault that is not there.

The robustness properties feed in documents and scripts nobody would write on purpose.
Whatever comes in, `scenet check` answers with findings, never a traceback, and never
with the `internal` rule that admits it did not know what went wrong.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from scenet.cli import main
from scenet.diagnostics import RULES, Diagnostic, diagnose_script, diagnose_source, to_sarif
from tests.strategies import (
    LIBRARY,
    MISTAKES,
    Drawn,
    DrawnScene,
    DrawnScript,
    mistakes,
    panels,
    scenes,
    scripts,
)


def _line(text: str, found: Diagnostic) -> str:
    assert found.region is not None, f"{found.rule} has no region"
    return text.splitlines()[found.region.start.line - 1]


def _assert_one(
    found: list[Diagnostic],
    text: str,
    *,
    rule: str,
    path: tuple[Any, ...],
    needle: str | None,
    exact: bool = True,
) -> None:
    assert [item.rule for item in found] == [rule], [(item.rule, item.message) for item in found]
    (finding,) = found
    assert (finding.path if exact else finding.path[: len(path)]) == path
    line = _line(text, finding)
    if needle is not None:
        assert needle in line, f"{rule} points at {line!r}, which does not hold {needle!r}"
    document = to_sarif(found, root=None)
    (run,) = document["runs"]
    (result,) = run["results"]
    assert result["ruleId"] == f"scenet/{rule}"
    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize("kind", sorted(MISTAKES))
@given(data=st.data())
def test_one_mistake_is_one_finding_at_the_right_place(kind: str, data: st.DataObject):
    """Every entry of the catalogue, each against its own generated panels."""
    mistake = data.draw(mistakes(kind))
    found = diagnose_source(mistake.text, source=Path("x.panel.yaml"), library=LIBRARY)
    _assert_one(
        found,
        mistake.text,
        rule=mistake.rule,
        path=mistake.path,
        needle=mistake.needle,
        exact=mistake.exact,
    )


@given(panels())
def test_two_field_mistakes_are_two_findings(drawn: Drawn):
    """Additivity: two independent mistakes in fields are two findings, not one."""
    document = dict(drawn.document)
    document["panel"] = {**document["panel"], "margin": -5}
    document["camera"] = {**document["camera"], "shot": 5}
    found = diagnose_source(Drawn(document).text, source=Path("x.panel.yaml"), library=LIBRARY)
    assert sorted(item.path for item in found) == [("camera", "shot"), ("panel", "margin")]
    assert {item.rule for item in found} == {"invalid-field"}


@pytest.mark.parametrize("kind", ["missing-panel", "placed-twice", "missing-parent", "two-stacks"])
@given(drawn=scenes())
def test_one_mistake_in_a_scene_is_one_finding(kind: str, drawn: DrawnScene):
    document = json.loads(json.dumps(drawn.document))
    if kind == "two-stacks":
        # Two stacked columns side by side, which readers go across rather than down.
        names = list(document["panels"])
        document["panels"].update({f"extra{index}": {} for index in range(4)})
        document["pages"] = [
            {
                "tiers": [
                    {"panels": names},
                    {
                        "columns": [
                            {"panels": ["extra0", "extra1"]},
                            {"panels": ["extra2", "extra3"]},
                        ]
                    },
                ]
            }
        ]
        text = DrawnScene(document, drawn.order).text
        path = ("pages", 0, "tiers", 1, "columns", 1)
        _assert_one(
            diagnose_source(text, library=LIBRARY), text, rule="page-layout", path=path, needle=None
        )
        return
    tier = document["pages"][0]["tiers"][0]
    slots = tier.get("panels") or tier["columns"][0]["panels"]
    where = ("panels", 0) if "panels" in tier else ("columns", 0, "panels", 0)
    path: tuple[Any, ...]
    if kind == "missing-panel":
        slots[0]["use"] = "ghost"
        rule, path, needle = "page-layout", ("pages", 0, "tiers", 0, *where), "ghost"
    elif kind == "placed-twice":
        # In a tier of its own, so the second placement is the only thing wrong.
        document["pages"][0]["tiers"].append({"panels": [slots[0]["use"]]})
        last = len(document["pages"][0]["tiers"]) - 1
        rule, path, needle = "page-layout", ("pages", 0, "tiers", last, "panels", 0), None
    else:
        name = next(iter(document["panels"]))
        document["panels"][name]["over"] = "ghost"
        rule, path, needle = "composition", ("panels", name, "over"), "ghost"
    text = DrawnScene(document, drawn.order).text
    _assert_one(diagnose_source(text, library=LIBRARY), text, rule=rule, path=path, needle=needle)


@given(scripts())
def test_a_repeated_panel_heading_is_one_finding(drawn: DrawnScript):
    """The #63 class: a PANEL number written twice on one page."""
    lines = drawn.text.splitlines()
    first = next(index for index, line in enumerate(lines) if line.startswith("PANEL "))
    lines.insert(first, lines[first])
    text = "\n".join(lines) + "\n"
    found = diagnose_script(text, library=LIBRARY)
    assert [item.rule for item in found] == ["duplicate-panel"]
    assert _line(text, found[0]).startswith("PANEL ")


# ---------------------------------------------------------------- robustness

#: Keys the language uses, mixed with ones it does not, so arbitrary documents reach
#: past the first unknown key into the validators.
_KEYS = st.sampled_from(
    [
        "panel",
        "camera",
        "cast",
        "staging",
        "script",
        "setting",
        "panels",
        "pages",
        "page",
        "size",
        "margin",
        "shot",
        "reference",
        "pose",
        "say",
        "caption",
        "by",
        "text",
        "over",
        "tiers",
        "columns",
        "insets",
        "use",
        "place",
        "masses",
    ]
) | st.text(max_size=8)
_SCALARS = (
    st.none()
    | st.booleans()
    | st.integers(-(10**6), 10**6)
    | st.floats(allow_nan=True, allow_infinity=True)
    | st.text(max_size=12)
)
_KEYS_ANY_TYPE = _KEYS | st.integers(-5, 5) | st.booleans() | st.none()
_VALUES = st.recursive(
    _SCALARS,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(_KEYS_ANY_TYPE, inner, max_size=4),
    max_leaves=25,
)


def _assert_answered(found: list[Diagnostic]) -> None:
    for item in found:
        assert item.rule in RULES
        assert item.rule != "internal", item.message


@given(st.dictionaries(_KEYS_ANY_TYPE, _VALUES, max_size=6))
def test_any_document_gets_findings_not_a_traceback(document: dict[Any, Any]):
    text = yaml.safe_dump(document, allow_unicode=True)
    _assert_answered(diagnose_source(text, library=LIBRARY))


@given(st.text(max_size=200))
def test_any_text_gets_findings_not_a_traceback(text: str):
    _assert_answered(diagnose_source(text, library=LIBRARY))


@given(st.text(max_size=300))
def test_any_script_gets_findings_not_a_traceback(text: str):
    _assert_answered(diagnose_script(text, library=LIBRARY))


@given(document=st.dictionaries(_KEYS, _VALUES, max_size=6))
def test_scenet_check_exits_zero_or_one(
    tmp_path_factory: pytest.TempPathFactory, document: dict[Any, Any]
):
    path = tmp_path_factory.mktemp("check") / "x.panel.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    assert main(["check", "--quiet", str(path)]) in (0, 1)
