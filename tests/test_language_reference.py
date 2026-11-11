"""The language reference says what the compiler does (#319).

The reference is `docs/reference/language.md`. These tests hold it to the facts an audit
found it getting wrong: a key called required that has a default, a value left out of a
table, a key that does not exist, a count of layers that leaves some out. And a reader
cannot act on an issue number, so the reference says what a thing does instead.
"""

import re
from pathlib import Path

import pytest

from scenet.ir import CaptionTone, PanelIR

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference"


def _pages() -> list[Path]:
    """Every page of the language reference: one page, or a folder of them."""
    folder = REFERENCE / "language"
    return sorted(folder.glob("*.md")) if folder.is_dir() else [REFERENCE / "language.md"]


def _text() -> str:
    return "\n".join(page.read_text(encoding="utf-8") for page in _pages())


@pytest.mark.parametrize("page", _pages(), ids=lambda page: page.name)
def test_it_cites_no_issue_number(page: Path):
    text = page.read_text(encoding="utf-8")
    assert re.findall(r"\(#\d+\)|\bissue #?\d+", text) == []


def test_a_panels_size_is_not_required():
    """`panel.size` defaults to a square of 1000 units."""
    assert PanelIR().panel.size == (1000.0, 1000.0)
    flat = " ".join(_text().split())
    assert "| `size` | `[width, height]` | required |" not in flat
    assert "`[1000, 1000]`" in flat


def test_every_caption_tone_is_in_the_key_table():
    tones = [tone.value for tone in CaptionTone]
    rows = [line for line in _text().splitlines() if line.startswith("| `tone` |")]
    assert rows, "the caption key table has a row for tone"
    assert all(f"`{tone}`" in row for row in rows for tone in tones)


def test_footroom_is_the_shots_and_not_a_key():
    """No key raises footroom: each shot type sets its own, in the table."""
    shot_types = (REFERENCE / "shot_types.md").read_text(encoding="utf-8")
    flat = " ".join(shot_types.split())
    assert "may raise it" not in flat
    assert "no key" in flat.lower()


def test_it_counts_no_layers_it_leaves_out():
    """A panel's blocks are listed, not counted: the old count of five left out four."""
    flat = " ".join(_text().split())
    assert re.search(r"\b(?:five|six|seven) (?:authored )?layers\b", flat) is None
    for block in ("lettering", "direction", "palette", "description"):
        assert f"`{block}`" in flat


def test_it_says_how_a_tie_between_two_figures_is_broken():
    """Ordering with no `left_of` falls to `at`, then to the actor id (`horizontal_order`)."""
    flat = " ".join(_text().split())
    assert "actor id" in flat
    assert "alphabetical" in flat.lower() or "by id" in flat
