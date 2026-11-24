"""Language limits: every size, count and length has a bound and a finding (#363).

The language had no upper bound on anything, so one line could make the compiler allocate
without end. Each limit is one finding, rule `limit`, at the value, that says the limit.
They are constants in `scenet.limits`, the page `docs/reference/language/limits.md` lists
them, and a host may hold a document to tighter ones.
"""

import re
import time
from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from scenet import diagnostics, ir
from scenet.diagnostics import RULES, diagnose_source
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends import script_front, yaml_front
from scenet.frontends.positions import DOCUMENT_START
from scenet.frontends.script_front import parse_script
from scenet.frontends.yaml_front import parse_panel, parse_scene_document
from scenet.images import load_image
from scenet.lettering import load_font
from scenet.limits import LIMIT_RULE, LIMITS, Limits, exceeded, past
from scenet.pipeline import compile_book, compile_source
from scenet.safe_yaml import _load_fast, _ProfileLoader
from scenet.schema import panel_schema, scene_schema
from tests.images import png

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "docs" / "reference" / "language" / "limits.md"
GALLERY = ROOT / "examples" / "gallery"
CAST = "cast: {a: {reference: alice}}\n"


def _cast(count: int) -> str:
    return (
        "cast: {" + ", ".join(f"a{index}: {{reference: alice}}" for index in range(count)) + "}\n"
    )


def _panels(count: int) -> str:
    return CAST + "panels: {" + ", ".join(f"p{index}: {{}}" for index in range(count)) + "}\n"


#: The four cases of the issue's acceptance, each with the limit it is past and where.
ACCEPTANCE = {
    "a huge panel": ("panel: {size: [1e12, 1e12]}\n" + CAST, ("panel", "size", 0)),
    "ten thousand and one panels": (_panels(LIMITS.panels_per_document + 1), ("panels",)),
    "two hundred actors": (_cast(200), ("cast",)),
    "a megabyte balloon": (
        CAST + "script: [{say: {by: a, text: " + "x" * 1_000_000 + "}}]\n",
        ("script", 0, "say", "text"),
    ),
}


class TestTheAcceptance:
    @pytest.mark.parametrize(("source", "path"), list(ACCEPTANCE.values()), ids=list(ACCEPTANCE))
    def test_check_finds_it_at_the_value_in_under_a_second(
        self, source: str, path: tuple[str | int, ...]
    ):
        start = time.perf_counter()
        found = diagnose_source(source)
        took = time.perf_counter() - start
        first = found[0]
        assert (first.rule, first.path) == (LIMIT_RULE, path)
        assert first.region is not None
        assert "at most" in first.message
        assert took < 1.0, took

    @pytest.mark.parametrize(("source", "path"), list(ACCEPTANCE.values()), ids=list(ACCEPTANCE))
    def test_build_refuses_it_under_the_rule(self, source: str, path: tuple[str | int, ...]):
        with pytest.raises(PanelSyntaxError) as caught:
            compile_book(source)
        assert caught.value.rule == LIMIT_RULE

    def test_the_finding_says_the_limit_and_the_value(self):
        (first, _) = diagnose_source(ACCEPTANCE["a huge panel"][0])
        assert first.message == (
            "a panel is at most 10000 units on a side in Scenet, and this is 1e+12"
        )

    def test_the_rule_is_catalogued(self):
        assert RULES[LIMIT_RULE].level == "error"


class TestEachLimit:
    def test_a_page_side(self):
        source = (
            CAST
            + "panels: {a: {}}\npage: {size: [20000, 3000]}\npages: [{tiers: [{panels: [a]}]}]\n"
        )
        (found,) = diagnose_source(source)
        assert (found.rule, found.path) == (LIMIT_RULE, ("page", "size", 0))

    def test_a_script_too_long(self):
        events = ", ".join("{caption: {text: x}}" for _ in range(LIMITS.events_per_panel + 1))
        (found,) = diagnose_source(CAST + f"script: [{events}]\n")
        assert (found.rule, found.path) == (LIMIT_RULE, ("script",))

    def test_a_description_too_long(self):
        (found,) = diagnose_source(CAST + "description: " + "x" * 3000 + "\n")
        assert (found.rule, found.path) == (LIMIT_RULE, ("description",))

    def test_a_list_form_cast(self):
        cast = ", ".join(f"{{id: a{index}, reference: alice}}" for index in range(51))
        (found,) = diagnose_source(f"cast: [{cast}]\n")
        assert (found.rule, found.path) == (LIMIT_RULE, ("cast",))

    def test_too_many_pages(self):
        pages = ", ".join("{tiers: [{panels: [a]}]}" for _ in range(LIMITS.pages_per_document + 1))
        found = diagnose_source(CAST + f"panels: {{a: {{}}}}\npages: [{pages}]\n")
        assert (found[0].rule, found[0].path) == (LIMIT_RULE, ("pages",))

    def test_too_many_panels_on_a_page(self):
        count = LIMITS.panels_per_page + 1
        names = ", ".join(f"p{index}" for index in range(count))
        source = CAST + "panels: {" + ", ".join(f"p{i}: {{}}" for i in range(count)) + "}\n"
        source += f"pages: [{{tiers: [{{panels: [{names}]}}]}}]\n"
        found = diagnose_source(source)
        assert (found[0].rule, found[0].path) == (LIMIT_RULE, ("pages", 0))

    def test_a_document_too_large(self):
        found = diagnose_source("x-pad: '" + "x" * (LIMITS.document_bytes + 1) + "'\n")
        assert [item.rule for item in found] == [LIMIT_RULE]

    def test_a_picture_with_too_many_pixels(self):
        with pytest.raises(PanelSyntaxError) as caught:
            load_image(
                "art/big.png", {"art/big.png": png(20_000, 20_000)}, loc=("setting", "image")
            )
        assert caught.value.rule == LIMIT_RULE
        assert caught.value.loc == ("setting", "image")

    def test_a_font_too_large(self):
        """Refused by its size before it is read, as every file is, under the font's own rule."""
        with pytest.raises(PanelSyntaxError) as caught:
            load_font("fonts/big.ttf", {"fonts/big.ttf": bytes(LIMITS.font_bytes + 1)}, loc=())
        assert caught.value.rule == "font-file"
        assert "larger than 64 MiB" in str(caught.value)

    def test_a_value_at_the_limit_is_taken(self):
        assert compile_source(f"panel: {{size: [{LIMITS.panel_side:g}, 500]}}\n" + CAST).core


class TestAtTheEdge:
    """A value at a limit is taken, and one past it is refused, where it is read.

    Each with the limit tightened where it is read, so a document at it is a short one.
    """

    TEXT = "cast: {a: {reference: alice}}\n"
    SCRIPT = "PANEL 1\nA street.\n"

    @pytest.fixture
    def tight(self, monkeypatch: pytest.MonkeyPatch) -> int:
        size = len(self.TEXT.encode())
        for module in (yaml_front, diagnostics):
            monkeypatch.setattr(module, "LIMITS", Limits(document_bytes=size))
        return size

    def test_a_document_of_the_limit_is_read(self, tight: int):
        assert parse_panel(self.TEXT).cast
        assert diagnose_source(self.TEXT) == []

    def test_a_byte_more_is_refused(self, tight: int):
        source = Path("x.panel.yaml")
        with pytest.raises(PanelSyntaxError) as caught:
            parse_panel(self.TEXT + " ", source=source)
        assert (caught.value.rule, caught.value.source) == (LIMIT_RULE, source)
        assert past("document_bytes", tight + 1, tight) in str(caught.value)
        (found,) = diagnose_source(self.TEXT + " ", source=source)
        assert (found.rule, found.source, found.region) == (LIMIT_RULE, source, DOCUMENT_START)
        assert found.message == past("document_bytes", tight + 1, tight)

    def test_a_script_of_the_limit_is_read(self, monkeypatch: pytest.MonkeyPatch):
        size = len(self.SCRIPT.encode())
        monkeypatch.setattr(script_front, "LIMITS", Limits(document_bytes=size))
        assert parse_script(self.SCRIPT)
        with pytest.raises(ScriptSyntaxError) as caught:
            parse_script(self.SCRIPT + " ")
        assert caught.value.rule == LIMIT_RULE

    @pytest.mark.parametrize("count", [2, 3])
    def test_panels_up_to_the_limit_are_read(self, monkeypatch: pytest.MonkeyPatch, count: int):
        for module in (yaml_front, diagnostics):
            monkeypatch.setattr(module, "LIMITS", Limits(panels_per_document=2))
        names = ", ".join(f"p{index}: {{}}" for index in range(count))
        text, source = self.TEXT + f"panels: {{{names}}}\n", Path("x.scene.yaml")
        found = diagnose_source(text, source=source)
        if count == 2:
            assert found == []
            assert len(parse_scene_document(text).panels) == 2
            return
        assert [(item.rule, item.path, item.message) for item in found] == [
            (LIMIT_RULE, ("panels",), past("panels_per_document", 3, 2))
        ]
        with pytest.raises(PanelSyntaxError) as caught:
            parse_scene_document(text, source=source)
        error = caught.value
        assert (error.rule, error.loc, error.source) == (LIMIT_RULE, ("panels",), source)
        assert past("panels_per_document", 3, 2) in str(error)

    @pytest.mark.parametrize("count", [2, 3])
    def test_panels_on_a_page_up_to_the_limit(self, monkeypatch: pytest.MonkeyPatch, count: int):
        monkeypatch.setattr(ir, "LIMITS", Limits(panels_per_page=2))
        names = [f"p{index}" for index in range(count)]
        text = self.TEXT + "panels: {" + ", ".join(f"{name}: {{}}" for name in names) + "}\n"
        text += "pages: [{tiers: [{panels: [" + ", ".join(names) + "]}]}]\n"
        found = [(item.rule, item.path, item.message) for item in diagnose_source(text)]
        expected = [(LIMIT_RULE, ("pages", 0), past("panels_per_page", 3, 2))]
        assert found == ([] if count == 2 else expected)

    def test_a_host_limit_of_one_is_a_limit(self):
        assert Limits(panels_per_page=1).panels_per_page == 1

    def test_a_host_limit_takes_what_is_at_it(self):
        text = (
            self.TEXT + "panels: {a: {panel: {size: [500, 400]}, script: [{caption: {text: x}}]}}\n"
        )
        panels = parse_scene_document(text).panels
        at_it = Limits(
            panels_per_document=1, panel_side=500, actors_per_panel=1, events_per_panel=1
        )
        assert list(exceeded(panels, at_it)) == []
        below = Limits(
            panels_per_document=1, panel_side=499, actors_per_panel=1, events_per_panel=1
        )
        assert [found.loc for found in exceeded(panels, below)] == [
            ("panels", "a", "panel", "size")
        ]

    def test_a_host_limit_on_panels_counts_them(self):
        panels = parse_scene_document(self.TEXT + "panels: {a: {}, b: {}}\n").panels
        (found,) = exceeded(panels, Limits(panels_per_document=1))
        assert found.loc == ("panels",)

    def test_a_host_limit_on_events_and_people(self):
        two = "cast: {a: {reference: alice}, b: {reference: bob}}\n"
        text = two + "script: [{caption: {text: x}}, {caption: {text: y}}]\n"
        panels = {"one": parse_panel(text)}
        found = [
            item.loc for item in exceeded(panels, Limits(actors_per_panel=2, events_per_panel=2))
        ]
        assert found == []
        found = [
            item.loc for item in exceeded(panels, Limits(actors_per_panel=1, events_per_panel=1))
        ]
        assert found == [("panels", "one", "cast"), ("panels", "one", "script")]


class TestTheMessage:
    @pytest.mark.parametrize(
        ("value", "written"),
        [
            (200, "200"),
            (1_000_000_000, "1000000000"),
            (2.5, "2.5"),
            (1e9, "1e+09"),
            (999_999_999.0, "999999999"),
            (1e12, "1e+12"),
        ],
    )
    def test_a_number_is_written_as_it_reads(self, value: float, written: str):
        assert past("panel_side", value, 10000.0).endswith(f"and this is {written}")
        assert past("panel_side", value, 10000.0).startswith("a panel is at most 10000 units")

    def test_a_side_says_whose_it_is(self):
        page = CAST + "panels: {a: {}}\npage: {size: [20000, 3000]}\n"
        (found,) = diagnose_source(page + "pages: [{tiers: [{panels: [a]}]}]\n")
        assert found.message.startswith("a page is at most")
        (found,) = diagnose_source(CAST + "panel: {size: [20000, 3000]}\n")
        assert found.message.startswith("a panel is at most")

    def test_a_bound_that_is_no_limit_is_an_ordinary_fault(self):
        (found,) = diagnose_source(CAST + "script: [{sfx: {text: BAM, rotate: 50}}]\n")
        assert (found.rule, found.path) == ("invalid-field", ("script", 0, "sfx", "rotate"))


class TestTheSchemaStatesThem:
    def test_the_panel_schema(self):
        schema = panel_schema()
        size = schema["$defs"]["PanelSpec"]["properties"]["size"]["anyOf"][0]["prefixItems"]
        assert {item["maximum"] for item in size} == {LIMITS.panel_side}
        cast = next(b for b in schema["properties"]["cast"]["anyOf"] if "maxItems" in b)
        assert (cast["maxProperties"], cast["maxItems"]) == (LIMITS.actors_per_panel,) * 2

    def test_the_scene_schema(self):
        panels = scene_schema()["properties"]["panels"]
        assert (panels["maxProperties"], panels["maxItems"]) == (LIMITS.panels_per_document,) * 2


class TestALimitsValue:
    def test_it_only_tightens(self):
        with pytest.raises(ValueError, match="at most"):
            Limits(actors_per_panel=LIMITS.actors_per_panel + 1)
        with pytest.raises(ValueError, match="above 0"):
            Limits(panel_side=0)

    def test_a_tighter_one_finds_what_the_language_allows(self):
        panels = parse_scene_document(_cast(3)).panels
        (found,) = exceeded(panels, Limits(actors_per_panel=2), scene=False)
        assert found.loc == ("cast",)
        assert found.message == past("actors_per_panel", 3, 2)
        assert list(exceeded(panels, LIMITS, scene=False)) == []


class TestThePage:
    def test_it_lists_every_limit_with_its_value(self):
        text = PAGE.read_text(encoding="utf-8")
        for item in fields(LIMITS):
            value = getattr(LIMITS, item.name)
            row = re.search(rf"^\| `{item.name}` \| ([^|]+) \|", text, flags=re.MULTILINE)
            assert row is not None, item.name
            assert row[1].strip() == f"{value:,.0f}".replace(",", " "), item.name

    @pytest.mark.parametrize(
        "page", [ROOT / "docs" / "reference" / "api" / "guarantees.md", ROOT / "SECURITY.md"]
    )
    def test_it_is_linked_from(self, page: Path):
        assert "limits" in page.read_text(encoding="utf-8")


def _margins() -> list[tuple[str, str, float]]:
    """How close each gallery document comes to each limit it can approach, as a fraction."""
    margins: list[tuple[str, str, float]] = []
    for path in sorted([*GALLERY.glob("*.panel.yaml"), *GALLERY.glob("*.scene.yaml")]):
        document = parse_scene_document(path.read_text(encoding="utf-8"))
        used = {
            "panels_per_document": len(document.panels),
            "pages_per_document": len(document.layout.pages),
            "panel_side": max(max(panel.panel.size) for panel in document.panels.values()),
            "page_side": max(document.layout.page.size),
            "actors_per_panel": max(len(panel.cast) for panel in document.panels.values()),
            "events_per_panel": max(len(panel.script) for panel in document.panels.values()),
        }
        margins += [
            (path.name, name, value / getattr(LIMITS, name)) for name, value in used.items()
        ]
    return margins


def test_no_gallery_example_is_near_a_limit():
    """Generous for real comics: nothing in the gallery comes within half of one."""
    margins = _margins()
    closest = max(margins, key=lambda margin: margin[2])
    print(f"closest to a limit: {closest[0]} at {closest[2]:.1%} of {closest[1]}")
    assert closest[2] < 0.5, closest


class TestTheFastReader:
    """libyaml reads a document the profile allows; anything else goes back to the profile."""

    DOCUMENTS = sorted(
        path
        for folder in (
            ROOT / "examples",
            ROOT / "tests" / "rule_corpus",
            ROOT / "tests" / "finding_corpus",
        )
        for path in folder.rglob("*.yaml")
    )

    @pytest.mark.parametrize("path", DOCUMENTS, ids=[path.name for path in DOCUMENTS])
    def test_it_reads_what_the_profile_reads(self, path: Path):
        text = path.read_text(encoding="utf-8")
        fast, data = _load_fast(text)
        loader = _ProfileLoader(text)
        try:
            slow: object = loader.get_single_data()
        except yaml.YAMLError:
            assert not fast
            return
        finally:
            loader.dispose()
        if fast:
            assert repr(data) == repr(slow)

    @pytest.mark.parametrize(
        "text",
        [
            "a: !!str x\n",
            "a: &x 1\nb: *x\n",
            "a: {<<: {b: 1}}\n",
            "a:\t1\n",
            "a: 1\na: 2\n",
            "? [a]\n: 1\n",
        ],
        ids=["tag", "anchor", "merge-key", "tab", "twice", "list-key"],
    )
    def test_what_the_profile_refuses_goes_back_to_it(self, text: str):
        assert _load_fast(text) == (False, None)
