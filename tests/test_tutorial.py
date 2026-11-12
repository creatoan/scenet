"""The author's tour: a chapter per gallery group, each in the same shape (#321).

The tour, the gallery and the playground share one syllabus. The gallery's manifest names
its groups in order, and the tutorial's table of contents names a chapter for each, in the
same order: chapter one is the group "Your first panel", and so on. So:

- **every chapter has the same parts**, in order: what you will make, with a picture; the
  documents; what the compiler decided; "Try it" links into the playground; a `scenet
  check` step; what you learned; and where to go next;
- **its pictures are the gallery's goldens** (`scripts/update_golden.py` writes them), of
  examples in its own group, each shown beside the example's source, word for word, so a
  picture cannot drift from the document it is said to draw;
- **its "Try it" links open every example of its group**, and no other;
- **it links the language reference and the diagnostics catalogue**, by anchors that exist;
- **what a chapter says a command prints is what it prints**: a `text` block right after a
  `bash` block is that block's output, run on the documents the chapter wrote;
- **the tour introduces the whole language**: every key of a panel or a scene, and every
  top-level key of a puppet file and an artwork contract, is written in a chapter's
  document and linked to its card.

Every document a chapter shows compiles, under the rule of `tests/test_doc_examples.py`;
every `scenet` line it runs is run, under `tests/shell_examples.py`.
"""

import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from scenet.diagnostics import COMPILE_NOTES, RULES
from tests import myst
from tests.doc_examples import fences
from tests.shell_examples import Transcript, commands, run_transcript, transcripts
from tests.test_docs_gallery import (
    ENTRIES,
    MANIFEST,
    PLAYGROUND,
    _accessible_text,
    _images,
    _pictures_of,
)
from tests.test_language_cards import CARDS, _keys

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TUTORIAL = DOCS / "tutorial"
GALLERY = ROOT / "examples" / "gallery"
LANGUAGE = DOCS / "reference" / "language"
GALLERY_PAGE = DOCS / "gallery.md"

#: The parts of a chapter, as its `##` headings, in order. Others may come between them.
PARTS = (
    "What you will make",
    "What the compiler decided",
    "Try it",
    "Check it",
    "What you learned",
    "Where to go next",
)

#: A link into the language reference, from a chapter: its page and its anchor.
LANGUAGE_LINK = re.compile(r"\]\(\.\./reference/language/([\w-]+)\.md(?:#([\w-]+))?\)")
#: A link to an entry of the diagnostics catalogue, from a chapter.
DIAGNOSTIC_LINK = re.compile(r"\]\(\.\./reference/diagnostics\.md#([\w-]+)\)")
#: A link that opens a gallery example in the playground.
EXAMPLE_LINK = re.compile(rf"\]\({re.escape(PLAYGROUND)}#example=([\w.-]+)\)")


def chapters() -> list[Path]:
    """The chapters, in the order the tutorial's table of contents lists them."""
    index = (TUTORIAL / "index.md").read_text(encoding="utf-8")
    toctree = re.search(r"```\{toctree\}\n(.*?)```", index, re.DOTALL)
    assert toctree, "the tutorial has a table of contents"
    names = [
        line.strip()
        for line in toctree.group(1).splitlines()
        if line.strip() and not line.startswith(":")
    ]
    return [TUTORIAL / f"{name}.md" for name in names]


CHAPTERS = chapters()
GROUPS: list[str] = MANIFEST["groups"]
IDS = [chapter.stem for chapter in CHAPTERS]


def _group_of(chapter: Path) -> str:
    return GROUPS[CHAPTERS.index(chapter)]


def _members(group: str) -> list[dict[str, Any]]:
    return [entry for entry in ENTRIES if entry["group"] == group]


def _title(chapter: Path) -> str:
    (title,) = [h.text for h in myst.headings(chapter.read_text(encoding="utf-8")) if h.level == 1]
    return title


def _part(chapter: Path, part: str) -> str:
    """The text of a chapter's part: under the `##` heading that starts with its name."""
    text = chapter.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = _line_of(chapter, part)
    following = [h.line for h in myst.headings(text) if h.level <= 2 and h.line >= start]
    end = following[0] if following else len(lines)
    return "\n".join(lines[start:end])


class TestTheTourIsTheGallerysSyllabus:
    def test_a_chapter_for_each_group_in_order(self):
        assert len(CHAPTERS) == len(GROUPS)

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_a_chapter_is_named_after_its_group(self, chapter: Path):
        assert _title(chapter).startswith(_group_of(chapter))

    def test_the_first_chapter_keeps_its_address(self):
        """The first panel has been at `tutorial/first_panel` since the site began."""
        assert CHAPTERS[0] == TUTORIAL / "first_panel.md"

    def test_every_page_of_the_tutorial_is_a_chapter(self):
        pages = {path for path in TUTORIAL.glob("*.md") if path.name != "index.md"}
        assert pages == set(CHAPTERS)

    @pytest.mark.parametrize("group", GROUPS)
    def test_the_gallery_page_sends_each_group_to_its_chapter(self, group: str):
        chapter = CHAPTERS[GROUPS.index(group)]
        sections = {
            section.heading.text: section.text
            for section in myst.sections(GALLERY_PAGE.read_text(encoding="utf-8"))
            if section.heading.level == 2
        }
        link = f"[{_title(chapter)}](tutorial/{chapter.name})"
        assert link in sections[group]


class TestEveryChapterHasItsParts:
    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_its_parts_in_order(self, chapter: Path):
        headings = [
            h.text for h in myst.headings(chapter.read_text(encoding="utf-8")) if h.level == 2
        ]
        found = [part for heading in headings for part in PARTS if heading.startswith(part)]
        assert found == list(PARTS)

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_it_shows_what_you_will_make(self, chapter: Path):
        """A picture of an example of its own group, saying what it shows."""
        theirs = {
            f"../{picture.relative_to(DOCS).as_posix()}": picture
            for entry in _members(_group_of(chapter))
            for picture in _pictures_of(entry)
        }
        shown = _images(_part(chapter, "What you will make"))
        assert shown, "a picture of what you will make"
        for source, alt in shown:
            assert source in theirs, f"{source} is no picture of this chapter's group"
            assert alt == _accessible_text(theirs[source])

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_every_picture_is_shown_with_its_document(self, chapter: Path):
        """A gallery picture anywhere in the chapter sits beside its example's source."""
        pictures = {
            f"../{picture.relative_to(DOCS).as_posix()}": entry
            for entry in ENTRIES
            for picture in _pictures_of(entry)
        }
        texts = {fence.text for fence in fences(chapter)}
        shown = [
            pictures[source]["file"]
            for source, _ in _images(chapter.read_text(encoding="utf-8"))
            if source in pictures
        ]
        assert shown
        missing = [
            file for file in shown if (GALLERY / file).read_text(encoding="utf-8") not in texts
        ]
        assert missing == []

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_try_it_opens_every_example_of_its_group(self, chapter: Path):
        linked = EXAMPLE_LINK.findall(_part(chapter, "Try it"))
        expected = [entry["file"] for entry in _members(_group_of(chapter))]
        assert sorted(set(linked)) == sorted(expected)

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_every_playground_link_opens_an_example(self, chapter: Path):
        files = {entry["file"] for entry in ENTRIES}
        linked = EXAMPLE_LINK.findall(chapter.read_text(encoding="utf-8"))
        assert [file for file in linked if file not in files] == []

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_it_checks_its_documents(self, chapter: Path):
        checks = [
            command
            for fence in fences(chapter)
            if fence.language == "bash" and fence.line > _line_of(chapter, "Check it")
            for command in commands(fence.text)
            if command.words[:1] == ["check"]
        ]
        assert checks, "a `scenet check` step"

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_it_links_the_language_reference(self, chapter: Path):
        links = LANGUAGE_LINK.findall(chapter.read_text(encoding="utf-8"))
        assert links
        for page, anchor in links:
            assert (LANGUAGE / f"{page}.md").is_file(), page
            if anchor:
                assert anchor in myst.anchors(LANGUAGE / f"{page}.md"), f"{page}.md#{anchor}"

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_it_links_the_diagnostics(self, chapter: Path):
        links = DIAGNOSTIC_LINK.findall(chapter.read_text(encoding="utf-8"))
        assert links
        assert [link for link in links if link not in RULES and link not in COMPILE_NOTES] == []


def _line_of(chapter: Path, part: str) -> int:
    """The line, counted from 1, of the heading a part starts at."""
    for heading in myst.headings(chapter.read_text(encoding="utf-8")):
        if heading.level == 2 and heading.text.startswith(part):
            return heading.line + 1
    raise AssertionError(f"{chapter.name} has no part {part!r}")


class TestWhatAChapterSaysAppears:
    def test_the_chapters_show_output(self):
        assert transcripts(CHAPTERS)

    @pytest.mark.parametrize(
        "transcript", transcripts(CHAPTERS), ids=[found.where for found in transcripts(CHAPTERS)]
    )
    def test_it_is_what_the_commands_print(self, transcript: Transcript):
        assert run_transcript(transcript) == transcript.output


def _documents(chapter: Path) -> list[Any]:
    """Every YAML document a chapter shows, parsed."""
    return [
        yaml.safe_load(fence.text)
        for fence in fences(chapter)
        if fence.language == "yaml" and fence.text.strip()
    ]


@cache
def _written() -> set[str]:
    """Every key written in any chapter's documents, at any depth."""
    return {
        key for chapter in CHAPTERS for document in _documents(chapter) for key in _keys(document)
    }


@cache
def _top_level() -> set[str]:
    return {
        str(key)
        for chapter in CHAPTERS
        for document in _documents(chapter)
        if isinstance(document, dict)
        for key in document
    }


@cache
def _linked() -> set[tuple[str, str]]:
    """Every card a chapter links, as its page and its anchor: a page alone is its title."""
    found: set[tuple[str, str]] = set()
    for chapter in CHAPTERS:
        for page, anchor in LANGUAGE_LINK.findall(chapter.read_text(encoding="utf-8")):
            found.add((page, anchor or page))
    return found


#: The keys the tour must introduce: every key of a panel or a scene, and the top-level keys
#: of the two files a document can name beside it, a puppet and an artwork contract.
MAJOR = sorted(
    name
    for name, card in CARDS.items()
    if card.family == "document" or (card.owner in ("Puppet", "Artwork") and "." not in name)
)


#: The blocks a document opens with: a panel's, a scene's, a puppet file's and a contract's.
TOP_LEVEL = frozenset(
    {
        "panel",
        "camera",
        "setting",
        "cast",
        "staging",
        "script",
        "description",
        "lettering",
        "direction",
        "palette",
        "panels",
        "page",
        "pages",
    }
    | {name for name in MAJOR if CARDS[name].family != "document"}
)


class TestTheTourIntroducesTheWholeLanguage:
    def test_every_block_is_a_card(self):
        assert sorted(TOP_LEVEL - {card.name for card in CARDS.values()}) == []

    @pytest.mark.parametrize("name", MAJOR)
    def test_a_chapter_writes_it(self, name: str):
        card = CARDS[name]
        if name in TOP_LEVEL:
            assert card.key in _top_level(), f"no chapter's document writes `{name}`"
        else:
            assert card.key in _written(), f"no chapter's document writes `{name}`"

    @pytest.mark.parametrize("name", MAJOR)
    def test_a_chapter_links_its_card(self, name: str):
        card = CARDS[name]
        assert (card.page, card.anchor) in _linked(), f"no chapter links the card of `{name}`"
