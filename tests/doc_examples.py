"""What an example in the documentation has to be: something a reader can paste and run (#317).

A reader copies an example into a fresh file and runs it. So:

- **a docstring example runs in a clean namespace**, builtins only, rather than in its
  module's globals, where it could call the function it documents without importing it
  (:func:`clean_doctest_globals`);
- **each Python block of a Markdown page runs in a namespace of its own**, rather than in
  one the whole page shares, where a block could lean on the names an earlier one made
  (:class:`FreshPythonCodeBlockParser`);
- **an example imports a public name from** `scenet`, the import the API promises, and
  anything else from the module that defines it (:func:`import_faults`);
- **every YAML and comic-script block is a document that compiles**, unless its caption
  names the document it is a part of (:func:`document_blocks`) -- or, written as a
  ```` ```{scenet-example} ```` with `:gives:`, it gives exactly the diagnostic it names.

`conftest.py` puts the first two to work on the whole suite; `tests/test_doc_examples.py`
holds all four to that.
"""

import ast
import doctest
import importlib.util
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from markdown_it import MarkdownIt
from sybil import Document, Example, Region
from sybil.parsers.markdown import PythonCodeBlockParser

import scenet
from scenet import compile_book, compile_script, compile_source, load_puppet
from scenet.assets.artwork import ArtworkContract
from scenet.safe_yaml import load

__all__ = [
    "DOCUMENT_LANGUAGES",
    "SCENET_SUFFIXES",
    "DocumentBlock",
    "FreshPythonCodeBlockParser",
    "clean_doctest_globals",
    "document_blocks",
    "fences",
    "file_named",
    "import_faults",
    "markdown_pages",
    "told",
]

ROOT = Path(__file__).resolve().parents[1]

#: The fence languages that show a document: YAML, and a comic script, by the language id
#: the editor extension gives `.script` files.
DOCUMENT_LANGUAGES = ("yaml", "scenet-script")

#: Each kind of document Scenet reads, by the suffix of its file name.
SCENET_SUFFIXES = {
    ".panel.yaml": "panel",
    ".scene.yaml": "scene",
    ".script": "script",
    ".puppet.yaml": "puppet",
    ".art.yaml": "artwork",
}

#: A caption that says a block is a part of a document, and names it.
_PART_OF = re.compile(r"^Part of (?P<name>\S.*)$")
#: A caption that is a file name and nothing else, in backticks or not.
_FILE_NAME = re.compile(r"^`?(?P<name>[\w./-]+\.\w+)`?$")
#: A directive's option line, `:caption: ...`, at the top of its body.
_OPTION = re.compile(r"^:(?P<key>[\w-]+):\s*(?P<value>.*)$")


def markdown_pages() -> list[Path]:
    """Every page of the documentation, and the README, in a stable order."""
    pages = sorted((ROOT / "docs").rglob("*.md"))
    return [ROOT / "README.md", *(page for page in pages if "_build" not in page.parts)]


# --- Doctests ------------------------------------------------------------------------------


def clean_doctest_globals(items: Iterable[pytest.Item]) -> None:
    """Run every collected doctest in a namespace holding builtins only.

    `--doctest-modules` runs a docstring's examples in a copy of its module's globals, so an
    example that forgets to import the very function it documents still passes. Here each
    starts with nothing but `__name__`, as a script a reader pasted it into would; pytest's
    own `getfixture` is added back when the test is set up.
    """
    for item in items:
        if isinstance(item, pytest.DoctestItem):
            item.dtest.globs = {"__name__": "__main__"}


# --- Markdown's Python blocks --------------------------------------------------------------


def _fresh(region: Region) -> Region:
    """The region, evaluated in an emptied namespace."""
    evaluator = region.evaluator
    if evaluator is None:
        return region

    def evaluate(example: Example) -> str | None:
        example.namespace.clear()
        return evaluator(example)

    region.evaluator = evaluate
    return region


class FreshPythonCodeBlockParser(PythonCodeBlockParser):
    """Sybil's Python block parser, each block starting from an empty namespace.

    Sybil evaluates every example of a page in one namespace, so a block can use a name an
    earlier block defined, and passes only because it ran after it. Here the first example of
    each block empties the namespace. A block of `>>>` lines is several examples, which share
    it among themselves, as the lines of one session do.
    """

    def __call__(self, document: Document) -> Iterator[Region]:
        for region in self.codeblock_parser(document):
            source = region.parsed
            if source.startswith(">>>"):
                for index, doctest_region in enumerate(self.doctest_parser(source, document.path)):
                    doctest_region.adjust(region, source)
                    yield _fresh(doctest_region) if index == 0 else doctest_region
            else:
                yield _fresh(region)


# --- Import paths --------------------------------------------------------------------------


def _source_of(text: str) -> str:
    """The Python an example runs: its `>>>` and `...` lines, or the block as it is."""
    if not re.search(r"^\s*>>>", text, re.MULTILINE):
        return text
    examples = doctest.DocTestParser().get_examples(text)
    return "".join(example.source for example in examples)


def import_faults(text: str) -> list[str]:
    """What an example imports from somewhere other than where the API promises it.

    - A name in `scenet.__all__` is imported from `scenet`: `from scenet.emit.pdf import
      render_pdf` teaches an import path the API does not promise.
    - Any other class or function is imported from the module that defines it, not from one
      that happens to import it too.

    Args:
        text: An example: a docstring's `>>>` lines, or a Markdown block's Python.

    Returns:
        One line for each import at fault, empty when there is none.
    """
    try:
        tree = ast.parse(_source_of(text))
    except SyntaxError:  # A deliberately broken sample: the example runner says so.
        return []
    faults: list[str] = []
    public = set(scenet.__all__)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or node.module is None:
            continue
        module_name = node.module
        if module_name == "scenet" or not module_name.startswith("scenet."):
            continue
        module = __import__(module_name, fromlist=["_"])
        for alias in node.names:
            value = getattr(module, alias.name, None)
            if alias.name in public and value is getattr(scenet, alias.name):
                faults.append(f"from {module_name} import {alias.name}: import it from scenet")
                continue
            home = getattr(value, "__module__", None)
            if (isinstance(value, type) or callable(value)) and home not in (None, module_name):
                faults.append(f"from {module_name} import {alias.name}: it is defined in {home}")
    return faults


# --- Documents -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Fence:
    """A fenced block of a Markdown page: its language, caption and text."""

    path: Path
    #: The line its fence opens on, counted from 1.
    line: int
    language: str
    #: The directive's `:caption:`, when the block is written as a `{code-block}`.
    caption: str | None
    text: str
    #: The directive the block is written as, `code-block` or `scenet-example`, if any.
    directive: str | None = None
    #: Its options, `:beside: examples/gallery`, by name.
    options: tuple[tuple[str, str], ...] = ()

    @property
    def where(self) -> str:
        """`page:line`, for a test id and a failure message."""
        return f"{self.path.relative_to(ROOT).as_posix()}:{self.line}"


def fences(path: Path) -> list[Fence]:
    """Every fenced block of a page, as MyST reads it.

    A ```` ```{code-block} yaml ```` directive is a block in `yaml`; its option lines are
    read off the top of it, and its `:caption:` kept. A ```` ```{scenet-example} ```` is a
    document the build compiles and pictures: in `yaml`, or a comic script with
    `:kind: script`.
    """
    tokens = MarkdownIt("commonmark").parse(path.read_text(encoding="utf-8"))
    found: list[Fence] = []
    for token in tokens:
        if token.type != "fence" or token.map is None:
            continue
        info = token.info.split()
        language = info[0] if info else ""
        text = token.content
        caption: str | None = None
        directive: str | None = None
        options: list[tuple[str, str]] = []
        if language in ("{code-block}", "{scenet-example}"):
            directive = language.strip("{}")
            lines = text.splitlines(keepends=True)
            while lines and (option := _OPTION.match(lines[0].strip())):
                options.append((option["key"], option["value"].strip()))
                if option["key"] == "caption":
                    caption = option["value"].strip()
                lines.pop(0)
            if lines and not lines[0].strip():
                lines.pop(0)
            text = "".join(lines)
            if directive == "code-block":
                language = info[1] if len(info) > 1 else ""
            else:
                kind = dict(options).get("kind")
                language = "scenet-script" if kind == "script" else "yaml"
        found.append(
            Fence(path, token.map[0] + 1, language, caption, text, directive, tuple(options))
        )
    return found


@dataclass(frozen=True)
class DocumentBlock:
    """A block of the documentation that shows a document, and what it is said to be.

    Attributes:
        fence: The block.
        kind: The kind of document to compile it as: `panel`, `scene`, `script`, `puppet` or
            `artwork`. `None` when it is not compiled: a part of a document, or a file Scenet
            does not read, such as a CI workflow.
        part_of: The document a fragment is a part of, as its caption names it.
        copy_of: The example file it is a copy of, when it is one, word for word.
    """

    fence: Fence
    kind: str | None
    part_of: str | None = None
    copy_of: Path | None = None


def file_named(fence: Fence) -> str | None:
    """The file a block shows, when its caption is a file name: `hello.panel.yaml`."""
    if fence.caption is None:
        return None
    named = _FILE_NAME.match(fence.caption)
    return named["name"] if named else None


def _example_files() -> dict[str, Path]:
    """Every document under `examples/`, by its text."""
    files: dict[str, Path] = {}
    for path in sorted((ROOT / "examples").rglob("*")):
        if path.is_file() and any(path.name.endswith(suffix) for suffix in SCENET_SUFFIXES):
            files.setdefault(path.read_text(encoding="utf-8"), path)
    return files


def _kind_of_name(name: str) -> str | None:
    return next((kind for suffix, kind in SCENET_SUFFIXES.items() if name.endswith(suffix)), None)


def _inferred_kind(fence: Fence) -> str:
    """A panel, unless it is a script or holds panels or pages: a scene.

    A `scenet-example` may say which with `:kind:`, as its directive reads it.
    """
    kind = dict(fence.options).get("kind")
    if kind:
        return kind
    if fence.language == "scenet-script":
        return "script"
    if re.search(r"^(panels|pages):", fence.text, re.MULTILINE):
        return "scene"
    return "panel"


def classify(fence: Fence, examples: dict[str, Path]) -> DocumentBlock:
    """What a document block is said to be: by its caption, or else by what it holds.

    Raises:
        ValueError: The caption is neither `Part of <document>` nor a file name.
    """
    if fence.caption is not None:
        if part := _PART_OF.match(fence.caption):
            return DocumentBlock(fence, None, part_of=part["name"].strip("`"))
        if named := _FILE_NAME.match(fence.caption):
            # Saved under a name of the reader's own -- the tour's `hello.panel.yaml` -- a
            # gallery example is still that example, compiled beside the files it names.
            kind = _kind_of_name(named["name"])
            return DocumentBlock(fence, kind, copy_of=examples.get(fence.text))
        message = (
            f"{fence.where}: a caption on a {fence.language} block names the document it "
            f"shows (`story.scene.yaml`) or the one it is a part of (`Part of "
            f"story.scene.yaml`), not {fence.caption!r}"
        )
        raise ValueError(message)
    copy = examples.get(fence.text)
    return DocumentBlock(fence, _inferred_kind(fence), copy_of=copy)


def document_blocks() -> list[DocumentBlock]:
    """Every YAML and comic-script block of the documentation and the README."""
    examples = _example_files()
    return [
        classify(fence, examples)
        for page in markdown_pages()
        for fence in fences(page)
        if fence.language in DOCUMENT_LANGUAGES
    ]


def _examples_extension() -> ModuleType:
    """The documentation's `scenet-example` directive, which is not a package's module."""
    name = "scenet_examples"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "docs" / "_ext" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def told(text: str, kind: str, base: Path | None) -> list[str]:
    """Every diagnostic a document gives, by id, as the `scenet-example` directive reads it."""
    given: list[str] = _examples_extension().told(text, kind, base)
    return given


def compile_block(block: DocumentBlock, tmp_path: Path) -> Any:
    """Compile a block as the kind of document it is said to be, and return the result.

    A `scenet-example` compiled `:beside:` a folder of the repository finds the files it
    names there, as the documentation's build does. One with `:gives:` is there to show a
    diagnostic: it must give exactly that one, and the ids it gives are returned.

    Raises:
        AssertionError: A `:gives:` block gives something else, or more.
    """
    text = block.fence.text
    options = dict(block.fence.options)
    beside = options.get("beside")
    base = ROOT / beside if beside else None
    gives = options.get("gives")
    if gives is not None and block.kind in ("panel", "scene", "script"):
        given = told(text, block.kind, base)
        assert given == [gives], f"{block.fence.where} gives {given}, not [{gives!r}]"
        return given
    return _compiled(block, base, tmp_path)


def _compiled(block: DocumentBlock, base: Path | None, tmp_path: Path) -> Any:
    """A block compiled, or read, as the kind of document it is."""
    text = block.fence.text
    match block.kind:
        case "panel":
            return compile_source(text, base=base)
        case "scene":
            return compile_book(text, base=base)
        case "script":
            return compile_script(text, base=base)
        case "puppet":
            path = tmp_path / "shown.puppet.yaml"
            path.write_text(text, encoding="utf-8")
            return load_puppet(path)
        case "artwork":
            return ArtworkContract.model_validate(load(text))
        case _:
            return load(text) if block.fence.language == "yaml" else None
