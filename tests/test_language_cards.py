"""Every key of the language has one card, its facts are current, and it shows itself (#319).

An author looking up one key lands on its card: where it is written, its type, values and
default, the release it appeared in, the findings it can give, what it means, and a document
that shows it with the picture that document compiles to. The facts come from the published
schemas (`scripts/build_language_pages.py`); these tests fail on a key without a card, a card
for a key that does not exist, facts that are stale, and a card that shows nothing.
"""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from scenet.diagnostics import RULES
from scenet.ir import PlacementZone
from tests import myst
from tests.doc_examples import fences

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE = ROOT / "docs" / "reference" / "language"
GLOSSARY = ROOT / "docs" / "reference" / "glossary.md"
MANIFEST = ROOT / "examples" / "gallery" / "manifest.yaml"


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


build = _load("build_language_pages")
CARDS: dict[str, Any] = build.cards()
NAMES = sorted(CARDS)


def _section(card: Any) -> str:
    """A card's own text: from its heading to the next heading of its level or above."""
    page = LANGUAGE / f"{card.page}.md"
    for section in myst.sections(page.read_text(encoding="utf-8")):
        if section.heading.anchor == card.anchor:
            return section.text
    raise AssertionError(f"{page.name} has no heading for {card.name}")


class TestEveryKeyHasOneCard:
    def test_there_is_a_card_for_each_key_of_the_four_schemas(self):
        families = {card.family for card in CARDS.values()}
        assert families == {"document", "artwork", "puppet"}
        assert len(CARDS) > 120

    @pytest.mark.parametrize("name", NAMES)
    def test_it_has_exactly_one_card(self, name: str):
        placed = build.placed().get(name, [])
        assert len(placed) == 1, f"{name}: add `<!-- facts: {name} -->` under its heading"
        assert placed[0].stem == CARDS[name].page

    def test_no_card_is_for_a_key_that_does_not_exist(self):
        assert sorted(set(build.placed()) - set(CARDS)) == []

    @pytest.mark.parametrize("name", NAMES)
    def test_its_heading_is_its_name(self, name: str):
        text = (LANGUAGE / f"{CARDS[name].page}.md").read_text(encoding="utf-8")
        assert re.search(
            rf"^## `{re.escape(name)}`\n\n<!-- facts: {re.escape(name)} -->", text, re.M
        )


class TestTheFactsAreCurrent:
    def test_every_page_matches_a_fresh_build(self):
        stale = [path.name for path in build.stale()]
        assert stale == [], "run `uv run python scripts/build_language_pages.py`"

    def test_generation_is_deterministic(self):
        assert build.expected() == build.expected()

    @pytest.mark.parametrize("name", NAMES)
    def test_it_opens_on_the_editors_hover_text(self, name: str):
        card = CARDS[name]
        assert card.description
        assert build.facts(card).startswith(card.description)


#: The defaults an audit found the reference never stated.
DEFAULTS = {
    "cast.<id>.pose": "`standing_neutral`",
    "cast.<id>.at": "`center`",
    "cast.<id>.facing": "`right`",
    "say.kind": "`speech`",
    "say.size": "`normal`",
    "caption.kind": "`locale`",
    "caption.tone": "`paper`",
    "setting.horizon": "`mid`",
    "setting.time": "`day`",
    "setting.weather": "`clear`",
    "panel.size": "`[1000, 1000]`",
}


class TestEveryDefaultAndValueIsStated:
    @pytest.mark.parametrize(("name", "default"), sorted(DEFAULTS.items()))
    def test_the_default(self, name: str, default: str):
        assert f"| Default | {default} |" in build.facts(CARDS[name])

    @pytest.mark.parametrize("name", ["say.prefer", "caption.prefer", "sfx.prefer"])
    def test_every_zone(self, name: str):
        facts = build.facts(CARDS[name])
        assert all(f"`{zone.value}`" in facts for zone in PlacementZone)


class TestSince:
    @pytest.mark.parametrize("name", NAMES)
    def test_every_card_has_one(self, name: str):
        """A key added since the last release takes the next minor version in `since.toml`."""
        version = build.since()["keys"].get(name)
        assert version is not None, f"add {name!r} to [keys] in docs/reference/language/since.toml"
        assert re.fullmatch(r"0\.\d+", version), "a minor version"

    def test_it_names_no_other_key(self):
        assert sorted(set(build.since()["keys"]) - set(CARDS)) == []

    def test_each_value_is_one_its_key_takes(self):
        for entry in build.since()["values"]:
            name, value = entry.split("=", 1)
            assert value in build.values_of(CARDS[name].node), entry

    def test_a_value_added_later_is_marked(self):
        assert "`warm` (since 0.13)" in build.facts(CARDS["caption.tone"])


#: Rules about a whole document or a comic script's own form, which no key gives.
DOCUMENT_RULES = {
    "syntax",
    "not-a-mapping",
    "internal",
    "duplicate-panel",
    "panel-count",
    "looks-like-dialogue",
}


class TestDiagnostics:
    def test_every_rule_a_card_names_exists(self):
        named = {rule for rules in build.DIAGNOSTICS.values() for rule in rules}
        assert sorted(named - set(RULES)) == []

    def test_every_rule_a_key_can_give_is_on_a_card(self):
        """#320's catalogue links each rule to the cards that give it."""
        given = {
            rule.strip("`")
            for card in CARDS.values()
            for rule in build.facts(card).split("| Diagnostics | ", 1)[1].split(" |")[0].split(", ")
        }
        assert sorted(set(RULES) - DOCUMENT_RULES - given) == []

    def test_a_card_names_only_keys_that_exist(self):
        assert sorted(set(build.DIAGNOSTICS) - set(CARDS)) == []
        assert sorted(set(build.SCRIPT_FORMS) - set(CARDS)) == []


#: The complete examples the puppet and artwork cards share, one on each page: a puppet file
#: is a whole skeleton, and a contract needs its picture, so no card has one of its own.
SHARED_EXAMPLES = {"puppet": "a-puppet-file", "artwork": "an-artwork-contract"}


class TestEveryCardShowsItsKey:
    @pytest.mark.parametrize("name", NAMES)
    def test_it_has_an_example(self, name: str):
        card = CARDS[name]
        text = _section(card)
        if card.page in SHARED_EXAMPLES:
            assert f"](#{SHARED_EXAMPLES[card.page]})" in text, "link the page's example"
            return
        assert "```{scenet-example}" in text, f"{name}: end on a ```{{scenet-example}} block"

    @pytest.mark.parametrize(
        "name", [name for name in NAMES if CARDS[name].page not in SHARED_EXAMPLES]
    )
    def test_its_example_writes_it(self, name: str):
        card = CARDS[name]
        page = LANGUAGE / f"{card.page}.md"
        start = myst.headings(page.read_text(encoding="utf-8"))
        line = next(h.line for h in start if h.anchor == card.anchor)
        after = [h.line for h in start if h.line > line and h.level <= 2]
        end = after[0] if after else 10**9
        blocks = [
            fence
            for fence in fences(page)
            if fence.directive == "scenet-example" and line < fence.line - 1 < end
        ]
        assert blocks, name
        word = re.split(r"[.\[]", card.name)[-1].strip("[]") or card.key
        written = (
            set(_keys(yaml.safe_load(blocks[0].text))) if blocks[0].language == "yaml" else set()
        )
        assert card.key in written or word in written, (
            f"{name}'s example does not write `{card.key}`"
        )

    @pytest.mark.parametrize("page", sorted(SHARED_EXAMPLES))
    def test_the_shared_example_is_there(self, page: str):
        assert SHARED_EXAMPLES[page] in myst.anchors(LANGUAGE / f"{page}.md")


def _keys(node: object) -> list[str]:
    """Every mapping key in a parsed document, at any depth."""
    if isinstance(node, dict):
        return [str(key) for key in node] + [k for value in node.values() for k in _keys(value)]
    if isinstance(node, list):
        return [k for value in node for k in _keys(value)]
    return []


class TestTheIndex:
    def test_it_lists_every_card_once(self):
        text = build.INDEX.read_text(encoding="utf-8")
        listed = re.findall(r"^\| \[`([^`]+)`\]\(([\w-]+)\.md#([\w-]+)\)", text, re.M)
        assert sorted(name for name, _, _ in listed) == NAMES
        for name, page, anchor in listed:
            assert page == CARDS[name].page
            assert anchor in myst.anchors(LANGUAGE / f"{page}.md"), name

    def test_it_is_in_the_table_of_contents(self):
        overview = (LANGUAGE / "index.md").read_text(encoding="utf-8")
        assert re.search(r"^keys$", overview, re.M)


class TestTheGalleryLandsOnACard:
    """'Read about it' in the playground opens the card of the key its example shows."""

    #: What a gallery example may name other than a card: the overview's sections, and the
    #: pages that are not the language's keys.
    NOT_A_CARD = ("reference/language/index.md#",)

    def test_every_doc_into_the_reference_names_a_card(self):
        entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["examples"]
        cards = {f"reference/language/{card.page}.md#{card.anchor}" for card in CARDS.values()}
        named = [
            entry["doc"]
            for entry in entries
            if entry["doc"].startswith("reference/language/")
            and not entry["doc"].startswith(self.NOT_A_CARD)
        ]
        assert named
        assert [doc for doc in named if doc not in cards] == []


#: Terms the cards use, and later documentation links: what #319 asks the glossary to hold.
TERMS = (
    "actor",
    "puppet",
    "cast member",
    "figure",
    "panel unit",
    "Panel Core",
    "staging",
    "gaze",
    "emanata",
    "mass",
    "plane",
    "tier",
    "inset",
    "gutter",
    "slant",
    "bleed",
    "reading order",
)


class TestTheGlossary:
    def test_it_is_a_glossary(self):
        assert "```{glossary}" in GLOSSARY.read_text(encoding="utf-8")

    @pytest.mark.parametrize("term", TERMS)
    def test_it_defines(self, term: str):
        text = GLOSSARY.read_text(encoding="utf-8")
        assert re.search(rf"^{re.escape(term)}$", text, re.M | re.I), term

    @pytest.mark.parametrize("term", TERMS)
    def test_the_cards_link_it(self, term: str):
        linked = " ".join(page.read_text(encoding="utf-8") for page in LANGUAGE.glob("*.md"))
        pattern = rf"\{{term\}}`(?:[^`<]*<)?{re.escape(term)}>?`"
        assert re.search(pattern, linked, re.I), f"no card links {{term}}`{term}`"
