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
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from markdown_it import MarkdownIt

from tests import myst

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


def _entries_on_the_page() -> dict[str, str]:
    """The text under each `###` heading of the page, by the heading."""
    sections = myst.sections(PAGE.read_text(encoding="utf-8"))
    return {
        section.heading.text: section.text for section in sections if section.heading.level == 3
    }


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
        headings = myst.headings(PAGE.read_text(encoding="utf-8"))
        found = [(heading.level, heading.text) for heading in headings if heading.level > 1]
        assert found == expected

    def test_every_heading_has_an_anchor_of_its_own(self):
        slugs = [heading.anchor for heading in myst.headings(PAGE.read_text(encoding="utf-8"))]
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


#: The gallery's copy of the language reference's complete example (#243).
COMPLETE = GALLERY / "71-a-complete-panel.panel.yaml"


def _without_its_comment(path: Path) -> str:
    """A gallery document less the comment that introduces it there."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return "".join(lines)


class TestTheReferenceIsInTheGallery:
    """What the language reference shows as a whole is a gallery example, so it has a picture,
    and the test suite compiles it."""

    def test_its_complete_example_is_the_gallerys(self):
        overview = (LANGUAGE / "index.md").read_text(encoding="utf-8")
        block = re.search(r"## A complete example\n\n```yaml\n(.*?)```", overview, re.DOTALL)
        assert block, "the reference shows a complete example"
        assert block.group(1) == _without_its_comment(COMPLETE)

    def test_the_example_points_back_at_it(self):
        (entry,) = [entry for entry in ENTRIES if entry["file"] == COMPLETE.name]
        assert entry["doc"] == "reference/language/index.md#a-complete-example"

    def test_one_example_sets_every_horizon_in_one_place(self):
        """`horizon` has an example of its own: the same place under each horizon."""
        (entry,) = [
            entry for entry in ENTRIES if entry["doc"] == "reference/language/setting.md#horizon"
        ]
        document = yaml.safe_load((GALLERY / entry["file"]).read_text(encoding="utf-8"))
        settings = [panel["setting"] for panel in document["panels"].values()]
        assert sorted(setting["horizon"] for setting in settings) == ["high", "low", "mid"]
        assert len({setting["place"] for setting in settings}) == 1


#: The language reference: a page per block, and an overview.
LANGUAGE = DOCS / "reference" / "language"

#: Sections of the language reference that explain rather than define, and so show no
#: construct of their own: why each has no picture, by page and anchor. An entry whose heading
#: goes, or which an example's `doc:` comes to name, fails `test_every_excuse_is_current`.
EXPLAINED = {
    "index#the-scenet-language": "the overview: its sections show the language whole",
    "setting#backdrops-are-never-author-drawn": (
        "why no backdrop is drawn in the language; `masses`, `place` and the image behind "
        "the cast show what there is"
    ),
    "staging#why-ordering-must-be-explicit": "why the solver needs `left_of`; `staging` shows it",
    "lettering#capitals-are-yours-to-set": (
        "what Scenet does not do to lettering, so nothing to draw"
    ),
    "index#determinism": "a promise about bytes, which a picture cannot show",
    "index#the-contract-is-on-the-svg-text-not-on-pixels": "the same promise, and which bytes",
}

#: A link from the language reference to an example on the Gallery page.
GALLERY_LINK = re.compile(r"\[([^\]]+)\]\(\.\./\.\./gallery\.md#([\w-]+)\)")


@dataclass(frozen=True)
class Part:
    """A section of one page of the language reference, its title's included."""

    page: str
    section: myst.Section

    @property
    def name(self) -> str:
        """`page#anchor`, as `EXPLAINED` and a test id name it."""
        return f"{self.page}#{self.section.heading.anchor}"

    @property
    def doc(self) -> str:
        """What an example's `doc:` says to name it."""
        return f"reference/language/{self.page}.md#{self.section.heading.anchor}"


def _examples_of(part: Part) -> list[dict[str, Any]]:
    """The examples whose `doc:` is this section, as the menu orders them."""
    return [
        entry for _, members in _display_order() for entry in members if entry["doc"] == part.doc
    ]


def _language_parts() -> list[Part]:
    return [
        Part(page.stem, section)
        for page in sorted(LANGUAGE.glob("*.md"))
        for section in myst.sections(page.read_text(encoding="utf-8"), titles=True)
    ]


def _subsections(part: Part) -> list[Part]:
    """The sections nested in this one: those after it on its page, up to one at its level."""
    found = [other for other in _language_parts() if other.page == part.page]
    after = found[found.index(part) + 1 :]
    nested: list[Part] = []
    for other in after:
        if other.section.heading.level <= part.section.heading.level:
            break
        nested.append(other)
    return nested


def _shows_its_examples(part: Part) -> bool:
    return bool(_examples_of(part))


class TestEveryConstructIsShown:
    """Every section of the language reference shows its construct (#243): a picture of a
    gallery example whose `doc:` names the section, and a link to each of those examples on
    the Gallery page, in the playground menu's order. A section no example names is shown by
    its subsections when one of them shows its own and the rest explain; a section that only
    explains says why, in `EXPLAINED`."""

    @pytest.mark.parametrize(
        "part",
        [part for part in _language_parts() if _shows_its_examples(part)],
        ids=lambda part: part.name,
    )
    def test_it_shows_a_picture_of_an_example(self, part: Part):
        examples = _examples_of(part)
        theirs = {
            f"../../{picture.relative_to(DOCS).as_posix()}"
            for entry in examples
            for picture in _pictures_of(entry)
        }
        shown = [source for source, alt in _images(part.section.text) if alt.strip()]
        assert set(shown) & theirs, f"no picture of {[entry['file'] for entry in examples]}"
        assert set(shown) <= theirs, "a picture of an example that names another section"

    @pytest.mark.parametrize(
        "part",
        [part for part in _language_parts() if _shows_its_examples(part)],
        ids=lambda part: part.name,
    )
    def test_it_links_its_examples_in_the_gallery(self, part: Part):
        examples = _examples_of(part)
        assert GALLERY_LINK.findall(part.section.text) == [
            (entry["title"], myst.slug(entry["title"])) for entry in examples
        ]

    @pytest.mark.parametrize(
        "part",
        [part for part in _language_parts() if not _shows_its_examples(part)],
        ids=lambda part: part.name,
    )
    def test_one_with_no_example_explains_or_has_sections_that_show(self, part: Part):
        if part.name in EXPLAINED:
            return
        nested = _subsections(part)
        assert nested, f"{part.name} has no example: name it in an example's doc:"
        shown = [other for other in nested if _shows_its_examples(other)]
        assert shown, f"{part.name} and its sections show nothing"
        assert all(_shows_its_examples(other) or other.name in EXPLAINED for other in nested), (
            f"a section of {part.name} shows nothing and does not say why"
        )

    def test_every_excuse_is_current(self):
        parts = {part.name: part for part in _language_parts()}
        assert sorted(EXPLAINED.keys() - parts.keys()) == [], "a heading that is gone"
        assert [name for name in EXPLAINED if _examples_of(parts[name])] == [], (
            "an example names it now: show it"
        )

    def test_a_link_names_an_example_on_the_gallery_page(self):
        """Its anchor is the example's title, so a link cannot name an example that is not
        there, or name it by another title."""
        titles = {myst.slug(entry["title"]): entry["title"] for entry in ENTRIES}
        links = [
            link
            for page in sorted(LANGUAGE.glob("*.md"))
            for link in GALLERY_LINK.findall(page.read_text(encoding="utf-8"))
        ]
        assert links, "the reference links the gallery"
        assert [(title, anchor) for title, anchor in links if titles.get(anchor) != title] == []


README = ROOT / "README.md"

#: Where the README's pictures are fetched from: the README is PyPI's project page too, where
#: a path in the repository leads nowhere, and GitHub serves an SVG there as an image.
RAW = "https://raw.githubusercontent.com/creatoan/scenet/main/"

#: The Gallery page on the site, at the root, which serves the latest release.
GALLERY_PAGE = "https://creatoan.github.io/scenet/gallery.html"


class TestTheReadme:
    """The README shows the tour, the example the playground opens on, and links the Gallery
    page (#243)."""

    def test_it_shows_the_tours_pictures(self):
        (start,) = [entry for entry in ENTRIES if entry["file"] == MANIFEST["start"]]
        shown = [source for source, _ in _images(README.read_text(encoding="utf-8"))]
        expected = [
            f"{RAW}{picture.relative_to(ROOT).as_posix()}" for picture in _pictures_of(start)
        ]
        assert expected
        assert [source for source in shown if source.startswith(RAW)] == expected

    def test_its_pictures_say_what_they_show(self):
        assert all(alt.strip() for _, alt in _images(README.read_text(encoding="utf-8")))

    def test_it_links_the_gallery(self):
        readme = README.read_text(encoding="utf-8")
        assert f"]({GALLERY_PAGE})" in readme
        assert "](docs/gallery.md)" in readme

    def test_it_opens_the_tour_in_the_playground(self):
        readme = README.read_text(encoding="utf-8")
        assert f"]({PLAYGROUND}#example={MANIFEST['start']})" in readme
