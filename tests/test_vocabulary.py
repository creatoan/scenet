"""The vocabulary review before the freeze (#361).

After 1.0.0 every key name and every value is permanent, so one pass either fixed or
knowingly accepted each inconsistency: `wide` is gone, an inset's `size` is its `scale`,
the two shots that lacked the suffix have it, and every key that means more than one
thing is in a reviewed table in the reference.

A spelling the language no longer takes is one finding, at the value or the key written,
that says what to write instead -- in `scenet check`, in `build`, and in a comic script.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from scenet.diagnostics import diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.common import _name_what_replaced, errors_of
from scenet.frontends.script_front import FRENCH_SHOTS, parse_script
from scenet.frontends.yaml_front import parse_scene_document
from scenet.ir import (
    RETIRED_KEYS,
    RETIRED_VALUES,
    Corner,
    Inset,
    PanelPlacement,
    ShotType,
    retired_key,
    retired_value,
)
from scenet.pipeline import compile_source

ROOT = Path(__file__).parent.parent
KEYS = ROOT / "docs" / "reference" / "language" / "keys.md"

#: Each spelling taken away, and what to write instead.
RETIRED_SHOTS = [
    ("wide", "long_shot"),
    ("medium_full", "medium_full_shot"),
    ("cowboy", "cowboy_shot"),
]


def scene(insets: str) -> str:
    """A scene with one panel on a page, carrying the insets given."""
    return (
        "cast: {x: {reference: alice}}\n"
        "pages:\n"
        "  - tiers:\n"
        "      - panels:\n"
        "          - use: street\n"
        f"            insets: {insets}\n"
        "panels: {street: {}, a: {}, b: {}}\n"
    )


class TestTheShots:
    def test_every_rung_is_named_as_the_literature_names_it(self):
        """A shot is an *X shot* or an *X close-up*: no rung lacks the suffix."""
        for shot in ShotType:
            assert shot.value.endswith(("_shot", "close_up")), shot

    @pytest.mark.parametrize(("written", "instead"), RETIRED_SHOTS)
    def test_a_retired_shot_is_no_shot(self, written: str, instead: str):
        assert written not in {shot.value for shot in ShotType}
        assert ShotType(instead)

    @pytest.mark.parametrize(("written", "instead"), RETIRED_SHOTS)
    def test_check_names_the_shot_to_write(self, written: str, instead: str):
        source = f"camera:\n  shot: {written}\ncast: {{a: {{reference: alice}}}}\n"
        (found,) = diagnose_source(source)
        assert found.rule == "invalid-field"
        assert found.path == ("camera", "shot")
        assert f"'{instead}'" in found.message
        assert found.region is not None
        assert (found.region.start.line, found.region.start.column) == (2, 9)

    @pytest.mark.parametrize(("written", "instead"), RETIRED_SHOTS)
    def test_build_names_the_shot_to_write(self, written: str, instead: str):
        with pytest.raises(PanelSyntaxError, match=f"'{instead}'") as caught:
            compile_source(f"camera: {{shot: {written}}}\ncast: {{a: {{reference: alice}}}}")
        assert caught.value.rule == "invalid-field"
        assert caught.value.loc == ("camera", "shot")

    def test_a_retired_shot_in_a_scene_default_is_one_finding(self):
        source = "camera: {shot: wide}\ncast: {a: {reference: alice}}\npanels: {one: {}, two: {}}\n"
        (found,) = diagnose_source(source)
        assert found.path == ("camera", "shot")
        assert "'long_shot'" in found.message

    @pytest.mark.parametrize(("written", "instead"), RETIRED_SHOTS)
    def test_a_script_names_the_shot_to_write(self, written: str, instead: str):
        script = f"PANEL 1\n@shot: {written}\n@cast: {{ALICE: {{reference: alice}}}}\nALICE\nHi.\n"
        with pytest.raises(ScriptSyntaxError, match=f"'{instead}'") as caught:
            parse_script(script)
        assert caught.value.rule == "invalid-field"
        (found,) = diagnose_script(script)
        assert found.rule == "invalid-field"
        assert f"'{instead}'" in found.message
        assert found.region is not None
        assert found.region.start.line == 2

    def test_the_plan_americain_is_the_cowboy_shot(self):
        assert FRENCH_SHOTS["plan americain"] == "cowboy_shot"
        assert set(FRENCH_SHOTS.values()) <= {shot.value for shot in ShotType}

    def test_the_table_lists_what_each_retired_shot_became(self):
        assert RETIRED_VALUES["shot"] == dict(RETIRED_SHOTS)

    def test_a_document_is_told_the_key_as_it_writes_it(self):
        """Only a comic script puts a prefix before the key: `@shot:`."""
        assert retired_value("shot", "cowboy") == (
            "'cowboy' is now 'cowboy_shot': write 'shot: cowboy_shot'"
        )


class TestTheInsetScale:
    def test_an_inset_is_scaled(self):
        inset = Inset(use="a", at=Corner.TOP_LEFT, scale=0.3)
        assert inset.scale == 0.3
        assert "size" not in Inset.model_fields

    def test_check_names_the_key_to_write(self):
        (found,) = diagnose_source(scene("[{use: a, at: top_left, size: 0.2}]"))
        assert found.rule == "unknown-key"
        assert found.path == ("pages", 0, "tiers", 0, "panels", 0, "insets", 0, "size")
        assert "'scale'" in found.message
        assert found.region is not None
        assert found.region.start.line == 6

    def test_build_names_the_key_to_write(self):
        with pytest.raises(PanelSyntaxError, match="'scale'") as caught:
            parse_scene_document(scene("[{use: a, at: top_left, size: 0.2}]"))
        assert caught.value.rule == "unknown-key"

    def test_size_and_scale_together_is_still_one_finding(self):
        (found,) = diagnose_source(scene("[{use: a, at: top_left, size: 0.2, scale: 0.2}]"))
        assert found.path[-1] == "size"
        assert "'scale'" in found.message

    def test_a_size_elsewhere_is_not_renamed(self):
        """`size` stays the key of a panel, a page, a line and a sound: only an inset's moved."""
        (found,) = diagnose_source("panel: {size: [1, 1], scale: 2}\ncast: {a: {reference: alice}}")
        assert found.rule == "unknown-key"
        assert "'size'" not in found.message

    def test_two_insets_sized_are_one_finding_each(self):
        found = diagnose_source(
            scene("[{use: a, at: top_left, size: 0.2}, {use: b, at: bottom_right, size: 0.2}]")
        )
        assert [item.rule for item in found] == ["unknown-key", "unknown-key"]

    def test_a_key_missing_elsewhere_is_still_missing(self):
        """Only the `scale` the inset's `size` stands for is spoken for, not another."""
        found = diagnose_source(scene("[{at: top_left, size: 0.2}]"))
        assert sorted(item.rule for item in found) == ["missing-field", "unknown-key"]

    def test_an_inset_validated_on_its_own_is_told_too(self):
        with pytest.raises(ValidationError) as caught:
            PanelPlacement.model_validate(
                {"use": "a", "insets": [{"use": "b", "at": "top_left", "size": 0.2}]}
            )
        (error,) = errors_of(caught.value)
        assert error["msg"] == retired_key("insets", "size")

    def test_a_fault_at_an_index_does_not_stop_the_rest_being_told(self):
        errors: list[ErrorDetails] = [
            {"type": "enum", "loc": ("marks", 0), "msg": "m", "input": "x"},
            {"type": "enum", "loc": ("camera", "shot"), "msg": "m", "input": "wide"},
        ]
        assert [error["msg"] for error in _name_what_replaced(errors)] == [
            "m",
            retired_value("shot", "wide"),
        ]

    def test_the_table_lists_the_renamed_key(self):
        assert RETIRED_KEYS["insets"] == {"size": "scale"}

    def test_a_key_that_is_no_text_was_never_renamed(self):
        """A key is any value pydantic was handed, a list among them, which no table holds."""
        assert retired_key("insets", ["size"]) is None


def _keys_by_name() -> dict[str, set[str]]:
    """Every key path in the A-Z index, grouped by the key's own name."""
    text = KEYS.read_text(encoding="utf-8")
    grouped: dict[str, set[str]] = {}
    for path in re.findall(r"^\| \[`([^`]+)`\]\(", text, flags=re.MULTILINE):
        name = [step for step in re.split(r"[.\[\]]+", path) if step][-1]
        grouped.setdefault(name, set()).add(path)
    return grouped


def _reviewed() -> dict[str, set[str]]:
    """The reviewed table: each key it lists, and the places it gives for it."""
    text = KEYS.read_text(encoding="utf-8")
    start = text.index("## One name, several meanings")
    section = text[start : text.index("## Where, in words", start)]
    table: dict[str, set[str]] = {}
    for name, places in re.findall(r"^\| `([^`]+)` \| (.+?) \|", section, flags=re.MULTILINE):
        table.setdefault(name, set()).update(re.findall(r"`([^`]+)`", places))
    return table


class TestTheReviewedTable:
    def test_it_is_marked_reviewed(self):
        text = KEYS.read_text(encoding="utf-8")
        assert "Reviewed for 1.0" in text

    def test_every_key_written_in_more_than_one_place_has_a_row(self):
        """A key added later under a name already in use cannot skip the review."""
        repeated = {name for name, paths in _keys_by_name().items() if len(paths) > 1}
        assert repeated <= set(_reviewed()), sorted(repeated - set(_reviewed()))

    def test_every_row_names_each_place_the_key_is_written(self):
        grouped = _keys_by_name()
        for name, places in _reviewed().items():
            if name in grouped:
                assert places >= grouped[name], (name, sorted(grouped[name] - places))

    def test_no_retired_spelling_is_left_in_the_index(self):
        assert "insets[].size" not in KEYS.read_text(encoding="utf-8")
