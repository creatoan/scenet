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
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "examples" / "gallery"
DIGESTS: dict[str, str] = json.loads(
    (ROOT / "tests" / "golden" / "digests.json").read_text(encoding="utf-8")
)
ENTRIES: list[dict[str, Any]] = yaml.safe_load(
    (GALLERY / "manifest.yaml").read_text(encoding="utf-8")
)["examples"]


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
    return file.split(".")[0]


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
