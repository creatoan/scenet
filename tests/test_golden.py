"""Byte-identical output, across machines, hash seeds and paths.

`docs/reference/cli.md` (*Determinism*): "The same input always produces byte-identical
output ... Two runs on different machines produce files you can compare with `cmp`."

The determinism tests elsewhere compile twice **in one process** and compare strings in
memory, which cannot see three ways the promise breaks:

- **Another machine.** Every output was CRLF on Windows until #89. Here the gallery is
  built through `scenet build` and the bytes on disk are compared with goldens committed
  from Linux, in every CI job, Windows included.
- **Another hash seed.** Two compiles in one process share `PYTHONHASHSEED`, so an output
  that followed set or dict order would pass. Here two processes with different seeds
  must write the same bytes.
- **Another path.** An absolute path, or the working directory, leaking into an output
  would make it differ between checkouts. Here a relative and an absolute source, from
  two directories, must write the same bytes, and none of it may hold the path.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scenet.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _load_updater() -> ModuleType:
    """Import `scripts/update_golden.py`, which is a script rather than a package module."""
    path = ROOT / "scripts" / "update_golden.py"
    spec = importlib.util.spec_from_file_location("update_golden", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_golden"] = module
    spec.loader.exec_module(module)
    return module


update_golden = _load_updater()


class TestTheGalleryMatchesItsGoldens:
    def test_every_output_is_byte_identical_to_its_golden(self, tmp_path: Path):
        written = update_golden.build(update_golden.gallery(), tmp_path)
        stale = update_golden.differences(written)
        assert not stale, (
            f"{len(stale)} outputs differ from their goldens: {', '.join(stale[:10])}"
            + (" ..." if len(stale) > 10 else "")
            + f". If the change is intended, run `{update_golden.COMMAND}` and review the diff."
        )

    def test_the_goldens_cover_every_document(self):
        """A gallery document with no golden would be a promise nobody checks."""
        cores, digests = update_golden.committed()
        for source in update_golden.gallery():
            stem = source.name.split(".")[0]
            assert any(name.startswith(f"{stem}.") for name in digests), source.name
            assert any(name.startswith(f"{stem}.") for name in cores), source.name

    def test_a_changed_byte_is_caught_and_named(self, tmp_path: Path):
        """The check would notice a coordinate moving: alter one output and it is named."""
        written = update_golden.build(update_golden.gallery()[:1], tmp_path)
        name = next(name for name in written if name.endswith(".core.json"))
        written[name] = written[name].replace(b".", b",", 1)
        assert name in update_golden.differences(written)


class TestEveryFindingIsItsGolden:
    """What `scenet check` says, in full, on every document of the rule corpus (#345).

    The corpus pins which rule each document breaks. Mutation testing found that nothing
    held the rest of a finding: the file it names, where it points, the path it gives. A
    finding that pointed at the start of the document, or named no file, passed every
    test. This holds every field, with and without `--deep`.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def golden(cls) -> dict[str, Any]:
        return json.loads(update_golden.FINDINGS.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "path",
        update_golden.finding_documents(),
        ids=lambda path: path.relative_to(ROOT).as_posix(),
    )
    def test_its_findings_are_as_committed(self, path: Path, golden: dict[str, Any]):
        found = update_golden.findings_of(path)
        assert found == {key: golden.get(key) for key in found}, (
            f"a finding changed: if it is intended, run `{update_golden.COMMAND}` and review "
            "the diff of tests/golden/findings.json"
        )

    def test_every_kept_document_is_in_it_and_nothing_else(self, golden: dict[str, Any]):
        documents = {
            path.relative_to(ROOT).as_posix() for path in update_golden.finding_documents()
        }
        assert {name.removesuffix(" --deep") for name in golden} == documents

    def test_every_finding_names_its_file_and_a_place_in_it(self, golden: dict[str, Any]):
        for name, found in golden.items():
            document = name.removesuffix(" --deep")
            folder = document.rpartition("/")[0] + "/"
            for finding in found:
                # A fault inside a file the document names -- a puppet, a contract -- is
                # reported in that file, which is beside the document.
                assert finding["source"] == document or finding["source"].startswith(folder), name
                assert finding["region"] is not None, name


class TestEveryDocumentReadsAsItsGolden:
    """What the front ends read from every kept document, or how they refuse it (#345).

    A Core says what was drawn, and the findings what was wrong; neither holds everything
    read on the way -- a script's line numbers, its notes, a field the solver happens not to
    use. Mutation testing found the front ends' changes to all of those unnoticed.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def golden(cls) -> dict[str, str]:
        return json.loads(update_golden.PARSED.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "path",
        update_golden.finding_documents(),
        ids=lambda path: path.relative_to(ROOT).as_posix(),
    )
    def test_it_reads_as_committed(self, path: Path, golden: dict[str, str]):
        assert update_golden.parsed_of(path) == golden.get(path.relative_to(ROOT).as_posix()), (
            f"what {path.name} reads as changed: if it is intended, run "
            f"`{update_golden.COMMAND}` and review the change"
        )

    def test_every_kept_document_is_in_it_and_nothing_else(self, golden: dict[str, str]):
        documents = {
            path.relative_to(ROOT).as_posix() for path in update_golden.finding_documents()
        }
        assert set(golden) == documents


# A program each child process runs: build the gallery into the directory it is given.
_CHILD = """
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("update_golden", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.build(module.gallery(), Path(sys.argv[2]))
"""


def _build_in_a_process(directory: Path, *, seed: str) -> dict[str, bytes]:
    environment = {**os.environ, "PYTHONHASHSEED": seed}
    subprocess.run(  # noqa: S603 -- our own interpreter, running our own script
        [sys.executable, "-c", _CHILD, str(ROOT / "scripts" / "update_golden.py"), str(directory)],
        check=True,
        env=environment,
        cwd=ROOT,
    )
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


class TestTheHashSeedChangesNothing:
    def test_two_seeds_write_the_same_bytes(self, tmp_path: Path):
        first = _build_in_a_process(tmp_path / "zero", seed="0")
        second = _build_in_a_process(tmp_path / "other", seed="12345")
        assert first.keys() == second.keys()
        differing = sorted(name for name in first if first[name] != second[name])
        assert not differing, f"these depend on the hash seed: {differing}"


class TestThePathChangesNothing:
    #: A scene with pages and a comic script in each format it reads: between them they
    #: write every kind of file.
    SOURCES = (
        "24-page.scene.yaml",
        "13-comic-script.script",
        "31-dark-horse.script",
        "33-planche.script",
        "35-figures.scene.yaml",
        "36-right-to-left.scene.yaml",
    )

    def _build(self, source: str, out: Path, cwd: Path) -> dict[str, bytes]:
        out.mkdir(parents=True)
        with pytest.MonkeyPatch.context() as patch:
            patch.chdir(cwd)
            status = main(
                [
                    "build",
                    source,
                    "-o",
                    f"{out}/",
                    "--core",
                    "--debug",
                    "--strip",
                    "--pdf",
                    "--quiet",
                ]
            )
        assert status == 0
        return {path.name: path.read_bytes() for path in sorted(out.iterdir())}

    @pytest.mark.parametrize("name", SOURCES)
    def test_relative_absolute_and_elsewhere_write_the_same_bytes(self, tmp_path: Path, name: str):
        gallery = ROOT / "examples" / "gallery"
        builds = [
            self._build(f"examples/gallery/{name}", tmp_path / "relative", ROOT),
            self._build(str(gallery / name), tmp_path / "absolute", ROOT),
            self._build(name, tmp_path / "beside", gallery),
        ]
        assert builds[0] == builds[1] == builds[2]

        markers = {str(tmp_path), str(ROOT), tmp_path.name}
        for file_name, data in builds[0].items():
            # Searched as bytes, since a PDF is not text; a path written into one is still
            # its UTF-8 bytes.
            leaked = [marker for marker in markers if marker.encode("utf-8") in data]
            assert not leaked, f"{file_name} holds the path {leaked[0]!r}"
