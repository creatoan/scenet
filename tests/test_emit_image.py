"""Drawing a supplied picture: an `<image>` behind the cast, linked or embedded (#70).

The emitter decides nothing. Where the picture is drawn, and how it fits, come from Panel
Core; what is written here is how SVG says so, checked against what renderers do:

- `xlink:href`, not `href`. SVG 2 deprecates the XLink spelling, but Inkscape still does
  not load a resource named by plain `href` (inkscape/inbox#4411), and with both, a
  renderer reads `href` and an editor that rewrites one leaves them disagreeing.
- The namespace is declared on the element itself, so a panel's body placed in a strip
  or a page carries it along.
- Linked by default, by the path as written, percent-encoded so a space or a `#` stays a
  path. Embedded on request, as a `data:` URI of the very bytes Panel Core names: an SVG
  shown as an `<img>`, or rasterised, loads no external file at all (MDN, "SVG as an
  image"), so the playground and the MCP server embed.
"""

import base64
import hashlib
import os
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scenet.cli import main
from scenet.core import PanelCore
from scenet.emit.debug_svg import render_debug
from scenet.emit.page import render_page, render_pages
from scenet.emit.strip import render_strip
from scenet.emit.svg import render
from scenet.pipeline import compile_book, compile_source
from tests.images import tiny_png
from tests.invariants import assert_accessible, assert_svg_is_sound

SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"
PICTURE = tiny_png(3, 2)
FILES = {"art/street.png": PICTURE}
CAST = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"


def _compile(setting: str = "setting: {image: art/street.png}\n", files: dict[str, bytes] = FILES):
    return compile_source(f"panel: {{size: [1200, 600]}}\n{CAST}{setting}", base=files)


def _image(svg: str) -> ElementTree.Element:
    found = ElementTree.fromstring(svg.encode("utf-8")).findall(f".//{SVG}image")
    assert len(found) == 1
    return found[0]


class TestTheElement:
    def test_it_is_drawn_where_panel_core_says(self):
        core = _compile().core
        image = _image(render(core))
        assert (image.get("x"), image.get("y"), image.get("width"), image.get("height")) == (
            "0",
            "-100",
            "1200",
            "800",
        )
        assert image.get("preserveAspectRatio") == "xMidYMid slice"

    def test_contain_is_meet(self):
        image = _image(render(_compile("setting: {image: art/street.png, fit: contain}\n").core))
        assert image.get("preserveAspectRatio") == "xMidYMid meet"
        assert (image.get("x"), image.get("width"), image.get("height")) == ("150", "900", "600")

    def test_it_is_linked_by_xlink_href_alone(self):
        svg = render(_compile().core)
        image = _image(svg)
        assert image.get(f"{XLINK}href") == "art/street.png"
        assert image.get("href") is None
        assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in svg

    def test_it_has_an_id_to_find_it_by(self):
        assert _image(render(_compile().core)).get("id") == "image"

    def test_it_is_behind_the_cast_and_under_the_weather(self):
        svg = render(_compile("setting: {image: art/street.png, weather: rain}\n").core)
        fill = svg.index('fill="#ffffff"/>')
        image = svg.index("<image ")
        veil = svg.index('filter="url(#scenet-veil-')
        cast = svg.index('id="actor-alice"')
        weather = svg.index('id="weather"')
        assert fill < image < veil < cast < weather

    def test_a_hand_edited_box_moves_the_picture(self):
        core = _compile().core
        assert core.backdrop is not None
        assert core.backdrop.image is not None
        moved = core.backdrop.image.box.model_copy(update={"x": 40.0})
        edited = core.model_copy(
            update={
                "backdrop": core.backdrop.model_copy(
                    update={"image": core.backdrop.image.model_copy(update={"box": moved})}
                )
            }
        )
        assert _image(render(edited)).get("x") == "40"

    @pytest.mark.parametrize(
        ("declared", "written"),
        [
            ("art/my street #1.png", "art/my%20street%20%231.png"),
            ("art/café.png", "art/caf%C3%A9.png"),
            ("./art/a:b?.png", "./art/a%3Ab%3F.png"),
        ],
    )
    def test_the_link_is_a_path_whatever_the_file_is_called(self, declared: str, written: str):
        core = _compile(f"setting: {{image: '{declared}'}}\n", files={declared: PICTURE}).core
        assert _image(render(core)).get(f"{XLINK}href") == written

    def test_a_panel_without_a_picture_draws_none(self):
        svg = render(compile_source(CAST).core)
        assert "<image" not in svg
        assert "xlink" not in svg


class TestEmbedding:
    def test_the_bytes_are_embedded_as_a_data_uri(self):
        result = _compile()
        href = _image(render(result.core, embed=result.images)).get(f"{XLINK}href")
        assert href is not None
        prefix = "data:image/png;base64,"
        assert href.startswith(prefix)
        assert base64.b64decode(href.removeprefix(prefix)) == PICTURE

    def test_a_picture_not_handed_over_is_refused(self):
        result = _compile()
        with pytest.raises(ValueError, match=r"art/street.png"):
            render(result.core, embed={})

    def test_the_refusal_names_the_picture_by_the_start_of_its_digest(self):
        result = _compile()
        digest = next(iter(result.images))
        with pytest.raises(ValueError, match=re.escape(f"(sha256 {digest[:12]}...)")):
            render(result.core, embed={})

    def test_pages_side_by_side_embed_too(self):
        book = compile_book(
            "cast: {alice: {reference: alice}}\nsetting: {image: art/street.png}\n"
            "page: {size: [1500, 1000], margin: 50, gutter: 30}\n"
            "pages:\n  - tiers:\n      - panels: [one]\n  - tiers:\n      - panels: [two]\n"
            "panels:\n  one: {}\n  two: {}\n",
            base=FILES,
        )
        cores = {name: result.core for name, result in book.panels.items()}
        svg = render_pages(book.pages, cores, embed=book.images)
        assert svg.count('xlink:href="data:image/png;base64,') == 2
        assert "art/street.png" not in svg.replace("art/street.png 3x2", "")

    def test_bytes_that_are_not_the_picture_measured_are_refused(self):
        result = _compile()
        digest = next(iter(result.images))
        with pytest.raises(ValueError, match=r"art/street.png"):
            render(result.core, embed={digest[::-1]: PICTURE})

    def test_embedding_is_byte_identical_across_runs(self):
        first, second = _compile(), _compile()
        assert render(first.core, embed=first.images) == render(second.core, embed=second.images)

    def test_a_strip_and_a_page_embed_and_link_alike(self):
        book = compile_book(
            "cast: {alice: {reference: alice}}\nsetting: {image: art/street.png}\n"
            "page: {size: [1500, 1000], margin: 50, gutter: 30}\n"
            "pages:\n  - tiers:\n      - panels: [one, two]\n"
            "panels:\n  one: {}\n  two: {}\n",
            base=FILES,
        )
        cores = [(name, result.core) for name, result in book.panels.items()]
        strip = render_strip(cores, embed=book.images)
        page = render_page(book.pages[0], dict(cores), embed=book.images)
        for svg in (strip, page):
            root = ElementTree.fromstring(svg.encode("utf-8"))
            hrefs = [image.get(f"{XLINK}href") for image in root.iter(f"{SVG}image")]
            assert len(hrefs) == 2
            assert all(href is not None and href.startswith("data:image/png") for href in hrefs)
            ids = [image.get("id") for image in root.iter(f"{SVG}image")]
            assert ids == ["p1-image", "p2-image"]
        linked = render_strip(cores)
        assert linked.count('xlink:href="art/street.png"') == 2


class TestTheOverlay:
    def test_it_shows_where_the_picture_is_placed(self):
        debug = render_debug(_compile().core)
        assert 'class="image"' in debug
        assert 'x="0" y="-100" width="1200" height="800"' in debug
        assert "art/street.png 3x2 px cover" in debug

    def test_it_draws_no_horizon_over_a_picture(self):
        assert "horizon" not in render_debug(_compile().core)

    def test_it_never_links_the_picture(self):
        assert "<image" not in render_debug(_compile().core)


class TestItIsSound:
    def test_the_svg_holds_together_linked_and_embedded(self):
        result = _compile("setting: {image: art/street.png, weather: snow}\n")
        sizes = [balloon.font_size for balloon in result.core.balloons]
        for svg in (render(result.core), render(result.core, embed=result.images)):
            assert_svg_is_sound(svg, size=(1200, 600), font_sizes=sizes)
            assert_accessible(svg, result.core)

    def test_the_picture_adds_nothing_to_what_is_read(self):
        """It is a child of the panel's one image, so it is presentational: the name is
        what it was, and the picture has no title of its own."""
        painted = _compile().core
        root = ElementTree.fromstring(render(painted).encode("utf-8"))
        titles = list(root.iter(f"{SVG}title"))
        assert len(titles) == 1
        assert titles[0].text == " ".join(
            [painted.description or "", *(balloon.label or "" for balloon in painted.balloons)]
        )

    def test_a_core_read_back_draws_the_same(self):
        result = _compile()
        restored = PanelCore.from_json(result.core.to_json())
        assert render(restored) == render(result.core)
        assert render(restored, embed=result.images) == render(result.core, embed=result.images)


class TestTheCommandLine:
    @pytest.fixture
    def comic(self, tmp_path: Path) -> Path:
        folder = tmp_path / "comic"
        (folder / "art").mkdir(parents=True)
        (folder / "art" / "street.png").write_bytes(PICTURE)
        (folder / "p1.panel.yaml").write_text(
            f"{CAST}setting: {{image: art/street.png}}\n", encoding="utf-8"
        )
        return folder

    def test_beside_the_document_it_links_with_no_note(self, comic: Path, capsys):
        assert main(["build", str(comic / "p1.panel.yaml")]) == 0
        assert 'xlink:href="art/street.png"' in (comic / "p1.svg").read_text(encoding="utf-8")
        assert "linked" not in capsys.readouterr().out

    def test_elsewhere_a_note_says_the_link_will_not_resolve(
        self, comic: Path, tmp_path: Path, capsys
    ):
        out = tmp_path / "out"
        assert main(["build", str(comic / "p1.panel.yaml"), "-o", f"{out}{os.sep}"]) == 0
        written = capsys.readouterr().out
        assert "art/street.png" in written
        assert "--embed-images" in written

    def test_quiet_says_nothing(self, comic: Path, tmp_path: Path, capsys):
        out = tmp_path / "out"
        main(["build", str(comic / "p1.panel.yaml"), "-o", f"{out}{os.sep}", "--quiet"])
        assert capsys.readouterr().out == ""

    def test_embed_images_writes_the_bytes_in(self, comic: Path, tmp_path: Path, capsys):
        out = tmp_path / "out"
        main(["build", str(comic / "p1.panel.yaml"), "-o", f"{out}{os.sep}", "--embed-images"])
        svg = (out / "p1.svg").read_text(encoding="utf-8")
        assert base64.b64encode(PICTURE).decode("ascii") in svg
        assert "--embed-images" not in capsys.readouterr().out

    @pytest.mark.parametrize("flags", [[], ["--embed-images"]])
    def test_the_same_bytes_from_any_working_directory(
        self, comic: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str]
    ):
        digests: list[str] = []
        for cwd, document in ((tmp_path, "comic/p1.panel.yaml"), (comic, "p1.panel.yaml")):
            monkeypatch.chdir(cwd)
            out = tmp_path / f"out-{len(digests)}"
            main(["build", document, "-o", f"{out}{os.sep}", "--quiet", *flags])
            svg = (out / "p1.svg").read_bytes()
            assert str(tmp_path).encode() not in svg
            assert tmp_path.as_posix().encode() not in svg
            digests.append(hashlib.sha256(svg).hexdigest())
        assert digests[0] == digests[1]
