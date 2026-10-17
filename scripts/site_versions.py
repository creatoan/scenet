"""The documentation site serves several versions; this is what keeps them apart.

    /scenet/                  the latest release
    /scenet/dev/              main
    /scenet/vX.Y/             each released minor version, its highest patch
    /scenet/switcher.json     the version switcher's data, read by every version

A release's site is built once, from the wheel the release publishes, and attached to the
GitHub Release as `scenet-X.Y.Z-site.zip`. The same build is then served at the root and
under its `vX.Y/`, so nothing in it may depend on where it lives -- apart from three
things every page carries on purpose: which version it documents, where the one
`switcher.json` is, and the canonical address of the page at the root. `check_docs`
refuses a build that does not say them. See docs/explanation/design_decisions.md.

Run from the repository root, to check a documentation build:

    uv run python scripts/site_versions.py check docs/_build/html
"""

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from importlib.metadata import version as package_version
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple
from urllib.parse import urlsplit

#: Where the site is published. Every canonical link points under it.
SITE_URL = "https://creatoan.github.io/scenet/"

#: The repository whose releases carry each version's site.
REPOSITORY = "creatoan/scenet"
GH = "gh"

#: The path the site is served under, on Pages and in the local preview alike.
SITE_PATH = urlsplit(SITE_URL).path

#: The version switcher's data, at one address every version reads. Site-absolute rather
#: than a full URL, so a build works on any host serving it under SITE_PATH -- the local
#: preview included -- while still never reading a stale copy of its own.
SWITCHER_URL = f"{SITE_PATH}switcher.json"

#: What the build of `main` calls itself, in the switcher and in the banner.
DEV = "dev"

# A zip entry's timestamp cannot be earlier than this, and a fixed one is what makes the
# same files produce the same archive.
_EPOCH = (1980, 1, 1, 0, 0, 0)

_RELEASE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_ARCHIVE = re.compile(r"scenet-(\d+\.\d+\.\d+)-site\.zip")


class SiteError(ValueError):
    """A build, an archive or a site that is not what it claims to be."""


class Version(NamedTuple):
    """A final release, `X.Y.Z`. Pre-releases and development versions are not served."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "Version":
        """Read `0.11.0` or `v0.11.0`.

        Raises:
            ValueError: Anything else, such as `0.11` or `0.12.0rc1`.
        """
        match = _RELEASE.fullmatch(text)
        if match is None:
            raise ValueError(f"{text!r} is not a release version, such as 0.11.0")
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    def __str__(self) -> str:
        """The version as `X.Y.Z`."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def minor_name(self) -> str:
        """`X.Y`: the documentation's `version`, and the switcher's."""
        return f"{self.major}.{self.minor}"

    @property
    def directory(self) -> str:
        """Where the minor version is served: `vX.Y`."""
        return f"v{self.minor_name}"

    @property
    def tag(self) -> str:
        """The release's git tag."""
        return f"v{self}"

    @property
    def archive(self) -> str:
        """The name of the site archive attached to the release."""
        return f"scenet-{self}-site.zip"


# ---------------------------------------------------------------- what a build says

_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]*)"')
_JSON_URL = re.compile(r"DOCUMENTATION_OPTIONS\.theme_switcher_json_url = '([^']*)';")
_VERSION_MATCH = re.compile(r"DOCUMENTATION_OPTIONS\.theme_switcher_version_match = '([^']*)';")
_BANNER_ON = re.compile(r"DOCUMENTATION_OPTIONS\.show_version_warning_banner =\s*true;")
_BANNER_PLACE = 'id="bd-header-version-warning"'
_RELEASE_JS = re.compile(r"VERSION: '([^']*)'")


def _pages(html: Path) -> list[Path]:
    """Every page a reader can land on: the HTML outside the theme's assets."""
    return sorted(
        path
        for path in html.rglob("*.html")
        if path.relative_to(html).parts[0] not in {"_static", "_sources", "playground"}
    )


def _page_problems(html: Path, page: Path, version_match: str) -> list[str]:
    relative = page.relative_to(html).as_posix()
    text = page.read_text(encoding="utf-8")
    problems: list[str] = []

    canonical = _CANONICAL.search(text)
    expected = f"{SITE_URL}{relative}"
    if canonical is None or canonical.group(1) != expected:
        found = canonical.group(1) if canonical else "none"
        problems.append(f"{relative}: canonical link is {found}, not {expected}")

    json_url = _JSON_URL.search(text)
    if json_url is None or json_url.group(1) != SWITCHER_URL:
        problems.append(f"{relative}: the version switcher does not read {SWITCHER_URL}")

    matched = _VERSION_MATCH.search(text)
    if matched is None or matched.group(1) != version_match:
        found = matched.group(1) if matched else "none"
        problems.append(f"{relative}: version_match is {found}, not {version_match}")

    if _BANNER_ON.search(text) is None or _BANNER_PLACE not in text:
        problems.append(f"{relative}: the version warning banner is off")
    return problems


def check_docs(html: Path, version_match: str, release: str) -> int:
    """Check that a documentation build says which version it is, on every page.

    Args:
        html: The Sphinx HTML output.
        version_match: What the switcher should match: `X.Y`, or `dev`.
        release: The release string the banner compares: `X.Y.Z`, or `dev`.

    Returns:
        How many pages were checked.

    Raises:
        SiteError: Some page does not say it, listing every one that does not.
    """
    pages = _pages(html)
    if not (html / "index.html").is_file():
        raise SiteError(f"{html} has no index.html; is it a documentation build?")

    problems = [problem for page in pages for problem in _page_problems(html, page, version_match)]

    options = html / "_static" / "documentation_options.js"
    found = _RELEASE_JS.search(options.read_text(encoding="utf-8")) if options.is_file() else None
    if found is None or found.group(1) != release:
        problems.append(f"_static/documentation_options.js: VERSION is not {release!r}")

    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise SiteError(f"{html} does not say it documents {release}:\n  {shown}{more}")
    return len(pages)


# ---------------------------------------------------------------- archives


def write_archive(tree: Path, archive: Path, version: Version) -> None:
    """Zip one version's site, the same files always making the same bytes.

    Everything goes under one folder, `scenet-X.Y.Z-site/`, so unpacking it by hand does
    not scatter files: the archive is also how anyone gets a release's site to read offline.

    Args:
        tree: The built site.
        archive: The zip to write.
        version: The release it documents.
    """
    top = archive_folder(version)
    files = sorted(
        (path.relative_to(tree).as_posix(), path) for path in tree.rglob("*") if path.is_file()
    )
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as opened:
        for name, path in files:
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=_EPOCH)
            info.create_system = 3  # Unix, so the mode below means the same everywhere
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            opened.writestr(info, path.read_bytes(), compresslevel=9)


def archive_folder(version: Version) -> str:
    """The one folder a release's archive holds."""
    return f"scenet-{version}-site"


def archive_version(archive: Path) -> Version:
    """The release an archive's name says it holds.

    Raises:
        SiteError: The name is not `scenet-X.Y.Z-site.zip`.
    """
    match = _ARCHIVE.fullmatch(archive.name)
    if match is None:
        raise SiteError(f"{archive.name}: not a site archive name, scenet-X.Y.Z-site.zip")
    return Version.parse(match.group(1))


def read_archive(archive: Path, into: Path) -> Version:
    """Unpack a release's site, refusing any entry that could land outside `into`.

    Args:
        archive: A `scenet-X.Y.Z-site.zip`.
        into: The directory to unpack into; its contents are the archive's folder's.

    Returns:
        The release the archive holds.

    Raises:
        SiteError: The name is not a release's, or an entry is outside the archive's one
            folder, climbs out of it, is absolute, or is a link.
    """
    version = archive_version(archive)
    top = archive_folder(version)
    with zipfile.ZipFile(archive) as opened:
        entries = opened.infolist()
        for info in entries:
            _check_entry(archive, info, top)
        for info in entries:
            if info.is_dir():
                continue
            target = into.joinpath(*PurePosixPath(info.filename).parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(opened.read(info))
    return version


def _check_entry(archive: Path, info: zipfile.ZipInfo, top: str) -> None:
    name = info.filename
    path = PurePosixPath(name)
    if "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
        raise SiteError(f"{archive.name}: entry {name!r} could land outside the site")
    if not path.parts or path.parts[0] != top or (len(path.parts) == 1 and not info.is_dir()):
        raise SiteError(f"{archive.name}: entry {name!r} is not inside {top}/")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise SiteError(f"{archive.name}: entry {name!r} is a link, which Pages refuses")


# ---------------------------------------------------------------- which releases


class ReleaseSite(NamedTuple):
    """A release whose site is attached to it, and the attachment's digest if known."""

    version: Version
    digest: str | None


def select(releases: list[dict[str, Any]]) -> tuple[list[ReleaseSite], list[str]]:
    """Choose the release that serves each minor version, from the GitHub releases API.

    The highest patch of each minor version that has its site attached. Drafts,
    pre-releases and tags that are not `vX.Y.Z` are never served.

    Args:
        releases: Release objects as `GET /repos/{owner}/{repo}/releases` lists them.

    Returns:
        The chosen releases, newest first, and a note on each release passed over for
        having no site -- worth saying, since its minor version then serves an older patch.
    """
    chosen: dict[tuple[int, int], ReleaseSite] = {}
    notes: list[str] = []
    for release in releases:
        tag = str(release.get("tag_name", ""))
        if release.get("draft") or release.get("prerelease") or not tag.startswith("v"):
            continue
        try:
            version = Version.parse(tag)
        except ValueError:
            continue
        assets = {str(asset["name"]): asset for asset in release.get("assets", [])}
        asset = assets.get(version.archive)
        if asset is None:
            notes.append(f"{tag} has no {version.archive} attached; it is not served")
            continue
        key = (version.major, version.minor)
        if key not in chosen or chosen[key].version < version:
            chosen[key] = ReleaseSite(version, asset.get("digest"))
    return sorted(chosen.values(), reverse=True), sorted(notes)


def select_archives(directory: Path) -> list[Path]:
    """Choose, among the site archives in a directory, the highest patch of each minor.

    Returns:
        The chosen archives, newest first. Other files are ignored.
    """
    chosen: dict[tuple[int, int], tuple[Version, Path]] = {}
    for path in directory.iterdir():
        try:
            version = archive_version(path)
        except SiteError:
            continue
        key = (version.major, version.minor)
        if key not in chosen or chosen[key][0] < version:
            chosen[key] = (version, path)
    return [path for _, path in sorted(chosen.values(), reverse=True)]


def download(repository: str, into: Path) -> list[Path]:
    """Download the site attached to each release that serves a minor version.

    Uses the `gh` command line, which reads its token from `GH_TOKEN`. An archive already
    downloaded is kept when it matches the digest GitHub lists for the attachment.

    Returns:
        The archives, newest first.

    Raises:
        SiteError: A download does not match the digest GitHub lists for it.
    """
    listed = subprocess.run(  # noqa: S603
        [GH, "api", "--paginate", "--slurp", f"repos/{repository}/releases"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    releases = [release for page in json.loads(listed) for release in page]
    sites, notes = select(releases)
    for note in notes:
        print(f"note: {note}", flush=True)

    into.mkdir(parents=True, exist_ok=True)
    archives: list[Path] = []
    for site in sites:
        archive = into / site.version.archive
        if not (archive.is_file() and _digest_matches(archive, site.digest)):
            print(f"$ gh release download {site.version.tag} ({site.version.archive})", flush=True)
            subprocess.run(  # noqa: S603
                [GH, "release", "download", site.version.tag, "--repo", repository,
                 "--pattern", site.version.archive, "--dir", str(into), "--clobber"],
                check=True,
            )  # fmt: skip
            if not _digest_matches(archive, site.digest):
                raise SiteError(f"{archive.name} does not match the digest GitHub lists")
        archives.append(archive)
    return archives


def _digest_matches(archive: Path, digest: str | None) -> bool:
    """True when the file has the listed `sha256:` digest, or none is listed."""
    if digest is None:
        return True
    algorithm, _, expected = digest.partition(":")
    if algorithm != "sha256":
        return True
    return hashlib.sha256(archive.read_bytes()).hexdigest() == expected


# ---------------------------------------------------------------- the assembled site

#: Versions under vX.Y/ that keep their playground, newest first. The root and dev/
#: always keep theirs. A playground is 28 MB of a version's 40, and Pages caps a site
#: at 1 GB with no way for two versions to share a file.
PLAYGROUNDS_KEPT = 3

#: The largest site GitHub Pages publishes.
SIZE_LIMIT = 1_000_000_000

#: Where a version's playground was, once it has retired.
RETIRED_PLAYGROUND = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Scenet {minor} playground, retired</title>
    <link rel="canonical" href="{site}playground/" />
  </head>
  <body>
    <h1>The Scenet {minor} playground has retired</h1>
    <p>
      To keep this site within GitHub Pages' size limit, only the newest versions keep a
      playground. The <a href="../">documentation of {minor}</a> is still here.
    </p>
    <ul>
      <li><a href="../../playground/">The playground of the latest release</a></li>
      <li>
        The whole {version} site, playground included, is attached to
        <a href="https://github.com/{repository}/releases/tag/{tag}">its release</a> as
        <code>{archive}</code>. Serve it from any local web server.
      </li>
    </ul>
    <p>Scenet is a deliberately AI-generated project.</p>
  </body>
</html>
"""


def switcher_entries(versions: list[Version]) -> list[dict[str, Any]]:
    """The version switcher's data: dev, then each minor version, newest first.

    The newest is served at the root, and is the one entry marked preferred -- which the
    theme's warning banner needs exactly one of.
    """
    newest = sorted(versions, reverse=True)
    entries: list[dict[str, Any]] = [{"name": DEV, "version": DEV, "url": f"{SITE_PATH}{DEV}/"}]
    for index, version in enumerate(newest):
        if index == 0:
            entries.append(
                {
                    "name": f"{version.minor_name} (latest)",
                    "version": version.minor_name,
                    "url": SITE_PATH,
                    "preferred": True,
                }
            )
        else:
            entries.append(
                {
                    "name": version.minor_name,
                    "version": version.minor_name,
                    "url": f"{SITE_PATH}{version.directory}/",
                }
            )
    return entries


def retire_playground(directory: Path, version: Version) -> None:
    """Replace a version's playground by a page saying where to go instead."""
    playground = directory / "playground"
    shutil.rmtree(playground, ignore_errors=True)
    playground.mkdir()
    (playground / "index.html").write_text(
        RETIRED_PLAYGROUND.format(
            minor=version.minor_name,
            version=version,
            tag=version.tag,
            archive=version.archive,
            site=SITE_URL,
            repository=REPOSITORY,
        ),
        encoding="utf-8",
        newline="\n",
    )


_VERSION_DIRECTORY = re.compile(r"v\d+\.\d+")


def assemble(dev: Path, archives: list[Path], out: Path) -> int:
    """Put every version of the site together.

    The latest release goes at the root, `main` under dev/, each minor version under
    vX.Y/, and the version switcher's data beside them. Every input is checked to say
    the version it is served as, so no copy can show the wrong banner or the wrong
    version in the switcher.

    Args:
        dev: The built site of `main`, labelled dev.
        archives: The site archive of each minor version's release, one per minor.
        out: Where to write the site; anything there is replaced.

    Returns:
        The site's size in bytes.

    Raises:
        SiteError: No release, two of one minor version, an input that does not say the
            version it is served as, a root entry in a version's way, or a site over the
            size Pages publishes.
    """
    if not archives:
        raise SiteError("no release has a site attached; see docs/maintainer/releasing.md")
    versions = {archive: archive_version(archive) for archive in archives}
    minors = [version.minor_name for version in versions.values()]
    for minor in sorted(set(minors)):
        if minors.count(minor) > 1:
            raise SiteError(f"two archives for {minor}; give the highest patch of each")
    ordered = sorted(archives, key=versions.__getitem__, reverse=True)
    latest = versions[ordered[0]]

    check_docs(dev, DEV, DEV)
    if out.exists():
        shutil.rmtree(out)

    read_archive(ordered[0], out)
    in_the_way = sorted(
        path.name
        for path in out.iterdir()
        if path.name in {DEV, "switcher.json"} or _VERSION_DIRECTORY.fullmatch(path.name)
    )
    if in_the_way:
        raise SiteError(f"{latest}'s site has {', '.join(in_the_way)} where a version goes")
    check_docs(out, latest.minor_name, str(latest))

    for index, archive in enumerate(ordered):
        version = versions[archive]
        directory = out / version.directory
        read_archive(archive, directory)
        check_docs(directory, version.minor_name, str(version))
        if index >= PLAYGROUNDS_KEPT:
            retire_playground(directory, version)

    shutil.copytree(dev, out / DEV)

    (out / "switcher.json").write_text(
        json.dumps(switcher_entries(list(versions.values())), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / ".nojekyll").touch()

    size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    if size > SIZE_LIMIT:
        raise SiteError(
            f"the site is {size / 1e6:.0f} MB, over GitHub Pages' {SIZE_LIMIT / 1e9:.0f} GB "
            "limit; keep fewer playgrounds (PLAYGROUNDS_KEPT)"
        )
    return size


# ---------------------------------------------------------------- command line


def main() -> None:
    """Check a documentation build, as the installed package's release by default."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check a documentation build says its version")
    check.add_argument("html", type=Path)
    check.add_argument("--dev", action="store_true", help="the build of main, not a release")
    args = parser.parse_args()

    if args.dev:
        version_match = release = DEV
    else:
        release = package_version("scenet")
        version_match = Version.parse(release).minor_name
    try:
        pages = check_docs(args.html, version_match, release)
    except SiteError as error:
        sys.exit(str(error))
    print(f"{args.html}: {pages} pages say they document {release}")


if __name__ == "__main__":
    main()
