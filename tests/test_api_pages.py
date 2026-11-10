"""The Python reference has a page for every public name, and the pages are current.

`scripts/build_api_pages.py` writes them: a header card for each name -- its import line,
where it is defined, what to install, the release it appeared in, how stable it is --
then its autodoc entry. These tests regenerate every page and fail on any difference, so a
page cannot go stale, and fail on a public name without a page or a "since".
"""

import importlib.util
import inspect
import re
import runpy
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import scenet
import scenet.core

ROOT = Path(__file__).resolve().parents[1]
REGENERATE = "run `uv run python scripts/build_api_pages.py`"


def _load_generator() -> ModuleType:
    """Import `scripts/build_api_pages.py`, which is a script rather than a package module."""
    path = ROOT / "scripts" / "build_api_pages.py"
    spec = importlib.util.spec_from_file_location("build_api_pages", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_api_pages"] = module
    spec.loader.exec_module(module)
    return module


pages = _load_generator()


def _next_minor() -> str:
    major, minor, *_ = scenet.__version__.split(".")
    return f"{major}.{int(minor) + 1}"


class TestCommittedPages:
    def test_every_committed_page_matches_a_fresh_build(self):
        for path, content in pages.committed_files().items():
            assert path.is_file(), f"{path.relative_to(ROOT)} is missing: {REGENERATE}"
            assert path.read_bytes() == content, f"{path.relative_to(ROOT)} is stale: {REGENERATE}"

    def test_no_page_is_left_over(self):
        expected = set(pages.committed_files())
        leftover = [p for p in pages.PUBLIC.rglob("*") if p.is_file() and p not in expected]
        assert leftover == [], REGENERATE

    def test_generation_is_deterministic(self):
        assert pages.committed_files() == pages.committed_files()

    def test_no_two_pages_differ_only_in_case(self):
        """A case-insensitive file system, as Windows' and macOS's are, would merge them."""
        stems = [spec.stem.lower() for spec in pages.pages()]
        assert len(stems) == len(set(stems))


class TestEveryPublicName:
    def test_has_one_entry(self):
        documented = [name for spec in pages.pages() for name in spec.names]
        public = [name for name in documented if name in scenet.__all__]
        assert sorted(public) == sorted(scenet.__all__)
        assert len(public) == len(set(public))

    def test_has_a_since(self):
        """Add a name to `since.toml` with the next minor version: it ships in that one."""
        known = pages.since()
        missing = [name for name in scenet.__all__ if name not in known]
        assert missing == [], (
            f"add each to [since] in docs/reference/api/since.toml as "
            f'"{_next_minor()}", the release it will ship in: {missing}'
        )

    def test_and_since_names_nothing_else(self):
        assert sorted(set(pages.since()) - set(scenet.__all__)) == []

    @pytest.mark.parametrize("name", scenet.__all__)
    def test_since_is_a_minor_version_no_later_than_the_next(self, name: str):
        version = pages.since()[name]
        assert re.fullmatch(r"\d+\.\d+", version), version
        assert _tuple(version) <= _tuple(_next_minor())

    @pytest.mark.parametrize("name", scenet.__all__)
    def test_has_a_card(self, name: str):
        card = pages.card(name)
        for row in ("Import", "Defined in", "Install", "Since", "Stability"):
            assert f"| {row} |" in card, (name, row)
        assert f"`from scenet import {name}`" in card
        assert f"| Since | {pages.since()[name]} |" in card

    def test_its_card_links_its_source(self):
        card = pages.card("compile_source")
        assert "{py:mod}`scenet.pipeline`" in card
        assert f"({pages.SOURCE}scenet/pipeline.py)" in card


class TestParametersAddedLater:
    def test_each_is_a_parameter_of_a_public_function(self):
        for key in pages.parameters_since():
            function, _, parameter = key.partition(".")
            assert function in scenet.__all__, key
            assert parameter in inspect.signature(getattr(scenet, function)).parameters, key

    def test_each_is_later_than_its_function(self):
        for key, version in pages.parameters_since().items():
            function = key.partition(".")[0]
            assert _tuple(version) > _tuple(pages.since()[function]), key

    def test_each_is_marked_on_its_page(self):
        for key, version in pages.parameters_since().items():
            function, _, parameter = key.partition(".")
            (page,) = [spec for spec in pages.pages() if function in spec.names]
            text = pages.page(page)
            assert f".. versionadded:: {version}\n      The ``{parameter}`` parameter." in text


class TestGroups:
    def test_they_are_all_of_all_in_order(self):
        names = [name for group in pages.groups() for name in group.names]
        assert names == list(scenet.__all__)

    def test_each_is_named(self):
        assert all(group.title for group in pages.groups())

    def test_at_a_glance_lists_every_public_name(self):
        glance = pages.at_a_glance()
        missing = [name for name in scenet.__all__ if f"[`{name}`](public/" not in glance]
        assert missing == []

    def test_every_page_is_in_its_toctree(self):
        glance = pages.at_a_glance()
        assert all(f"\npublic/{spec.stem}\n" in glance for spec in pages.pages())

    def test_enumerations_share_a_page_and_functions_do_not(self):
        by_name = {name: spec for spec in pages.pages() for name in spec.names}
        assert len(by_name["compile_source"].names) == 1
        assert len(by_name["PanelCore"].names) == 1
        assert "ShotType" in by_name["Facing"].names
        assert by_name["ScenetError"] is by_name["RenderError"]


class TestTheTypesTheApiReturns:
    def test_the_core_types_have_a_page(self):
        (core,) = [spec for spec in pages.pages() if spec.stem == "core-types"]
        assert {"CoreActor", "CoreBalloon", "CoreFrame"} <= set(core.names)

    def test_their_card_imports_them_from_scenet_core(self):
        card = pages.card("CoreActor")
        assert "`from scenet.core import CoreActor`" in card
        assert "| Since |" not in card


# ---------------------------------------------------------------- what the build does


@pytest.fixture(scope="module")
def conf() -> dict[str, Any]:
    return runpy.run_path(str(ROOT / "docs" / "conf.py"))


class TestModulePages:
    """A module page documents the internals: what a public page does not."""

    def test_a_public_name_is_left_off(self, conf: dict[str, Any]):
        skip = conf["_api_members_only"]
        assert skip(None, "module", "compile_source", scenet.compile_source, False, {}) is True

    def test_so_is_a_core_type(self, conf: dict[str, Any]):
        from scenet.core import CoreActor  # noqa: PLC0415 -- not public, only documented

        assert conf["_api_members_only"](None, "module", "CoreActor", CoreActor, False, {}) is True

    def test_an_internal_name_is_kept(self, conf: dict[str, Any]):
        from scenet.pipeline import DOCUMENT_LOADERS  # noqa: PLC0415

        keep = conf["_api_members_only"]
        assert keep(None, "module", "DOCUMENT_LOADERS", DOCUMENT_LOADERS, False, {}) is None

    def test_a_method_of_a_public_class_is_kept(self, conf: dict[str, Any]):
        actor = scenet.PanelCore.actor
        assert conf["_api_members_only"](None, "class", "actor", actor, False, {}) is None


class TestSourceLinks:
    def test_a_release_links_its_tag(self, conf: dict[str, Any]):
        moved = conf["_source_at"]("0.13.0", f"{pages.SOURCE}scenet/pipeline.py")
        assert moved == "https://github.com/creatoan/scenet/blob/v0.13.0/src/scenet/pipeline.py"

    def test_dev_links_main(self, conf: dict[str, Any]):
        link = f"{pages.SOURCE}scenet/pipeline.py"
        assert conf["_source_at"]("dev", link) == link

    def test_another_link_is_left_alone(self, conf: dict[str, Any]):
        link = "https://github.com/creatoan/scenet/blob/main/CHANGELOG.md"
        assert conf["_source_at"]("0.13.0", link) == link


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class TestThePanelCoreFieldTable:
    """`docs/reference/panel_core.md` has a table of every field, made from the models."""

    @pytest.mark.parametrize("model", ["PanelCore", "PageCore"])
    def test_every_field_is_a_row(self, model: str):
        table = pages.field_table(getattr(scenet.core, model))
        for field in getattr(scenet.core, model).model_fields:
            assert f"| `{field}` |" in table, field

    def test_every_row_says_what_it_holds(self):
        table = pages.field_table(scenet.core.PanelCore)
        empty = [row for row in table.splitlines()[2:] if row.rstrip().endswith("|  |")]
        assert empty == []

    def test_the_page_carries_it(self):
        text = pages.PANEL_CORE.read_text(encoding="utf-8")
        assert pages.field_table(scenet.core.PanelCore) in text
