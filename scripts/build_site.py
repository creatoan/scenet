"""Build the GitHub Pages site: every version of Scenet, as Pages serves it.

One Pages site per repository, so the documentation, the playground and the published
schemas share an origin. It holds several versions (scripts/site_versions.py):

    site/                     the latest release
    site/dev/                 this checkout -- main, on Pages
    site/vX.Y/                each released minor version
    site/switcher.json        the version switcher's data

Each version's site is:

    index.html ...            documentation (Sphinx)
    playground/               the browser playground (Vite)
    schemas/*.json            the JSON Schemas, at stable URLs
    scenet-spec.md            the spec pack: the whole language, in one file for a model
    llms.txt                  an index for retrieval systems, per llmstxt.org

A release's site is built once, by the release, and attached to it; this downloads those
rather than rebuilding them, so a version is served exactly as it was released. Nothing in
a version's site depends on where it is served from. What it does carry is which version
it documents: the installed package's for a release, `dev` for this checkout.

The schemas are served from a stable URL on purpose. Any editor with a YAML language
server can validate a panel document against them with a one-line comment and no
Scenet-specific plugin -- see docs/howto/editor_support.md.

Run from the repository root:

    uv run python scripts/build_site.py                       # releases from GitHub
    uv run python scripts/build_site.py --releases DIR        # releases from DIR
    uv run python scripts/build_site.py --release-archive F   # this checkout, as a release

Downloading the releases uses the `gh` command line, signed in or given `GH_TOKEN`.
"""

import argparse
import os
import shutil
import subprocess
import sys
from importlib.metadata import version as package_version
from pathlib import Path

import build_spec
import site_versions

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
STAGING = ROOT / "build" / "site-release"
DEV_STAGING = ROOT / "build" / "site-dev"
RELEASES = ROOT / "build" / "site-releases"
DOCS_BUILD = ROOT / "docs" / "_build" / "html"
# Sphinx's pickled build state. Left to its default it lands inside the HTML, and would be
# published -- several megabytes nobody reads, in every version of the site.
DOCTREES = ROOT / "docs" / "_build" / "doctrees"
PLAYGROUND = ROOT / "playground"
SCHEMAS = ROOT / "editor" / "schemas"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    """Run a command, echoing it first so a CI log shows what happened.

    Args:
        command: Program and arguments.
        cwd: Directory to run in.
        env: Extra environment variables, merged over the current environment.

    Raises:
        SystemExit: The command failed.
    """
    print(f"$ {' '.join(command)}  (in {cwd.relative_to(ROOT) or '.'})", flush=True)
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(command, cwd=cwd, env=merged, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def documented(*, dev: bool) -> tuple[str, str]:
    """What the documentation says it is: the switcher's `version_match`, and the release."""
    if dev:
        return site_versions.DEV, site_versions.DEV
    release = package_version("scenet")
    return site_versions.Version.parse(release).minor_name, release


def build_docs(*, dev: bool) -> None:
    """Build the documentation with warnings as errors, labelled with its version."""
    run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-W",
            "--keep-going",
            "-b",
            "html",
            "-d",
            str(DOCTREES),
            "docs",
            str(DOCS_BUILD),
        ],
        cwd=ROOT,
        # Read by docs/conf.py. A release needs nothing: it documents the installed package.
        env={"SCENET_DOCS_VERSION": site_versions.DEV} if dev else None,
    )


def build_playground() -> None:
    """Build the playground. Its base is relative, so one build serves at any path."""
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    # `npm ci` wipes node_modules, which fails on Windows if anything is holding a file
    # in it -- a running dev server, most often. CI always starts clean, so only install
    # when there is nothing there.
    if not (PLAYGROUND / "node_modules").is_dir():
        run([npm, "ci"], cwd=PLAYGROUND)
    run([npm, "run", "build"], cwd=PLAYGROUND)


def compose(out: Path, *, dev: bool) -> None:
    """Copy one version's built pieces into `out`, after checking the docs say which it is.

    Raises:
        SystemExit: The documentation build does not carry its version on every page.
    """
    version_match, release = documented(dev=dev)
    try:
        pages = site_versions.check_docs(DOCS_BUILD, version_match, release)
    except site_versions.SiteError as error:
        sys.exit(f"{error}\n(rebuild without --skip-docs?)")
    print(f"docs: {pages} pages document {release}")

    if out.exists():
        shutil.rmtree(out)
    # .doctrees too, in case an earlier build left one in the HTML.
    shutil.copytree(DOCS_BUILD, out, ignore=shutil.ignore_patterns(".doctrees"))
    shutil.copytree(PLAYGROUND / "dist", out / "playground")

    schemas = out / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for name in ("panel.schema.json", "scene.schema.json", "artwork.schema.json"):
        shutil.copyfile(SCHEMAS / name, schemas / name)

    # Generated fresh from the sources rather than copied from the committed spec pack,
    # so the published one is current even on a branch that forgot to regenerate.
    build_spec.write_site_files(out)

    # Sphinx writes .nojekyll itself for _static/, but a site served from a branch also
    # needs it at the root or every directory beginning with an underscore is dropped.
    (out / ".nojekyll").touch()
    _report(out)


def _report(tree: Path) -> None:
    files = [path for path in tree.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    print(f"\n{tree.relative_to(ROOT)}/: {len(files)} files, {total / 1e6:.1f} MB", flush=True)


def archive_release(archive: Path) -> None:
    """Archive the release site just composed, under the name the release attaches.

    Raises:
        SystemExit: The file name is not the installed version's archive name.
    """
    version = site_versions.Version.parse(package_version("scenet"))
    if archive.name != version.archive:
        sys.exit(f"{archive.name}: the release being built is {version}; name it {version.archive}")
    site_versions.write_archive(STAGING, archive, version)
    print(f"{archive}: {archive.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    """Build this checkout's site, and put every version together, or archive a release."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--releases",
        type=Path,
        metavar="DIR",
        help="take the releases' site archives from DIR instead of downloading them",
    )
    source.add_argument(
        "--release-archive",
        type=Path,
        metavar="FILE",
        help="build the installed release's site and zip it to FILE, scenet-X.Y.Z-site.zip",
    )
    parser.add_argument("--skip-docs", action="store_true", help="reuse an existing docs build")
    parser.add_argument(
        "--skip-playground", action="store_true", help="reuse an existing playground build"
    )
    args = parser.parse_args()
    dev = args.release_archive is None

    if not args.skip_docs:
        build_docs(dev=dev)
    if not args.skip_playground:
        build_playground()

    if not dev:
        compose(STAGING, dev=False)
        archive_release(args.release_archive.resolve())
        return

    compose(DEV_STAGING, dev=True)
    if args.releases is None:
        archives = site_versions.download(site_versions.REPOSITORY, RELEASES)
    else:
        archives = site_versions.select_archives(args.releases)
    try:
        size = site_versions.assemble(DEV_STAGING, archives, SITE)
    except site_versions.SiteError as error:
        sys.exit(str(error))
    latest = site_versions.archive_version(archives[0])
    served = ", ".join(site_versions.archive_version(archive).directory for archive in archives)
    print(f"\nsite/: {latest} at the root, then dev/, {served}: {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
