"""Reading YAML without losing a repeated key (#83).

PyYAML keeps the last of two equal keys in a mapping and drops the first without a
word, although the YAML specification makes a repeated key an error. Upstream has long
been asked not to (yaml/pyyaml#41, still open). For a language that rejects every unknown key,
silently losing a known one -- a whole panel, a cast member -- is the worst failure.
"""

from pathlib import Path

import pytest
import yaml

from scenet.assets.contract import load_puppet
from scenet.errors import AssetError
from scenet.safe_yaml import DuplicateKeyError, load

ROOT = Path(__file__).resolve().parents[1]


class TestRepeatedKeys:
    def test_a_repeated_top_level_key_is_refused(self):
        with pytest.raises(DuplicateKeyError) as caught:
            load("camera: {shot: close_up}\ncamera: {shot: long_shot}\n")
        assert caught.value.key == "camera"
        assert (caught.value.first_line, caught.value.line) == (1, 2)

    def test_a_repeated_cast_member_is_refused(self):
        """The case that lost a character: both compiled, one survived."""
        with pytest.raises(DuplicateKeyError) as caught:
            load("cast:\n  alice: {reference: alice}\n  alice: {reference: bob}\n")
        assert caught.value.key == "alice"
        assert (caught.value.first_line, caught.value.line) == (2, 3)

    def test_a_repeated_panel_is_refused(self):
        with pytest.raises(DuplicateKeyError) as caught:
            load("panels:\n  one: {}\n  two: {}\n  one: {}\n")
        assert (caught.value.key, caught.value.line) == ("one", 4)

    def test_a_repeat_inside_a_flow_mapping_is_refused(self):
        with pytest.raises(DuplicateKeyError) as caught:
            load("setting: {place: docks, place: street}\n")
        assert caught.value.key == "place"

    def test_keys_that_load_as_the_same_value_are_a_repeat(self):
        """`1`, `1.0` and `true` are three keys in the text and one in the result."""
        with pytest.raises(DuplicateKeyError):
            load("{1: a, 1.0: b}\n")

    def test_the_message_says_where_both_are(self):
        with pytest.raises(DuplicateKeyError, match="line 2") as caught:
            load("cast:\n  alice: {}\n  alice: {}\n")
        assert "alice" in str(caught.value)

    def test_it_is_still_a_yaml_error(self):
        """Every caller already handles `yaml.YAMLError`; a repeated key is one."""
        with pytest.raises(yaml.YAMLError):
            load("a: 1\na: 2\n")


class TestPuppetFiles:
    def test_a_repeated_pose_is_refused_with_the_file_named(self, tmp_path: Path):
        """A puppet is YAML too, and a second `pointing:` silently replaced the first."""
        text = (ROOT / "src/scenet/assets/library/alice.puppet.yaml").read_text(encoding="utf-8")
        doubled = text.replace("poses:\n", "poses:\n  pointing: {}\n", 1)
        assert doubled != text
        path = tmp_path / "alice.puppet.yaml"
        path.write_text(doubled, encoding="utf-8")

        with pytest.raises(AssetError, match="pointing") as caught:
            load_puppet(path)
        assert "alice.puppet.yaml" in str(caught.value)


class TestWhatIsStillAllowed:
    def test_the_same_key_in_different_mappings(self):
        source = "cast:\n  alice: {reference: alice}\nstaging: []\nscript: [{say: {by: alice}}]\n"
        assert load(source) == yaml.safe_load(source)

    def test_a_merge_key_override_is_not_a_repeat(self):
        """`<<: *base` then the key again is how YAML spells an override. PyYAML puts the
        merged keys into the mapping before it builds it, so the check has to look at
        the keys as written."""
        source = "base: &base {shot: close_up, angle: low}\npanel: {<<: *base, shot: long_shot}\n"
        assert load(source) == {
            "base": {"shot": "close_up", "angle": "low"},
            "panel": {"shot": "long_shot", "angle": "low"},
        }

    def test_an_empty_document(self):
        assert load("") is None

    @pytest.mark.parametrize(
        "path",
        sorted(
            [
                *ROOT.glob("examples/*.yaml"),
                *ROOT.glob("examples/gallery/*.yaml"),
                *ROOT.glob("src/scenet/assets/library/*.yaml"),
            ]
        ),
        ids=lambda path: path.name,
    )
    def test_every_shipped_document_loads_exactly_as_before(self, path: Path):
        text = path.read_text(encoding="utf-8")
        assert load(text) == yaml.safe_load(text)

    def test_it_is_safe(self):
        """It builds on `SafeLoader`: no tag constructs an arbitrary Python object."""
        with pytest.raises(yaml.YAMLError):
            load("!!python/object/apply:os.system ['echo hi']\n")
