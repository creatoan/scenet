"""Render every place at every time of day onto one page, and every weather onto another.

Whether three greys read as depth is not a question a test can answer. It is a question
about a picture, and the only way to settle it is to look -- so this puts every place
the library has on one sheet, at every hour, and you look at it.

That makes it the instrument for the decisions the code cannot make on its own: the two
endpoints of the value ladder at each time of day, how far the plane scales separate the
bands, and whether a night panel is still legible once the ladder has been compressed
into the dark end.

    uv run python scripts/setting_sheet.py -o out/setting.svg
    uv run python scripts/setting_sheet.py --palette tinted -o out/tinted.svg

`--palette tinted` draws the same sheets with `palette: tinted` (#244), every value in the
colour that is its twin, so that the hues `scripts/make_palette.py` produces can be judged
the same way the greys were: by looking.

Written as the sibling of `scripts/contact_sheet.py`, which did the same job for faces.
Each cell is a real panel drawn small, **not** a small panel: the mass profiles are
composed against panel proportions, so a genuinely small panel would answer a different
question from the one being asked.
"""

import argparse
import re
from pathlib import Path

from scenet import Palette, ShotType, compile_source, render
from scenet.ir import TimeOfDay, Weather
from scenet.places import Place

CELL_WIDTH = 300
CELL_HEIGHT = 200
LABEL = 26
GUTTER = 8

#: A figure in every cell, because the point of a backdrop is what it does behind
#: somebody. A long shot, because that is the rung the setting layer was meant to rescue.
CAST = "cast: {a: {reference: alice, pose: standing_neutral}}"
SHOT = ShotType.LONG_SHOT

INNER = re.compile(r"<svg[^>]*>(.*)</svg>", re.DOTALL)


def cell(setting: str, palette: str = "mono") -> str:
    """One panel's drawable content, without its document wrapper."""
    core = compile_source(
        f"{{panel: {{size: [900, 600]}}, camera: {{shot: {SHOT.value}}}, "
        f"{CAST}, setting: {{{setting}}}, palette: {palette}}}"
    ).core
    match = INNER.search(render(core))
    return match.group(1) if match else ""


def sheet(
    title: str,
    rows: list[tuple[str, str]],
    columns: list[tuple[str, str]],
    palette: str = "mono",
) -> str:
    """A grid of panels, one row label and one column label each.

    Args:
        title: What the sheet is showing.
        rows: `(label, setting fragment)` down the page.
        columns: `(label, setting fragment)` across it.
        palette: `mono`, or `tinted` for the ladder in colour.

    Returns:
        One standalone SVG document.
    """
    width = LABEL * 4 + len(columns) * (CELL_WIDTH + GUTTER)
    height = LABEL * 2 + len(rows) * (CELL_HEIGHT + GUTTER)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f4f3f1"/>',
        f'<text x="8" y="18" font-family="monospace" font-size="15">{title}</text>',
    ]
    for index, (label, _) in enumerate(columns):
        x = LABEL * 4 + index * (CELL_WIDTH + GUTTER)
        parts.append(
            f'<text x="{x}" y="{LABEL * 2 - 8}" font-family="monospace" '
            f'font-size="12">{label}</text>'
        )

    for row, (label, row_setting) in enumerate(rows):
        y = LABEL * 2 + row * (CELL_HEIGHT + GUTTER)
        parts.append(
            f'<text x="8" y="{y + CELL_HEIGHT / 2}" font-family="monospace" '
            f'font-size="13">{label}</text>'
        )
        for column, (_, column_setting) in enumerate(columns):
            x = LABEL * 4 + column * (CELL_WIDTH + GUTTER)
            parts.append(
                f'<svg x="{x}" y="{y}" width="{CELL_WIDTH}" height="{CELL_HEIGHT}" '
                f'viewBox="0 0 900 600">{cell(f"{row_setting}, {column_setting}", palette)}</svg>'
            )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def places_sheet(palette: str = "mono") -> str:
    """Every place, at every hour."""
    return sheet(
        f"places x time, {palette}",
        [(place.value, f"place: {place.value}") for place in Place],
        [(time.value, f"time: {time.value}") for time in TimeOfDay],
        palette,
    )


def weather_sheet(palette: str = "mono") -> str:
    """Every weather, at every hour, over one place that shows all four planes."""
    return sheet(
        f"weather x time, on `docks`, {palette}",
        [(weather.value, f"place: docks, weather: {weather.value}") for weather in Weather],
        [(time.value, f"time: {time.value}") for time in TimeOfDay],
        palette,
    )


def main() -> None:
    """Write both sheets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=Path("out/setting.svg"))
    parser.add_argument(
        "--palette",
        choices=[palette.value for palette in Palette],
        default=Palette.MONO.value,
        help="what the panels are drawn in",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheets = (("places", places_sheet(args.palette)), ("weather", weather_sheet(args.palette)))
    for name, content in sheets:
        path = args.output.with_name(f"{args.output.stem}-{name}{args.output.suffix}")
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
