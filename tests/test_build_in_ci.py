"""The CI how-to installs the current release, and says so (#322).

`docs/howto/build_in_ci.md` pins the version a workflow installs, as it should: below 1.0 a
minor release may break things. A pin that is never moved teaches a reader an old release,
and each flag the page shows may be one that release lacks. So the pin it shows, and the
release it says it was last checked with, are held to the project's version: a release PR
that bumps `pyproject.toml` fails here until the page follows.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "howto" / "build_in_ci.md"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_the_workflow_installs_the_current_release():
    pins = re.findall(r"scenet==([\w.+-]+)", PAGE.read_text(encoding="utf-8"))
    assert pins
    assert set(pins) == {VERSION}


def test_it_says_the_release_it_was_checked_with():
    checked = re.findall(r"Last checked with Scenet ([\w.+-]+?)\.?\s", PAGE.read_text("utf-8"))
    assert checked == [VERSION]
