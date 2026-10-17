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
import json
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
            [
                sys.executable,
                "-m",
                "sphinx",
                "-W",
                "-q",
                "-b",
                "html",
                "-d",
                str(base / "doctrees"),
                str(source),
                str(output),
            ],
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


# ---------------------------------------------------------------- the assembled site


def _version_site(docs: Path, target: Path, label: str) -> Path:
    """A version's whole site: real documentation, stand-ins for the rest."""
    _copy(docs, target)
    (target / "playground").mkdir()
    (target / "playground" / "index.html").write_text(f"<p>{label}</p>\n", encoding="utf-8")
    (target / "schemas").mkdir()
    (target / "schemas" / "panel.schema.json").write_text(f'{{"title": "{label}"}}\n')
    (target / "scenet-spec.md").write_text(f"# Scenet {label}\n", encoding="utf-8")
    (target / "llms.txt").write_text(f"# Scenet {label}\n", encoding="utf-8")
    return target


@pytest.fixture(scope="session")
def release_archive(
    build_docs: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], Path]:
    """The archive a release attaches, holding a real build of its documentation."""
    made: dict[str, Path] = {}

    def make(release: str) -> Path:
        if release not in made:
            version = site_versions.Version.parse(release)
            base = tmp_path_factory.mktemp(f"release-{release}")
            tree = _version_site(build_docs(release), base / "tree", release)
            made[release] = base / version.archive
            site_versions.write_archive(tree, made[release], version)
        return made[release]

    return make


@pytest.fixture
def dev_site(build_docs: Callable[[str], Path], tmp_path: Path) -> Path:
    return _version_site(build_docs("dev"), tmp_path / "dev-build", "dev")


@pytest.fixture
def assembled(release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path) -> Path:
    out = tmp_path / "site"
    site_versions.assemble(dev_site, [release_archive("0.10.0"), release_archive("0.11.0")], out)
    return out


def _switcher(site: Path) -> list[dict[str, Any]]:
    return json.loads((site / "switcher.json").read_text(encoding="utf-8"))


def _baked(page: Path, name: str) -> str:
    """A value the theme writes into a page's DOCUMENTATION_OPTIONS."""
    text = page.read_text(encoding="utf-8")
    marker = f"DOCUMENTATION_OPTIONS.{name} = '"
    start = text.index(marker) + len(marker)
    return text[start : text.index("'", start)]


#: Where each copy is, and what it documents: the root is the latest release.
COPIES = {"": "0.11", "v0.11/": "0.11", "v0.10/": "0.10", "dev/": "dev"}


class TestAssembledSite:
    """The latest release at the root, main under dev/, each minor version under vX.Y/."""

    def test_the_layout(self, assembled: Path):
        assert (assembled / "llms.txt").read_text(encoding="utf-8") == "# Scenet 0.11.0\n"
        assert "0.11.0" in (assembled / "schemas" / "panel.schema.json").read_text()
        assert "0.11.0" in (assembled / "playground" / "index.html").read_text()
        for prefix, label in [("v0.11/", "0.11.0"), ("v0.10/", "0.10.0"), ("dev/", "dev")]:
            assert (assembled / prefix / "scenet-spec.md").read_text() == f"# Scenet {label}\n"
            assert label in (assembled / prefix / "playground" / "index.html").read_text()
        assert sorted(path.name for path in assembled.iterdir() if path.is_dir()) == sorted(
            ["_static", "dev", "howto", "playground", "schemas", "v0.10", "v0.11"]
        )

    def test_a_release_is_served_exactly_as_attached(
        self, assembled: Path, release_archive: Callable[[str], Path], tmp_path: Path
    ):
        unpacked = tmp_path / "unpacked"
        site_versions.read_archive(release_archive("0.10.0"), unpacked)
        assert _contents(assembled / "v0.10") == _contents(unpacked)
        root = {
            name: data
            for name, data in _contents(assembled).items()
            if not name.startswith(("dev/", "v0.1")) and name not in {"switcher.json", ".nojekyll"}
        }
        assert root == _contents(assembled / "v0.11")

    def test_the_switcher_lists_dev_then_each_version(self, assembled: Path):
        assert _switcher(assembled) == [
            {"name": "dev", "version": "dev", "url": "/scenet/dev/"},
            {"name": "0.11 (latest)", "version": "0.11", "url": "/scenet/", "preferred": True},
            {"name": "0.10", "version": "0.10", "url": "/scenet/v0.10/"},
        ]

    def test_exactly_one_version_is_preferred(self, assembled: Path):
        """The banner does nothing at all otherwise (the theme's documented requirement)."""
        assert [entry["version"] for entry in _switcher(assembled) if entry.get("preferred")] == [
            "0.11"
        ]

    @pytest.mark.parametrize(("prefix", "version_match"), COPIES.items())
    def test_each_copy_is_in_the_switcher(self, assembled: Path, prefix: str, version_match: str):
        """So the switcher can show which version a reader is on."""
        for page in ("index.html", "howto/other.html"):
            baked = _baked(assembled / prefix / page, "theme_switcher_version_match")
            assert baked == version_match
            assert baked in {entry["version"] for entry in _switcher(assembled)}
            assert _baked(assembled / prefix / page, "theme_switcher_json_url") == (
                "/scenet/switcher.json"
            )

    @pytest.mark.parametrize("prefix", COPIES)
    def test_every_page_is_canonical_at_the_root(self, assembled: Path, prefix: str):
        page = (assembled / prefix / "howto" / "other.html").read_text(encoding="utf-8")
        assert (
            '<link rel="canonical" href="https://creatoan.github.io/scenet/howto/other.html"'
            in page
        )

    @pytest.mark.parametrize(
        ("prefix", "shown"), [("", False), ("v0.11/", False), ("v0.10/", True), ("dev/", True)]
    )
    def test_the_banner_shows_on_dev_and_old_versions_only(
        self, assembled: Path, prefix: str, shown: bool
    ):
        """The theme hides it exactly when the build's version_match is the preferred one."""
        page = assembled / prefix / "index.html"
        text = page.read_text(encoding="utf-8")
        assert 'id="bd-header-version-warning"' in text
        assert "show_version_warning_banner =" in text
        (preferred,) = [entry for entry in _switcher(assembled) if entry.get("preferred")]
        assert (_baked(page, "theme_switcher_version_match") != preferred["version"]) is shown

    def test_the_banner_calls_dev_unstable_and_old_versions_old(self, assembled: Path):
        """Its words come from the release string: "dev" in it, or lower than the latest."""

        def release(prefix: str) -> str:
            options = assembled / prefix / "_static" / "documentation_options.js"
            text = options.read_text(encoding="utf-8")
            return text.split("VERSION: '", 1)[1].split("'", 1)[0]

        assert "dev" in release("dev/")
        assert site_versions.Version.parse(release("v0.10/")) < site_versions.Version(0, 11, 0)

    def test_a_push_to_main_changes_only_dev(
        self, release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path
    ):
        archives = [release_archive("0.10.0"), release_archive("0.11.0")]
        before, after = tmp_path / "before", tmp_path / "after"
        site_versions.assemble(dev_site, archives, before)
        (dev_site / "llms.txt").write_text("# Scenet dev, one commit later\n", encoding="utf-8")
        site_versions.assemble(dev_site, archives, after)
        old, new = _contents(before), _contents(after)
        assert old.keys() == new.keys()
        assert [name for name in old if old[name] != new[name]] == ["dev/llms.txt"]

    def test_the_latest_is_the_highest_version_not_the_last_given(
        self, release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path
    ):
        """A patch to an older minor version must not take the root."""
        out = tmp_path / "site"
        site_versions.assemble(
            dev_site, [release_archive("0.11.0"), release_archive("0.10.0")], out
        )
        assert _baked(out / "index.html", "theme_switcher_version_match") == "0.11"


class TestAssemblyRefuses:
    def test_no_release(self, dev_site: Path, tmp_path: Path):
        with pytest.raises(site_versions.SiteError, match="no release"):
            site_versions.assemble(dev_site, [], tmp_path / "site")

    def test_a_mislabelled_release(
        self, release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path
    ):
        """An archive whose pages say another version would show the wrong banner."""
        wrong = tmp_path / "scenet-0.12.0-site.zip"
        unpacked = tmp_path / "unpacked"
        site_versions.read_archive(release_archive("0.11.0"), unpacked)
        site_versions.write_archive(unpacked, wrong, site_versions.Version(0, 12, 0))
        with pytest.raises(site_versions.SiteError, match="version_match"):
            site_versions.assemble(dev_site, [wrong], tmp_path / "site")

    def test_a_dev_build_labelled_as_a_release(
        self, release_archive: Callable[[str], Path], build_docs: Callable[[str], Path],
        tmp_path: Path,
    ):  # fmt: skip
        mislabelled = _version_site(build_docs("0.10.0"), tmp_path / "dev", "dev")
        with pytest.raises(site_versions.SiteError, match="version_match"):
            site_versions.assemble(mislabelled, [release_archive("0.11.0")], tmp_path / "site")

    def test_two_of_one_minor_version(
        self, release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path
    ):
        archive = release_archive("0.11.0")
        twin = tmp_path / "scenet-0.11.1-site.zip"
        twin.write_bytes(archive.read_bytes())
        with pytest.raises(site_versions.SiteError, match=r"0\.11"):
            site_versions.assemble(dev_site, [archive, twin], tmp_path / "site")

    def test_a_root_entry_in_the_way_of_a_version(
        self, release_archive: Callable[[str], Path], dev_site: Path, tmp_path: Path
    ):
        unpacked = tmp_path / "unpacked"
        site_versions.read_archive(release_archive("0.11.0"), unpacked)
        (unpacked / "dev").mkdir()
        (unpacked / "dev" / "notes.html").write_text("<p>a page called dev</p>\n")
        archive = tmp_path / "scenet-0.11.0-site.zip"
        site_versions.write_archive(unpacked, archive, site_versions.Version(0, 11, 0))
        with pytest.raises(site_versions.SiteError, match="dev"):
            site_versions.assemble(dev_site, [archive], tmp_path / "site")

    def test_a_site_over_the_pages_limit(
        self,
        release_archive: Callable[[str], Path],
        dev_site: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(site_versions, "SIZE_LIMIT", 1000)
        with pytest.raises(site_versions.SiteError, match="limit"):
            site_versions.assemble(dev_site, [release_archive("0.11.0")], tmp_path / "site")


class TestOldPlaygroundsRetire:
    """The root, dev and the newest minor versions keep a playground; older ones do not."""

    def test_the_newest_keep_theirs(self):
        assert site_versions.PLAYGROUNDS_KEPT == 3

    def test_an_older_one_becomes_a_page_pointing_on(
        self,
        release_archive: Callable[[str], Path],
        dev_site: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(site_versions, "PLAYGROUNDS_KEPT", 1)
        out = tmp_path / "site"
        site_versions.assemble(
            dev_site, [release_archive("0.10.0"), release_archive("0.11.0")], out
        )
        assert [path.name for path in (out / "v0.10" / "playground").iterdir()] == ["index.html"]
        stub = (out / "v0.10" / "playground" / "index.html").read_text(encoding="utf-8")
        assert 'href="../../playground/"' in stub
        assert "releases/tag/v0.10.0" in stub
        assert "scenet-0.10.0-site.zip" in stub
        assert "AI-generated" in stub
        assert "0.11.0" in (out / "v0.11" / "playground" / "index.html").read_text()
        assert "0.11.0" in (out / "playground" / "index.html").read_text()
        assert "dev" in (out / "dev" / "playground" / "index.html").read_text()
        # The rest of the old version is still served.
        assert (out / "v0.10" / "schemas" / "panel.schema.json").is_file()
        assert (out / "v0.10" / "howto" / "other.html").is_file()


# ---------------------------------------------------------------- which releases


def _release(tag: str, *assets: str, draft: bool = False, prerelease: bool = False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": name, "digest": f"sha256:{name}"} for name in assets],
    }


class TestSelect:
    """Which release serves each minor version, from what the releases API lists."""

    def test_the_highest_patch_of_each_minor_with_a_site(self):
        releases = [
            _release("v0.11.1", "scenet-0.11.1-site.zip", "scenet-0.11.1-py3-none-any.whl"),
            _release("v0.11.0", "scenet-0.11.0-site.zip"),
            _release("v0.10.0", "scenet-0.10.0-site.zip"),
            _release("v0.10.1", "scenet-0.10.1-site.zip"),
        ]
        sites, _ = site_versions.select(releases)
        assert [str(site.version) for site in sites] == ["0.11.1", "0.10.1"]
        assert sites[0].digest == "sha256:scenet-0.11.1-site.zip"

    def test_a_release_without_a_site_is_passed_over_and_said(self):
        releases = [
            _release("v0.11.1", "scenet-0.11.1-py3-none-any.whl"),
            _release("v0.11.0", "scenet-0.11.0-site.zip"),
            _release("v0.7.0"),
        ]
        sites, notes = site_versions.select(releases)
        assert [str(site.version) for site in sites] == ["0.11.0"]
        assert any("v0.11.1" in note for note in notes)
        assert any("v0.7.0" in note for note in notes)

    def test_drafts_prereleases_and_other_tags_are_not_served(self):
        releases = [
            _release("v0.12.0", "scenet-0.12.0-site.zip", draft=True),
            _release("v0.12.1", "scenet-0.12.1-site.zip", prerelease=True),
            _release("v0.13.0rc1", "scenet-0.13.0rc1-site.zip"),
            _release("nightly", "scenet-0.11.0-site.zip"),
            _release("v0.11.0", "scenet-0.11.0-site.zip"),
        ]
        sites, _ = site_versions.select(releases)
        assert [str(site.version) for site in sites] == ["0.11.0"]

    def test_from_a_directory(self, tmp_path: Path):
        for name in ["scenet-0.10.0-site.zip", "scenet-0.10.2-site.zip", "scenet-0.11.0-site.zip"]:
            (tmp_path / name).write_bytes(b"")
        (tmp_path / "notes.txt").write_text("not an archive")
        chosen = site_versions.select_archives(tmp_path)
        assert [path.name for path in chosen] == [
            "scenet-0.11.0-site.zip",
            "scenet-0.10.2-site.zip",
        ]


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
