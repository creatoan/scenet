"""CI checks the gallery through `scripts/check_gallery.py` (#240).

Some examples give a note on purpose, the ones that show what Scenet tells you, and their
manifest entry declares it under `notes:`. Uploaded to code scanning as `scenet check`
reports them, those notes would be alerts nobody will ever fix. So CI drops what an entry
declares, and fails on anything left: an error, or a note nobody declared.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scenet.diagnostics import Diagnostic

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def check_gallery() -> ModuleType:
    """Import `scripts/check_gallery.py`, which is a script rather than a package module."""
    path = ROOT / "scripts" / "check_gallery.py"
    spec = importlib.util.spec_from_file_location("check_gallery", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_gallery"] = module
    spec.loader.exec_module(module)
    return module


class TestWhatIsDropped:
    def test_a_declared_note(self, check_gallery: ModuleType):
        note = Diagnostic(rule="word-limit", message="this balloon holds 30 words")
        assert check_gallery.undeclared([note], ["word-limit"]) == []

    def test_not_a_note_nobody_declared(self, check_gallery: ModuleType):
        note = Diagnostic(rule="panel-count", message="PAGE ONE says three panels")
        assert check_gallery.undeclared([note], ["word-limit"]) == [note]

    def test_never_an_error(self, check_gallery: ModuleType):
        error = Diagnostic(rule="unknown-actor", message="'carol' is not in the cast")
        assert check_gallery.undeclared([error], ["unknown-actor"]) == [error]


class TestTheGallery:
    def test_it_passes_and_its_sarif_has_no_result(
        self, check_gallery: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(ROOT)
        output = tmp_path / "results.sarif"
        assert check_gallery.run(["-o", str(output)]) == 0
        (run,) = json.loads(output.read_text(encoding="utf-8"))["runs"]
        assert run["tool"]["driver"]["name"] == "scenet"
        assert run["results"] == []

    def test_a_finding_left_fails_it_and_is_reported(
        self,
        check_gallery: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        """What is left is written as SARIF, with paths relative to where CI runs it, and
        printed as `scenet check` prints a finding."""

        def a_note_everywhere(path: Path) -> list[Diagnostic]:
            return [Diagnostic(rule="panel-count", message="miscounted", source=path)]

        monkeypatch.chdir(ROOT)
        monkeypatch.setattr(check_gallery, "diagnose_file", a_note_everywhere)
        output = tmp_path / "results.sarif"
        assert check_gallery.run(["-o", str(output)]) == 1
        (run,) = json.loads(output.read_text(encoding="utf-8"))["runs"]
        uris = {
            result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for result in run["results"]
        }
        assert "examples/gallery/01-two-characters.panel.yaml" in uris
        err = capsys.readouterr().err
        assert "01-two-characters.panel.yaml:1:1: note: panel-count: miscounted" in err
