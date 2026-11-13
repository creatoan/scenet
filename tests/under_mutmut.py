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
