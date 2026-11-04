"""The documentation shows the gallery: every example's picture, exactly as it compiles (#243).

Each gallery example has its pictures under `docs/images/gallery/`: the document drawn whole,
as `scenet build` writes it -- its pages, or else its strip, or else its one panel. They are
golden outputs, rewritten with the others by `scripts/update_golden.py`, so here each is held
to the digest of the build it is a copy of: a picture in the documentation cannot drift from
what the compiler draws.

An example lettered over a picture of its own is shown as the build with `--embed-images`
writes it. A picture an SVG only links is missing from it wherever it is shown as an image --
on a page of the documentation, in the README -- since an SVG loaded that way may load nothing
from outside itself.
"""

import hashlib
import html
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "examples" / "gallery"
DIGESTS: dict[str, str] = json.loads(
    (ROOT / "tests" / "golden" / "digests.json").read_text(encoding="utf-8")
)
MANIFEST: dict[str, Any] = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = MANIFEST["examples"]
DOCS = ROOT / "docs"
PAGE = DOCS / "gallery.md"
PLAYGROUND = "https://creatoan.github.io/scenet/playground/"


def _load(name: str) -> ModuleType:
    """Import a script from `scripts/`, which is not a package."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


update_golden = _load("update_golden")
PICTURES: dict[Path, str] = update_golden.pictures(DIGESTS)
FOLDER: Path = update_golden.GALLERY_PICTURES
SHOWN = sorted(picture for picture in PICTURES if picture.parent == FOLDER)


def _stem(file: str) -> str:
    return file.split(".", maxsplit=1)[0]


def _pictures_of(entry: dict[str, Any]) -> list[Path]:
    return [picture for picture in SHOWN if _stem(picture.name) == _stem(entry["file"])]


class TestEveryPictureIsAGolden:
    @pytest.mark.parametrize(
        ("picture", "golden"),
        sorted(PICTURES.items()),
        ids=[picture.relative_to(ROOT).as_posix() for picture in sorted(PICTURES)],
    )
    def test_it_is_the_build_it_is_named_after(self, picture: Path, golden: str):
        assert picture.is_file(), f"{picture.name} is missing; run `{update_golden.COMMAND}`"
        digest = hashlib.sha256(picture.read_bytes()).hexdigest()
        assert digest == DIGESTS[golden], f"{picture.name} is stale; run `{update_golden.COMMAND}`"

    def test_every_example_has_its_pictures(self):
        assert [entry["file"] for entry in ENTRIES if not _pictures_of(entry)] == []

    def test_the_folder_holds_nothing_else(self):
        assert sorted(FOLDER.iterdir()) == SHOWN

    @pytest.mark.parametrize(
        "entry",
        [entry for entry in ENTRIES if update_golden.lettered_over_a_picture(entry)],
        ids=lambda entry: entry["file"],
    )
    def test_a_picture_it_is_lettered_over_is_written_in(self, entry: dict[str, Any]):
        for picture in _pictures_of(entry):
            svg = picture.read_text(encoding="utf-8")
            assert 'xlink:href="data:image/' in svg, picture.name
            assert 'xlink:href="art/' not in svg, picture.name

    def test_the_others_are_the_build_without_embedding(self):
        """Embedding changes nothing in a document with no picture of its own, so only the
        examples that have one are built a second time."""
        for entry in ENTRIES:
            embedded = update_golden.lettered_over_a_picture(entry)
            for picture in _pictures_of(entry):
                assert PICTURES[picture].startswith(update_golden.EMBEDDED) == embedded


class TestWhatShowsADocument:
    """A document is shown whole: by its pages, or else its strip, or else its one panel."""

    def test_one_panel_is_its_svg_without_the_overlays(self):
        names = ["a.svg", "a.debug.svg", "a.depth.svg", "a.mask.svg", "a.core.json"]
        assert update_golden.shown("a", names) == ["a.svg"]

    def test_several_panels_are_their_strip(self):
        assert update_golden.shown("a", ["a.x.svg", "a.y.svg", "a.strip.svg"]) == ["a.strip.svg"]

    def test_pages_come_before_the_strip_in_order(self):
        names = ["a.page-10.svg", "a.page-2.svg", "a.page-1.svg", "a.strip.svg", "a.x.svg"]
        assert update_golden.shown("a", names) == ["a.page-1.svg", "a.page-2.svg", "a.page-10.svg"]

    def test_another_document_is_not_this_one(self):
        assert update_golden.shown("a", ["ab.svg", "a.x.svg", "b/a.y.svg"]) == ["a.x.svg"]

    @pytest.mark.parametrize("names", [[], ["a.x.svg", "a.y.svg"]])
    def test_nothing_to_show_is_refused(self, names: list[str]):
        with pytest.raises(ValueError, match="'a'"):
            update_golden.shown("a", names)


def _display_order() -> list[tuple[str, list[dict[str, Any]]]]:
    """The playground's menu (`grouped()` in playground/src/gallery.ts): by group, in the
    order `groups:` names them, each in the manifest's order with the opening example first."""
    order = []
    for group in MANIFEST["groups"]:
        members = [entry for entry in ENTRIES if entry["group"] == group]
        start = [entry for entry in members if entry["file"] == MANIFEST["start"]]
        order.append((group, start + [entry for entry in members if entry not in start]))
    return order


def _headings(text: str) -> list[tuple[int, str, int]]:
    """Each `##` and `###` heading outside a fenced block: its level, its text, its line.

    A fence closes only on a run of its own character at least as long as the one that
    opened it, so a script's own fences and headings, shown as its source, stay inside.
    """
    headings: list[tuple[int, str, int]] = []
    fence = ""
    for number, line in enumerate(text.splitlines()):
        marker = re.match(r"(`{3,}|~{3,})", line)
        if fence:
            closing = re.fullmatch(rf"{re.escape(fence[0])}{{{len(fence)},}}\s*", line)
            if closing:
                fence = ""
        elif marker:
            fence = marker.group(1)
        elif match := re.match(r"(#{2,3}) (.+)", line):
            headings.append((len(match.group(1)), match.group(2), number))
    return headings


def _entries_on_the_page() -> dict[str, str]:
    """The text under each `###` heading of the page, by the heading."""
    text = PAGE.read_text(encoding="utf-8")
    lines = text.splitlines()
    headings = _headings(text)
    sections: dict[str, str] = {}
    for index, (level, title, start) in enumerate(headings):
        if level == 3:
            end = headings[index + 1][2] if index + 1 < len(headings) else len(lines)
            sections[title] = "\n".join(lines[start + 1 : end])
    return sections


def _accessible_text(picture: Path) -> str:
    """What the SVG says to a screen reader: its titles, in order."""
    titles = re.findall(r"<title>(.*?)</title>", picture.read_text(encoding="utf-8"), re.DOTALL)
    return " ".join(html.unescape(title) for title in titles)


def _images(markdown: str) -> list[tuple[str, str]]:
    """Every image the Markdown shows, as CommonMark reads it: its source and its alt text.

    Read from the parse rather than the rendered HTML, whose alt text markdown-it-py writes
    without the characters a backslash escapes.
    """
    return [
        (str(child.attrs["src"]), "".join(text.content for text in child.children or []))
        for token in MarkdownIt("commonmark").parse(markdown)
        if token.type == "inline"
        for child in token.children or []
        if child.type == "image"
    ]


def _slug(heading: str) -> str:
    """A heading's anchor as MyST (and GitHub) make it."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower().replace(" ", "-"))


class TestTheGalleryPage:
    """`docs/gallery.md`, generated from the manifest by `scripts/build_spec.py`: every example
    in the order the playground's menu offers them, each with its summary, its pictures, a
    link that opens it in the playground, the page that explains it, and its source."""

    def test_it_holds_every_example_once_in_the_menus_order(self):
        expected = [
            heading
            for group, members in _display_order()
            for heading in [(2, group), *((3, entry["title"]) for entry in members)]
        ]
        found = [(level, text) for level, text, _ in _headings(PAGE.read_text(encoding="utf-8"))]
        assert found == expected

    def test_every_heading_has_an_anchor_of_its_own(self):
        slugs = [_slug(text) for _, text, _ in _headings(PAGE.read_text(encoding="utf-8"))]
        assert len(slugs) == len(set(slugs))

    @pytest.mark.parametrize("entry", ENTRIES, ids=[entry["file"] for entry in ENTRIES])
    def test_an_example_shows_its_summary_and_pictures(self, entry: dict[str, Any]):
        section = _entries_on_the_page()[entry["title"]]
        assert entry["summary"] in section
        assert _images(section) == [
            (picture.relative_to(DOCS).as_posix(), _accessible_text(picture))
            for picture in _pictures_of(entry)
        ]

    @pytest.mark.parametrize("entry", ENTRIES, ids=[entry["file"] for entry in ENTRIES])
    def test_an_example_opens_in_the_playground_and_says_where_to_read(self, entry: dict[str, Any]):
        """Written in full, as GitHub needs it; `docs/conf.py` makes the playground link
        relative in each version of the site, so it opens that version's playground."""
        section = _entries_on_the_page()[entry["title"]]
        assert f"[Open in the playground]({PLAYGROUND}#example={entry['file']})" in section
        assert f"[Read about it]({entry['doc']})" in section

    @pytest.mark.parametrize("entry", ENTRIES, ids=[entry["file"] for entry in ENTRIES])
    def test_an_example_shows_its_source(self, entry: dict[str, Any]):
        section = _entries_on_the_page()[entry["title"]]
        source = (GALLERY / entry["file"]).read_text(encoding="utf-8")
        tokens = MarkdownIt("commonmark").parse(section)
        assert [token.content for token in tokens if token.type == "fence"] == [source]

    def test_it_is_in_the_documentations_contents(self):
        home = (DOCS / "index.md").read_text(encoding="utf-8")
        toctree = re.search(r"```\{toctree\}(.*?)```", home, re.DOTALL)
        assert toctree
        assert "gallery" in toctree.group(1).split()
