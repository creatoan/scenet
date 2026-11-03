"""A puppet of your own, named by its path from a cast member's `reference` (#242).

A document names its puppet the way it names a font or a picture: relative to the folder
it is in, with `/` between folders, never absolute -- `reference: puppets/kid.puppet.yaml`.
The file is read through the same folder, or the same files sent with the text, so the
command line, the playground and the MCP server read it alike. A fault in it is reported
as `puppet-file`: in the puppet file itself, at its line, when the document is checked as a
file, and otherwise where the document names it.
"""

import json
from pathlib import Path

import pydantic
import pytest

from scenet import compile_file, compile_source, default_library
from scenet.assets.contract import (
    PUPPET_RULE,
    PUPPET_SUFFIX,
    PuppetFileError,
    PuppetSpec,
    is_puppet_file,
    library_for,
    load_puppet,
    load_puppet_file,
)
from scenet.cli import main
from scenet.diagnostics import RULES, Diagnostic, diagnose_file, diagnose_script, diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.paths import NamedFileError, track_dependencies
from scenet.pipeline import compile_script
from scenet.safe_yaml import load
from tests.puppets import KID, KID_PATH, kid

LOC = ("cast", "kid", "reference")

#: alice, and a kid of the author's own beside her.
PANEL = """\
panel: {size: [900, 600]}
cast:
  alice: {reference: alice, at: left_third}
  kid: {reference: puppets/kid.puppet.yaml, at: right_third, facing: left}
staging: [alice left_of kid]
script:
  - say: {by: kid, text: "Is it far?"}
"""

#: The kid's file with a joint whose parent is misspelt.
MISSPELT = kid("knee_l: {parent: hip_l,", "knee_l: {parent: hipl,")


def _files(text: str | bytes = KID) -> dict[str, bytes]:
    return {KID_PATH: text.encode("utf-8") if isinstance(text, str) else text}


def _one(found: list[Diagnostic], rule: str = PUPPET_RULE) -> Diagnostic:
    assert [item.rule for item in found] == [rule], [(item.rule, item.message) for item in found]
    return found[0]


def _line(text: str, found: Diagnostic) -> str:
    assert found.region is not None
    return text.splitlines()[found.region.start.line - 1]


def _write(folder: Path, puppet: str = KID, document: str = PANEL, name: str = "p.panel.yaml"):
    (folder / "puppets").mkdir(exist_ok=True)
    (folder / KID_PATH).write_text(puppet, encoding="utf-8")
    path = folder / name
    path.write_text(document, encoding="utf-8")
    return path


class TestNamedByItsPath:
    def test_a_member_is_drawn_by_the_file_its_reference_names(self):
        core = compile_source(PANEL, base=_files()).core
        assert core.actor("kid").reference == KID_PATH

        def height(actor: str) -> float:
            anchors = core.actor(actor).anchors
            return anchors["feet"][1] - anchors["head_top"][1]

        # Five heads tall to alice's seven and a half, at the one scale the panel has.
        assert height("kid") == pytest.approx(height("alice") * 500 / 750, rel=0.01)

    def test_from_a_folder_as_from_the_files_sent(self, tmp_path: Path):
        document = _write(tmp_path)
        from_folder = compile_file(document).core
        assert from_folder.to_json() == compile_source(PANEL, base=_files()).core.to_json()

    def test_written_with_dot_slash(self):
        source = PANEL.replace("reference: puppets/", "reference: ./puppets/")
        assert compile_source(source, base=_files()).core.actor("kid").reference == (
            "./puppets/kid.puppet.yaml"
        )

    def test_from_a_folder_beside_the_documents_own(self, tmp_path: Path):
        """A shared library of characters, as `../fonts/` is a shared folder of faces."""
        (tmp_path / "puppets").mkdir()
        (tmp_path / KID_PATH).write_text(KID, encoding="utf-8")
        (tmp_path / "chapter").mkdir()
        document = tmp_path / "chapter" / "p.panel.yaml"
        document.write_text(PANEL.replace("puppets/", "../puppets/"), encoding="utf-8")
        assert compile_file(document).core.actor("kid").reference == "../puppets/kid.puppet.yaml"

    def test_the_camera_records_the_reference_as_the_actor_does(self):
        source = PANEL.replace("  alice: {reference: alice, at: left_third}\n", "").replace(
            "staging: [alice left_of kid]\n", ""
        )
        core = compile_source(source, base=_files()).core
        assert core.camera is not None
        assert core.camera.reference == KID_PATH
        alone = compile_source("cast: {a: {reference: alice}}").core
        assert alone.camera is not None
        assert alone.camera.reference == "alice"

    def test_its_poses_and_expressions_are_its_own(self):
        source = PANEL.replace("facing: left}", "facing: left, pose: cartwheel, expression: dizzy}")
        actor = compile_source(source, base=_files()).core.actor("kid")
        assert (actor.pose, actor.expression) == ("cartwheel", "dizzy")

    def test_two_members_may_be_drawn_by_one_file(self):
        source = PANEL.replace(
            "  alice: {reference: alice, at: left_third}",
            "  twin: {reference: puppets/kid.puppet.yaml, at: left_third}",
        ).replace("alice left_of kid", "twin left_of kid")
        core = compile_source(source, base=_files()).core
        assert [actor.reference for actor in core.actors] == [KID_PATH, KID_PATH]

    def test_a_name_is_never_read_as_a_file(self):
        """A path is never a name: `alice` is the shipped puppet whatever sits beside."""
        files = {"alice": KID.encode("utf-8"), "alice.puppet.yaml": KID.encode("utf-8")}
        source = "cast: {a: {reference: alice}}\n"
        assert compile_source(source, base=files).core == compile_source(source).core

    def test_a_file_nobody_casts_is_never_read(self):
        source = "cast: {a: {reference: alice}}\n"
        assert compile_source(source, base=_files("- not a puppet\n")).core.actors

    def test_the_output_names_no_folder(self, tmp_path: Path):
        document = _write(tmp_path)
        core = compile_file(document).core.to_json()
        assert str(tmp_path) not in core
        assert tmp_path.as_posix() not in core

    def test_watching_a_build_watches_its_puppet_too(self, tmp_path: Path):
        """`scenet build --watch` rebuilds when a file the document read changes."""
        document = _write(tmp_path)
        dependencies: set[Path] = set()
        with track_dependencies(dependencies):
            compile_file(document)
        assert (tmp_path / KID_PATH).resolve() in dependencies


class TestTheLibrary:
    @pytest.mark.parametrize(
        ("reference", "expected"),
        [
            ("puppets/kid.puppet.yaml", True),
            ("kid.puppet.yaml", True),
            ("../Kid.PUPPET.YAML", True),
            ("alice", False),
            ("kid.yaml", False),
            ("art/p01.art.yaml", False),
        ],
    )
    def test_a_reference_names_a_file_by_its_suffix(self, reference: str, expected: bool):
        assert PUPPET_SUFFIX == ".puppet.yaml"
        assert is_puppet_file(reference) is expected

    def test_the_library_of_a_cast_holds_each_file_under_its_reference(self):
        cast = {"alice": "alice", "kid": KID_PATH, "twin": KID_PATH}
        library = library_for(cast, _files(), default_library())
        assert library.names() == ("alice", "bob", KID_PATH)
        assert library.get(KID_PATH).name == "kid"
        assert default_library().names() == ("alice", "bob")

    def test_a_cast_of_names_is_drawn_from_the_library_as_it_is(self):
        library = default_library()
        assert library_for({"a": "alice"}, None, library) is library

    def test_a_file_reads_as_load_puppet_reads_it(self, tmp_path: Path):
        (tmp_path / "kid.puppet.yaml").write_text(KID, encoding="utf-8")
        assert load_puppet_file("kid.puppet.yaml", tmp_path, loc=LOC) == load_puppet(
            tmp_path / "kid.puppet.yaml"
        )


class TestEachFaultIsOneFinding:
    """`check` reports one `puppet-file` where the file is named; `build` refuses alike."""

    def _agree(self, source: str, files: dict[str, bytes] | None) -> Diagnostic:
        found = _one(diagnose_source(source, base=files))
        with pytest.raises(PanelSyntaxError) as caught:
            compile_source(source, base=files)
        assert caught.value.rule == PUPPET_RULE
        assert found.message in str(caught.value)
        assert found.path == LOC
        assert "reference: " in _line(source, found)
        return found

    @pytest.mark.parametrize(
        ("written", "said"),
        [
            ("/srv/puppets/kid.puppet.yaml", "is absolute"),
            ("C:/puppets/kid.puppet.yaml", "is absolute"),
            ("puppets\\\\kid.puppet.yaml", "has a backslash in it"),
            ("puppets/kidd.puppet.yaml", "was not found beside the document"),
        ],
    )
    def test_a_path_that_cannot_be_read(self, written: str, said: str):
        found = self._agree(PANEL.replace("puppets/kid.puppet.yaml", f'"{written}"'), _files())
        assert said in found.message

    def test_text_with_no_folder_names_no_file(self):
        assert "has no folder" in self._agree(PANEL, None).message

    @pytest.mark.parametrize(
        ("text", "said"),
        [
            (b"\xff\xfe\x00name", "not UTF-8"),
            ("name: [kid\n", "not valid YAML"),
            ("name: kid\nname: kid\n", "appears twice"),
            ("- a list\n", "must be a mapping"),
            ("", "must be a mapping"),
            (MISSPELT, "names unknown parent 'hipl'"),
        ],
    )
    def test_a_file_that_is_not_a_puppet(self, text: str | bytes, said: str):
        found = self._agree(PANEL, _files(text))
        assert said in found.message
        assert f"puppet file '{KID_PATH}'" in found.message

    def test_its_own_line_is_in_the_message_when_checked_as_text(self):
        found = self._agree(PANEL, _files(MISSPELT))
        number = MISSPELT.splitlines().index("  knee_l: {parent: hipl, offset: [0, 122]}") + 1
        assert f"'{KID_PATH}', line {number}" in found.message

    def test_a_file_cast_twice_is_one_fault(self):
        source = PANEL.replace(
            "  alice: {reference: alice, at: left_third}",
            "  twin: {reference: puppets/kid.puppet.yaml, at: left_third}",
        ).replace("alice left_of kid", "twin left_of kid")
        found = _one(diagnose_source(source, base=_files(MISSPELT)))
        assert found.path == ("cast", "twin", "reference")

    def test_a_pose_or_an_expression_is_held_to_the_files_puppet(self):
        source = PANEL.replace("facing: left}", "facing: left, pose: pointing}")
        found = _one(diagnose_source(source, base=_files()), "unknown-pose")
        assert "'cartwheel'" in found.message
        assert found.path == ("cast", "kid", "pose")
        source = PANEL.replace("facing: left}", "facing: left, expression: angry}")
        found = _one(diagnose_source(source, base=_files()), "unknown-expression")
        assert "'dizzy'" in found.message

    def test_a_name_no_puppet_has_is_unknown_and_the_fix_says_how_to_name_a_file(self):
        found = _one(diagnose_source("cast: {a: {reference: kid}}\n"), "unknown-puppet")
        assert "'kid'" in found.message
        assert PUPPET_SUFFIX in RULES["unknown-puppet"].help


class TestCheckedAsAFile:
    """A fault inside a puppet file is reported in the file, which the author can open."""

    def test_in_the_puppet_file_at_its_line(self, tmp_path: Path):
        document = _write(tmp_path, MISSPELT)
        found = _one(diagnose_file(document))
        assert found.source == tmp_path / "puppets" / "kid.puppet.yaml"
        assert found.path == ("joints", "knee_l", "parent")
        assert _line(MISSPELT, found) == "  knee_l: {parent: hipl, offset: [0, 122]}"

    def test_a_missing_file_is_reported_where_it_is_named(self, tmp_path: Path):
        document = tmp_path / "p.panel.yaml"
        document.write_text(PANEL, encoding="utf-8")
        found = _one(diagnose_file(document))
        assert found.source == document
        assert found.path == LOC

    def test_once_however_many_panels_cast_it(self, tmp_path: Path):
        scene = (
            "cast: {kid: {reference: puppets/kid.puppet.yaml}}\n"
            "panels:\n  one: {panel: {size: [600, 600]}}\n  two: {panel: {size: [900, 600]}}\n"
        )
        document = _write(tmp_path, MISSPELT, scene, name="s.scene.yaml")
        found = _one(diagnose_file(document))
        assert found.source == tmp_path / "puppets" / "kid.puppet.yaml"

    def test_once_from_a_scenes_defaults_when_checked_as_text(self):
        scene = (
            "cast: {kid: {reference: puppets/kid.puppet.yaml}}\n"
            "panels:\n  one: {panel: {size: [600, 600]}}\n  two: {panel: {size: [900, 600]}}\n"
        )
        found = _one(diagnose_source(scene, base=_files(MISSPELT)))
        assert found.path == LOC

    def test_a_valid_file_compiles_and_checks_clean(self, tmp_path: Path):
        assert diagnose_file(_write(tmp_path), deep=True) == []


class TestInAComicScript:
    SCRIPT = """\
---
cast:
  KID: {reference: puppets/kid.puppet.yaml}
---

PANEL 1

KID
Is it far?

PANEL 2

KID
Are we there yet?
"""

    def test_its_front_matter_casts_a_puppet_file(self):
        book = compile_script(self.SCRIPT, base=_files())
        assert {
            actor.reference for result in book.panels.values() for actor in result.core.actors
        } == {KID_PATH}

    def test_a_fault_is_one_finding_at_the_front_matter(self):
        found = _one(diagnose_script(self.SCRIPT, base=_files(MISSPELT)))
        assert found.path == ("cast", "KID", "reference")
        assert _line(self.SCRIPT, found) == "  KID: {reference: puppets/kid.puppet.yaml}"

    def test_checked_as_a_file_it_is_in_the_puppet_file(self, tmp_path: Path):
        document = _write(tmp_path, MISSPELT, self.SCRIPT, name="k.script")
        found = _one(diagnose_file(document))
        assert found.source == tmp_path / "puppets" / "kid.puppet.yaml"
        assert found.path == ("joints", "knee_l", "parent")

    def test_somebody_only_heard_from_off_panel_has_their_puppet_read_too(self):
        """As a misspelt shipped name is: nobody draws them here, but the cast says who."""
        script = """\
---
cast:
  ALICE: {reference: alice}
  KID: {reference: puppets/kid.puppet.yaml}
---

PANEL 1

ALICE
Wait here.

KID (OP)
Is it far?
"""
        found = _one(diagnose_script(script, base=_files(MISSPELT)))
        assert found.path == ("cast", "KID", "reference")


#: Each slip, where it is written, and what the finding is located at. Every one of them is
#: a fault no schema can see, which is why the validators say where.
SLIPS = [
    ("  knees: 375\n", "", ("landmarks",), "landmarks:"),
    ("  chin: 100", "  chin: 40", ("landmarks", "chin"), "  chin: 40"),
    ("  head_top: 0\n", "  head_top: 5\n", ("landmarks", "head_top"), "  head_top: 5"),
    ("units_per_head: 100\n", "units_per_head: 100\nroot: pelvis\n", ("root",), "root: pelvis"),
    (
        "  root: {parent: null,",
        "  root: {parent: spine,",
        ("joints", "root", "parent"),
        "  root: {parent: spine",
    ),
    (
        "knee_l: {parent: hip_l,",
        "knee_l: {parent: hipl,",
        ("joints", "knee_l", "parent"),
        "  knee_l: {parent: hipl",
    ),
    (
        "  spine: {parent: root,",
        "  spine: {parent: neck,",
        ("joints", "spine", "parent"),
        "  spine: {parent: neck",
    ),
    ("to: knee_l, width: 28}", "to: knee_x, width: 28}", ("parts", 3, "to"), "to: knee_x"),
    ("  - {at: head, radius: 50}", "  - {at: hed, radius: 50}", ("parts", 5, "at"), "at: hed"),
    (
        "mouth: {joint: head, offset: [0, 26]}",
        "mouth: {joint: jaw, offset: [0, 26]}",
        ("anchors", "mouth", "joint"),
        "  mouth: {joint: jaw",
    ),
    ("face:\n  joint: head", "face:\n  joint: skull", ("face", "joint"), "  joint: skull"),
    (
        "    mouth: {offset: [0, 26], size: 12}",
        "    mouth: {joint: jaw, offset: [0, 26], size: 12}",
        ("face", "features", "mouth", "joint"),
        "    mouth: {joint: jaw",
    ),
    ("  origin: eyes", "  origin: brow", ("gaze", "origin"), "  origin: brow"),
    (
        "standing_neutral: {elbow_l: -5,",
        "standing_neutral: {elbo_l: -5,",
        ("poses", "standing_neutral", "elbo_l"),
        "  standing_neutral: {elbo_l",
    ),
    ("    brow_r: {offset: [18, -30], size: 10}\n", "", ("face", "features", "brow_l"), "brow_l"),
    ("  neutral: {}\n", "", ("expressions",), "expressions:"),
    (
        "{from: neck, to: root, width: 64}",
        "{from: neck, to: root, width: -64}",
        ("parts", 0, "width"),
        "width: -64",
    ),
    (
        "neck: {parent: spine, offset:",
        "neck: {parent: spine, ofset:",
        ("joints", "neck", "ofset"),
        "ofset",
    ),
    ("units_per_head: 100", "units_per_head: .inf", ("units_per_head",), "units_per_head: .inf"),
]


class TestEachSlipIsLocatedInTheFile:
    """What the author must open and where: the key that is wrong, on its line."""

    @pytest.mark.parametrize(
        ("old", "new", "inner", "written"), SLIPS, ids=[".".join(map(str, s[2])) for s in SLIPS]
    )
    def test_at_the_key(self, old: str, new: str, inner: tuple[str | int, ...], written: str):
        text = kid(old, new)
        with pytest.raises(PuppetFileError) as caught:
            load_puppet_file(KID_PATH, _files(text), loc=LOC)
        error = caught.value
        assert isinstance(error, NamedFileError)
        assert (error.rule, error.loc, error.file) == (PUPPET_RULE, LOC, KID_PATH)
        assert error.inner == inner
        assert error.region is not None
        assert written in text.splitlines()[error.region.start.line - 1]

    def test_expressions_with_no_features_to_move(self):
        bare = "\n".join(
            line
            for line in KID.splitlines()
            if not line.startswith(("    brow", "    eye", "    mouth"))
        ).replace("  features:\n", "")
        with pytest.raises(PuppetFileError) as caught:
            load_puppet_file(KID_PATH, _files(bare), loc=LOC)
        assert caught.value.inner == ("expressions",)

    def test_the_messages_are_the_ones_the_how_to_lists(self):
        """Located, and still worded as before: `PuppetSpec` raises them as it always has."""
        with pytest.raises(pydantic.ValidationError, match="missing landmarks"):
            PuppetSpec.model_validate(load(kid("  knees: 375\n", "")))
        with pytest.raises(pydantic.ValidationError, match="sits in a cycle"):
            PuppetSpec.model_validate(
                load(kid("  spine: {parent: root,", "  spine: {parent: neck,"))
            )


class TestTheCommandLine:
    def test_build_and_check_a_document_beside_its_puppet(self, tmp_path: Path):
        document = _write(tmp_path)
        assert main(["check", str(document)]) == 0
        out = tmp_path / "out"
        out.mkdir()
        assert main(["build", str(document), "-o", f"{out}/", "--quiet", "--core"]) == 0
        core = json.loads((out / "p.core.json").read_text(encoding="utf-8"))
        assert [actor["reference"] for actor in core["actors"]] == ["alice", KID_PATH]

    def test_prose_names_the_puppet_file_and_its_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        _write(tmp_path, MISSPELT)
        monkeypatch.chdir(tmp_path)
        assert main(["check", "p.panel.yaml"]) == 1
        number = MISSPELT.splitlines().index("  knee_l: {parent: hipl, offset: [0, 122]}") + 1
        err = capsys.readouterr().err
        assert f"{Path('puppets') / 'kid.puppet.yaml'}:{number}:" in err
        assert "puppet-file:" in err

    def test_sarif_names_the_puppet_file_relative_to_where_check_ran(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        _write(tmp_path, MISSPELT)
        monkeypatch.chdir(tmp_path)
        assert main(["check", "--format", "sarif", "p.panel.yaml"]) == 1
        (result,) = json.loads(capsys.readouterr().out)["runs"][0]["results"]
        location = result["locations"][0]["physicalLocation"]
        assert result["ruleId"] == "scenet/puppet-file"
        assert location["artifactLocation"]["uri"] == KID_PATH

    def test_build_says_what_is_wrong_in_one_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        document = _write(tmp_path, MISSPELT)
        assert main(["build", str(document), "-o", f"{tmp_path}/"]) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert f"puppet file '{KID_PATH}'" in err

    def test_a_puppet_is_not_itself_a_document(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        _write(tmp_path)
        puppet = tmp_path / KID_PATH
        assert main(["check", str(puppet)]) == 2
        assert "a puppet is not a document" in capsys.readouterr().err
        assert main(["build", str(puppet)]) == 2
