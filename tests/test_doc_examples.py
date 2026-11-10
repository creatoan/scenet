"""Every example carries its imports, and every document compiles (#317).

A reader copies an example into a fresh file and runs it, and it must work. These tests fail
on each way it can not:

- an example with a missing import;
- a block that leans on an earlier one;
- a public name imported from a submodule;
- a document that does not compile.

The first two are checked by running every example the way `conftest.py` sets it up. The
tests here prove that set-up catches each, on examples written to fail, and then hold every
docstring and every block of the documentation to the last two.
"""

import doctest
import importlib
import importlib.util
import os
import pkgutil
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest
from sybil import Sybil
from sybil.parsers.markdown import PythonCodeBlockParser, SkipParser

import scenet
from scenet import PanelSyntaxError
from tests import doc_examples
from tests.doc_examples import (
    DocumentBlock,
    Fence,
    FreshPythonCodeBlockParser,
    compile_block,
    document_blocks,
    fences,
    import_faults,
    markdown_pages,
)

ROOT = doc_examples.ROOT


# --- The set-up catches what it is meant to ------------------------------------------------


_MODULE = '''"""A module whose docstrings use a name it defines."""


def double(n):
    """Twice `n`.

    >>> double(2)
    4
    """
    return 2 * n


def triple(n):
    """Three times `n`.

    >>> from example import triple
    >>> triple(2)
    6
    """
    return 3 * n
'''

_CONFTEST = """from tests.doc_examples import clean_doctest_globals


def pytest_collection_modifyitems(items):
    clean_doctest_globals(items)
"""


class TestDoctestsRunWithBuiltinsOnly:
    def test_an_example_that_forgets_its_import_fails(self, tmp_path: Path):
        # Its module's globals hold `double`, so plain `--doctest-modules` passes both.
        (tmp_path / "example.py").write_text(_MODULE, encoding="utf-8")
        (tmp_path / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
        run = subprocess.run(  # noqa: S603 -- our own interpreter, on a file written here
            [
                sys.executable,
                "-m",
                "pytest",
                "--doctest-modules",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                "--rootdir",
                str(tmp_path),
                str(tmp_path / "example.py"),
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT)])},
            check=False,
        )
        assert "NameError: name 'double' is not defined" in run.stdout, run.stdout
        assert "1 failed, 1 passed" in run.stdout, run.stdout


def _root_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location("root_conftest", ROOT / "conftest.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheSuiteRunsExamplesSo:
    def test_conftest_empties_every_doctest(self):
        item = object.__new__(pytest.DoctestItem)
        item.dtest = doctest.DocTest(
            [], {"compile_source": scenet.compile_source}, "x", None, 0, None
        )
        _root_conftest().pytest_collection_modifyitems([item])
        assert item.dtest.globs == {"__name__": "__main__"}

    def test_conftest_runs_each_python_block_alone(self):
        (sybils,) = [
            cell.cell_contents for cell in _root_conftest().pytest_collect_file.__closure__
        ]
        (sybil,) = sybils
        assert any(isinstance(parser, FreshPythonCodeBlockParser) for parser in sybil.parsers)
        assert not any(
            isinstance(parser, PythonCodeBlockParser)
            and not isinstance(parser, FreshPythonCodeBlockParser)
            for parser in sybil.parsers
        )


class TestEachMarkdownBlockRunsAlone:
    def _evaluate(self, tmp_path: Path, page: str) -> None:
        path = tmp_path / "page.md"
        path.write_text(textwrap.dedent(page), encoding="utf-8")
        sybil = Sybil(parsers=[FreshPythonCodeBlockParser(), SkipParser()])
        for example in sybil.parse(path):
            example.evaluate()

    def test_a_block_that_leans_on_an_earlier_one_fails(self, tmp_path: Path):
        page = """\
            ```python
            from scenet import Facing
            facing = Facing("left")
            ```

            ```python
            assert facing.value == "left"
            ```
            """
        with pytest.raises(NameError, match="facing"):
            self._evaluate(tmp_path, page)

    def test_the_lines_of_one_session_share_it(self, tmp_path: Path):
        page = """\
            ```python
            >>> from scenet import Facing
            >>> Facing("left").value
            'left'
            ```
            """
        self._evaluate(tmp_path, page)

    def test_a_block_that_carries_its_imports_passes(self, tmp_path: Path):
        page = """\
            ```python
            from scenet import Facing
            ```

            ```python
            from scenet import Facing
            assert Facing("left").value == "left"
            ```
            """
        self._evaluate(tmp_path, page)


class TestImportFaults:
    def test_a_public_name_from_its_submodule_is_a_fault(self):
        faults = import_faults(">>> from scenet.emit.pdf import render_pdf\n")
        assert faults == ["from scenet.emit.pdf import render_pdf: import it from scenet"]

    def test_a_public_name_from_scenet_is_not(self):
        assert import_faults("from scenet import render_pdf, Mass\n") == []

    def test_a_public_name_from_a_module_that_only_imports_it_is_a_fault(self):
        faults = import_faults("from scenet.cli import compile_book_file")
        assert faults == ["from scenet.cli import compile_book_file: import it from scenet"]

    def test_an_internal_name_from_a_module_that_only_imports_it_is_a_fault(self):
        faults = import_faults("from scenet.cli import Diagnostic")
        assert faults == ["from scenet.cli import Diagnostic: it is defined in scenet.diagnostics"]

    def test_an_internal_name_from_its_own_module_is_not(self):
        assert import_faults("from scenet.ir import PUPPET_KEYS") == []
        assert import_faults("from scenet.diagnostics import Diagnostic, diagnose_file") == []


# --- Every example imports public names from scenet ----------------------------------------


def _docstring_examples() -> list[tuple[str, str]]:
    """Every docstring with an example in the package: its name and its text."""
    found: list[tuple[str, str]] = []
    finder = doctest.DocTestFinder()
    for info in pkgutil.walk_packages(scenet.__path__, "scenet."):
        module = importlib.import_module(info.name)
        for test in finder.find(module):
            if test.examples:
                source = "".join(example.source for example in test.examples)
                found.append((test.name, source))
    return sorted(found)


def _python_blocks() -> list[Fence]:
    return [
        fence for page in markdown_pages() for fence in fences(page) if fence.language == "python"
    ]


DOCSTRINGS = _docstring_examples()
PYTHON_BLOCKS = _python_blocks()


def test_there_are_examples_to_check():
    assert len(DOCSTRINGS) > 100
    assert len(PYTHON_BLOCKS) > 30


@pytest.mark.parametrize(("name", "source"), DOCSTRINGS, ids=[name for name, _ in DOCSTRINGS])
def test_a_docstring_imports_public_names_from_scenet(name: str, source: str):
    assert import_faults(source) == [], name


@pytest.mark.parametrize("fence", PYTHON_BLOCKS, ids=[fence.where for fence in PYTHON_BLOCKS])
def test_a_python_block_imports_public_names_from_scenet(fence: Fence):
    assert import_faults(fence.text) == [], fence.where


# --- Every document compiles ---------------------------------------------------------------


BLOCKS = document_blocks()
COMPILED = [block for block in BLOCKS if block.kind is not None and block.copy_of is None]


def test_there_are_documents_to_compile():
    assert len(COMPILED) > 20
    assert {block.kind for block in COMPILED} >= {"panel", "scene", "script"}


@pytest.mark.parametrize("block", COMPILED, ids=[block.fence.where for block in COMPILED])
def test_a_document_compiles(block: DocumentBlock, tmp_path: Path):
    compile_block(block, tmp_path)


def test_a_copy_of_an_example_is_one_the_gallery_compiles():
    # A block that is an example file word for word -- the gallery page prints every one
    # of them -- is compiled where that file is, by `tests/test_gallery.py`, from beside
    # the pictures and puppets it names.
    copies = [block for block in BLOCKS if block.copy_of is not None]
    assert copies
    for block in copies:
        assert block.copy_of is not None
        assert block.copy_of.is_relative_to(ROOT / "examples" / "gallery"), block.fence.where


FRAGMENTS = [block for block in BLOCKS if block.part_of is not None]


@pytest.mark.parametrize("block", FRAGMENTS, ids=[block.fence.where for block in FRAGMENTS])
def test_a_fragment_is_still_yaml(block: DocumentBlock, tmp_path: Path):
    # A part of a document is not compiled, on purpose and by its caption. It is still read.
    compile_block(block, tmp_path)


def test_a_caption_names_a_document():
    fence = Fence(ROOT / "docs" / "x.md", 1, "yaml", "An example", "panel: {}\n")
    with pytest.raises(ValueError, match="names the document"):
        doc_examples.classify(fence, {})


def test_a_caption_says_what_to_compile_a_block_as():
    def kind(caption: str | None, text: str = "cast: {}\n") -> str | None:
        fence = Fence(ROOT / "docs" / "x.md", 1, "yaml", caption, text)
        return doc_examples.classify(fence, {}).kind

    assert kind(None) == "panel"
    assert kind(None, "pages:\n  - tiers: []\n") == "scene"
    assert kind("`pip.puppet.yaml`") == "puppet"
    assert kind("art/p01.art.yaml") == "artwork"
    assert kind(".github/workflows/comic.yml") is None
    assert kind("Part of hello.panel.yaml") is None


def test_a_document_that_does_not_compile_fails(tmp_path: Path):
    fence = Fence(ROOT / "README.md", 1, "scenet-script", None, "PANEL 1\n\nALICE\nHello.\n")
    block = doc_examples.classify(fence, {})
    with pytest.raises(PanelSyntaxError, match="ALICE"):
        compile_block(block, tmp_path)


#: A line that only a comic script has: a panel or a page heading, in English or French.
_SCRIPT_HEADING = re.compile(r"^(#+ |\*\*)?(PANEL|Panel|PAGE|PLANCHE|CASE) \S", re.MULTILINE)


def test_every_comic_script_says_it_is_one():
    # A comic script in an untagged block would never be compiled, and nothing would say so.
    untagged = [
        fence.where
        for page in markdown_pages()
        for fence in fences(page)
        if fence.language in ("", "text") and _SCRIPT_HEADING.search(fence.text)
    ]
    assert untagged == [], "tag each comic script ```scenet-script"


def test_the_readme_has_no_caption():
    # GitHub and PyPI render no MyST directive, so every block of the README is complete.
    assert [fence.where for fence in fences(ROOT / "README.md") if fence.caption] == []
