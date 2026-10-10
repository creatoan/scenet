"""The VS Code extension's version is the compiler's.

The extension ships as `scenet.vsix` on each release, built from the same commit, and
its diagnostics and preview shell out to that release's `scenet`. One number for both
says which compiler an extension was written against. The release bumps
`project.version`; `editor/package.json` and its lockfile have to move with it.
"""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return project["version"]


def test_the_extension_version_is_the_compilers():
    manifest = json.loads((ROOT / "editor" / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == _project_version()


def test_the_lockfile_agrees_with_the_manifest():
    """`npm ci` does not check this, so nothing else would notice it drift."""
    lockfile = json.loads((ROOT / "editor" / "package-lock.json").read_text(encoding="utf-8"))
    assert lockfile["version"] == _project_version()
    assert lockfile["packages"][""]["version"] == _project_version()
