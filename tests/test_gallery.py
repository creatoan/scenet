"""Every example the playground offers must actually compile.

The playground's gallery is not a list of strings inside a TypeScript file. It is these
files, compiled here, and served to the browser at build time. So an example that stops
working fails the build rather than greeting the first visitor with a stack trace.

That also makes the gallery a coverage instrument in its own right: between them these
files exercise every shot type, every camera angle, every balloon kind, every placement
zone, every predicate and both frontends. A construct that no example uses is a
construct nobody has looked at.
"""

import re
from pathlib import Path

import pytest
import yaml

from scenet import (
    BalloonKind,
    CameraAngle,
    CaptionKind,
    CaptionTone,
    Direction,
    Fit,
    Horizon,
    Mark,
    MassKind,
    Place,
    PlacementZone,
    Plane,
    Predicate,
    SfxSize,
    ShotType,
    Side,
    Spans,
    TimeOfDay,
    Weather,
    compile_book_file,
    compile_document,
    default_library,
    render,
    render_debug,
    render_strip,
)
from scenet.diagnostics import diagnose_file

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
        for result in results.values():
            assert render(result.core).lstrip().startswith("<?xml")
            assert render_debug(result.core).lstrip().startswith("<?xml")
        strip = render_strip([(name, result.core) for name, result in results.items()])
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


class TestTheGalleryCoversTheLanguage:
    """A construct no example demonstrates is a construct nobody is looking at."""

    @staticmethod
    def _all_text() -> str:
        return "\n".join(
            path.read_text(encoding="utf-8")
            for path in GALLERY.iterdir()
            if path.is_file() and path != MANIFEST_PATH
        )

    def test_every_shot_type_appears(self):
        text = self._all_text()
        missing = [shot.value for shot in ShotType if shot.value not in text]
        assert missing == []

    def test_every_camera_angle_appears(self):
        text = self._all_text()
        missing = [angle.value for angle in CameraAngle if angle.value not in text]
        assert missing == []

    def test_every_balloon_kind_appears(self):
        text = self._all_text()
        missing = [kind.value for kind in BalloonKind if kind.value not in text]
        assert missing == []

    def test_every_caption_kind_appears(self):
        text = self._all_text()
        missing = [kind.value for kind in CaptionKind if kind.value not in text]
        assert missing == []

    def test_every_caption_tone_appears(self):
        """A tone nobody has looked at is a tone nobody has checked reads."""
        text = self._all_text()
        missing = [tone.value for tone in CaptionTone if f"tone: {tone.value}" not in text]
        assert missing == []

    def test_every_expression_appears(self):
        """The expression vocabulary is only worth having if every face in it has been
        looked at at least once."""
        text = self._all_text()
        names = sorted(default_library().get("alice").expressions)
        missing = [name for name in names if name not in text]
        assert missing == []

    def test_every_direction_appears(self):
        """A page read right to left has been looked at beside its left-to-right twin."""
        text = self._all_text()
        missing = [value.value for value in Direction if f"direction: {value.value}" not in text]
        assert missing == []

    def test_every_type_size_appears(self):
        """Small type is read at the size it is lettered, so it has been looked at."""
        text = self._all_text()
        assert "size: small" in text

    def test_every_off_panel_side_appears(self):
        """A tail ending on each edge of the frame has been looked at, and one whose side
        the compiler chose."""
        text = self._all_text()
        missing = [side.value for side in Side if f"off_panel: {side.value}" not in text]
        assert missing == []
        assert "off_panel: true" in text

    def test_every_sound_effect_size_appears(self):
        """A size nobody has looked at is a size nobody has checked reads at a long shot."""
        text = self._all_text()
        missing = [size.value for size in SfxSize if f"size: {size.value}" not in text]
        assert missing == []

    def test_every_mark_appears(self):
        """Emanata are drawn outside the head, where balloons go, so each one is a
        layout question as well as a drawing one. Both get looked at here."""
        text = self._all_text()
        missing = [mark.value for mark in Mark if mark.value not in text]
        assert missing == []

    @pytest.mark.parametrize(
        "enum",
        [MassKind, Plane, Spans, Horizon, TimeOfDay, Weather, Place, Fit],
        ids=lambda enum: enum.__name__,
    )
    def test_every_setting_word_appears(self, enum):
        """The setting vocabulary is twelve mass kinds, four planes, four spans, three
        horizons, four hours, four weathers and ten places. A word no example uses is a
        word nobody has looked at -- and for this feature, "looked at" is literal: the
        contact sheet is the only thing that can tell whether a value reads as depth."""
        text = self._all_text()
        missing = [member.value for member in enum if member.value not in text]
        assert missing == []

    def test_every_predicate_appears(self):
        text = self._all_text()
        missing = [predicate.value for predicate in Predicate if predicate.value not in text]
        assert missing == []

    def test_the_corner_placement_zones_appear(self):
        text = self._all_text()
        corners = [
            PlacementZone.TOP_LEFT,
            PlacementZone.TOP_RIGHT,
            PlacementZone.BOTTOM_LEFT,
            PlacementZone.BOTTOM_RIGHT,
        ]
        assert all(zone.value in text for zone in corners)

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

    def test_a_figure_appears(self):
        assert "figure:" in TestTheGalleryCoversTheLanguage._all_text()

    def test_the_example_letters_figures_over_its_picture(self):
        for panel, result in compile_document(GALLERY / "35-figures.scene.yaml").items():
            core = result.core
            assert core.actors == (), panel
            assert {figure.actor for figure in core.figures} == {"ana", "ben", None}, panel
            assert core.backdrop is not None, panel
            assert core.backdrop.image is not None, panel
            assert core.backdrop.image.keep_out, panel
            assert result.camera is None, panel
