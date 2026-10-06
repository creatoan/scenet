"""IR validation: what the language accepts, and what it must reject.

These tests are mostly about rejection. A compiler for a precise language earns its
keep by refusing ambiguous input loudly rather than rendering something plausible and
wrong.
"""

import json

import pytest
from pydantic import ValidationError

from scenet.core import PanelCore
from scenet.diagnostics import diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.frontends.yaml_front import parse_panel, parse_scene_document
from scenet.ir import (
    AnchorX,
    CaptionEvent,
    CaptionKind,
    CastMember,
    PanelIR,
    PanelSpec,
    PlacementZone,
    Predicate,
    Relation,
    SayEvent,
)
from scenet.pipeline import compile_source


def cast(*names: str) -> dict[str, CastMember]:
    return {name: CastMember(reference=name) for name in names}


class TestPanelSpec:
    def test_rejects_non_positive_size(self):
        with pytest.raises(ValidationError, match="must be positive"):
            PanelSpec(size=(0.0, 100.0))

    def test_rejects_margin_that_consumes_the_panel(self):
        with pytest.raises(ValidationError, match="no usable panel area"):
            PanelSpec(size=(100.0, 100.0), margin=50.0)

    def test_exposes_width_and_height(self):
        spec = PanelSpec(size=(800.0, 600.0))
        assert (spec.width, spec.height) == (800.0, 600.0)


class TestStrictness:
    def test_unknown_key_is_rejected(self):
        """A silently ignored typo is the worst failure mode for a precise language."""
        with pytest.raises(ValidationError, match=r"camra|extra"):
            PanelIR.model_validate({"camra": {"shot": "close_up"}})

    def test_models_are_immutable(self):
        member = CastMember(reference="alice")
        with pytest.raises(ValidationError):
            member.reference = "bob"  # ty: ignore[invalid-assignment]


class TestReferenceResolution:
    def test_staging_naming_unknown_actor_is_rejected(self):
        with pytest.raises(ValidationError, match="unknown actor 'carol'"):
            PanelIR(
                cast=cast("alice"),
                staging=(Relation(subject="alice", predicate=Predicate.LEFT_OF, object="carol"),),
            )

    def test_script_spoken_by_unknown_actor_is_rejected(self):
        with pytest.raises(ValidationError, match="unknown actor 'ghost'"):
            PanelIR(cast=cast("alice"), script=(SayEvent(by="ghost", text="hello"),))

    def test_reflexive_relation_is_rejected(self):
        with pytest.raises(ValidationError, match="cannot relate"):
            Relation(subject="alice", predicate=Predicate.LEFT_OF, object="alice")


class TestOrdering:
    def test_direct_cycle_is_rejected(self):
        with pytest.raises(ValidationError, match="cyclic"):
            PanelIR(
                cast=cast("alice", "bob"),
                staging=(
                    Relation(subject="alice", predicate=Predicate.LEFT_OF, object="bob"),
                    Relation(subject="bob", predicate=Predicate.LEFT_OF, object="alice"),
                ),
            )

    def test_indirect_cycle_is_rejected(self):
        with pytest.raises(ValidationError, match="cyclic"):
            PanelIR(
                cast=cast("a", "b", "c"),
                staging=(
                    Relation(subject="a", predicate=Predicate.LEFT_OF, object="b"),
                    Relation(subject="b", predicate=Predicate.LEFT_OF, object="c"),
                    Relation(subject="c", predicate=Predicate.LEFT_OF, object="a"),
                ),
            )

    def test_chain_without_a_cycle_is_accepted(self):
        panel = PanelIR(
            cast=cast("a", "b", "c"),
            staging=(
                Relation(subject="a", predicate=Predicate.LEFT_OF, object="b"),
                Relation(subject="b", predicate=Predicate.LEFT_OF, object="c"),
            ),
        )
        assert panel.ordering_constraints() == (("a", "b"), ("b", "c"))

    def test_right_of_is_normalised_to_a_left_right_pair(self):
        """left_of and right_of are the same constraint written from either end."""
        panel = PanelIR(
            cast=cast("a", "b"),
            staging=(Relation(subject="a", predicate=Predicate.RIGHT_OF, object="b"),),
        )
        assert panel.ordering_constraints() == (("b", "a"),)

    def test_right_of_participates_in_cycle_detection(self):
        with pytest.raises(ValidationError, match="cyclic"):
            PanelIR(
                cast=cast("a", "b"),
                staging=(
                    Relation(subject="a", predicate=Predicate.LEFT_OF, object="b"),
                    Relation(subject="a", predicate=Predicate.RIGHT_OF, object="b"),
                ),
            )


class TestGroundGroups:
    def test_shared_ground_is_transitive(self):
        """'a with b' plus 'b with c' must put all three on one ground line without
        the author having to state 'a with c'."""
        panel = PanelIR(
            cast=cast("a", "b", "c"),
            staging=(
                Relation(subject="a", predicate=Predicate.GROUND_SHARED_WITH, object="b"),
                Relation(subject="b", predicate=Predicate.GROUND_SHARED_WITH, object="c"),
            ),
        )
        assert panel.ground_groups() == (frozenset({"a", "b", "c"}),)

    def test_unrelated_actors_form_no_group(self):
        panel = PanelIR(cast=cast("a", "b"))
        assert panel.ground_groups() == ()

    def test_separate_groups_stay_separate(self):
        panel = PanelIR(
            cast=cast("a", "b", "c", "d"),
            staging=(
                Relation(subject="a", predicate=Predicate.GROUND_SHARED_WITH, object="b"),
                Relation(subject="c", predicate=Predicate.GROUND_SHARED_WITH, object="d"),
            ),
        )
        assert set(panel.ground_groups()) == {frozenset({"a", "b"}), frozenset({"c", "d"})}


class TestGaze:
    def test_looking_at_is_collected(self):
        panel = PanelIR(
            cast=cast("alice", "bob"),
            staging=(Relation(subject="alice", predicate=Predicate.LOOKING_AT, object="bob"),),
        )
        assert panel.gaze_targets() == {"alice": "bob"}


class TestPlacementZone:
    @pytest.mark.parametrize(
        ("zone", "expected"),
        [
            (PlacementZone.TOP_LEFT, (0.25, 0.2)),
            (PlacementZone.MIDDLE_CENTRE, (0.5, 0.5)),
            (PlacementZone.BOTTOM_RIGHT, (0.75, 0.8)),
        ],
    )
    def test_fractions(self, zone: PlacementZone, expected: tuple[float, float]):
        assert zone.fractions == expected

    def test_every_zone_resolves(self):
        """Guards against a member whose name does not parse into two known halves."""
        for zone in PlacementZone:
            across, down = zone.fractions
            assert 0.0 < across < 1.0
            assert 0.0 < down < 1.0

    def test_balloon_hint_is_two_dimensional(self):
        """A regression guard: `prefer` was briefly typed as the horizontal-only
        AnchorX, which cannot express 'top_left' at all."""
        event = SayEvent(by="alice", text="hi", prefer=PlacementZone.TOP_LEFT)
        assert event.prefer is PlacementZone.TOP_LEFT
        assert PlacementZone.TOP_LEFT.value not in {member.value for member in AnchorX}


class TestCaptionEvent:
    def test_the_four_kinds_are_the_letterers_vocabulary(self):
        """Blambot's set, taken rather than invented -- as the predicates were taken
        from Visual Genome. 'narration' is deliberately not among them."""
        assert {kind.value for kind in CaptionKind} == {
            "locale",
            "monologue",
            "spoken",
            "editorial",
        }

    def test_locale_is_the_default_kind(self):
        assert CaptionEvent(text="Midnight. The docks.").kind is CaptionKind.LOCALE

    def test_top_left_is_the_default_placement(self):
        assert CaptionEvent(text="Midnight.").prefer is PlacementZone.TOP_LEFT

    @pytest.mark.parametrize(
        ("kind", "italic"),
        [
            (CaptionKind.LOCALE, True),
            (CaptionKind.MONOLOGUE, True),
            (CaptionKind.EDITORIAL, True),
            (CaptionKind.SPOKEN, False),
        ],
    )
    def test_only_spoken_is_set_roman(self, kind: CaptionKind, italic: bool):
        assert kind.is_italic is italic

    def test_only_spoken_takes_quotation_marks(self):
        quoted = [kind for kind in CaptionKind if kind.is_quoted]
        assert quoted == [CaptionKind.SPOKEN]

    def test_empty_text_is_rejected(self):
        with pytest.raises(ValidationError):
            CaptionEvent(text="")


class TestCaptionSpeaker:
    """`by` names an off-panel speaker, which only `spoken` has."""

    def test_spoken_may_name_a_speaker(self):
        assert CaptionEvent(text="Get down!", kind=CaptionKind.SPOKEN, by="doctor").by == "doctor"

    @pytest.mark.parametrize(
        "kind", [CaptionKind.LOCALE, CaptionKind.MONOLOGUE, CaptionKind.EDITORIAL]
    )
    def test_the_other_kinds_may_not(self, kind: CaptionKind):
        with pytest.raises(ValidationError, match="only a 'spoken' caption"):
            CaptionEvent(text="Midnight.", kind=kind, by="alice")

    def test_an_off_panel_speaker_need_not_be_in_the_cast(self):
        """The point of the field: the speaker is off panel, so by definition not cast."""
        panel = PanelIR(
            cast=cast("alice"),
            script=(CaptionEvent(text="Get down!", kind=CaptionKind.SPOKEN, by="doctor"),),
        )
        assert panel.script[0].by == "doctor"

    def test_a_say_by_the_same_unknown_actor_is_still_rejected(self):
        """The exemption is for captions only; it must not have widened the hole."""
        with pytest.raises(ValidationError, match="unknown actor 'doctor'"):
            PanelIR(cast=cast("alice"), script=(SayEvent(by="doctor", text="Get down!"),))


class TestScriptIsAUnion:
    def test_both_events_carry_their_verb(self):
        assert SayEvent(by="alice", text="hi").verb == "say"
        assert CaptionEvent(text="Midnight.").verb == "caption"

    def test_a_tagged_mapping_resolves_to_the_right_type(self):
        panel = PanelIR.model_validate(
            {
                "cast": {"alice": {"reference": "alice"}},
                "script": [
                    {"verb": "caption", "text": "Midnight."},
                    {"verb": "say", "by": "alice", "text": "Hello."},
                ],
            }
        )
        assert [type(event) for event in panel.script] == [CaptionEvent, SayEvent]

    def test_an_untagged_mapping_still_resolves(self):
        """The verb is defaulted rather than a discriminator, so callers that never
        write it -- every existing one -- keep working."""
        panel = PanelIR.model_validate(
            {
                "cast": {"alice": {"reference": "alice"}},
                "script": [{"by": "alice", "text": "Hello."}, {"text": "Midnight."}],
            }
        )
        assert [type(event) for event in panel.script] == [SayEvent, CaptionEvent]

    def test_a_caption_may_be_mixed_into_a_script(self):
        panel = PanelIR(
            cast=cast("alice"),
            script=(
                SayEvent(by="alice", text="Hello."),
                CaptionEvent(text="Later."),
                SayEvent(by="alice", text="Still here."),
            ),
        )
        assert len(panel.script) == 3


class TestNonFiniteNumbers:
    """`.inf` and `.nan` are valid YAML floats, and pydantic accepts them by default. One
    in a size reached the solver, where kiwisolver ended the interpreter outright -- no
    exception, no traceback, no finding. Every number a document holds is a length, a
    weight or a fraction, and none of those means anything infinite or undefined."""

    PANEL = "panel: {size: [600, 400], margin: 10}\ncast: {a: {reference: alice}}\n"
    SCENE = (
        "cast: {a: {reference: alice}}\n"
        "page: {size: [2000, 3000]}\n"
        "pages: [{tiers: [{height: 1, panels: [{use: one, width: 1}]}]}]\n"
        "panels: {one: {}}\n"
    )

    @pytest.mark.parametrize("value", [".inf", "-.inf", ".nan"])
    @pytest.mark.parametrize(
        ("original", "path"),
        [
            ("size: [600, 400]", ("panel", "size", 0)),
            ("margin: 10", ("panel", "margin")),
        ],
    )
    def test_a_panel_refuses_them(self, value: str, original: str, path: tuple[str | int, ...]):
        replaced = original.replace("600", value) if "size" in original else f"margin: {value}"
        source = self.PANEL.replace(original, replaced)
        with pytest.raises(PanelSyntaxError):
            parse_panel(source)
        (finding,) = diagnose_source(source)
        assert finding.rule == "invalid-field"
        assert finding.path == path

    @pytest.mark.parametrize("value", [".inf", ".nan"])
    @pytest.mark.parametrize(
        ("original", "replacement", "path"),
        [
            ("size: [2000, 3000]", "size: [{v}, 3000]", ("page", "size", 0)),
            ("height: 1", "height: {v}", ("pages", 0, "tiers", 0, "height")),
            ("width: 1", "width: {v}", ("pages", 0, "tiers", 0, "panels", 0, "width")),
        ],
    )
    def test_a_page_refuses_them(
        self, value: str, original: str, replacement: str, path: tuple[str | int, ...]
    ):
        source = self.SCENE.replace(original, replacement.format(v=value))
        with pytest.raises(PanelSyntaxError):
            parse_scene_document(source)
        (finding,) = diagnose_source(source)
        assert finding.rule == "invalid-field"
        assert finding.path == path

    def test_a_panel_core_refuses_them(self):
        """A Core is a format people hand-edit, and `json.loads` reads `NaN`."""
        payload = json.loads(compile_source(self.PANEL).core.to_json())
        payload["width"] = float("nan")
        with pytest.raises(ValidationError):
            PanelCore.from_json(json.dumps(payload))
