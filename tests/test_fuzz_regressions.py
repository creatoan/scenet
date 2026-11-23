"""Every input the fuzzers ever found, replayed against the oracle on every run (#378).

`tests/fuzz_regressions/<entry point>/` holds one file per input, named for what it once did.
Each passes the oracle of `tests/fuzzing.py` -- findings or a `ScenetError`, in time and
memory -- and a file put there before its fix fails here until the fix lands.
"""

from pathlib import Path

import pytest

from tests.fuzzing import ENTRY_POINTS, REGRESSIONS, check, regressions, seeds

KEPT = regressions()


def test_every_folder_is_an_entry_point():
    folders = {folder.name for folder in REGRESSIONS.iterdir() if folder.is_dir()}
    assert folders <= set(ENTRY_POINTS)


def test_some_were_kept():
    """The fonts that once failed half way through a compile, at the least."""
    assert {entry for entry, _ in KEPT} >= {"font"}


@pytest.mark.parametrize(
    ("entry", "path"), KEPT, ids=[f"{entry}/{path.name}" for entry, path in KEPT]
)
def test_it_passes_the_oracle(entry: str, path: Path):
    check(entry, path.read_bytes())


@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_every_seed_passes_the_oracle(entry: str):
    """The real inputs a fuzzer starts from: the oracle refuses none of them."""
    for data in seeds(entry):
        check(entry, data)
