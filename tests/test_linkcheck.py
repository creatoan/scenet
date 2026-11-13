"""What the weekly link check is told it cannot check, and only that.

`.github/workflows/linkcheck.yml` runs Sphinx's `linkcheck` builder over the whole site. Two
kinds of result are not about the link: the playground's fragment is application state,
which no element's id matches, and some publishers answer every automated client with 403.
Both are configured in `docs/conf.py` -- the second by host, each with the reason -- so a
real 404 anywhere else still fails the run.
"""

import ast
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "docs" / "conf.py"


def _assigned(name: str) -> Any:
    for node in ast.parse(CONF.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"docs/conf.py does not set {name}")


def _linked() -> set[str]:
    """Every absolute address the documentation's pages link to."""
    found: set[str] = set()
    for page in (ROOT / "docs").rglob("*.md"):
        if "_build" in page.parts or "_linkcheck" in page.parts:
            continue
        found |= set(re.findall(r"https?://[^\s)\]>\"'`]+", page.read_text(encoding="utf-8")))
    return found


@pytest.mark.parametrize(
    "anchor", ["example=02-shot-ladder.scene.yaml", "src=eJwLz8kvSlXIzAMAEXIDmw"]
)
def test_the_playground_state_is_not_an_anchor(anchor: str):
    assert any(re.match(pattern, anchor) for pattern in _assigned("linkcheck_anchors_ignore"))


@pytest.mark.parametrize("anchor", ["the-checks-a-pull-request-runs", "feTurbulenceElement"])
def test_a_real_anchor_is_still_checked(anchor: str):
    assert not any(re.match(pattern, anchor) for pattern in _assigned("linkcheck_anchors_ignore"))


def test_nothing_is_ignored_for_a_whole_page():
    """The playground's page is checked; only the state after its `#` is not."""
    assert "linkcheck_anchors_ignore_for_url" not in CONF.read_text(encoding="utf-8")


def test_each_ignored_link_is_a_host_and_says_why():
    source = CONF.read_text(encoding="utf-8")
    block = re.search(r"^linkcheck_ignore = \[\n(.*?)^\]", source, re.MULTILINE | re.DOTALL)
    assert block is not None
    lines = block.group(1).splitlines()
    entries = [i for i, line in enumerate(lines) if not line.strip().startswith("#")]
    assert entries, "linkcheck_ignore is empty"
    for i in entries:
        assert re.fullmatch(r'\s*r"\^https://[\w\\.-]+/[\w\\./-]*",', lines[i]), lines[i]
        assert i > 0, f"no reason above {lines[i]}"
        assert lines[i - 1].strip().startswith("#"), f"no reason above {lines[i]}"


@pytest.mark.parametrize("pattern", _assigned("linkcheck_ignore"))
def test_every_ignored_host_is_still_linked(pattern: str):
    """An entry nothing matches any more is a hole a future link would fall into."""
    assert any(re.match(pattern, url) for url in _linked()), pattern


def test_only_the_hosts_that_refuse_are_ignored():
    hosts = {
        re.sub(r"\\", "", p).removeprefix("^https://").split("/")[0]
        for p in _assigned("linkcheck_ignore")
    }
    assert hosts == {
        "dl.acm.org",
        "doi.org",
        "www.sciencedirect.com",
        "pmc.ncbi.nlm.nih.gov",
        "gitlab.gnome.org",
        "blankcomic.com",
    }


def test_a_doi_is_ignored_only_for_the_publisher_that_refuses():
    """A DOI redirects to its publisher: only ACM's prefix, 10.1145, is one that refuses."""
    dois = [p for p in _assigned("linkcheck_ignore") if "doi" in p and "acm" not in p]
    assert dois == [r"^https://doi\.org/10\.1145/"]
