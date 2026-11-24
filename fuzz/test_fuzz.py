"""The short fuzzing run on every pull request: Hypothesis against the shared oracle (#378).

Outside `tests/` on purpose: the ordinary suite, and every mutation leg, would otherwise pay
for it. The `Fuzz` workflow runs it on every pull request, in under five minutes, with
`uv run pytest fuzz/test_fuzz.py --no-cov`; `tests/test_fuzz_regressions.py` replays what
it ever found.

Three kinds of input for every entry point:

- the real inputs it is seeded with, bent by byte-level mutation -- a byte changed, a run
  deleted, repeated or inserted, the file cut short;
- for documents, the structure-aware ones `tests/strategies.py` draws, dumped and then bent;
- for documents, any text at all, and for every entry point any bytes at all.

A failure prints the input as a blob Hypothesis replays (`@reproduce_failure`), and
`docs/maintainer/testing.md` says how to keep it as a regression.
"""

import os

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.fuzzing import ENTRY_POINTS, check, seeds
from tests.strategies import Drawn, DrawnScene, DrawnScript, dump, panels, scenes, scripts

#: Examples per test, so the whole run stays well under five minutes on a runner; the
#: weekly run's coverage-guided engine is what goes deep.
EXAMPLES = int(os.environ.get("SCENET_FUZZ_EXAMPLES", "60"))

FUZZ = settings(
    max_examples=EXAMPLES,
    deadline=None,
    derandomize=os.environ.get("SCENET_FUZZ_RANDOM", "") == "",
    database=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@st.composite
def _bent(draw: st.DrawFn, data: bytes) -> bytes:
    """`data` with a few byte-level mutations, as a mutation fuzzer makes them."""
    bent = bytearray(data)
    for _ in range(draw(st.integers(1, 6))):
        if not bent:
            bent += draw(st.binary(min_size=1, max_size=8))
            continue
        at = draw(st.integers(0, len(bent) - 1))
        kind = draw(st.sampled_from(["set", "delete", "insert", "repeat", "cut", "token"]))
        if kind == "set":
            bent[at] = draw(st.integers(0, 255))
        elif kind == "delete":
            del bent[at : at + draw(st.integers(1, 64))]
        elif kind == "insert":
            bent[at:at] = draw(st.binary(min_size=1, max_size=16))
        elif kind == "repeat":
            run = bytes(bent[at : at + draw(st.integers(1, 256))])
            bent[at:at] = run * draw(st.integers(1, 8))
        elif kind == "cut":
            del bent[at:]
        else:
            token = draw(
                st.sampled_from(
                    [b"\x00", b"\xff", b"-1", b"1e308", b".nan", b"{", b"[", b": ", b"\n  ", b".."]
                )
            )
            bent[at:at] = token
    return bytes(bent)


def _mutated(entry: str) -> st.SearchStrategy[bytes]:
    return st.sampled_from(seeds(entry)).flatmap(_bent)


@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_every_seed_passes_the_oracle(entry: str) -> None:
    """The real inputs a mutation starts from: the oracle refuses none of them."""
    for data in seeds(entry):
        check(entry, data)


@settings(FUZZ)
@given(entry=st.sampled_from(sorted(ENTRY_POINTS)), data=st.data())
def test_a_real_input_bent(entry: str, data: st.DataObject) -> None:
    check(entry, data.draw(_mutated(entry)))


@settings(FUZZ)
@given(entry=st.sampled_from(sorted(ENTRY_POINTS)), data=st.binary(max_size=4096))
def test_any_bytes(entry: str, data: bytes) -> None:
    check(entry, data)


@settings(FUZZ)
@given(text=st.text(max_size=2048))
def test_any_text_as_a_panel_and_a_script(text: str) -> None:
    for entry in ("panel", "script"):
        check(entry, text.encode("utf-8"))


@settings(FUZZ)
@given(drawn=panels(), data=st.data())
def test_a_drawn_panel_bent(drawn: Drawn, data: st.DataObject) -> None:
    check("panel", data.draw(_bent(drawn.text.encode("utf-8"))))


@settings(FUZZ)
@given(drawn=scenes(), data=st.data())
def test_a_drawn_scene_bent(drawn: DrawnScene, data: st.DataObject) -> None:
    check("panel", data.draw(_bent(dump(drawn.document).encode("utf-8"))))


@settings(FUZZ)
@given(drawn=scripts(), data=st.data())
def test_a_drawn_script_bent(drawn: DrawnScript, data: st.DataObject) -> None:
    check("script", data.draw(_bent(drawn.text.encode("utf-8"))))
