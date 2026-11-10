"""The API reference renders, and a build in which it would not says so (#316).

Autodoc writes reStructuredText. Called from a MyST fence, its output was read as Markdown:
from v0.8 on, every page of the reference showed `.. py:class::` as text, and the published
`objects.inv` named no Python object, while `sphinx-build -W` passed. `docs/conf.py` now
warns of both, and `-W` makes either warning a failure.

These tests hold the two checks to that, on a small real build made with the project's own
configuration: of the mistake as it shipped, of its fix, and of markup shown on purpose. The
documentation job builds the whole reference with them; this build only proves they work.
"""

import ast
import os
import re
import runpy
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel
from sphinx.ext.napoleon.docstring import GoogleDocstring

from scenet.assets import artwork
from scenet.core import CoreModel
from scenet.ir import BalloonKind, CaptionEvent, CaptionKind, PanelSpec

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SRC = ROOT / "src"

#: The project's own configuration, less what needs the network.
_CONF = """\
import runpy

globals().update(
    {{k: v for k, v in runpy.run_path({conf!r}).items() if not k.startswith("__")}}
)
intersphinx_mapping = {{}}
templates_path = [{templates!r}]
html_static_path = [{static!r}]
"""

_PAGES = {
    "index.md": "# Reference\n\n```{toctree}\nraw\nrendered\nquoted\n```\n",
    # The mistake as it shipped: autodoc called from a MyST fence.
    "raw.md": "# Raw\n\n```{automodule} scenet.places\n```\n",
    # Its fix: autodoc inside an {eval-rst} fence, so reStructuredText reads its output.
    "rendered.md": "# Rendered\n\n```{eval-rst}\n.. automodule:: scenet.errors\n```\n",
    # Markup a page shows as code, on purpose.
    "quoted.md": (
        "# Quoted\n\n"
        "A docstring's `.. seealso::` and `:py:func:` read as code here.\n\n"
        "```rst\n.. py:function:: render(core)\n\n   See :py:class:`scenet.core.PanelCore`.\n```\n"
    ),
}


@dataclass(frozen=True)
class Build:
    """What a build of the pages above said, and what it wrote."""

    warnings: list[str]
    html: Path

    def said(self, subtype: str) -> list[str]:
        """The warnings of one of the two checks: `raw_markup` or `undocumented`."""
        return [warning for warning in self.warnings if f"[scenet.{subtype}]" in warning]


@pytest.fixture(scope="module")
def build(tmp_path_factory: pytest.TempPathFactory) -> Build:
    base = tmp_path_factory.mktemp("api-reference")
    source = base / "source"
    source.mkdir()
    (source / "conf.py").write_text(
        _CONF.format(
            conf=str(DOCS / "conf.py"),
            templates=str(DOCS / "_templates"),
            static=str(DOCS / "_static"),
        ),
        encoding="utf-8",
    )
    for name, text in _PAGES.items():
        (source / name).write_text(text, encoding="utf-8")
    warnings = base / "warnings.txt"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "sphinx",
            "-q",
            "-N",
            "-b",
            "html",
            "-w",
            str(warnings),
            "-d",
            str(base / "doctrees"),
            str(source),
            str(base / "html"),
        ],
        env={**os.environ, "SCENET_DOCS_VERSION": "dev"},
        capture_output=True,
        text=True,
        check=False,
    )
    # Warnings are expected -- they are what these tests read. An error is not.
    assert "Exception occurred" not in result.stderr, result.stderr
    return Build(warnings.read_text(encoding="utf-8").splitlines(), base / "html")


class TestRawMarkup:
    """A `doctree-resolved` check: no page shows markup that never rendered."""

    def test_autodoc_read_as_markdown_is_refused(self, build: Build):
        raw = [warning for warning in build.said("raw_markup") if "raw shows" in warning]
        assert any("'.. py:'" in warning for warning in raw), build.warnings

    def test_it_says_how_to_fix_it(self, build: Build):
        assert all("{eval-rst}" in warning for warning in build.said("raw_markup"))

    def test_autodoc_inside_eval_rst_is_not(self, build: Build):
        assert [w for w in build.said("raw_markup") if "rendered shows" in w] == []

    def test_markup_shown_as_code_is_not(self, build: Build):
        assert [w for w in build.said("raw_markup") if "quoted shows" in w] == []


class TestEveryPublicNameIsDocumented:
    """A `build-finished` check: each name in `scenet.__all__` is in `objects.inv`."""

    @staticmethod
    def _named(build: Build) -> set[str]:
        return {
            match.group(1)
            for warning in build.said("undocumented")
            if (match := re.search(r"scenet\.(\w+) is public", warning))
        }

    def test_a_public_name_the_reference_leaves_out_is_named(self, build: Build):
        """`scenet.places` reached autodoc, and autodoc's output was never read as such."""
        assert {"Place", "PLACES", "compile_source", "__version__"} <= self._named(build)

    def test_a_documented_one_is_not(self, build: Build):
        named = self._named(build)
        assert named, build.warnings
        assert {"ScenetError", "LayoutError", "UnknownPuppetError"}.isdisjoint(named)

    def test_it_reads_the_inventory_the_build_wrote(self, build: Build):
        assert (build.html / "objects.inv").is_file()


class TestOnePagePerObject:
    def test_a_field_is_documented_once(self, build: Build):
        """By its class's `Attributes:` section, and not a second time, bare, by autodoc."""
        assert [w for w in build.warnings if "duplicate object description" in w] == []


# ---------------------------------------------------------------- what autodoc is told


@pytest.fixture(scope="module")
def conf() -> dict[str, Any]:
    return runpy.run_path(str(DOCS / "conf.py"))


class TestMembers:
    """Which members an entry lists: the API, and none of the machinery around it."""

    def test_an_enum_lists_its_members(self, conf: dict[str, Any]):
        """They are the values an author writes, and have no docstring of their own."""
        keep = conf["_api_members_only"]
        assert keep(None, "class", "SHOUT", BalloonKind.SHOUT, True, {}) is False

    def test_not_what_enum_builds_them_with(self, conf: dict[str, Any]):
        new = BalloonKind.__dict__["__new__"]
        assert conf["_api_members_only"](None, "class", "__new__", new, False, {}) is True

    def test_a_validator_is_not_a_method(self, conf: dict[str, Any]):
        skip = conf["_api_members_only"]
        assert skip(None, "class", "check_positive", PanelSpec.check_positive, False, {}) is True

    def test_nor_is_a_field_validator(self, conf: dict[str, Any]):
        validator = CaptionEvent.check_speaker_is_meaningful
        skip = conf["_api_members_only"]
        assert skip(None, "class", "check_speaker_is_meaningful", validator, False, {}) is True

    @pytest.mark.parametrize(
        ("name", "member"),
        [("width", PanelSpec.width), ("is_italic", CaptionKind.is_italic), ("x", 1.0)],
    )
    def test_everything_else_is_left_to_autodoc(
        self, conf: dict[str, Any], name: str, member: object
    ):
        assert conf["_api_members_only"](None, "class", name, member, False, {}) is None


class TestAttributeDocstrings:
    """Napoleon reads an attribute's first line as `type: description`."""

    TEXT = "How a drop is sampled: points along its rounded end."

    def _napoleon(self, lines: list[str]) -> list[str]:
        # No configuration given: napoleon then takes its own defaults, as a build does.
        return GoogleDocstring(lines, what="data", name="DROP_SAMPLES").lines()

    def test_left_to_itself_it_makes_a_type_of_prose(self):
        assert ":type: How a drop is sampled" in self._napoleon([self.TEXT])

    def test_here_it_reads_a_description_only(self, conf: dict[str, Any]):
        lines = [self.TEXT]
        conf["_no_inline_types"](None, "data", "DROP_SAMPLES", 11, {}, lines)
        read = self._napoleon(lines)
        assert self.TEXT in read
        assert not [line for line in read if line.startswith(":type:")]

    def test_a_class_docstring_is_not_touched(self, conf: dict[str, Any]):
        lines = [self.TEXT]
        conf["_no_inline_types"](None, "class", "Drop", object, {}, lines)
        assert lines == [self.TEXT]


class TestBases:
    def test_a_private_base_shows_as_what_it_is_built_on(self, conf: dict[str, Any]):
        bases: list[object] = [artwork._Strict]
        conf["_public_bases"](None, "scenet.assets.artwork.ArtworkFace", None, {}, bases)
        assert bases == [BaseModel]

    def test_a_public_one_shows_as_itself(self, conf: dict[str, Any]):
        bases: list[object] = [CoreModel]
        conf["_public_bases"](None, "scenet.core.Blob", None, {}, bases)
        assert bases == [CoreModel]


# ---------------------------------------------------------------- the sources


def _pages() -> list[Path]:
    return [page for page in DOCS.rglob("*.md") if "_build" not in page.parts]


class TestSources:
    """What the reference is written in, checked without a build."""

    def test_autodoc_is_never_called_from_a_myst_fence(self):
        """The reference broke that way: MyST reads what a directive writes as Markdown."""
        fence = re.compile(r"^\s*(`{3,}|:{3,})\s*\{auto\w+\}", re.MULTILINE)
        offenders = [
            page.relative_to(ROOT).as_posix()
            for page in _pages()
            if fence.search(page.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    #: What MyST rendered in a docstring and reStructuredText shows as text.
    MARKDOWN: ClassVar[dict[str, re.Pattern[str]]] = {
        "a pipe table": re.compile(r"^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$", re.MULTILINE),
        "a heading": re.compile(r"^\s*#{2,6} \S", re.MULTILINE),
        "a link": re.compile(r"\[[^\]]+\]\((?:https?://|\.{0,2}/)"),
    }

    @pytest.mark.parametrize("markdown", sorted(MARKDOWN))
    def test_no_docstring_holds_markdown(self, markdown: str):
        """Docstrings are reStructuredText, and these only rendered while MyST read them."""
        pattern = self.MARKDOWN[markdown]
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                ):
                    continue
                docstring = ast.get_docstring(node, clean=False)
                if docstring and pattern.search(docstring):
                    where = getattr(node, "name", "the module")
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}: {where}")
        assert offenders == []
