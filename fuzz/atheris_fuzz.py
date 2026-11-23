"""The weekly coverage-guided run: Atheris against the shared oracle (#378).

Atheris is libFuzzer for Python: it mutates its inputs towards the branches no input has
reached yet, which a property test does not. The first byte of an input picks the entry
point, and the rest is the input itself, so one corpus holds them all and a mutation can
carry a document from one entry point to another.

Run it on Linux, from the repository's root, after `uv sync --group fuzz`:

.. code-block:: bash

    uv run python fuzz/atheris_fuzz.py fuzz/corpus -max_total_time=600 -rss_limit_mb=2048

`fuzz/corpus` grows with every input that reaches a new branch; the `Fuzz` workflow keeps it
between weekly runs as a cache. A failure is written as `crash-<sha1>` in the working
directory; `docs/maintainer/testing.md` says how to turn it into a regression.
"""

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with atheris.instrument_imports(include=["scenet"]):
    from tests.fuzzing import ENTRY_POINTS, check, seeds

#: Entry points in a fixed order, so the byte that picks one means the same in every run.
ENTRIES = sorted(ENTRY_POINTS)


def one_input(data: bytes) -> None:
    """Feed one input to the entry point its first byte picks."""
    if not data:
        return
    check(ENTRIES[data[0] % len(ENTRIES)], data[1:])


def seed(corpus: Path) -> None:
    """Start an empty corpus from every entry point's real inputs, each behind its byte."""
    if corpus.exists() and any(corpus.iterdir()):
        return
    corpus.mkdir(parents=True, exist_ok=True)
    for index, entry in enumerate(ENTRIES):
        for number, data in enumerate(seeds(entry)):
            (corpus / f"{entry}-{number}").write_bytes(bytes([index]) + data)


def main() -> None:
    """Seed the corpus a run is pointed at, then fuzz until libFuzzer's flags say stop."""
    folders = [Path(argument) for argument in sys.argv[1:] if not argument.startswith("-")]
    for corpus in folders[:1]:
        seed(corpus)
    atheris.Setup(sys.argv, one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
