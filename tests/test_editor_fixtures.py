"""The SARIF reports the VS Code extension's tests read are what `scenet check` writes.

The extension maps `scenet check --format sarif` to editor diagnostics, and its tests run
that mapping over reports captured from the checker. A capture that fell behind the
checker would keep the extension's tests green against output the checker no longer
produces, so each one is regenerated here and compared.

To refresh them after a deliberate change to the output, from `editor/test/fixtures/`::

    uv run scenet check --format sarif -o <name>.sarif <sources...>

with the sources listed against each name in `captured.json`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scenet.cli import main

FIXTURES = Path(__file__).parent.parent / "editor" / "test" / "fixtures"
CAPTURED: dict[str, list[str]] = json.loads(
    (FIXTURES / "captured.json").read_text(encoding="utf-8")
)


def _without_version(document: dict[str, Any]) -> dict[str, Any]:
    """The report minus the tool version, which every release changes and nothing reads."""
    for run in document["runs"]:
        run["tool"]["driver"].pop("version", None)
    return document


@pytest.mark.parametrize("name", sorted(CAPTURED))
def test_the_capture_is_what_scenet_check_writes(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # From the fixtures directory, with relative sources, as the capture was made: the
    # uris in the report are relative to the working directory.
    monkeypatch.chdir(FIXTURES)
    written = tmp_path / f"{name}.sarif"
    main(["check", "--format", "sarif", "-o", str(written), *CAPTURED[name]])

    expected = _without_version(json.loads(written.read_text(encoding="utf-8")))
    captured = _without_version(
        json.loads((FIXTURES / f"{name}.sarif").read_text(encoding="utf-8"))
    )
    assert captured == expected, f"{name}.sarif is stale; see this module's docstring"


def test_every_capture_is_listed():
    """A capture nobody regenerates is one nobody checks."""
    on_disk = {path.stem for path in FIXTURES.glob("*.sarif")}
    assert on_disk == set(CAPTURED)
