"""The documentation site serves several versions, and each build must say which it is.

The site holds the latest release at its root, `main` under `/dev/` and each released minor
version under `/vX.Y/` (docs/explanation/design_decisions.md). A release's site is built
once and served unchanged at two of those paths, so a build may not know where it lives:
everything in it is relative, apart from three things every page carries and the version
switcher, the warning banner and search engines read -- which version it is, where the one
`switcher.json` is, and the canonical address of the page at the root.

The builds these tests check are real: a two-page Sphinx project built with the project's
own `docs/conf.py` and theme, as a release and as `dev`. A hand-written imitation of the
theme's output would test only the imitation.
"""

import importlib.util
import os
import runpy
import subprocess
import sys
import zipfile
from collections.abc import Callable
from importlib.metadata import version as package_version
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DOCS = ROOT / "docs"


def _load(name: str) -> ModuleType:
    """Import a script from `scripts/`, which is not a package."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


site_versions = _load("site_versions")
serve_site = _load("serve_site")


# ---------------------------------------------------------------- real builds

#: A conf.py that is the project's own, minus what needs the network or the package's API.
_CONF = """\
import runpy

globals().update(
    {{k: v for k, v in runpy.run_path({conf!r}).items() if not k.startswith("__")}}
)
extensions = ["myst_parser"]
intersphinx_mapping = {{}}
templates_path = [{templates!r}]
"""

_INDEX = """\
# Scenet

```{toctree}
howto/other
```
"""

_OTHER = "# Another page\n\nOne level down, so its links are not at the root.\n"


@pytest.fixture(scope="session")
def build_docs(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """Build the two-page project documenting a version; each version is built once."""
    built: dict[str, Path] = {}

    def build(documented: str) -> Path:
        if documented in built:
            return built[documented]
        base = tmp_path_factory.mktemp(f"docs-{documented}")
        source = base / "source"
        (source / "howto").mkdir(parents=True)
        (source / "conf.py").write_text(
            _CONF.format(conf=str(DOCS / "conf.py"), templates=str(DOCS / "_templates")),
            encoding="utf-8",
        )
        (source / "index.md").write_text(_INDEX, encoding="utf-8")
        (source / "howto" / "other.md").write_text(_OTHER, encoding="utf-8")
        output = base / "html"
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "sphinx", "-W", "-q", "-b", "html", str(source), str(output)],
            env={**os.environ, "SCENET_DOCS_VERSION": documented},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        built[documented] = output
        return output

    return build


# ---------------------------------------------------------------- conf.py


def _conf(monkeypatch: pytest.MonkeyPatch, documented: str | None) -> dict[str, Any]:
    if documented is None:
        monkeypatch.delenv("SCENET_DOCS_VERSION", raising=False)
    else:
        monkeypatch.setenv("SCENET_DOCS_VERSION", documented)
    return runpy.run_path(str(DOCS / "conf.py"))


class TestConf:
    """What `docs/conf.py` tells the theme, for a release and for `main`."""

    def test_a_release_documents_the_installed_version(self, monkeypatch: pytest.MonkeyPatch):
        conf = _conf(monkeypatch, None)
        installed = package_version("scenet")
        assert conf["release"] == installed
        assert conf["version"] == ".".join(installed.split(".")[:2])
        assert conf["html_theme_options"]["switcher"]["version_match"] == conf["version"]

    def test_main_is_labelled_dev(self, monkeypatch: pytest.MonkeyPatch):
        """Between releases `main`'s package version is the last release's own."""
        conf = _conf(monkeypatch, "dev")
        assert conf["release"] == conf["version"] == "dev"
        assert conf["html_theme_options"]["switcher"]["version_match"] == "dev"

    def test_an_explicit_version(self, monkeypatch: pytest.MonkeyPatch):
        conf = _conf(monkeypatch, "0.10.2")
        assert (conf["release"], conf["version"]) == ("0.10.2", "0.10")

    def test_every_version_reads_the_one_switcher(self, monkeypatch: pytest.MonkeyPatch):
        options = _conf(monkeypatch, None)["html_theme_options"]
        assert options["switcher"]["json_url"] == site_versions.SWITCHER_URL
        assert site_versions.SWITCHER_URL == "/scenet/switcher.json"

    def test_the_build_never_fetches_the_switcher(self, monkeypatch: pytest.MonkeyPatch):
        """The theme's check fetches `json_url` while building: network, and a -W failure."""
        assert _conf(monkeypatch, None)["html_theme_options"]["check_switcher"] is False

    def test_the_switcher_and_the_banner_are_on(self, monkeypatch: pytest.MonkeyPatch):
        options = _conf(monkeypatch, None)["html_theme_options"]
        assert "version-switcher" in options["navbar_start"]
        assert options["show_version_warning_banner"] is True

    def test_pages_are_canonical_at_the_root(self, monkeypatch: pytest.MonkeyPatch):
        conf = _conf(monkeypatch, None)
        assert conf["html_baseurl"] == site_versions.SITE_URL
        assert site_versions.SITE_URL == "https://creatoan.github.io/scenet/"

    def test_the_playground_link_is_the_versions_own(self, monkeypatch: pytest.MonkeyPatch):
        options = _conf(monkeypatch, None)["html_theme_options"]
        assert "playground-link" in options["navbar_end"]
        assert not any("playground" in link["url"] for link in options["icon_links"])


# ---------------------------------------------------------------- versions


class TestVersion:
    def test_parse(self):
        version = site_versions.Version.parse("v0.11.2")
        assert version == site_versions.Version.parse("0.11.2")
        assert (str(version), version.minor_name, version.directory) == (
            "0.11.2",
            "0.11",
            "v0.11",
        )
        assert version.archive == "scenet-0.11.2-site.zip"

    @pytest.mark.parametrize("text", ["0.11", "v0.12.0rc1", "0.11.0.dev0", "latest", "v1.2.3.4"])
    def test_only_a_final_release(self, text: str):
        with pytest.raises(ValueError, match="version"):
            site_versions.Version.parse(text)

    def test_order_is_numeric(self):
        parse = site_versions.Version.parse
        assert parse("0.10.0") > parse("0.9.3")


# ---------------------------------------------------------------- what a build says


class TestCheckDocs:
    """`check_docs` is what refuses a build that does not say which version it is."""

    def test_a_release_build_passes(self, build_docs: Callable[[str], Path]):
        pages = site_versions.check_docs(build_docs("0.10.0"), "0.10", "0.10.0")
        assert pages >= 2

    def test_a_dev_build_passes(self, build_docs: Callable[[str], Path]):
        site_versions.check_docs(build_docs("dev"), "dev", "dev")

    def test_the_wrong_version_is_refused(self, build_docs: Callable[[str], Path]):
        with pytest.raises(site_versions.SiteError, match="version_match"):
            site_versions.check_docs(build_docs("0.10.0"), "0.11", "0.11.0")

    def test_every_page_is_canonical_at_the_root(self, build_docs: Callable[[str], Path]):
        page = (build_docs("dev") / "howto" / "other.html").read_text(encoding="utf-8")
        assert (
            '<link rel="canonical" href="https://creatoan.github.io/scenet/howto/other.html"'
            in page
        )

    def test_a_page_without_a_canonical_link_is_refused(
        self, build_docs: Callable[[str], Path], tmp_path: Path
    ):
        copy = _copy(build_docs("dev"), tmp_path / "html")
        page = copy / "howto" / "other.html"
        text = page.read_text(encoding="utf-8")
        page.write_text(text.replace('rel="canonical"', 'rel="alternate"'), encoding="utf-8")
        with pytest.raises(site_versions.SiteError, match=r"howto/other\.html.*canonical"):
            site_versions.check_docs(copy, "dev", "dev")

    def test_a_build_without_the_banner_is_refused(
        self, build_docs: Callable[[str], Path], tmp_path: Path
    ):
        copy = _copy(build_docs("dev"), tmp_path / "html")
        for page in copy.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            page.write_text(text.replace("bd-header-version-warning", "x"), encoding="utf-8")
        with pytest.raises(site_versions.SiteError, match="banner"):
            site_versions.check_docs(copy, "dev", "dev")

    def test_the_banner_knows_the_release(self, build_docs: Callable[[str], Path]):
        """The theme compares `DOCUMENTATION_OPTIONS.VERSION` -- the release -- for its words."""
        options = build_docs("dev") / "_static" / "documentation_options.js"
        assert "VERSION: 'dev'" in options.read_text(encoding="utf-8")

    def test_the_playground_link_stays_in_its_version(self, build_docs: Callable[[str], Path]):
        page = (build_docs("dev") / "howto" / "other.html").read_text(encoding="utf-8")
        assert 'href="../playground/"' in page
        assert "creatoan.github.io/scenet/playground" not in page


def _copy(source: Path, target: Path) -> Path:
    for path in source.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    return target


# ---------------------------------------------------------------- archives


def _tree(root: Path) -> Path:
    (root / "playground").mkdir(parents=True)
    (root / "index.html").write_text("<html>root</html>\n", encoding="utf-8")
    (root / "playground" / "index.html").write_text("<html>play</html>\n", encoding="utf-8")
    (root / "llms.txt").write_text("# Scenet\n", encoding="utf-8")
    return root


def _contents(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestArchive:
    """A release's site travels as a zip attached to the release."""

    VERSION = site_versions.Version(0, 11, 0)

    def test_it_is_deterministic(self, tmp_path: Path):
        tree = _tree(tmp_path / "tree")
        first, second = tmp_path / "a.zip", tmp_path / "b.zip"
        site_versions.write_archive(tree, first, self.VERSION)
        os.utime(tree / "llms.txt", (0, 0))
        site_versions.write_archive(tree, second, self.VERSION)
        assert first.read_bytes() == second.read_bytes()

    def test_it_unpacks_into_one_folder(self, tmp_path: Path):
        archive = tmp_path / self.VERSION.archive
        site_versions.write_archive(_tree(tmp_path / "tree"), archive, self.VERSION)
        with zipfile.ZipFile(archive) as opened:
            names = opened.namelist()
        assert names == sorted(names)
        assert all(name.startswith("scenet-0.11.0-site/") for name in names)

    def test_it_round_trips(self, tmp_path: Path):
        tree = _tree(tmp_path / "tree")
        archive = tmp_path / self.VERSION.archive
        site_versions.write_archive(tree, archive, self.VERSION)
        found = site_versions.read_archive(archive, tmp_path / "out")
        assert found == self.VERSION
        assert _contents(tmp_path / "out") == _contents(tree)

    @pytest.mark.parametrize(
        "name",
        [
            "scenet-0.11.0-site/../escape.html",
            "/scenet-0.11.0-site/index.html",
            "scenet-0.10.0-site/index.html",
            "index.html",
        ],
    )
    def test_a_stray_entry_is_refused(self, tmp_path: Path, name: str):
        archive = tmp_path / self.VERSION.archive
        with zipfile.ZipFile(archive, "w") as opened:
            opened.writestr("scenet-0.11.0-site/index.html", "<html></html>")
            opened.writestr(name, "<html></html>")
        with pytest.raises(site_versions.SiteError):
            site_versions.read_archive(archive, tmp_path / "out")
        assert not (tmp_path / "escape.html").exists()

    def test_a_link_is_refused(self, tmp_path: Path):
        """Pages refuses an artifact holding one, so it is refused here, before deploying."""
        archive = tmp_path / self.VERSION.archive
        with zipfile.ZipFile(archive, "w") as opened:
            link = zipfile.ZipInfo("scenet-0.11.0-site/latest")
            link.external_attr = 0o120777 << 16
            opened.writestr(link, "index.html")
        with pytest.raises(site_versions.SiteError, match="link"):
            site_versions.read_archive(archive, tmp_path / "out")

    def test_the_name_must_be_a_release(self, tmp_path: Path):
        archive = tmp_path / "site.zip"
        site_versions.write_archive(_tree(tmp_path / "tree"), archive, self.VERSION)
        with pytest.raises(site_versions.SiteError, match="name"):
            site_versions.read_archive(archive, tmp_path / "out")


# ---------------------------------------------------------------- backfill


class TestBackfill:
    """Releases v0.8.0 to v0.11.0 get their site built with today's tooling overlaid."""

    @pytest.fixture(scope="class")
    @classmethod
    def backfill(cls) -> ModuleType:
        return _load("backfill_site")

    def test_what_it_overlays_exists(self, backfill: ModuleType):
        for relative in backfill.OVERLAY:
            assert (ROOT / relative).is_file(), relative

    def test_it_overlays_what_makes_a_build_versioned(self, backfill: ModuleType):
        assert {
            "docs/conf.py",
            "docs/_templates/playground-link.html",
            "scripts/build_site.py",
            "scripts/site_versions.py",
            "playground/vite.config.ts",
        } <= set(backfill.OVERLAY)

    def test_the_tooling_it_requires_unchanged_exists(self, backfill: ModuleType):
        """Files it compares at the tag with the last release before versioning."""
        assert backfill.BEFORE_VERSIONING == "v0.11.0"
        for relative in backfill.TOOLING:
            assert (ROOT / relative).is_file(), relative

    def test_a_tag(self, backfill: ModuleType):
        assert backfill.release_tag("v0.11.0") == site_versions.Version(0, 11, 0)

    @pytest.mark.parametrize("tag", ["0.11.0", "v0.11", "main", "v0.11.0; rm -rf /"])
    def test_anything_else_is_refused(self, backfill: ModuleType, tag: str):
        with pytest.raises(ValueError, match="tag"):
            backfill.release_tag(tag)


# ---------------------------------------------------------------- local preview


class TestServeSite:
    """The local preview serves the site under `/scenet/`, as Pages does."""

    @pytest.mark.parametrize(
        ("request_path", "served"),
        [
            ("/scenet/", "/"),
            ("/scenet/index.html", "/index.html"),
            ("/scenet/v0.10/howto/install.html?x=1", "/v0.10/howto/install.html?x=1"),
            ("/", None),
            ("/scenet", None),
            ("/other/index.html", None),
        ],
    )
    def test_the_prefix(self, request_path: str, served: str | None):
        assert serve_site.site_path(request_path) == served
