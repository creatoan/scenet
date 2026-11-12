"""Learn Scenet from Python: the developer's track, five chapters in the same shape (#322).

The author's tour teaches the language; this track teaches the library, from `pip install
scenet` to Scenet inside a program of the reader's own. So:

- **its chapters are the five the issue names**, in order, each under `docs/tutorial/python/`;
- **every chapter has the same parts**, in order: what you will build; then its examples;
  what you learned; and where to go next;
- **every example is a complete script with its output**: each `python` block imports what
  it uses, runs alone in a folder holding what the page made so far, and is followed by a
  `text` block holding exactly what it prints (`tests/python_examples.py` runs them so,
  through Sybil);
- **every `scenet` line a chapter shows is run**, and what it is shown printing, if anything,
  is what it prints, as in the author's tour;
- **the track calls every public `compile_*` and `render_*` function**, and links each one's
  page in the Python reference;
- **every link into the Python reference resolves**, and every chapter has some.
"""

import ast
import re
from pathlib import Path

import pytest

import scenet
from tests import myst
from tests.doc_examples import fences
from tests.python_examples import (
    TRACK,
    TrackPythonCodeBlockParser,
    in_the_track,
    run_python,
    scripts,
)
from tests.shell_examples import commands, run_transcript, transcripts
from tests.test_doc_examples import _root_conftest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
API = DOCS / "reference" / "api"

#: The track's chapters, by title, in order: the five parts of the issue.
TITLES = (
    "Compile and render",
    "Read what it decided",
    "Errors and notes",
    "Bring your own",
    "Outputs, batch and CI",
)

#: The parts of a chapter, as its `##` headings, in order. Its examples come between.
PARTS = ("What you will build", "What you learned", "Where to go next")

#: A link from a chapter into the Python reference: the page, under `docs/reference/api/`.
API_LINK = re.compile(r"\]\(\.\./\.\./reference/api/([\w/.-]+\.md)(?:#([\w-]+))?\)")

#: The functions the track must call and link: every compile and every renderer.
ENTRY_POINTS = sorted(name for name in scenet.__all__ if name.startswith(("compile_", "render")))


def chapters() -> list[Path]:
    """The chapters, in the order the track's table of contents lists them."""
    index = (TRACK / "index.md").read_text(encoding="utf-8")
    toctree = re.search(r"```\{toctree\}\n(.*?)```", index, re.DOTALL)
    assert toctree, "the track has a table of contents"
    names = [
        line.strip()
        for line in toctree.group(1).splitlines()
        if line.strip() and not line.startswith(":")
    ]
    return [TRACK / f"{name}.md" for name in names]


CHAPTERS = chapters()
IDS = [chapter.stem for chapter in CHAPTERS]


def _title(page: Path) -> str:
    (title,) = [h.text for h in myst.headings(page.read_text(encoding="utf-8")) if h.level == 1]
    return title


def _calls(page: Path) -> set[str]:
    """Every name a page's Python calls, as `name(...)` or `module.name(...)`."""
    called: set[str] = set()
    for fence in fences(page):
        if fence.language != "python":
            continue
        for node in ast.walk(ast.parse(fence.text)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
    return called


class TestTheTrackIsFiveChapters:
    def test_the_five_chapters_in_order(self):
        assert [_title(chapter) for chapter in CHAPTERS] == list(TITLES)

    def test_every_page_of_the_track_is_a_chapter(self):
        pages = {path for path in TRACK.glob("*.md") if path.name != "index.md"}
        assert pages == set(CHAPTERS)

    def test_the_tutorial_leads_to_it(self):
        index = (DOCS / "tutorial" / "index.md").read_text(encoding="utf-8")
        assert "python/index" in index

    def test_the_how_to_for_a_library_leads_to_it(self):
        howto = (DOCS / "howto" / "use_as_a_library.md").read_text(encoding="utf-8")
        assert "../tutorial/python/index.md" in howto


class TestEveryChapterHasItsParts:
    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_its_parts_in_order(self, chapter: Path):
        headings = [
            h.text for h in myst.headings(chapter.read_text(encoding="utf-8")) if h.level == 2
        ]
        found = [part for heading in headings for part in PARTS if heading.startswith(part)]
        assert found == list(PARTS)
        assert headings[0].startswith(PARTS[0])
        assert headings[-1].startswith(PARTS[-1])
        assert len(headings) > len(PARTS), "examples between what you build and what you learned"

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_every_example_shows_what_it_prints(self, chapter: Path):
        shown = scripts(chapter)
        assert shown, "a complete example"
        assert [found.where for found in shown if not found.output] == []

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_it_links_the_python_reference(self, chapter: Path):
        links = API_LINK.findall(chapter.read_text(encoding="utf-8"))
        assert links
        for page, anchor in links:
            assert (API / page).is_file(), page
            if anchor:
                assert anchor in myst.anchors(API / page), f"{page}#{anchor}"

    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_where_to_go_next_links_somewhere(self, chapter: Path):
        sections = {
            section.heading.text: section.text
            for section in myst.sections(chapter.read_text(encoding="utf-8"))
            if section.heading.level == 2
        }
        (next_part,) = [text for heading, text in sections.items() if heading.startswith(PARTS[-1])]
        assert "](" in next_part


class TestTheTrackCoversEveryEntryPoint:
    @pytest.mark.parametrize("name", ENTRY_POINTS)
    def test_a_chapter_calls_it(self, name: str):
        assert any(name in _calls(chapter) for chapter in CHAPTERS), f"no chapter calls {name}"

    @pytest.mark.parametrize("name", ENTRY_POINTS)
    def test_a_chapter_links_its_reference(self, name: str):
        linked = {
            page for chapter in CHAPTERS for page, _ in API_LINK.findall(chapter.read_text("utf-8"))
        }
        assert f"public/{name}.md" in linked, f"no chapter links the reference of {name}"


class TestWhatAChapterSaysAppears:
    @pytest.mark.parametrize("chapter", CHAPTERS, ids=IDS)
    def test_what_it_says_a_command_prints_is_what_it_prints(self, chapter: Path):
        """As in the author's tour: a `text` block right after a `bash` block is its output."""
        for transcript in transcripts([chapter]):
            assert run_transcript(transcript) == transcript.output, transcript.where

    def test_every_chapter_that_runs_a_command_checks_it(self):
        """A `scenet` line is run for its status, under `tests/shell_examples.py`."""
        ran = [
            chapter
            for chapter in CHAPTERS
            for fence in fences(chapter)
            if fence.language == "bash" and commands(fence.text)
        ]
        assert ran

    def test_the_suite_runs_the_tracks_python_as_scripts(self):
        """Through Sybil, each block of the track is run and its output compared."""
        collect = _root_conftest().pytest_collect_file
        (sybils,) = [cell.cell_contents for cell in collect.__closure__]
        (sybil,) = sybils
        assert any(isinstance(parser, TrackPythonCodeBlockParser) for parser in sybil.parsers)
        assert all(in_the_track(chapter) for chapter in CHAPTERS)


class TestAnExampleRunsAsAScript:
    """What `tests/python_examples.py` promises of the track's blocks."""

    def test_it_starts_from_nothing(self):
        with pytest.raises(NameError):
            run_python("print(scenet)", CHAPTERS[0], 1)

    def test_it_finds_the_files_the_page_showed(self):
        first = next(fence for fence in fences(CHAPTERS[0]) if fence.caption)
        source = f"from pathlib import Path\nprint(Path({first.caption!r}).is_file())\n"
        assert run_python(source, CHAPTERS[0], first.line + 1) == "True\n"

    def test_it_writes_nothing_beside_the_documentation(self, tmp_path: Path):
        before = sorted(path.name for path in ROOT.iterdir())
        run_python("from pathlib import Path\nPath('left.txt').write_text('x')\n", CHAPTERS[0], 1)
        assert sorted(path.name for path in ROOT.iterdir()) == before
