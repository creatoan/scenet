"""IR checks whose answer no document's finding shows, held directly (#345).

Each test kills a mutant the mutation run left alive in `ir.py`; `docs/maintainer/testing.md`
lists them with the others.
"""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from scenet.errors import RuleViolationError
from scenet.ir import CastMember, PanelIR, SettingSpec, Side, unholdable


class TestWhatATextCannotHold:
    def test_it_says_why(self):
        """Held by a doctest until now, and mutmut runs no doctest."""
        assert unholdable("Alice \x07 waits.") == (
            "contains U+0007, a control character an SVG cannot hold; delete it"
        )

    def test_text_it_can_hold_has_no_reason(self):
        assert unholdable("Alice waits.") is None


class TestAMemberWhoIsNeitherPuppetNorFigure:
    def test_every_other_fault_keeps_its_input(self):
        """Reported as `reference` missing, beside what else is wrong with the member, each
        detail exactly as pydantic gave it."""
        with pytest.raises(ValidationError) as caught:
            CastMember.model_validate({"facing": 5})
        missing, wrong = caught.value.errors()
        assert missing["loc"] == ("reference",)
        assert missing["input"] == {"facing": 5}
        assert wrong["loc"] == ("facing",)
        assert wrong["input"] == 5


def _refusal(model: type[BaseModel], data: dict[str, Any]) -> RuleViolationError:
    """The rule a model's own check broke, as pydantic keeps it."""
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    (error,) = caught.value.errors()
    found = (error.get("ctx") or {}).get("error")
    assert isinstance(found, RuleViolationError)
    return found


class TestTheIRsOwnChecks:
    """What the IR refuses when it is built in Python. The front ends refuse each of these
    first, in their own words, so no document reaches the IR's."""

    def test_masses_beside_a_picture(self):
        refusal = _refusal(SettingSpec, {"image": "art/x.png", "masses": [{"kind": "sky"}]})
        assert str(refusal) == (
            "'setting' lists masses and names an image; the picture is the whole backdrop, "
            "so write one or the other"
        )
        assert (refusal.rule, refusal.loc) == ("conflicting-setting", ("setting", "masses"))

    def test_a_fit_with_no_picture(self):
        refusal = _refusal(SettingSpec, {"fit": "cover"})
        assert str(refusal) == (
            "'setting' has a fit and no image; `fit` says how a picture fills the panel, so "
            "it goes beside `image`"
        )
        assert (refusal.rule, refusal.loc) == ("invalid-field", ("setting", "fit"))

    def test_a_figure_that_names_a_puppet_after_one_that_does_not(self):
        cast = {"a": {"figure": "ana"}, "b": {"figure": "ben", "reference": "bob"}}
        refusal = _refusal(PanelIR, {"cast": cast, "setting": {"image": "art/x.png"}})
        assert str(refusal) == (
            "cast member 'b' names a puppet and a figure the picture draws; it is one or the "
            "other. Over an inherited member, write `reference: null`"
        )
        assert (refusal.rule, refusal.loc) == ("conflicting-cast", ("cast", "b", "reference"))

    def test_a_figure_placed(self):
        cast = {"a": {"figure": "ana", "facing": "left"}}
        refusal = _refusal(PanelIR, {"cast": cast, "setting": {"image": "art/x.png"}})
        assert str(refusal) == (
            "cast member 'a' is a figure the picture draws, which nobody poses or places, so "
            "'facing' does not apply to it"
        )
        assert refusal.loc == ("cast", "a", "facing")

    def test_a_figure_staged(self):
        data = {
            "cast": {"a": {"figure": "ana"}, "b": {"figure": "ben"}},
            "setting": {"image": "art/x.png"},
            "staging": [{"subject": "a", "predicate": "left_of", "object": "b"}],
        }
        refusal = _refusal(PanelIR, data)
        assert str(refusal) == (
            "staging relation 'left_of' names 'a', a figure the picture draws: the artist "
            "already placed and staged everyone in it"
        )
        assert (refusal.rule, refusal.loc) == ("figure-staging", ("staging", 0))

    def test_a_figure_that_names_a_puppet_after_a_puppet(self):
        """The puppet is passed over, and the figure after it is still checked."""
        cast = {"p": {"reference": "alice"}, "f": {"figure": "ana", "reference": "bob"}}
        refusal = _refusal(PanelIR, {"cast": cast, "setting": {"image": "art/x.png"}})
        assert refusal.loc == ("cast", "f", "reference")


class TestAVoiceFromOffPanel:
    def test_the_first_side_it_names_is_where_it_is(self):
        script = [
            {"verb": "say", "by": "carol", "text": "Here.", "off_panel": "left"},
            {"verb": "say", "by": "carol", "text": "Now here.", "off_panel": "right"},
        ]
        panel = PanelIR.model_validate({"script": script})
        assert panel.off_panel_speakers() == {"carol": Side.LEFT}


class TestTheTitleOfAMembersError:
    """Pydantic names the model a refusal is of; the member's own check keeps the name."""

    def test_alone(self):
        with pytest.raises(ValidationError) as caught:
            CastMember.model_validate({})
        assert caught.value.title == "CastMember"

    def test_with_another_fault(self):
        with pytest.raises(ValidationError) as caught:
            CastMember.model_validate({"facing": 5})
        assert caught.value.title == "CastMember"
