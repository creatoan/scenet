"""Generate the tinted ladder: the value ladder in colour, with every value kept (#244).

The colour policy's first rule is that a colour is a twin of a grey on the ladder in
`src/scenet/solve/backdrop.py`, with the grey's OKLab lightness. So this does not invent a
palette. It takes each rung's grey, keeps its lightness, and gives it a hue and a chroma by
one parametric rule -- the painters' warm light and cool shadow, with aerial perspective:

- Each hour has two ends: the shadow's hue and chroma at the foreground (t = 0), and the
  atmosphere's at the sky (t = 1). They are the only inputs, in `ENDS` below.
- Between them, rung by rung, the hue turns the short way round the circle and the chroma
  moves in a straight line, so with distance colour drifts toward the colour of the air.
- Chroma is capped at what sRGB can show at that lightness. That cap, not a tuning, is what
  drains the colour out of night and out of a noon sky.
- Each colour is rounded to the `#rrggbb` closest to it whose lightness is within
  `TOLERANCE` of its grey's, and which is not itself a grey.

The output is hardcoded in `solve/backdrop.py` as `TINTED`, beside the ladder, for the same
reason the ladder is: a handful of values that never change at runtime are not worth a
colour library in `dependencies`. `tests/test_tinted_ladder.py` regenerates the table and
fails on any difference, so the hexes cannot drift from the rule.

Run from the repository root after changing `ENDS`:

    uv run python scripts/make_palette.py           # print the table to paste
    uv run python scripts/make_palette.py --check   # exit 1 if the committed table is stale

Then look at it, because whether these hues are right is a question about a picture:

    uv run python scripts/setting_sheet.py --palette tinted -o out/tinted.svg
"""

import argparse
import math
import sys
from itertools import product
from pathlib import Path

from scenet.ir import TimeOfDay
from scenet.solve import backdrop
from scenet.solve.backdrop import LADDER, lightness

#: Each hour's two ends, as `(hue in degrees, chroma)` in OKLCh: the shadow at the
#: foreground, then the atmosphere. Warm light, cool shadow, except at night, which is
#: blue all the way back.
ENDS: dict[TimeOfDay, tuple[tuple[float, float], tuple[float, float]]] = {
    TimeOfDay.DAWN: ((285.0, 0.020), (50.0, 0.050)),
    TimeOfDay.DAY: ((250.0, 0.015), (235.0, 0.030)),
    TimeOfDay.DUSK: ((300.0, 0.030), (55.0, 0.090)),
    TimeOfDay.NIGHT: ((260.0, 0.020), (250.0, 0.040)),
}

#: How far a colour's lightness may sit from its grey's.
TOLERANCE = 0.005

#: How much of the chroma is given up each time no `#rrggbb` near the colour keeps the
#: grey's lightness, which happens only in the dark, where one step of a channel is a
#: large step of lightness.
BACK_OFF = 0.9

_SRGB_TO_LMS = (
    (0.4122214708, 0.5363325363, 0.0514459929),
    (0.2119034982, 0.6806995451, 0.1073969566),
    (0.0883024619, 0.2817188376, 0.6299787005),
)
_LMS_TO_OKLAB = (
    (0.2104542553, 0.7936177850, -0.0040720468),
    (1.9779984951, -2.4285922050, 0.4505937099),
    (0.0259040371, 0.7827717662, -0.8086757660),
)
_OKLAB_TO_LMS = (
    (1.0, 0.3963377774, 0.2158037573),
    (1.0, -0.1055613458, -0.0638541728),
    (1.0, -0.0894841775, -1.2914855480),
)
_LMS_TO_SRGB = (
    (4.0767416621, -3.3077115913, 0.2309699292),
    (-1.2684380046, 2.6097574011, -0.3413193965),
    (-0.0041960863, -0.7034186147, 1.7076147010),
)

Vector = tuple[float, float, float]


def _apply(matrix: tuple[Vector, Vector, Vector], vector: Vector) -> Vector:
    first, second, third = (sum(m * v for m, v in zip(row, vector, strict=True)) for row in matrix)
    return first, second, third


def _decode(channel: float) -> float:
    """The sRGB transfer curve, undone: an encoded channel to linear light."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _encode(linear: float) -> float:
    """The sRGB transfer curve: linear light to an encoded channel."""
    return 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055


def _linear(tone: str) -> Vector:
    red, green, blue = (_decode(int(tone[index : index + 2], 16) / 255.0) for index in (1, 3, 5))
    return red, green, blue


def oklab(tone: str) -> Vector:
    """A `#rrggbb` colour in OKLab, by Ottosson's published matrices.

    Args:
        tone: Any `#rrggbb` colour, grey or not.

    Returns:
        `(L, a, b)`.
    """
    long, medium, short = _apply(_SRGB_TO_LMS, _linear(tone))
    return _apply(_LMS_TO_OKLAB, (math.cbrt(long), math.cbrt(medium), math.cbrt(short)))


def luminance(tone: str) -> float:
    """WCAG relative luminance, with the three weights a colour needs.

    Args:
        tone: Any `#rrggbb` colour, grey or not.

    Returns:
        Luminance in `0.0 .. 1.0`.
    """
    red, green, blue = _linear(tone)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(one: str, other: str) -> float:
    """WCAG contrast between any two colours.

    Args:
        one: A `#rrggbb` colour.
        other: The colour to compare it against.

    Returns:
        A ratio in `1.0 .. 21.0`.
    """
    lighter, darker = sorted((luminance(one), luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _from_oklch(lightness_: float, chroma: float, hue: float) -> Vector:
    """Linear sRGB for an OKLCh colour, which may lie outside the gamut."""
    angle = math.radians(hue)
    lab = (lightness_, chroma * math.cos(angle), chroma * math.sin(angle))
    long, medium, short = _apply(_OKLAB_TO_LMS, lab)
    return _apply(_LMS_TO_SRGB, (long**3, medium**3, short**3))


def _in_gamut(rgb: Vector) -> bool:
    return all(-1e-9 <= channel <= 1 + 1e-9 for channel in rgb)


def _gamut_chroma(lightness_: float, hue: float) -> float:
    """The most chroma sRGB can show at this lightness and hue, found by bisection."""
    low, high = 0.0, 0.4
    for _ in range(48):
        middle = (low + high) / 2
        if _in_gamut(_from_oklch(lightness_, middle, hue)):
            low = middle
        else:
            high = middle
    return low


def _hue_between(start: float, end: float, t: float) -> float:
    """The hue a fraction `t` of the way from `start` to `end`, the short way round."""
    turn = (end - start + 180.0) % 360.0 - 180.0
    return (start + turn * t) % 360.0


def _hex(red: int, green: int, blue: int) -> str:
    return f"#{red:02x}{green:02x}{blue:02x}"


def _nearest(lightness_: float, chroma: float, hue: float) -> str | None:
    """The `#rrggbb` closest to a colour that keeps its lightness and is not a grey.

    Searched among the codes either side of each channel, and a step beyond: in the dark a
    single step of one channel moves lightness by more than the tolerance, and the other
    two have to make up for it.
    """
    angle = math.radians(hue)
    target = (lightness_, chroma * math.cos(angle), chroma * math.sin(angle))
    codes = [
        math.floor(_encode(min(max(channel, 0.0), 1.0)) * 255)
        for channel in _from_oklch(lightness_, chroma, hue)
    ]
    nearby = [range(max(0, code - 1), min(255, code + 2) + 1) for code in codes]
    best: tuple[float, str] | None = None
    for red, green, blue in product(*nearby):
        if red == green == blue:
            continue
        code = _hex(red, green, blue)
        found = oklab(code)
        if abs(found[0] - lightness_) > TOLERANCE:
            continue
        distance = math.dist(found, target)
        if best is None or (distance, code) < best:
            best = (distance, code)
    return None if best is None else best[1]


def colour_for(grey: str, hue: float, chroma: float) -> str:
    """The twin of one grey: its lightness, the hue and as much of the chroma as fits.

    Args:
        grey: A `#rrggbb` rung of the ladder.
        hue: OKLCh hue, in degrees.
        chroma: The chroma the rule asks for, before the gamut has its say.

    Returns:
        A `#rrggbb` colour with the grey's lightness, to within `TOLERANCE`.
    """
    target = lightness(grey)
    chroma = min(chroma, _gamut_chroma(target, hue))
    while (found := _nearest(target, chroma, hue)) is None:
        chroma *= BACK_OFF
        if chroma < 1e-4:
            raise ValueError(f"no colour keeps the lightness of {grey}")
    return found


def tinted() -> dict[TimeOfDay, tuple[str, str, str, str, str]]:
    """Every hour's ladder, in colour, by the rule in `ENDS`.

    Returns:
        The table `solve/backdrop.py` hardcodes as `TINTED`.
    """
    table: dict[TimeOfDay, tuple[str, str, str, str, str]] = {}
    for time in TimeOfDay:
        (shadow_hue, shadow_chroma), (air_hue, air_chroma) = ENDS[time]
        rungs = LADDER[time]
        colours = [
            colour_for(
                grey,
                _hue_between(shadow_hue, air_hue, index / (len(rungs) - 1)),
                shadow_chroma + (air_chroma - shadow_chroma) * index / (len(rungs) - 1),
            )
            for index, grey in enumerate(rungs)
        ]
        first, second, third, fourth, fifth = colours
        table[time] = (first, second, third, fourth, fifth)
    return table


def table_source() -> str:
    """The table as `solve/backdrop.py` holds it, with each value's chroma and hue beside it.

    Returns:
        Python source, from the comment above `TINTED` to the closing brace.
    """
    table = tinted()
    lines = [
        "# Chroma and hue of each value, as `scripts/make_palette.py` found it. Its lightness",
        "# is its grey's, which the ladder's own comment gives.",
        "#",
        "#            foreground  near        mid         far         atmosphere",
    ]
    for time, colours in table.items():
        cells = []
        for colour in colours:
            _, a, b = oklab(colour)
            hue = math.degrees(math.atan2(b, a)) % 360.0
            cells.append(f"{math.hypot(a, b):.3f} h{hue:3.0f}")
        lines.append(f"#   {time.value:<8} " + "  ".join(cells))
    lines.append("TINTED: dict[TimeOfDay, tuple[str, str, str, str, str]] = {")
    for time, colours in table.items():
        values = ", ".join(f'"{colour}"' for colour in colours)
        lines.append(f"    TimeOfDay.{time.name}: ({values}),")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Print the table, or check the committed one."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if solve/backdrop.py holds another table"
    )
    args = parser.parse_args()

    source = table_source()
    if not args.check:
        sys.stdout.write(source)
        return
    if source not in Path(backdrop.__file__).read_text(encoding="utf-8"):
        sys.exit("solve/backdrop.py holds a stale TINTED: run scripts/make_palette.py")
    print("TINTED is what the rule produces")


if __name__ == "__main__":
    main()
