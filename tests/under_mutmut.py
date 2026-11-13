"""The tests that cannot pass in mutmut's mutants tree, marked so they are skipped there.

mutmut runs the suite in `mutants/`, a copy of the repository in which every file it
mutates is rewritten: each function is kept, renamed, beside its mutants, and a trampoline
picks one. A test that reads a mutated file's text -- to compare it with what a generator
writes, or to scan it for a pattern -- reads that rewrite, not the source, and fails
there and nowhere else. It holds the text, not the behaviour, so no mutant can be killed
by it, and skipping it under mutmut loses nothing.

`ci.yml`'s *Mutation clean run* runs the suite in that tree on every pull request, so a
new test of this kind fails before merge, not in the next weekly run (#345).
"""

import os

import pytest

#: mutmut sets it in every process it runs the suite in: the coverage and stats runs, the
#: clean run, and each mutant's.
UNDER_MUTMUT = "MUTANT_UNDER_TEST" in os.environ

reads_the_source = pytest.mark.skipif(
    UNDER_MUTMUT,
    reason="mutmut rewrites every file it mutates, so the text read is not the source",
)


def keep_the_stats_in_this_process() -> None:
    """Let no child process of the suite inherit mutmut's stats run.

    The stats run, which finds the tests that reach each function, sets
    `MUTANT_UNDER_TEST=stats`, and every process the suite starts inherits it. A child
    that imports a mutated module then records each call it makes, which nobody reads,
    and to do it loads mutmut's configuration from its working directory. Sphinx runs
    `conf.py` from the documentation's source directory, which holds none, and once
    `ir.py` was mutated -- it calls a mutated function as it is imported -- every build in
    the suite failed there (#345).

    mutmut keeps its own copy of the variable in this process and reads it when the
    variable is gone, so dropping it changes nothing here, and a child runs the
    unmutated code. Only the stats run is affected: a mutant's run, and the clean run,
    keep the variable, so a child runs the mutant too.
    """
    if os.environ.get("MUTANT_UNDER_TEST") == "stats":
        del os.environ["MUTANT_UNDER_TEST"]
