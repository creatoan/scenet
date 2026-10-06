"""Make the documentation part of the test suite.

Sybil collects every fenced ``python`` block in the Markdown under `docs/` and in
`README.md` and executes it during the normal pytest run, along with the `scenet`
commands in every ``bash`` block (see `tests/shell_examples.py`). That is the mechanism behind
one of this project's rules: **a documented example that does not run is a failing
build**.

It is aimed squarely at the commonest complaint about Python library documentation --
snippets that omit their imports, or that were correct against a version three releases
ago. Neither can survive here, because the example in the docs is the example that ran.

A block that genuinely cannot execute (a shell transcript, a deliberately broken sample)
is marked with an HTML comment:

    <!--- skip: next -->
"""

from sybil import Sybil
from sybil.parsers.markdown import CodeBlockParser, PythonCodeBlockParser, SkipParser

from tests.shell_examples import run_bash_block

pytest_collect_file = Sybil(
    parsers=[
        PythonCodeBlockParser(),
        # The `scenet` lines of every `bash` block are run too: a documented command
        # that stopped working fails the build, exactly as a Python example does.
        CodeBlockParser(language="bash", evaluator=run_bash_block),
        SkipParser(),
    ],
    patterns=["*.md"],
).pytest()
