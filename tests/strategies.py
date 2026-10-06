"""Hypothesis strategies that write Scenet documents.

Pydantic v2 dropped its Hypothesis plugin, and `st.builds(PanelIR)` would be no use
anyway: the model validators -- every id resolves, no ordering cycle, the margin leaves
room -- reject nearly everything it drew. So these are hand-written builders that produce
the document an author would write, as a dict, valid by construction. Black's fuzzer
works the same way: it generates valid input rather than deriving it from a model.

**The vocabulary comes from the code, never a copy of it**: the enums, the poses and
expressions of the shipped puppets, the named places, and the characters the shipped
fonts can draw. A new shot type or a new expression is drawn the day it lands.

Each strategy returns a :class:`Drawn`, which keeps the authored document beside its
YAML text, so a test can derive what it expects -- the margin, say -- from what was
written rather than from what the compiler made of it.
"""

import string
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from typing import Any

import yaml
from fontTools.ttLib import TTFont
from hypothesis import strategies as st

from scenet import (
    AnchorX,
    BalloonKind,
    CameraAngle,
    CaptionKind,
    CaptionTone,
    Facing,
    Mark,
    PlacementZone,
    ShotType,
    TimeOfDay,
    Weather,
)
from scenet.assets.contract import PuppetLibrary, default_library
from scenet.places import Place
from scenet.solve.text import DEFAULT_FONT_PATH, ITALIC_FONT_PATH

__all__ = ["LIBRARY", "Drawn", "panels", "words"]

#: The shipped puppets, loaded once. `default_library()` reads the files on every call.
LIBRARY: PuppetLibrary = default_library()

# Actor ids that YAML would read as something other than a string. `safe_dump` quotes
# them, but a staging sentence is split on whitespace and never re-read as YAML, so they
# are kept out rather than relied on.
_RESERVED = frozenset({"y", "n", "yes", "no", "on", "off", "true", "false", "null"})


#: How many lines of script a panel may hold at each of the tightest shots.
_LINES_AT: dict[ShotType, int] = {
    ShotType.CLOSE_UP: 1,
    ShotType.BIG_CLOSE_UP: 0,
    ShotType.EXTREME_CLOSE_UP: 0,
}


@dataclass(frozen=True, slots=True)
class Drawn:
    """One generated document, as written.

    Attributes:
        document: The mapping an author would have written.
        text: The same document as YAML, which is what goes to the compiler, so the
            frontend is exercised along with everything after it.
    """

    document: dict[str, Any]

    @property
    def text(self) -> str:
        return yaml.safe_dump(self.document, sort_keys=False, allow_unicode=True)

    @property
    def margin(self) -> float:
        return float(self.document["panel"].get("margin", 0.0))

    @property
    def size(self) -> tuple[float, float]:
        width, height = self.document["panel"]["size"]
        return float(width), float(height)


@cache
def _letterable() -> str:
    """Characters both shipped faces can draw, so every caption kind can letter them.

    Printable ASCII and Latin-1 letters only: enough to exercise kerning, accents and
    punctuation without drawing from the whole cmap, whose rarer corners are not what
    these properties are about.
    """
    roman = TTFont(DEFAULT_FONT_PATH).getBestCmap() or {}
    italic = TTFont(ITALIC_FONT_PATH).getBestCmap() or {}
    wanted = string.ascii_letters + string.digits + ".,!?'-:;" + "éèàçüöñÉ"
    return "".join(sorted(char for char in wanted if ord(char) in roman and ord(char) in italic))


def words(min_words: int = 1, max_words: int = 12) -> st.SearchStrategy[str]:
    """A line of 1 to 12 words, written as an author would: single spaces, no newlines."""
    word = st.text(alphabet=_letterable(), min_size=1, max_size=10)
    return st.lists(word, min_size=min_words, max_size=max_words).map(" ".join)


def _actor_ids() -> st.SearchStrategy[str]:
    return st.from_regex(r"[a-z][a-z0-9_]{0,7}", fullmatch=True).filter(
        lambda name: name not in _RESERVED
    )


@st.composite
def _cast_member(draw: st.DrawFn) -> dict[str, Any]:
    reference = draw(st.sampled_from(LIBRARY.names()))
    puppet = LIBRARY.get(reference)
    member: dict[str, Any] = {"reference": reference}
    if draw(st.booleans()):
        member["pose"] = draw(st.sampled_from(sorted(puppet.poses)))
    if draw(st.booleans()):
        member["expression"] = draw(st.sampled_from(sorted(puppet.expressions)))
    if draw(st.booleans()):
        marks = draw(st.lists(st.sampled_from(list(Mark)), max_size=2, unique=True))
        member["marks"] = [mark.value for mark in marks]
    if draw(st.booleans()):
        member["at"] = draw(st.sampled_from(list(AnchorX))).value
    if draw(st.booleans()):
        member["facing"] = draw(st.sampled_from(list(Facing))).value
    return member


@st.composite
def _event(draw: st.DrawFn, cast: list[str]) -> dict[str, Any]:
    if cast and draw(st.booleans()):
        say: dict[str, Any] = {"by": draw(st.sampled_from(cast)), "text": draw(words(max_words=8))}
        if draw(st.booleans()):
            say["kind"] = draw(st.sampled_from(list(BalloonKind))).value
        if draw(st.booleans()):
            say["prefer"] = draw(st.sampled_from(list(PlacementZone))).value
        return {"say": say}
    kind = draw(st.sampled_from(list(CaptionKind)))
    caption: dict[str, Any] = {"text": draw(words(max_words=8)), "kind": kind.value}
    if draw(st.booleans()):
        caption["tone"] = draw(st.sampled_from(list(CaptionTone))).value
    if draw(st.booleans()):
        caption["prefer"] = draw(st.sampled_from(list(PlacementZone))).value
    # `by` names an off-panel speaker, which only a `spoken` caption has.
    if kind.is_quoted and draw(st.booleans()):
        caption["by"] = draw(_actor_ids())
    return {"caption": caption}


@st.composite
def panels(draw: st.DrawFn) -> Drawn:
    """A single-panel document the compiler should accept.

    Draws a size and a margin that leaves room, one to three cast members, `left_of`
    relations read off a drawn permutation -- so they can never form a cycle -- and up to
    four lines of dialogue or captions. A panel that is valid but too crowded to letter
    is still possible, and is what the failure property is about.
    """
    width = draw(st.integers(min_value=360, max_value=1400))
    # No taller than two and a half times the width, nor wider than that times the height:
    # beyond it a panel is a sliver with no room to letter, which tests nothing new.
    height = draw(
        st.integers(min_value=max(360, int(width / 2.5)), max_value=min(1400, int(width * 2.5)))
    )
    panel: dict[str, Any] = {"size": [width, height]}
    if draw(st.booleans()):
        # Up to a tenth of the shorter side: `2 * margin < min(width, height)` with
        # plenty to spare, since a margin that leaves no room for a balloon is a
        # different property.
        panel["margin"] = draw(st.integers(min_value=0, max_value=min(width, height) // 10))

    document: dict[str, Any] = {"panel": panel}
    shot = draw(st.sampled_from(list(ShotType)))
    document["camera"] = {
        "shot": shot.value,
        "angle": draw(st.sampled_from(list(CameraAngle))).value,
    }

    ids = draw(st.lists(_actor_ids(), min_size=1, max_size=3, unique=True))
    document["cast"] = {actor: draw(_cast_member()) for actor in ids}

    order = draw(st.permutations(ids))
    staging = [f"{left} left_of {right}" for left, right in pairwise(order) if draw(st.booleans())]
    if staging:
        document["staging"] = staging

    if draw(st.booleans()):
        setting: dict[str, Any] = {
            "place": draw(st.sampled_from(list(Place))).value,
            "time": draw(st.sampled_from(list(TimeOfDay))).value,
            "weather": draw(st.sampled_from(list(Weather))).value,
        }
        document["setting"] = setting

    # The tighter the shot, the more of the frame is face, and a balloon may never cover
    # a face. At the two tightest there is often no legal place for even one word, which
    # is the language working as designed rather than anything worth generating.
    lines = _LINES_AT.get(shot, 4)
    script = draw(st.lists(_event(ids), min_size=min(1, lines), max_size=lines))
    if script:
        document["script"] = script
    return Drawn(document)
