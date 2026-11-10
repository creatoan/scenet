"""Every public name explains itself as a reference entry should.

A Qt class page or a cppreference function page says what a thing does, what it takes and
returns, what it raises and when, its limits, how to use it -- imports and output shown --
and where to look next. These tests hold each name in `scenet.__all__` to that, by kind:
a function is held to all of it, a class to an example and its fields, an enumeration and
an error to an example and where to look next.

They also hold three things napoleon and autodoc get wrong if a docstring lets them: a
field no `Attributes:` entry describes is left off its page, a `Returns:` whose first line
holds a colon renders its first words as a type, and an issue number means nothing to a
reader.
"""

import ast
import dataclasses
import doctest
import enum
import importlib
import inspect
import itertools
import pkgutil
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel
from sphinx.ext.napoleon import Config
from sphinx.ext.napoleon.docstring import GoogleDocstring
from sphinx.pycode import ModuleAnalyzer

import scenet

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "scenet"

PUBLIC = [name for name in scenet.__all__ if name != "__version__"]
#: A heading napoleon reads, alone on its line at the docstring's own indent.
SECTION = re.compile(r"^([A-Z][A-Za-z ]*):\s*$", re.MULTILINE)


def _doc(name: str) -> str:
    obj = getattr(scenet, name)
    if inspect.isclass(obj) or callable(obj):
        return inspect.getdoc(obj) or ""
    # A value's doc is the `#:` comment above it, which is what autodoc reads: in the
    # module that defines it, the one that comments it.
    for module in sorted(sys.modules):
        if module.startswith("scenet.") and getattr(sys.modules[module], name, None) is obj:
            analyzer = ModuleAnalyzer.for_module(module)
            analyzer.analyze()
            if ("", name) in analyzer.attr_docs:
                return "\n".join(analyzer.attr_docs[("", name)]).strip()
    return ""


def _sections(doc: str) -> set[str]:
    return set(SECTION.findall(doc))


def _section(doc: str, heading: str) -> str:
    """The body of one section: its indented lines, up to the next heading."""
    match = re.search(rf"^{heading}:\s*\n((?:[ \t]+.*\n?|\s*\n)*)", doc, re.MULTILINE)
    return match.group(1) if match else ""


def _kind(name: str) -> str:
    obj = getattr(scenet, name)
    if inspect.isclass(obj):
        if issubclass(obj, enum.Enum):
            return "enum"
        if issubclass(obj, BaseException):
            return "error"
        return "class"
    return "function" if callable(obj) else "data"


FUNCTIONS = [name for name in PUBLIC if _kind(name) == "function"]
CLASSES = [name for name in PUBLIC if _kind(name) == "class"]


class TestEveryPublicName:
    @pytest.mark.parametrize("name", PUBLIC)
    def test_has_a_one_line_summary(self, name: str):
        first = _doc(name).splitlines()[0]
        assert first.endswith("."), first
        assert len(first) <= 96, first

    @pytest.mark.parametrize("name", PUBLIC)
    def test_has_an_example_that_imports_it_from_scenet(self, name: str):
        doc = _doc(name)
        imports = re.findall(r">>> from scenet import ([^\n]+)", doc)
        assert any(re.search(rf"\b{re.escape(name)}\b", line) for line in imports), (
            f"{name}: its example imports it with `>>> from scenet import {name}`"
        )

    @pytest.mark.parametrize("name", PUBLIC)
    def test_its_example_shows_output(self, name: str):
        lines = _doc(name).splitlines()
        shown = [
            line
            for previous, line in itertools.pairwise(lines)
            if previous.lstrip().startswith((">>>", "..."))
            and line.strip()
            and not line.lstrip().startswith((">>>", "..."))
        ]
        assert shown, f"{name}: an example shows what it prints"

    @pytest.mark.parametrize("name", PUBLIC)
    def test_says_where_to_look_next(self, name: str):
        assert "See Also" in _sections(_doc(name)), name


class TestEveryPublicFunction:
    @pytest.mark.parametrize("name", FUNCTIONS)
    def test_describes_each_parameter(self, name: str):
        parameters = list(inspect.signature(getattr(scenet, name)).parameters)
        described = re.findall(r"^    (\w+)(?: \(.*\))?:", _section(_doc(name), "Args"), re.M)
        assert described == parameters

    @pytest.mark.parametrize("name", FUNCTIONS)
    def test_says_what_it_returns(self, name: str):
        assert _section(_doc(name), "Returns").strip(), name

    @pytest.mark.parametrize("name", FUNCTIONS)
    def test_says_what_it_raises_with_public_errors(self, name: str):
        doc = _doc(name)
        raised = re.findall(r"^    ~?([\w.]+):", _section(doc, "Raises"), re.M)
        if not raised:
            assert "raises nothing" in " ".join(doc.split()), (
                f"{name}: a Raises section, each error and when -- or a Note saying it "
                "raises nothing"
            )
        for error in raised:
            short = error.rpartition(".")[2]
            assert short in scenet.__all__, f"{name} raises {error}, which is not public"
            assert issubclass(getattr(scenet, short), scenet.ScenetError), error

    @pytest.mark.parametrize("name", FUNCTIONS)
    def test_states_its_limits(self, name: str):
        assert _sections(_doc(name)) & {"Note", "Notes"}, f"{name}: a Note on its limits"


# ---------------------------------------------------------------- fields


def _documented_types() -> Iterator[type]:
    """Every model and dataclass `scenet` or a module exports, which a page documents."""
    for name in PUBLIC:
        obj = getattr(scenet, name)
        if inspect.isclass(obj) and (issubclass(obj, BaseModel) or dataclasses.is_dataclass(obj)):
            yield obj
    for info in pkgutil.walk_packages(scenet.__path__, "scenet."):
        module = importlib.import_module(info.name)
        for name in getattr(module, "__all__", ()):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj)
                and obj.__module__ == module.__name__
                and (issubclass(obj, BaseModel) or dataclasses.is_dataclass(obj))
            ):
                yield obj


def _own_fields(cls: type) -> list[str]:
    """The fields a class declares itself, not those it inherits."""
    own = inspect.get_annotations(cls)
    if issubclass(cls, BaseModel):
        return [name for name in cls.model_fields if name in own]
    if dataclasses.is_dataclass(cls):
        return [field.name for field in dataclasses.fields(cls) if field.name in own]
    return [name for name in own if not name.startswith("_")]


def _attribute_docs(cls: type) -> set[str]:
    analyzer = ModuleAnalyzer.for_module(cls.__module__)
    analyzer.analyze()
    return {attr for (owner, attr) in analyzer.attr_docs if owner == cls.__qualname__}


@pytest.mark.parametrize("cls", list(_documented_types()), ids=lambda cls: cls.__name__)
def test_every_field_is_described(cls: type):
    """Autodoc lists a field only when something describes it: left out, it is not on the
    page at all."""
    doc = inspect.getdoc(cls) or ""
    described = set(re.findall(r"^    (\w+)(?: \(.*\))?:", _section(doc, "Attributes"), re.M))
    described |= _attribute_docs(cls)
    # `docs/conf.py` describes a field by its `Field(description=...)` too.
    fields = getattr(cls, "model_fields", {})
    described |= {name for name, info in fields.items() if info.description}
    missing = [field for field in _own_fields(cls) if field not in described]
    assert missing == [], f"describe each under Attributes: in {cls.__name__}'s docstring"


# ---------------------------------------------------------------- what napoleon reads


def _docstrings() -> Iterator[tuple[str, str]]:
    """Every docstring in the package: of a module, a class, a function, an attribute."""
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                docstring = ast.get_docstring(node)
                if docstring:
                    where = getattr(node, "name", "the module")
                    yield f"{path.relative_to(ROOT).as_posix()}: {where}", docstring
                body = node.body
                for before, statement in itertools.pairwise(body):
                    if (
                        isinstance(before, ast.Assign | ast.AnnAssign)
                        and isinstance(statement, ast.Expr)
                        and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)
                    ):
                        line = f"{path.relative_to(ROOT).as_posix()}:{statement.lineno}"
                        yield line, statement.value.value


def test_no_returns_section_reads_as_a_type():
    """Napoleon reads `Returns: A thing: more` as a type, "A thing", in italics."""
    config = Config(napoleon_use_rtype=False)
    offenders = [
        where
        for where, docstring in _docstrings()
        if "Returns:" in docstring
        and any(
            line.startswith(":returns: *")
            for line in GoogleDocstring(docstring, config, what="function").lines()
        )
    ]
    assert offenders == []


#: An issue number: `#71`, `(#242)`. Markup such as `#:` and `#ffffff` is not one.
ISSUE = re.compile(r"(?<![\w&])#\d{2,4}\b")


def test_no_docstring_cites_an_issue_number():
    """A reader cannot act on one: a docstring says what the thing does instead."""
    offenders = [where for where, docstring in _docstrings() if ISSUE.search(docstring)]
    for path in sorted(SRC.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#:") and ISSUE.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert offenders == []


@pytest.mark.parametrize("name", [name for name in PUBLIC if _kind(name) == "data"])
def test_a_value_s_example_runs(name: str):
    """Doctest collects no `#:` comment, so a value's example is run here."""
    parser = doctest.DocTestParser()
    test = parser.get_doctest(_doc(name), {}, name, None, 0)
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    assert test.examples
    assert runner.run(test).failed == 0
