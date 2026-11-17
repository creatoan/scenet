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
from types import SimpleNamespace
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
    """Every absolute address the documentation's pages link to, the CHANGELOG's among them:
    "What's new" includes it."""
    found: set[str] = set()
    for page in [*(ROOT / "docs").rglob("*.md"), ROOT / "CHANGELOG.md"]:
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


# --- The site's own pages -----------------------------------------------------------------
#
# The CHANGELOG, which "What's new" includes, links the site's pages by their full address,
# the only kind that works on GitHub. A page added on `main` is not on the published site
# until the next release, so the weekly check found it missing (#486). Built, each such
# link is this build's own page, and the build fails when that page or its anchor is not
# there -- on every pull request, not once a week against the last release.


@pytest.fixture(scope="module")
def conf() -> dict[str, Any]:
    import runpy  # noqa: PLC0415

    return runpy.run_path(str(CONF))


SITE = "https://creatoan.github.io/scenet/"


@pytest.mark.parametrize(
    ("link", "page"),
    [
        (f"{SITE}reference/language/yaml_profile.html", ("reference/language/yaml_profile", "")),
        (
            f"{SITE}reference/diagnostics.html#invalid-field",
            ("reference/diagnostics", "invalid-field"),
        ),
        (f"{SITE}gallery.html", ("gallery", "")),
    ],
)
def test_a_link_to_one_of_the_sites_pages_names_it(conf: dict[str, Any], link: str, page: Any):
    assert conf["_site_page"](link) == page


@pytest.mark.parametrize(
    "link",
    [
        # Another version's page is that version's, published already.
        f"{SITE}v0.11/howto/install.html",
        f"{SITE}dev/howto/install.html",
        # Not pages: the playground, the spec pack, a schema, the site itself.
        f"{SITE}playground/#example=01-two-characters.panel.yaml",
        f"{SITE}scenet-spec.md",
        f"{SITE}schemas/panel.schema.json",
        SITE,
        "https://example.org/reference/diagnostics.html",
    ],
)
def test_anything_else_is_left_to_the_link_check(conf: dict[str, Any], link: str):
    assert conf["_site_page"](link) is None


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **_: object) -> None:
        self.warnings.append(message)


def _linking(*targets: str) -> tuple[Any, list[Any]]:
    from docutils import nodes  # noqa: PLC0415
    from docutils.utils import new_document  # noqa: PLC0415

    document = new_document("test")
    references = [nodes.reference("", "a link", refuri=target) for target in targets]
    paragraph = nodes.paragraph()
    paragraph += references
    document += paragraph
    return document, references


def _app(
    pages: set[str], ids: dict[str, list[str]] | None = None, builds: str = "html"
) -> SimpleNamespace:
    from docutils import nodes  # noqa: PLC0415
    from docutils.utils import new_document  # noqa: PLC0415

    def get_doctree(page: str) -> Any:
        document = new_document(page)
        document += nodes.section(ids=(ids or {}).get(page, []))
        return document

    def get_relative_uri(source: str, page: str) -> str:
        return {
            ("explanation/whats_new", "reference/language/yaml_profile"): (
                "../reference/language/yaml_profile.html"
            ),
            ("explanation/whats_new", "reference/diagnostics"): "../reference/diagnostics.html",
        }[(source, page)]

    return SimpleNamespace(
        env=SimpleNamespace(found_docs=pages, get_doctree=get_doctree),
        builder=SimpleNamespace(name=builds, get_relative_uri=get_relative_uri),
    )


@pytest.fixture
def logged(conf: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> _Logger:
    logger = _Logger()
    monkeypatch.setitem(conf["_site_links_are_this_builds"].__globals__, "_logger", logger)
    return logger


def test_read_a_link_to_a_page_has_no_address_for_the_link_check(
    conf: dict[str, Any], logged: _Logger
):
    document, (reference,) = _linking(f"{SITE}reference/language/yaml_profile.html")
    conf["_site_links_are_this_builds"](_app({"reference/language/yaml_profile"}), document)
    assert "refuri" not in reference
    assert logged.warnings == []


def test_resolved_it_is_the_builders_address_for_that_page(conf: dict[str, Any], logged: _Logger):
    document, (profile, rule) = _linking(
        f"{SITE}reference/language/yaml_profile.html", f"{SITE}reference/diagnostics.html#yaml-tag"
    )
    app = _app(
        {"reference/language/yaml_profile", "reference/diagnostics"},
        {"reference/diagnostics": ["yaml-tag"]},
    )
    conf["_site_links_are_this_builds"](app, document)
    conf["_site_links_resolve"](app, document, "explanation/whats_new")
    assert profile["refuri"] == "../reference/language/yaml_profile.html"
    assert rule["refuri"] == "../reference/diagnostics.html#yaml-tag"
    assert logged.warnings == []


def test_a_page_this_build_does_not_have_is_a_warning(conf: dict[str, Any], logged: _Logger):
    document, (reference,) = _linking(f"{SITE}reference/language/gone.html")
    conf["_site_links_are_this_builds"](_app({"index"}), document)
    assert reference["refuri"] == f"{SITE}reference/language/gone.html"
    assert logged.warnings == [
        f"{SITE}reference/language/gone.html is a link to a page this documentation does not have"
    ]


def test_an_anchor_the_page_does_not_have_is_a_warning(conf: dict[str, Any], logged: _Logger):
    document, (reference,) = _linking(f"{SITE}reference/diagnostics.html#no-such-rule")
    app = _app({"reference/diagnostics"}, {"reference/diagnostics": ["yaml-tag"]})
    conf["_site_links_are_this_builds"](app, document)
    conf["_site_links_resolve"](app, document, "explanation/whats_new")
    assert reference["refuri"] == "../reference/diagnostics.html#no-such-rule"
    assert logged.warnings == [
        "reference/diagnostics has no anchor #no-such-rule, which this page links to"
    ]


def test_any_other_link_is_left_as_it_is(conf: dict[str, Any], logged: _Logger):
    document, (playground, other) = _linking(f"{SITE}playground/", "https://example.org/a.html")
    app = _app(set())
    conf["_site_links_are_this_builds"](app, document)
    conf["_site_links_resolve"](app, document, "index")
    assert (playground["refuri"], other["refuri"]) == (
        f"{SITE}playground/",
        "https://example.org/a.html",
    )
    assert logged.warnings == []


def test_the_link_that_failed_is_a_page_of_this_build(conf: dict[str, Any]):
    """The CHANGELOG's link to the profile page, which 0.13's site does not have."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"{SITE}reference/language/yaml_profile.html" in changelog
    assert (ROOT / "docs" / "reference" / "language" / "yaml_profile.md").is_file()
    assert conf["_site_page"](f"{SITE}reference/language/yaml_profile.html") is not None


@pytest.mark.parametrize("link", sorted(_linked()))
def test_every_link_to_a_page_of_the_site_names_one(conf: dict[str, Any], link: str):
    """The build warns on one that does not, and `-W` fails it; this says which, sooner."""
    page = conf["_site_page"](link.rstrip("."))
    if page is not None:
        assert (ROOT / "docs" / f"{page[0]}.md").is_file(), link
