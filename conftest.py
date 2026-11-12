"""Make the documentation part of the test suite.

Sybil collects every fenced ``python`` block in the Markdown under `docs/` and in
`README.md` and executes it during the normal pytest run, along with the `scenet`
commands in every ``bash`` block (see `tests/shell_examples.py`). That is the mechanism behind
one of this project's rules: **a documented example that does not run is a failing
build**.

It is aimed squarely at the commonest complaint about Python library documentation --
snippets that omit their imports, or that were correct against a version three releases
ago. Neither can survive here, because the example in the docs is the example that ran, and
it ran the way a reader runs it: pasted into a fresh file (#317).

- Each Python block runs in a namespace of its own, not one the page shares, so a block
  cannot lean on the names an earlier block made.
- Each docstring example runs with builtins only, not in its module's globals, so it cannot
  call the function it documents without importing it.

`tests/doc_examples.py` has both, and `tests/test_doc_examples.py` holds the rest of the
rule: public names imported from `scenet`, and every YAML and comic-script block compiled.

A block that genuinely cannot execute (a shell transcript, a deliberately broken sample)
is marked with an HTML comment:

    <!--- skip: next -->
"""

import pytest
from sybil import Sybil
from sybil.parsers.markdown import CodeBlockParser, SkipParser

from tests.doc_examples import clean_doctest_globals
from tests.python_examples import TrackPythonCodeBlockParser
from tests.shell_examples import run_bash_block

pytest_collect_file = Sybil(
    parsers=[
        # Each block alone; the developer's track's as scripts, checked against what they
        # print (`tests/python_examples.py`).
        TrackPythonCodeBlockParser(),
        # The `scenet` lines of every `bash` block are run too: a documented command
        # that stopped working fails the build, exactly as a Python example does.
        CodeBlockParser(language="bash", evaluator=run_bash_block),
        SkipParser(),
    ],
    patterns=["*.md"],
).pytest()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run every docstring example with builtins only, as a fresh file would."""
    clean_doctest_globals(items)
