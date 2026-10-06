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
from collections.abc import Callable
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


# ---------------------------------------------------------------- scenes and pages

#: Panel names a scene draws from. Plain words, so no name clashes with the files a
#: build writes beside it (`page-1`, `strip`) -- that is #93's business, not this one's.
_PANEL_NAMES: tuple[str, ...] = (
    "dawn",
    "door",
    "hall",
    "stair",
    "roof",
    "yard",
    "gate",
    "well",
    "loft",
)


@dataclass(frozen=True, slots=True)
class DrawnScene:
    """A generated scene and the reading order its pages promise.

    Attributes:
        document: The scene as written.
        order: Each page's panel names in the order a reader takes them -- tier by tier,
            left to right, down each column, an inset before or after its parent as its
            `read` says. Worked out from the authored structure alone, never by asking
            `solve/page.py`, so it can catch the solver getting it wrong.
    """

    document: dict[str, Any]
    order: tuple[tuple[str, ...], ...]

    @property
    def text(self) -> str:
        return yaml.safe_dump(self.document, sort_keys=False, allow_unicode=True)

    @property
    def page_margin(self) -> float:
        return float(self.document.get("page", {}).get("margin", 100.0))


@st.composite
def _scene_panel(draw: st.DrawFn, cast: list[str], earlier: list[str]) -> dict[str, Any]:
    """What one panel of a scene overrides, perhaps building on an earlier one."""
    panel: dict[str, Any] = {}
    if earlier and draw(st.booleans()):
        # Only ever an earlier panel, so `over:` chains cannot form a cycle.
        panel["over"] = draw(st.sampled_from(earlier))
    if draw(st.booleans()):
        shot = draw(st.sampled_from([ShotType.WIDE, ShotType.FULL_SHOT, ShotType.MEDIUM_SHOT]))
        panel["camera"] = {"shot": shot.value}
    script = draw(st.lists(_event(cast), max_size=2))
    if script:
        panel["script"] = script
    return panel


@st.composite
def _placement(
    draw: st.DrawFn, names: list[str], *, stacked: bool, allow_insets: bool
) -> tuple[dict[str, Any], list[str]]:
    """One panel in a tier or column, and the names it puts on the page in reading order."""
    use = names.pop(0)
    entry: dict[str, Any] = {"use": use}
    weight = draw(st.sampled_from([1, 1, 2]))
    if weight != 1:
        entry["height" if stacked else "width"] = weight
    order = [use]
    if allow_insets and names and draw(st.integers(0, 3)) == 0:
        inset = names.pop(0)
        read = draw(st.sampled_from(["before", "after"]))
        entry["insets"] = [
            {
                "use": inset,
                "at": draw(
                    st.sampled_from(["top_left", "top_right", "bottom_left", "bottom_right"])
                ),
                "size": draw(st.sampled_from([0.25, 0.3, 0.35])),
                "read": read,
            }
        ]
        order = [inset, use] if read == "before" else [use, inset]
    return entry, order


@st.composite
def _tier(draw: st.DrawFn, names: list[str]) -> tuple[dict[str, Any], list[str]]:
    tier: dict[str, Any] = {}
    order: list[str] = []
    if len(names) >= 3 and draw(st.integers(0, 2)) == 0:
        # Columns: a stack beside a single panel, never two stacks side by side.
        stack_first = draw(st.booleans())
        columns: list[dict[str, Any]] = []
        for is_stack in (stack_first, not stack_first):
            count = 2 if is_stack else 1
            panels = []
            for _ in range(count):
                entry, read = draw(_placement(names, stacked=True, allow_insets=False))
                panels.append(entry)
                order += read
            columns.append({"panels": panels})
        tier["columns"] = columns
    else:
        across = draw(st.integers(1, min(3, len(names))))
        slanted = across > 1 and draw(st.integers(0, 2)) == 0
        panels = []
        for _ in range(across):
            if not names:
                break
            entry, read = draw(_placement(names, stacked=False, allow_insets=not slanted))
            panels.append(entry)
            order += read
        tier["panels"] = panels
        if slanted and len(panels) > 1:
            tier["slant"] = draw(st.sampled_from([-8, -4, 4, 8]))
    if draw(st.booleans()):
        tier["height"] = draw(st.sampled_from([1, 2]))
    return tier, order


@st.composite
def scenes(draw: st.DrawFn) -> DrawnScene:
    """A scene of one to five panels laid out on one or two pages.

    Every panel is placed exactly once, insets included. Tiers hold panels or columns,
    never two stacked columns side by side, and an inset is a quarter to a third of its
    parent, in a corner, read before or after it.
    """
    ids = draw(st.lists(_actor_ids(), min_size=1, max_size=2, unique=True))
    document: dict[str, Any] = {
        "cast": {actor: {"reference": draw(st.sampled_from(LIBRARY.names()))} for actor in ids}
    }
    count = draw(st.integers(1, 5))
    names = list(draw(st.permutations(_PANEL_NAMES)))[:count]
    panels: dict[str, Any] = {}
    for index, name in enumerate(names):
        panels[name] = draw(_scene_panel(ids, names[:index]))
    document["panels"] = panels

    document["page"] = {
        "size": [draw(st.sampled_from([1600, 2000])), draw(st.sampled_from([2400, 3000]))],
        "margin": draw(st.sampled_from([60, 100])),
        "gutter": draw(st.sampled_from([30, 40])),
    }
    remaining = list(names)
    pages: list[dict[str, Any]] = []
    order: list[tuple[str, ...]] = []
    page_count = draw(st.integers(1, 2)) if len(remaining) > 1 else 1
    for page_index in range(page_count):
        last = page_index == page_count - 1
        share = remaining if last else remaining[: draw(st.integers(1, len(remaining) - 1))]
        on_page = list(share)
        del remaining[: len(on_page)]
        tiers: list[dict[str, Any]] = []
        read: list[str] = []
        while on_page:
            tier, tier_order = draw(_tier(on_page))
            tiers.append(tier)
            read += tier_order
        pages.append({"tiers": tiers})
        order.append(tuple(read))
    document["pages"] = pages
    return DrawnScene(document, tuple(order))


# ---------------------------------------------------------------- comic scripts


@dataclass(frozen=True, slots=True)
class DrawnScript:
    """A generated comic script, and what it says each panel holds.

    Attributes:
        text: The script.
        lines: For each panel, in order, how many balloons and captions it was written
            with. The compiled book must hold exactly that many -- nothing lost silently.
    """

    text: str
    lines: tuple[int, ...]


def _spoken() -> st.SearchStrategy[str]:
    """A line of dialogue that cannot be mistaken for anything else in a script.

    A line in capitals reads as a character cue, one starting `@` as a directive and
    one starting `PAGE`, `PANEL` or `CAPTION` as a heading, so a lowercase word leads.
    """
    return st.tuples(st.sampled_from(["so", "well", "and", "oh", "look"]), words(max_words=6)).map(
        " ".join
    )


@st.composite
def scripts(draw: st.DrawFn) -> DrawnScript:
    """A comic script of one to three pages, each with one to three panels.

    Panel numbers either run straight through or start again on each page, the case
    #63 was about. Cues carry balloon modifiers, speeches run on over continuation
    lines, and captions name their kind.
    """
    cast = ["ALICE", "BOB"]
    restart = draw(st.booleans())
    out = [
        "---",
        "cast:",
        "  ALICE: {reference: alice, at: left_third}",
        "  BOB: {reference: bob, at: right_third}",
        "staging: [ALICE left_of BOB]",
        "---",
        "",
    ]
    counts: list[int] = []
    number = 0
    for page in range(1, draw(st.integers(1, 3)) + 1):
        out += [f"PAGE {page}", ""]
        if restart:
            number = 0
        for _ in range(draw(st.integers(1, 3))):
            number += 1
            out += [f"PANEL {number}", "@shot: full_shot", "They stand on a corner.", ""]
            lines = 0
            for _ in range(draw(st.integers(0, 3))):
                if draw(st.integers(0, 3)) == 0:
                    kind = draw(st.sampled_from(["", " (locale)", " (monologue)"]))
                    out += [f"CAPTION{kind}: {draw(_spoken())}", ""]
                else:
                    modifier = draw(
                        st.sampled_from(["", " (whisper)", " (shouting)", " (thinking)"])
                    )
                    out += [f"{draw(st.sampled_from(cast))}{modifier}", draw(_spoken())]
                    if draw(st.integers(0, 3)) == 0:
                        out.append(draw(_spoken()))  # a continuation line
                    out.append("")
                lines += 1
            counts.append(lines)
    return DrawnScript("\n".join(out) + "\n", tuple(counts))


# ---------------------------------------------------------------- broken documents


@dataclass(frozen=True, slots=True)
class Mistake:
    """A valid document with exactly one mistake in it, and the finding it must produce.

    Attributes:
        name: Which mistake from the catalogue, for `hypothesis.event` statistics.
        text: The document, as written.
        rule: The rule `scenet check` must report it under.
        path: Where the finding must point, in pydantic's `loc` form.
        needle: Text the finding's first line must contain, or `None` where the mistake
            leaves nothing to point at -- a key that is missing, say.
        exact: Whether `path` is the whole path or only the start of it. A cycle is
            reported at whichever of its relations closes it, so only `staging` is fixed.
    """

    name: str
    text: str
    rule: str
    path: tuple[str | int, ...]
    needle: str | None
    exact: bool = True


def _dump(document: object) -> str:
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def _with_two_actors(document: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """The document, sure to have two cast members, and their ids."""
    cast = dict(document["cast"])
    for spare in ("zed", "yan"):
        if len(cast) >= 2:
            break
        if spare not in cast:
            cast[spare] = {"reference": LIBRARY.names()[0]}
    first, second = list(cast)[:2]
    return {**document, "cast": cast}, first, second


def _swap(word: str) -> str:
    """A typo: two adjacent letters swapped, guaranteed to differ from the word."""
    for index in range(len(word) - 1):
        if word[index] != word[index + 1]:
            return word[:index] + word[index + 1] + word[index] + word[index + 2 :]
    return word + "x"


# Each mistake takes a valid panel, a cast member's id and Hypothesis's `draw`, and
# returns the broken document with the finding it must produce. The document and the
# member are copies, free to change.
_Breaker = Callable[[dict[str, Any], str, st.DrawFn], Mistake]


def _misspelled_key(document: dict[str, Any], actor: str, draw: st.DrawFn) -> Mistake:
    key = draw(st.sampled_from([key for key in document if key != "cast"]))
    typo = _swap(key)
    broken = {typo if name == key else name: value for name, value in document.items()}
    return Mistake("misspelled-key", _dump(broken), "unknown-key", (typo,), typo)


def _misspelled_required_key(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    member = document["cast"][actor]
    member["referecne"] = member.pop("reference")
    path = ("cast", actor, "referecne")
    return Mistake("misspelled-required-key", _dump(document), "unknown-key", path, "referecne")


def _missing_field(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    del document["cast"][actor]["reference"]
    path = ("cast", actor, "reference")
    # Nothing to point at but the member it is missing from.
    return Mistake("missing-field", _dump(document), "missing-field", path, actor)


def _wrong_type(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["camera"] = {**document["camera"], "shot": 5}
    return Mistake("wrong-type", _dump(document), "invalid-field", ("camera", "shot"), "shot")


def _out_of_range(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["panel"] = {**document["panel"], "margin": -5}
    path = ("panel", "margin")
    return Mistake("out-of-range", _dump(document), "invalid-field", path, "margin")


def _nan(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    _, height = document["panel"]["size"]
    document["panel"] = {**document["panel"], "size": [float("nan"), height]}
    return Mistake("nan", _dump(document), "invalid-field", ("panel", "size", 0), ".nan")


def _infinity(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["panel"] = {**document["panel"], "margin": float("inf")}
    path = ("panel", "margin")
    return Mistake("infinity", _dump(document), "invalid-field", path, "margin")


def _unknown_actor_in_script(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["script"] = [{"say": {"by": "nobody_here", "text": "Hello."}}]
    path = ("script", 0, "say", "by")
    return Mistake("unknown-actor-in-script", _dump(document), "unknown-actor", path, "nobody_here")


def _unknown_actor_in_staging(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["staging"] = [f"{actor} left_of nobody_here"]
    path = ("staging", 0)
    return Mistake(
        "unknown-actor-in-staging", _dump(document), "unknown-actor", path, "nobody_here"
    )


def _reflexive_relation(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["staging"] = [f"{actor} left_of {actor}"]
    path = ("staging", 0)
    return Mistake("reflexive-relation", _dump(document), "reflexive-relation", path, "left_of")


def _ordering_cycle(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document, first, second = _with_two_actors(document)
    document["staging"] = [f"{first} left_of {second}", f"{second} left_of {first}"]
    text = _dump(document)
    return Mistake("ordering-cycle", text, "ordering-cycle", ("staging",), "left_of", exact=False)


def _unknown_puppet(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    # The pose and expression go too: they belong to the puppet that no longer resolves.
    document["cast"][actor] = {"reference": "nobody_drawn"}
    path = ("cast", actor, "reference")
    return Mistake("unknown-puppet", _dump(document), "unknown-puppet", path, "nobody_drawn")


def _unknown_pose(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["cast"][actor]["pose"] = "levitating"
    path = ("cast", actor, "pose")
    return Mistake("unknown-pose", _dump(document), "unknown-pose", path, "levitating")


def _unknown_expression(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["cast"][actor]["expression"] = "smug"
    path = ("cast", actor, "expression")
    return Mistake("unknown-expression", _dump(document), "unknown-expression", path, "smug")


def _unknown_place(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["setting"] = {"place": "moon"}
    return Mistake("unknown-place", _dump(document), "unknown-place", ("setting", "place"), "moon")


def _conflicting_setting(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    document["setting"] = {"place": "shore", "masses": [{"kind": "sky"}]}
    path = ("setting", "place")
    return Mistake("conflicting-setting", _dump(document), "conflicting-setting", path, "place")


def _duplicate_key(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    text = _dump(document) + "camera: {shot: wide}\n"
    return Mistake("duplicate-key", text, "duplicate-key", (), "camera")


def _panel_geometry(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    width, height = document["panel"]["size"]
    # Half the shorter side, rounded up: two margins then meet or cross.
    document["panel"] = {**document["panel"], "margin": -(-min(width, height) // 2)}
    return Mistake("panel-geometry", _dump(document), "panel-geometry", ("panel",), "panel")


def _not_a_mapping(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    return Mistake("not-a-mapping", _dump(list(document)), "not-a-mapping", (), None)


def _unbalanced(document: dict[str, Any], actor: str, _: st.DrawFn) -> Mistake:
    text = _dump(document) + "staging: [unclosed\n"
    return Mistake("syntax", text, "syntax", (), None)


def _truncated(document: dict[str, Any], actor: str, draw: st.DrawFn) -> Mistake:
    """Cut off in the middle of a flow mapping, as a document saved half-written is."""
    text = _dump(document) + "camera: {shot: wide, angle"
    return Mistake("truncated", text, "syntax", (), None)


#: Every mistake a single-panel document can make, after #92's catalogue.
MISTAKES: dict[str, _Breaker] = {
    "misspelled-key": _misspelled_key,
    "misspelled-required-key": _misspelled_required_key,
    "missing-field": _missing_field,
    "wrong-type": _wrong_type,
    "out-of-range": _out_of_range,
    "nan": _nan,
    "infinity": _infinity,
    "unknown-actor-in-script": _unknown_actor_in_script,
    "unknown-actor-in-staging": _unknown_actor_in_staging,
    "reflexive-relation": _reflexive_relation,
    "ordering-cycle": _ordering_cycle,
    "unknown-puppet": _unknown_puppet,
    "unknown-pose": _unknown_pose,
    "unknown-expression": _unknown_expression,
    "unknown-place": _unknown_place,
    "conflicting-setting": _conflicting_setting,
    "duplicate-key": _duplicate_key,
    "panel-geometry": _panel_geometry,
    "not-a-mapping": _not_a_mapping,
    "syntax": _unbalanced,
    "truncated": _truncated,
}


@st.composite
def mistakes(draw: st.DrawFn, kind: str) -> Mistake:
    """The mistake `kind` from the catalogue, applied to a generated panel.

    Each mistake carries the rule and the path its one finding must have, so a test can
    hold `scenet check` to *exactly one* finding per mistake, at the right place.
    """
    document = draw(panels()).document
    document = {
        **document,
        "cast": {name: dict(member) for name, member in document["cast"].items()},
    }
    actor = next(iter(document["cast"]))
    return MISTAKES[kind](document, actor, draw)
