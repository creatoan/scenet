"""A Panel Core is hand-edited, so every string of it that reaches an SVG attribute is checked.

Authored YAML cannot put a quotation mark in a colour: colours there are enumerations. A
`.core.json` is another matter -- it is read back and drawn -- so reading one refuses what
the compiler never wrote, and says where (#365). The emitter, for its part, writes every
attribute it did not compute through one escaping helper, so a value that got past the
reader is still only a value.
"""

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from scenet.core import PanelCore
from scenet.errors import CoreSyntaxError

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "core"
HOSTILE = 'x" onload="alert(1)'


def _golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / f"{name}.core.json").read_text(encoding="utf-8"))


def _set(payload: dict[str, Any], path: str, value: object) -> dict[str, Any]:
    """The payload with the value at a dotted path replaced, a number indexing a list."""
    payload = copy.deepcopy(payload)
    node: Any = payload
    *head, last = path.split(".")
    for part in head:
        node = node[int(part)] if part.isdigit() else node[part]
    node[int(last) if last.isdigit() else last] = value
    return payload


TINTED = _golden("40-tinted-hours.midnight")
WARM = _golden("39-warm-caption")
SOUND = _golden("30-sound-effects")
AIR = _golden("21-atmosphere.midnight")

#: Every colour a Core holds, and the document that has it set.
COLOURS = [
    (TINTED, "backdrop.masses.0.tone"),
    (TINTED, "backdrop.masses.0.colour"),
    (AIR, "backdrop.atmosphere.tone"),
    (AIR, "backdrop.atmosphere.fall_tone"),
    (AIR, "backdrop.atmosphere.veil.tone"),
    (TINTED, "backdrop.atmosphere.colour"),
    (TINTED, "backdrop.atmosphere.fall_colour"),
    (TINTED, "backdrop.atmosphere.veil.colour"),
    (SOUND, "sfx.0.fill"),
    (SOUND, "sfx.0.stroke"),
    (WARM, "captions.0.fill"),
    (WARM, "captions.0.ink"),
    (WARM, "captions.0.colour"),
]

#: Every id that is written into an attribute.
IDS = [
    (SOUND, "actors.0.id"),
    (SOUND, "balloons.0.id"),
    (WARM, "captions.0.id"),
    (SOUND, "sfx.0.id"),
    (AIR, "backdrop.masses.0.id"),
]


def _refused(payload: dict[str, Any]) -> str:
    with pytest.raises(CoreSyntaxError) as caught:
        PanelCore.from_json(json.dumps(payload))
    return str(caught.value)


def _has(payload: dict[str, Any], path: str) -> bool:
    node: Any = payload
    for part in path.split("."):
        try:
            node = node[int(part)] if part.isdigit() else node[part]
        except (KeyError, IndexError):
            return False
    return True


@pytest.mark.parametrize(
    "hostile", [HOSTILE, "red", "#fff", "#GGGGGG", "#11111", "#1111111", "url(#a)"]
)
@pytest.mark.parametrize(("payload", "path"), COLOURS)
def test_a_colour_that_is_not_a_hex_triplet_is_refused_where_it_is(
    payload: dict[str, Any], path: str, hostile: str
):
    assert _has(payload, path), f"the document has no {path}"
    message = _refused(_set(payload, path, hostile))
    assert message.startswith("invalid Panel Core:")
    assert path.replace(".", " -> ") in message or path.rsplit(".", maxsplit=1)[-1] in message


@pytest.mark.parametrize(("payload", "path"), COLOURS)
def test_the_colour_the_compiler_wrote_is_accepted(payload: dict[str, Any], path: str):
    PanelCore.from_json(json.dumps(payload))


@pytest.mark.parametrize(("payload", "path"), IDS)
@pytest.mark.parametrize("hostile", [HOSTILE, "a b", "a/b", ""])
def test_an_id_that_is_not_an_identifier_is_refused_where_it_is(
    payload: dict[str, Any], path: str, hostile: str
):
    assert _has(payload, path), f"the document has no {path}"
    assert path.rsplit(".", maxsplit=1)[-1] in _refused(_set(payload, path, hostile))


def test_an_outline_of_nothing_is_a_sound_effect_that_draws_no_stroke():
    """`none` is what a hollow effect fills with, so it is the one named value allowed."""
    PanelCore.from_json(json.dumps(_set(SOUND, "sfx.0.fill", "none")))


def test_a_face_mark_id_is_checked_as_an_id():
    payload = _golden("01-two-characters")
    path = "actors.0.face_marks.0.id"
    if not _has(payload, path):
        pytest.skip("this golden draws no face")
    assert "id" in _refused(_set(payload, path, HOSTILE))


class TestEveryAttributeIsEscaped:
    """No f-string in `emit/` writes a value it did not compute into an attribute raw."""

    #: What an attribute may be given without `attr`: a number the emitter formatted, a
    #: list of points it formatted, a constant, or a name it computed from constants.
    COMPUTED = re.compile(
        r"^(?:fmt\(|_points\(|_hull_points\(|[A-Z][A-Z_0-9]*$|[A-Z][A-Z_0-9]*\[|"
        r"\{|\d)"
    )
    #: `name="{expression}"`, in the source of an f-string.
    INTERPOLATED = re.compile(r'[A-Za-z:-]+="\{([^}]*)\}"')

    def test_the_reader_and_the_helper_agree_on_what_is_computed(self):
        for sample in ("fmt(x)", "STROKE", "_points(a)", "OPENPOSE_COLOURS[1]"):
            assert self.COMPUTED.match(sample), sample

    def test_a_name_is_quoted_by_the_helper(self):
        offenders: list[str] = []
        for path in sorted((ROOT / "src" / "scenet" / "emit").glob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for found in self.INTERPOLATED.finditer(line):
                    expression = found.group(1)
                    if expression in ALLOWED.get(path.name, ()) or self.COMPUTED.match(expression):
                        continue
                    offenders.append(f"{path.name}:{number}: {found.group(0)}")
        assert not offenders, "\n".join(offenders)


#: Interpolations that hold something the emitter computed from numbers or constants, by
#: file. Anything that comes from a Core is written with `attr`, not listed here.
ALLOWED: dict[str, tuple[str, ...]] = {
    "svg.py": (
        "outline",
        "path",
        "stroke",
        "matrix",
        "veil.frequency",
        "veil.octaves",
        "veil.seed",
        "image.preserve_aspect_ratio",
        "XLINK",
    ),
    "debug_svg.py": ("corners", "route", "points"),
    "conditioning.py": ("fill", "width", "height", "ramp_id", "ramp.start", "ramp.end"),
    "strip.py": ("frame", "hole", "d"),
    "preview.py": ("width", "height", "fill"),
    "page.py": (),
}
