"""A core vocabulary of poses and expressions that every puppet declares (#360).

Poses and expressions were free strings: a model invented `running` or `furious`, and only
the compiler noticed. Now a core vocabulary is normative. Every puppet, shipped or
supplied, declares all of it, so a document that keeps to it is valid with any conforming
puppet; a puppet may declare more, its own. The JSON Schema offers the core names, and
for a member whose `reference` names a shipped puppet, that puppet's names only.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from scenet.assets.contract import CORE_EXPRESSIONS, CORE_POSES, PuppetSpec, default_library
from scenet.diagnostics import diagnose_source
from scenet.pipeline import compile_source
from scenet.safe_yaml import load
from scenet.schema import panel_schema, puppet_schema, scene_schema, strict_schema
from tests.puppets import KID, KID_PATH
from tests.strategies import dump

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "docs" / "reference" / "language" / "puppet.md"


def _errors(schema: dict[str, Any], document: Any) -> list[str]:
    return [error.message for error in Draft202012Validator(schema).iter_errors(document)]


def _kid() -> dict[str, Any]:
    loaded = load(KID)
    assert isinstance(loaded, dict)
    return loaded


class TestEveryPuppet:
    @pytest.mark.parametrize("name", sorted(default_library().names()))
    def test_a_shipped_puppet_declares_it_all(self, name: str):
        puppet = default_library().get(name)
        assert set(CORE_POSES) <= set(puppet.poses)
        assert set(CORE_EXPRESSIONS) <= set(puppet.expressions)

    def test_the_gallery_puppet_declares_it_all(self):
        puppet = PuppetSpec.model_validate(
            load((ROOT / "examples" / "gallery" / "puppets" / "pip.puppet.yaml").read_text())
        )
        assert set(CORE_POSES) <= set(puppet.poses)
        assert set(CORE_EXPRESSIONS) <= set(puppet.expressions)

    @pytest.mark.parametrize(
        ("old", "missing"),
        [
            ("  pointing: {elbow_l: -8, elbow_r: -85}\n", "'pointing'"),
            ("  coy: {eyes: narrowed, mouth: small}\n", "'coy'"),
        ],
        ids=["a-pose", "an-expression"],
    )
    def test_a_puppet_that_leaves_one_out_is_a_finding_in_its_file(self, old: str, missing: str):
        assert old in KID
        files = {KID_PATH: KID.replace(old, "").encode()}
        (found,) = diagnose_source(f"cast: {{a: {{reference: {KID_PATH}}}}}\n", base=files)
        assert found.rule == "puppet-file"
        # Sent with the document, the file is named in the finding, with its line, and the
        # finding is where the document names it.
        assert found.message.startswith(f"puppet file '{KID_PATH}', line ")
        assert found.path == ("cast", "a", "reference")
        assert missing in found.message
        assert "every puppet declares" in found.message

    def test_a_puppet_may_declare_more(self):
        assert "cartwheel" in KID
        files = {KID_PATH: KID.encode()}
        source = f"cast: {{a: {{reference: {KID_PATH}, pose: cartwheel, expression: dizzy}}}}\n"
        assert diagnose_source(source, base=files) == []


@st.composite
def _puppets(draw: st.DrawFn) -> dict[str, Any]:
    """A conforming puppet: the kid, its core poses bent any way, and more of its own."""
    puppet = _kid()
    angle = st.floats(min_value=-170, max_value=170, allow_nan=False).map(lambda a: round(a, 1))
    puppet["poses"] = {
        name: {"elbow_l": draw(angle), "elbow_r": draw(angle)}
        for name in (
            *CORE_POSES,
            *draw(st.lists(st.sampled_from(["jump", "duck", "spin"]), unique=True)),
        )
    }
    puppet["name"] = draw(st.sampled_from(["kid", "imp", "sprite"]))
    return puppet


@settings(max_examples=25, deadline=None)
@given(
    puppet=_puppets(),
    pose=st.sampled_from(CORE_POSES),
    expression=st.sampled_from(CORE_EXPRESSIONS),
)
def test_a_document_of_core_names_is_valid_with_any_conforming_puppet(
    puppet: dict[str, Any], pose: str, expression: str
):
    files = {KID_PATH: dump(puppet).encode()}
    source = (
        f"cast: {{a: {{reference: {KID_PATH}, pose: {pose}, expression: {expression}}}}}\n"
        "script: [{say: {by: a, text: Hello.}}]\n"
    )
    assert diagnose_source(source, base=files) == []
    assert compile_source(source, base=files).core.actors


class TestTheSchema:
    def test_it_refuses_an_invented_pose_for_a_shipped_puppet(self):
        document = {"cast": {"a": {"reference": "alice", "pose": "shrugging"}}}
        assert _errors(panel_schema(), document)
        assert _errors(scene_schema(), {**document, "panels": {"one": {}}})

    def test_it_takes_the_core_and_a_shipped_puppets_own(self):
        for pose in CORE_POSES:
            assert (
                _errors(panel_schema(), {"cast": {"a": {"reference": "bob", "pose": pose}}}) == []
            )

    def test_a_supplied_puppet_may_name_any_pose(self):
        document = {"cast": {"a": {"reference": KID_PATH, "pose": "cartwheel"}}}
        assert _errors(panel_schema(), document) == []

    def test_it_offers_the_core_vocabulary(self):
        member = panel_schema()["$defs"]["CastMember"]["properties"]
        assert member["pose"]["anyOf"][0]["enum"] == list(CORE_POSES)
        assert member["expression"]["anyOf"][0]["enum"] == list(CORE_EXPRESSIONS)

    def test_the_puppet_schema_states_the_obligation(self):
        schema = puppet_schema()
        assert {"poses", "expressions"} <= set(schema["required"])
        assert schema["properties"]["poses"]["required"] == list(CORE_POSES)
        assert schema["properties"]["expressions"]["required"] == list(CORE_EXPRESSIONS)
        assert "Every puppet declares" in schema["properties"]["poses"]["description"]
        assert _errors(schema, {**_kid(), "poses": {"standing_neutral": {}}})

    def test_the_strict_schema_offers_it_too(self):
        member = strict_schema()["$defs"]["CastEntry"]["properties"]
        assert {"enum": list(CORE_POSES)} in [
            {k: v for k, v in branch.items() if k == "enum"} for branch in member["pose"]["anyOf"]
        ]


class TestTheReference:
    def test_it_lists_the_vocabulary_in_one_table(self):
        text = PAGE.read_text(encoding="utf-8")
        section = text[text.index("## The core vocabulary") :]
        rows = dict(re.findall(r"^\| (Poses|Expressions) \| (.+) \|$", section, flags=re.MULTILINE))
        assert re.findall(r"`([a-z_]+)`", rows["Poses"]) == list(CORE_POSES)
        assert re.findall(r"`([a-z_]+)`", rows["Expressions"]) == list(CORE_EXPRESSIONS)
