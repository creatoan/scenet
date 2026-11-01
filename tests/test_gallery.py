"""Every example the playground offers must actually compile.

The playground's gallery is not a list of strings inside a TypeScript file. It is these
files, compiled here, and served to the browser at build time. So an example that stops
working fails the build rather than greeting the first visitor with a stack trace.

That also makes the gallery a coverage instrument in its own right: between them these
files exercise every shot type, every camera angle, every balloon kind, every placement
zone, every predicate and both frontends. A construct that no example uses is a
construct nobody has looked at.
"""

import contextlib
import hashlib
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from fontTools.ttLib import TTFont

from scenet import (
    BalloonKind,
    CaptionKind,
    compile_book_file,
    compile_document,
    default_library,
    pipeline,
    render,
    render_debug,
    render_strip,
)
from scenet.diagnostics import RULES, diagnose_file, diagnose_script, diagnose_source
from scenet.images import MediaType, measure
from scenet.ir import PanelIR, Predicate, SayEvent
from scenet.pipeline import DOCUMENT_LOADERS, Book
from scenet.safe_yaml import load
from scenet.schema import panel_schema, scene_schema
from tests.written import Written, read, read_file, union, vocabulary

ROOT = Path(__file__).parent.parent
GALLERY = ROOT / "examples" / "gallery"
DOCS = ROOT / "docs"
MANIFEST_PATH = GALLERY / "manifest.yaml"
MANIFEST = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
ENTRIES = MANIFEST["examples"]
IDS = [entry["file"] for entry in ENTRIES]
TOUR = "38-tour.scene.yaml"

#: The longest title the gallery's menu shows whole, at a phone's width as at a desk.
MAX_TITLE = 28
#: A summary is one sentence under the editor, not a paragraph.
MAX_SUMMARY = 160


class TestManifestMatchesDisk:
    def test_every_listed_file_exists(self):
        missing = [entry["file"] for entry in ENTRIES if not (GALLERY / entry["file"]).is_file()]
        assert missing == []

    def test_every_file_is_listed(self):
        on_disk = {
            path.name for path in GALLERY.iterdir() if path.is_file() and path != MANIFEST_PATH
        }
        assert on_disk == {entry["file"] for entry in ENTRIES}

    def test_every_file_an_example_names_is_there(self):
        """A picture an example is drawn over is listed beside it, so the tools that copy
        the gallery -- the spec pack, the playground -- copy the picture with it."""
        named = [name for entry in ENTRIES for name in entry.get("files", [])]
        assert [name for name in named if not (GALLERY / name).is_file()] == []

    def test_every_asset_is_named_by_an_example(self):
        named = {name for entry in ENTRIES for name in entry.get("files", [])}
        on_disk = {
            path.relative_to(GALLERY).as_posix()
            for path in GALLERY.rglob("*")
            if path.is_file() and path.parent != GALLERY
        }
        assert on_disk == named

    def test_only_documents_sit_at_the_top(self):
        """Pictures go in a folder, so every file beside the manifest is a document."""
        top = [path for path in GALLERY.iterdir() if path.is_file() and path != MANIFEST_PATH]
        assert all(path.name.endswith((".panel.yaml", ".scene.yaml", ".script")) for path in top)

    def test_every_entry_has_a_title(self):
        assert all(entry["title"].strip() for entry in ENTRIES)

    def test_kinds_are_known(self):
        assert {entry["kind"] for entry in ENTRIES} <= {"panel", "scene", "script"}

    def test_no_file_is_listed_twice(self):
        """A `#example=` link finds an entry by its file, so a file is one entry."""
        assert len(IDS) == len(set(IDS))


def _slug(heading: str) -> str:
    """A heading's anchor as MyST makes it, by the rule `mdit_py_plugins.anchors` applies.

    Less its range of CJK ideographs, which no page here has.
    """
    return re.sub(r"[^\w\- ]", "", heading.strip().lower().replace(" ", "-"))


def _anchors(page: Path) -> set[str]:
    """The anchors a page has: its headings down to `###`, as `myst_heading_anchors` sets.

    A `#` line inside a fenced block is a comment in an example, not a heading.
    """
    anchors: set[str] = set()
    fenced = False
    for line in page.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (match := re.match(r"(#{1,3}) (.+)", line)):
            anchors.add(_slug(match.group(2)))
    return anchors


class TestTheGalleryIsGuided:
    """The playground walks the gallery as a tutorial (#237): by theme, from a tour, with a
    sentence on each example and a link to the page that explains it."""

    def test_the_groups_are_named_once_each(self):
        groups = MANIFEST["groups"]
        assert groups, "the gallery is offered by theme"
        assert all(isinstance(group, str) and group.strip() for group in groups)
        assert len(groups) == len(set(groups))

    def test_every_entry_is_in_a_known_group(self):
        groups = set(MANIFEST["groups"])
        assert [entry["file"] for entry in ENTRIES if entry.get("group") not in groups] == []

    def test_every_group_has_an_entry(self):
        used = {entry["group"] for entry in ENTRIES}
        assert [group for group in MANIFEST["groups"] if group not in used] == []

    def test_the_gallery_starts_on_the_tour(self):
        """The playground opens on it and lists it first: first in the first group."""
        assert MANIFEST["start"] == TOUR
        (start,) = [entry for entry in ENTRIES if entry["file"] == MANIFEST["start"]]
        assert start["group"] == MANIFEST["groups"][0]

    @pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
    def test_the_title_is_short(self, entry: dict[str, str]):
        """The long explanation is the file's leading comment; the title is a name."""
        assert len(entry["title"]) <= MAX_TITLE, entry["title"]

    @pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
    def test_the_summary_is_one_sentence(self, entry: dict[str, str]):
        summary = entry["summary"]
        assert summary == summary.strip()
        assert 0 < len(summary) <= MAX_SUMMARY, summary
        assert summary.endswith(".")
        assert ". " not in summary, "one sentence"

    @pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
    def test_the_doc_target_exists(self, entry: dict[str, str]):
        """'Read about it' goes to a page of the documentation, and to a heading on it."""
        page, _, anchor = entry["doc"].partition("#")
        assert page.endswith(".md")
        assert not page.startswith(("/", ".")), "relative to docs/"
        path = DOCS / page
        assert path.is_file(), page
        if anchor:
            assert anchor in _anchors(path), f"{page} has no heading #{anchor}"

    def test_the_slug_is_mysts(self):
        assert _slug("`page` and `pages`") == "page-and-pages"
        assert _slug("An image behind the cast") == "an-image-behind-the-cast"
        assert _slug("Reading order is enforced, not suggested") == (
            "reading-order-is-enforced-not-suggested"
        )


class TestTheTour:
    """The example the playground opens on shows, on one page and in colour, what Scenet
    letters: a picture behind posed puppets, the figures a picture draws, and every kind of
    thing it letters. And it says nothing it would then have to explain."""

    @staticmethod
    def _book():
        return compile_book_file(GALLERY / TOUR)

    def test_it_is_one_page(self):
        assert len(self._book().pages) == 1

    def test_it_has_nothing_to_note(self):
        book = self._book()
        assert book.notes == ()
        assert {name: result.notes for name, result in book.panels.items() if result.notes} == {}
        assert diagnose_file(GALLERY / TOUR) == []

    def test_it_letters_over_a_supplied_picture_and_its_figures(self):
        cores = [result.core for result in self._book().panels.values()]
        over_a_picture = [
            core for core in cores if core.backdrop is not None and core.backdrop.image is not None
        ]
        assert any(core.actors for core in over_a_picture), "posed puppets before a picture"
        assert any(figure.actor for core in cores for figure in core.figures), "a cast figure"

    def test_it_letters_everything(self):
        book = self._book()
        cores = [result.core for result in book.panels.values()]
        assert CaptionKind.LOCALE in {caption.kind for core in cores for caption in core.captions}
        kinds = {balloon.kind for core in cores for balloon in core.balloons}
        assert {BalloonKind.SPEECH, BalloonKind.THOUGHT} <= kinds
        assert any(actor.marks for core in cores for actor in core.actors), "emanata"
        assert any(core.sfx for core in cores), "a sound effect"
        assert any(frame.inset_of for frame in book.pages[0].frames), "an inset"


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
class TestEveryExampleWorks:
    def test_it_compiles(self, entry: dict[str, str]):
        results = compile_document(GALLERY / entry["file"])
        assert results, "a document that compiles to no panels is not an example of anything"

    def test_every_renderer_accepts_it(self, entry: dict[str, str]):
        results = compile_document(GALLERY / entry["file"])
        # A font the document names is handed over, as `scenet build` hands it over.
        fonts = {
            digest: font for result in results.values() for digest, font in result.fonts.items()
        }
        for result in results.values():
            assert render(result.core, fonts=fonts).lstrip().startswith("<?xml")
            assert render_debug(result.core).lstrip().startswith("<?xml")
        strip = render_strip([(name, result.core) for name, result in results.items()], fonts=fonts)
        assert strip.lstrip().startswith("<?xml")

    def test_it_is_deterministic(self, entry: dict[str, str]):
        first = compile_document(GALLERY / entry["file"])
        second = compile_document(GALLERY / entry["file"])
        assert [r.core.to_json() for r in first.values()] == [
            r.core.to_json() for r in second.values()
        ]

    def test_the_kind_in_the_manifest_is_right(self, entry: dict[str, str]):
        name = entry["file"]
        expected = (
            "script"
            if name.endswith(".script")
            else "scene"
            if name.endswith(".scene.yaml")
            else "panel"
        )
        assert entry["kind"] == expected


#: Every document of the gallery: the files beside the manifest.
DOCUMENTS = sorted(path for path in GALLERY.iterdir() if path.is_file() and path != MANIFEST_PATH)

#: Everything the two published schemas let a document write.
VOCABULARY = vocabulary(panel_schema()) | vocabulary(scene_schema())

#: What the schemas offer that no example could write, and why, by the name a failure gives
#: it. Empty: everything they offer today can be written. An entry that an example writes,
#: or the schemas drop, fails `test_the_allow_list_is_current`.
NOT_AUTHORABLE: dict[str, str] = {}

#: The removals the documentation teaches, and where. A `null` is not a word of the
#: schemas' -- written anywhere it may just leave a default as it is -- so they are listed.
REMOVALS = {
    "document.cast.*": "howto/compile_a_sequence.md#leaving-something-out",
    "document.camera": "reference/language.md#figures-the-picture-draws",
    "SettingSpec.place": "reference/language.md#place",
    "CastMember.reference": "reference/language.md#figures-the-picture-draws",
}


@cache
def _written() -> Written:
    return union(read_file(path) for path in DOCUMENTS)


@cache
def _book(name: str) -> Book:
    return compile_book_file(GALLERY / name)


def _missing(offered: frozenset[str], written: set[str]) -> list[str]:
    return sorted(offered - written - NOT_AUTHORABLE.keys())


class TestTheGalleryCoversTheLanguage:
    """Every construct of the language is written in some example (#239).

    Read against the published schemas, never as text: a word in a comment is not a
    construct, and `center` in `at: center` is not a span. A key the language gains, or a
    value, fails here until an example writes it. What no schema can say -- a puppet's
    poses, a removal, a second page -- is checked from what the examples compile to.
    """

    def test_every_property_is_written(self):
        assert _missing(VOCABULARY.properties, _written().properties) == []

    def test_every_enum_value_is_written(self):
        assert _missing(VOCABULARY.values, _written().values) == []

    def test_every_form_is_written(self):
        """A key written in more than one shape -- `off_panel` as `true` or as a side, a
        font as one file or as faces -- is written in each."""
        assert _missing(VOCABULARY.forms, _written().forms) == []

    def test_every_signed_number_is_written_both_ways(self):
        """A turn, an arc or a slant may lean either way, and is shown leaning both."""
        signs = frozenset(
            f"{place} {side} zero" for place in VOCABULARY.signed for side in ("above", "below")
        )
        assert _missing(signs, _written().signs) == []

    def test_every_removal_the_docs_teach_is_written(self):
        assert sorted(set(REMOVALS) - _written().nulls) == []

    def test_the_allow_list_is_current(self):
        offered = VOCABULARY.properties | VOCABULARY.values | VOCABULARY.forms
        written = _written()
        for name in NOT_AUTHORABLE:
            assert name in offered, f"{name} is not in the schemas any more"
            assert name not in written.properties | written.values | written.forms, name

    def test_every_pose_and_expression_of_every_puppet_is_drawn(self):
        """Per puppet: a face looked at on Alice has not been looked at on Bob."""
        drawn = {
            (actor.reference, shown)
            for name in IDS
            for result in _book(name).panels.values()
            for actor in result.core.actors
            for shown in (f"pose {actor.pose}", f"expression {actor.expression}")
        }
        library = default_library()
        declared = {
            (name, shown)
            for name in library.names()
            for shown in [
                *(f"pose {pose}" for pose in library.get(name).poses),
                *(f"expression {face}" for face in library.get(name).expressions),
            ]
        }
        assert sorted(declared - drawn) == []

    def test_a_document_has_more_than_one_page(self):
        """Pages side by side, as `scenet build` and the playground draw them."""
        assert any(len(_book(name).pages) > 1 for name in IDS)

    def test_somebody_looks_at_a_voice_from_off_panel(self):
        def looks(panel: PanelIR) -> bool:
            heard = {
                event.by
                for event in panel.script
                if isinstance(event, SayEvent) and event.off_panel is not False
            }
            return any(
                relation.predicate is Predicate.LOOKING_AT and relation.object in heard
                for relation in panel.staging
            )

        panels = [
            panel
            for path in DOCUMENTS
            for panel in DOCUMENT_LOADERS[path.suffix](path).panels.values()
        ]
        assert any(looks(panel) for panel in panels)

    def test_a_sound_is_pulled_toward_a_zone_from_its_source(self):
        assert any(
            owner == "SfxEvent" and {"from", "prefer"} <= keys
            for owner, keys in _written().mappings
        )

    def test_every_picture_format_is_supplied(self):
        """PNG and JPEG, told apart as the compiler tells them: by their first bytes."""
        named = {name for entry in ENTRIES for name in entry.get("files", [])}
        kinds: set[str] = set()
        for name in named:
            with contextlib.suppress(ValueError):
                kinds.add(measure((GALLERY / name).read_bytes())[0])
        assert kinds == set(get_args(MediaType))

    def test_both_frontends_appear(self):
        names = [entry["file"] for entry in ENTRIES]
        assert any(name.endswith(".script") for name in names)
        assert any(name.endswith(".panel.yaml") for name in names)
        assert any(name.endswith(".scene.yaml") for name in names)

    def test_the_setting_examples_actually_draw_something(self):
        """The examples claim to show masses. Check they resolve to some, rather than
        trusting a comment that may have outlived the behaviour it describes."""
        for name in ("19-setting.scene.yaml", "20-places.scene.yaml"):
            for panel, result in compile_document(GALLERY / name).items():
                assert result.core.backdrop is not None, f"{name}:{panel}"
                assert result.core.backdrop.masses, f"{name}:{panel}"

    def test_the_atmosphere_example_actually_has_weather(self):
        """One panel of it is `clear`, which must resolve to no atmosphere at all --
        that is the case most easily broken by making weather unconditional."""
        results = compile_document(GALLERY / "21-atmosphere.scene.yaml")
        air = {
            name: result.core.backdrop.atmosphere
            for name, result in results.items()
            if result.core.backdrop is not None
        }
        assert air["noon"] is None

        midnight, winter, morning = air["midnight"], air["winter"], air["morning"]
        assert midnight is not None
        assert winter is not None
        assert morning is not None
        assert midnight.streaks
        assert winter.flecks
        assert morning.veil is not None

    def test_the_camera_pullback_example_actually_pulls_back(self):
        """The example claims the camera retreats. Check it does, rather than trusting
        a comment that may have outlived the behaviour it describes."""
        results = compile_document(GALLERY / "10-crowd-pullback.panel.yaml")
        notes = [note for result in results.values() for note in result.notes]
        assert any("camera retreated" in note for note in notes)


class TestFiguresAPictureDraws:
    """The gallery shows a cast the picture draws (#71), and it is what it claims to be."""

    def test_the_example_letters_figures_over_its_picture(self):
        for panel, result in compile_document(GALLERY / "35-figures.scene.yaml").items():
            core = result.core
            assert core.actors == (), panel
            assert {figure.actor for figure in core.figures} == {"ana", "ben", None}, panel
            assert core.backdrop is not None, panel
            assert core.backdrop.image is not None, panel
            assert core.backdrop.image.keep_out, panel
            assert result.camera is None, panel


#: The group that shows what the checker and the compiler say of a document (#240).
TELLS = "What Scenet tells you"
#: Its entries: each shows a note, and a line away from it, an error.
TOLD = [entry for entry in ENTRIES if entry.get("group") == TELLS]
TOLD_IDS = [entry["file"] for entry in TOLD]

#: How the comment over an example's last line opens, when that line, uncommented, makes
#: the example an error.
TRY_THIS = "# Try this:"


def _note_names() -> set[str]:
    """Every note there is, by the name `notes:` gives it: a check's rule, or a compile note's."""
    checks = {name for name, rule in RULES.items() if rule.level == "note"}
    return checks | set(get_args(pipeline.CompileNoteRule))


@dataclass(frozen=True)
class TryThis:
    """The line an example ends with, commented out, that makes it an error.

    Attributes:
        line: Its number, from one.
        text: The document with that line uncommented.
        rule: The error the comment over it names.
    """

    line: int
    text: str
    rule: str


def _try_this(path: Path) -> TryThis:
    """An example's try-this: the last line of its YAML, under a `# Try this:` comment.

    The last line of the document, or of a comic script's front matter: that is the only
    place a script can hold a comment, since every line of its own is read, as prose if as
    nothing else. The line is written `# ` and then exactly as it must read, indentation
    and all, so deleting the `# ` -- what Ctrl+/ does in the playground's YAML editor --
    uncomments it. The comment names the error's rule in backticks.
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    if path.suffix == ".script":
        assert lines[0] == "---", f"{path.name}: a script's try-this is in its front matter"
        last = lines.index("---", 1) - 1
    else:
        last = max(index for index, line in enumerate(lines) if line.strip())
    assert lines[last].startswith("# "), f"{path.name} does not end with a line commented out"
    first = last
    while first > 0 and lines[first - 1].startswith("#"):
        first -= 1
    comment = lines[first:last]
    opening = [index for index, line in enumerate(comment) if line.startswith(TRY_THIS)]
    assert opening, f"{path.name}: no {TRY_THIS!r} comment over its last line"
    said = " ".join(comment[opening[-1] :])
    named = {name for name in re.findall(r"`([a-z-]+)`", said) if name in RULES}
    assert len(named) == 1, f"{path.name}: its try-this names one rule, not {sorted(named)}"
    lines[last] = lines[last].removeprefix("# ")
    return TryThis(line=last + 1, text="\n".join(lines), rule=named.pop())


class TestWhatScenetTellsYou:
    """The gallery shows what the checker and the compiler say of a document (#240): every
    note there is, each in an example that declares it -- and from each, a line away, an
    error, which an example that must compile cannot show otherwise."""

    def test_the_group_is_offered(self):
        assert TELLS in MANIFEST["groups"]

    @pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
    def test_notes_names_known_notes_each_once(self, entry: dict[str, Any]):
        if "notes" not in entry:
            return
        notes = entry["notes"]
        assert isinstance(notes, list), "`notes:` is a list"
        assert notes, "an example that gives no note leaves `notes:` out"
        assert len(notes) == len(set(notes)), "a note is given or it is not: name each once"
        assert sorted(set(notes) - _note_names()) == []

    def test_every_note_is_shown_by_an_example_of_the_group(self):
        """A note the playground cannot show is a gap, and this test says so (#236)."""
        shown = {note for entry in TOLD for note in entry.get("notes", [])}
        assert sorted(_note_names() - shown) == []

    @pytest.mark.parametrize("entry", TOLD, ids=TOLD_IDS)
    def test_each_of_its_examples_gives_a_note(self, entry: dict[str, Any]):
        assert entry.get("notes")

    @pytest.mark.parametrize("entry", TOLD, ids=TOLD_IDS)
    def test_its_last_line_uncommented_is_an_error_on_that_line(self, entry: dict[str, Any]):
        """The error the comment names, and nothing but it, located where it was written:
        what the playground lists under the editor, a click away from the line."""
        path = GALLERY / entry["file"]
        trial = _try_this(path)
        diagnose = diagnose_script if path.suffix == ".script" else diagnose_source
        errors = [item for item in diagnose(trial.text, source=path) if item.level == "error"]
        assert errors, f"{path.name} still compiles with its last line uncommented"
        where = {(item.rule, item.region.start.line if item.region else 0) for item in errors}
        assert where == {(trial.rule, trial.line)}


class TestReadingATryThis:
    """The test above is only as good as `_try_this`, which finds the line to uncomment."""

    def test_in_a_document_it_is_the_last_line(self, tmp_path: Path):
        path = tmp_path / "x.panel.yaml"
        path.write_text(
            "cast: {a: {reference: alice}}\nscript:\n  - say: {by: a, text: Hi.}\n\n"
            '# Try this: delete the "# " below. B is in no cast: `unknown-actor`.\n'
            "#   - say: {by: b, text: Hi.}\n",
            encoding="utf-8",
        )
        trial = _try_this(path)
        assert (trial.line, trial.rule) == (6, "unknown-actor")
        assert trial.text.split("\n")[5] == "  - say: {by: b, text: Hi.}"

    def test_in_a_script_it_closes_the_front_matter(self, tmp_path: Path):
        path = tmp_path / "x.script"
        path.write_text(
            "---\ncast:\n  A: {reference: alice}\n"
            "# Try this: on its own line, `reflexive-relation`.\n# staging: [A left_of A]\n---\n"
            "PANEL 1\nA\nHi.\n",
            encoding="utf-8",
        )
        trial = _try_this(path)
        assert (trial.line, trial.rule) == (5, "reflexive-relation")
        assert trial.text.split("\n")[4] == "staging: [A left_of A]"

    def test_only_a_rule_is_read_from_the_comment(self, tmp_path: Path):
        path = tmp_path / "x.panel.yaml"
        path.write_text(
            "script: []\n# Try this: `fit: contain` is no rule; `syntax` is.\n# : x\n",
            encoding="utf-8",
        )
        assert _try_this(path).rule == "syntax"


class TestWhatADocumentWrites:
    """The coverage above is only as good as the reading it rests on (`tests/written.py`)."""

    @staticmethod
    def _panel(text: str) -> Written:
        return read(panel_schema(), load(text))

    def test_a_comment_writes_nothing(self):
        written = self._panel("# setting: {place: docks, time: night}\npanel: {size: [10, 10]}\n")
        assert written.values == set()
        assert written.properties == {"document.panel", "PanelSpec.size"}

    def test_a_value_counts_for_the_enum_its_place_expects(self):
        written = self._panel("cast: {a: {reference: alice, at: center}}")
        assert "AnchorX.center" in written.values
        assert "Spans.center" not in written.values

    def test_a_staging_sentence_writes_its_predicate_and_its_form(self):
        written = self._panel("staging: [a left_of b]")
        assert "Predicate.left_of" in written.values
        assert "Relation as string" in written.forms
        assert "Relation.predicate" not in written.properties

    def test_a_null_is_recorded_where_it_is_written(self):
        written = read(scene_schema(), load("panels: {a: {camera: null, cast: {bob: null}}}"))
        assert {"document.camera", "document.cast.*"} <= written.nulls

    def test_a_number_records_its_sign(self):
        written = self._panel("script: [{sfx: {text: BAM, rotate: -12, arc: 30}}]")
        assert written.signs == {"SfxEvent.rotate below zero", "SfxEvent.arc above zero"}

    def test_a_script_writes_its_front_matter_and_directives_not_its_prose(self, tmp_path: Path):
        script = tmp_path / "x.script"
        script.write_text(
            "---\ncast: {A: {reference: alice}}\n---\nPANEL 1\n@shot: wide\n"
            "@setting: {place: docks}\nThe top_left of a dark night.\n\nA\nmiddle_center!\n",
            encoding="utf-8",
        )
        written = read_file(script)
        assert {"ShotType.wide", "Place.docks"} <= written.values
        assert {"PlacementZone.top_left", "PlacementZone.middle_center"}.isdisjoint(written.values)
        assert "document.panels" not in written.properties


class TestTheGalleryFont:
    """The face `lettering.font` is shown in (#239): Comic Neue, under the SIL Open Font
    License, which lets a font travel with software when its licence travels with it.

    So the licence is beside the fonts, and every example that names a font names it too,
    which is how the playground and the skill's copy of the gallery carry it along.
    """

    FONTS = GALLERY / "fonts"

    #: The SHA-256 of each file in google/fonts at commit
    #: 3dd78844021e948ceb633d1dcee3f7885561b5d9, `ofl/comicneue/`. A different file is a
    #: different font, and needs its licence read again.
    UPSTREAM_SHA256 = {
        "ComicNeue-Bold.ttf": "3e7e5fccfd7e0788f317b43312151c1bd5cf058c9697a8d83eac3939050bd61e",
        "ComicNeue-BoldItalic.ttf": (
            "5c312c2a2fa64eee82f3b87fcfab8f3b12a5e59b043124401d322eb323cfbf16"
        ),
        "ComicNeue-Italic.ttf": "e06bfd1552f5c9464c5665733ffd69239b0593885dbb9e059688a5900f78cf98",
        "ComicNeue-Regular.ttf": "a0ee5a37c8b27c4db0700137d928598b1e23b0089e1546a8961909176b779360",
        "OFL.txt": "7c38a22e5878e60fe423360553e63dd7be23d29f1f60336034935dbfc96e8320",
    }

    def test_every_file_is_the_one_fetched_from_google_fonts(self):
        on_disk = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.FONTS.iterdir()
        }
        assert on_disk == self.UPSTREAM_SHA256

    def test_its_licence_is_the_ofl(self):
        licence = (self.FONTS / "OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in licence
        assert "The Comic Neue Project Authors" in licence

    def test_every_face_says_the_same_licence(self):
        for path in self.FONTS.glob("*.ttf"):
            name = TTFont(str(path))["name"]
            assert "SIL Open Font License, Version 1.1" in (name.getDebugName(13) or ""), path

    def test_an_example_that_names_a_font_names_its_licence(self):
        for entry in ENTRIES:
            files = entry.get("files", [])
            if any(name.startswith("fonts/") for name in files):
                assert "fonts/OFL.txt" in files, entry["file"]

    def test_the_notices_record_it(self):
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        assert "### Comic Neue" in notices
