"""Monochrome as an output, not only as a source (#244): `--mono` and `render(mono=True)`.

Monochrome is a choice at two levels. `palette: mono` is the author's, written in the
source. `--mono` is the output's: a black-and-white edition of a book drawn in colour, made
without editing a single document. It draws every value as its grey and ignores its colour.

The emitter chooses no colour by it. It chooses which of two values the solver already
resolved to draw, the way `--live-text` chooses how to draw text the solver already set.
And because every decision was made on the grey, what it draws is byte for byte what
`palette: mono` draws -- which is what keeps the two routes to monochrome from drifting.
"""

import re
from pathlib import Path

import pytest

from scenet import (
    Palette,
    compile_book,
    compile_source,
    render,
    render_page,
    render_pages,
    render_strip,
)
from scenet.cli import main
from tests.test_palette import SETTINGS, core

GALLERY = Path(__file__).resolve().parents[1] / "examples" / "gallery"
EXAMPLES = sorted(
    path for path in GALLERY.iterdir() if path.name.endswith((".panel.yaml", ".scene.yaml"))
)

#: A palette an example writes for itself, at the top of the document.
PALETTE = re.compile(r"^palette: \w+$", re.MULTILINE)

SCENE = """\
palette: tinted
panel: {size: [900, 600]}
camera: {shot: long_shot}
cast: {alice: {reference: alice, pose: standing_neutral}}
setting: {place: docks, time: dusk, weather: rain}
pages: [{tiers: [{panels: [one, two]}]}]
panels:
  one: {}
  two: {setting: {time: night}}
"""


class TestTheSamePanelInGrey:
    @pytest.mark.parametrize("setting", SETTINGS)
    def test_a_tinted_core_in_mono_is_the_mono_core(self, setting: str):
        """Rule 2, at the level of the objects: nothing but the colour is different."""
        assert core(setting, "tinted").as_mono() == core(setting)

    def test_a_mono_core_is_already_in_mono(self):
        panel = core("place: street, time: day")
        assert panel.as_mono() == panel

    def test_it_says_mono_too(self):
        panel = core("place: street, time: day", "tinted").as_mono()
        assert panel.palette is Palette.MONO
        assert panel.to_json() == core("place: street, time: day").to_json()


class TestRenderedInMono:
    @pytest.mark.parametrize("path", EXAMPLES, ids=[path.name for path in EXAMPLES])
    def test_every_gallery_example_tinted_and_drawn_in_mono_is_the_mono_one(self, path: Path):
        """Each panel, each page and the strip: the two routes to monochrome agree."""
        text = path.read_text(encoding="utf-8")
        written = PALETTE.search(text) is not None
        coloured = PALETTE.sub("palette: tinted", text) if written else f"palette: tinted\n{text}"
        grey = PALETTE.sub("palette: mono", text) if written else text
        tinted = compile_book(coloured, source=path)
        mono = compile_book(grey, source=path)
        for name, result in tinted.panels.items():
            drawn = render(result.core, fonts=tinted.fonts, mono=True)
            assert drawn == render(mono.panels[name].core, fonts=mono.fonts), name
        cores = {name: result.core for name, result in tinted.panels.items()}
        greys = {name: result.core for name, result in mono.panels.items()}
        for page, grey in zip(tinted.pages, mono.pages, strict=True):
            drawn = render_page(page, cores, fonts=tinted.fonts, mono=True)
            assert drawn == render_page(grey, greys, fonts=mono.fonts)
        drawn = render_strip(list(cores.items()), fonts=tinted.fonts, mono=True)
        assert drawn == render_strip(list(greys.items()), fonts=mono.fonts)

    def test_without_it_the_colour_is_drawn(self):
        panel = core("place: docks, time: dusk", "tinted")
        assert render(panel) != render(panel, mono=True)

    def test_without_it_a_page_and_a_strip_draw_the_colour_too(self):
        book = compile_book(SCENE)
        cores = {name: result.core for name, result in book.panels.items()}
        fonts = book.fonts
        page = book.pages[0]
        assert render_page(page, cores, fonts=fonts) != render_page(
            page, cores, fonts=fonts, mono=True
        )
        assert render_pages(book.pages, cores, fonts=fonts) != render_pages(
            book.pages, cores, fonts=fonts, mono=True
        )
        strip = list(cores.items())
        assert render_strip(strip, fonts=fonts) != render_strip(strip, fonts=fonts, mono=True)

    def test_on_a_mono_panel_it_changes_nothing(self):
        panel = core("place: docks, time: dusk, weather: rain")
        assert render(panel, mono=True) == render(panel)

    def test_it_never_touches_a_panel_with_nothing_to_tint(self):
        panel = compile_source("palette: tinted\ncast: {a: {reference: alice}}").core
        assert render(panel, mono=True) == render(panel)


class TestTheCommand:
    def test_build_mono_writes_what_palette_mono_writes(self, tmp_path: Path):
        tinted = tmp_path / "tinted" / "docks.scene.yaml"
        plain = tmp_path / "plain" / "docks.scene.yaml"
        for path, text in ((tinted, SCENE), (plain, SCENE.replace("palette: tinted\n", ""))):
            path.parent.mkdir()
            path.write_text(text, encoding="utf-8")
        assert main(["build", str(tinted), "--mono", "--strip", "--quiet"]) == 0
        assert main(["build", str(plain), "--strip", "--quiet"]) == 0
        written = sorted(path.name for path in tinted.parent.glob("*.svg"))
        assert written == sorted(path.name for path in plain.parent.glob("*.svg"))
        assert len(written) == 4
        for name in written:
            assert (tinted.parent / name).read_bytes() == (plain.parent / name).read_bytes(), name

    def test_without_it_build_draws_the_colour(self, tmp_path: Path):
        path = tmp_path / "docks.scene.yaml"
        path.write_text(SCENE, encoding="utf-8")
        assert main(["build", str(path), "--quiet"]) == 0
        mono = tmp_path / "mono"
        mono.mkdir()
        assert main(["build", str(path), "--mono", "-o", str(mono / "docks.svg"), "--quiet"]) == 0
        assert (tmp_path / "docks.one.svg").read_bytes() != (mono / "docks.one.svg").read_bytes()
