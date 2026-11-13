"""`scenet check` resolves a cast against the library it is given, at every step (#345).

`diagnose_file`, `diagnose_source` and `diagnose_script` take a puppet library, and hand it
on to each check and, with `deep`, to the compiler. The mutation run found that dropping it
at any of those steps went unnoticed: every test used the shipped puppets, which are what a
dropped library falls back to. Here the library holds one puppet the shipped one does not,
so a step that loses it finds a puppet nobody wrote.
"""

import hashlib
from pathlib import Path

import pytest

from scenet.assets.contract import PuppetLibrary, PuppetSpec
from scenet.diagnostics import diagnose_file, diagnose_script, diagnose_source
from scenet.pipeline import compile_source
from tests.test_diagnostics import _FEATURELESS_PUPPET  # pyright: ignore[reportPrivateUsage]

PANEL = """\
panel: {size: [900, 600]}
cast: {a: {reference: plain}}
script: [{say: {by: a, text: "Hello."}}]
"""

SCENE = """\
panel: {size: [900, 600]}
cast: {a: {reference: plain}}
panels:
  one: {script: [{say: {by: a, text: "Hello."}}]}
  two: {over: one}
"""

PAGED = SCENE + "pages:\n  - tiers:\n      - panels: [one, two]\n"

SCRIPT = """\
---
panel: {size: [900, 600]}
cast: {A: {reference: plain}}
---
PANEL 1
A
Hello.
"""


VOICE = """---
panel: {size: [900, 600]}
cast: {A: {reference: plain}, B: {reference: plain}}
---
PANEL 1
A
Hello?

B (OP)
Out here.
"""


@pytest.fixture(scope="module")
def library() -> PuppetLibrary:
    return PuppetLibrary({"plain": PuppetSpec.model_validate(_FEATURELESS_PUPPET)})


@pytest.mark.parametrize("deep", [False, True], ids=["checked", "deep"])
class TestEveryStepUsesTheLibrary:
    @pytest.mark.parametrize("text", [PANEL, SCENE, PAGED], ids=["panel", "scene", "paged"])
    def test_a_document(self, library: PuppetLibrary, text: str, deep: bool):
        assert diagnose_source(text, library=library, deep=deep) == []

    def test_a_script(self, library: PuppetLibrary, deep: bool):
        assert diagnose_script(SCRIPT, library=library, deep=deep) == []

    def test_a_script_with_a_voice_no_panel_draws(self, library: PuppetLibrary, deep: bool):
        """B is heard from off panel only, so no panel's cast holds them: they are checked
        on their own, against the same library."""
        assert diagnose_script(VOICE, library=library, deep=deep) == []

    @pytest.mark.parametrize(
        ("name", "text"),
        [("one.panel.yaml", PANEL), ("book.scene.yaml", PAGED), ("comic.script", SCRIPT)],
    )
    def test_a_file(self, library: PuppetLibrary, tmp_path: Path, name: str, text: str, deep: bool):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8", newline="\n")
        assert diagnose_file(path, library=library, deep=deep) == []


def test_without_it_the_puppet_is_unknown():
    """What each test above would see if a step lost the library."""
    assert [item.rule for item in diagnose_source(PANEL)] == ["unknown-puppet"]
    assert [item.rule for item in diagnose_script(SCRIPT)] == ["unknown-puppet"]


class TestAPuppetWithNoDrawnParts:
    """A puppet file need not draw anything but a face. Its silhouette is then a line
    between two joints, and balloon placement made a polygon of it, which shapely refuses
    with a `ValueError` -- out of `scenet build`, not as a finding. Found by these tests."""

    def test_it_compiles_and_speaks(self, library: PuppetLibrary):
        result = compile_source(PANEL, library=library)
        (balloon,) = result.core.balloons
        assert balloon.speaker == "a"

    def test_lettering_sees_its_face_alone(self, library: PuppetLibrary):
        result = compile_source(PANEL, library=library)
        (actor,) = result.core.actors
        speaker = result.core.speaker("a")
        assert speaker.face == actor.face_exclusion


class TestTheFindingsAPI:
    """What a caller of the functions gets without asking for more (#345)."""

    def test_a_file_is_checked_without_compiling_unless_asked(self):
        """`deep` is off by default: the panel below only fails once compiled."""
        corpus = Path(__file__).parent / "rule_corpus"
        assert diagnose_file(corpus / "balloon-placement.panel.yaml") == []

    def test_a_finding_with_no_file_has_a_fingerprint_with_none(self):
        """Checked as text -- the playground, a model over MCP -- a finding names no file,
        and its fingerprint is of its rule, path and message alone."""
        (finding,) = diagnose_source("cast: {a: {reference: nobody}}\n")
        assert finding.source is None
        parts = [finding.rule, "cast.a.reference", finding.message, ""]
        expected = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:32]
        assert finding.fingerprint() == expected
