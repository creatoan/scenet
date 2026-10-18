"""Build the site of a release made before releases carried one.

From 0.12 on, the release workflow builds each release's documentation site and attaches
it to the GitHub Release, and Pages serves every version from those attachments. Releases
before that have none. This builds one for such a release, to attach by hand -- or by the
`Site backfill` workflow, which runs this and attaches the result.

It builds the release's own sources with its own lockfiles, and its playground runs the
wheel that release published, downloaded from the release. Only the files that make a build
versioned are taken from this checkout and laid over the release's: they label the build
with its version, point it at the one version switcher and give its pages their canonical
links. That is sound only where the release's site tooling is the tooling those files were
written against -- v0.11.0's -- so a release whose tooling differs is refused. That holds
from v0.8.0 to v0.11.0; earlier releases' documentation stays readable at their tag.

Run from the repository root:

    uv run python scripts/backfill_site.py v0.11.0 --out build/backfill
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from site_versions import Version

ROOT = Path(__file__).resolve().parent.parent
WORKTREES = ROOT / "build" / "backfill-worktrees"
REPOSITORY = "creatoan/scenet"
GIT, GH, UV = "git", "gh", "uv"

#: The last release before sites were versioned: the tooling OVERLAY was written against.
BEFORE_VERSIONING = "v0.11.0"

#: The files that build a site, which must be at the tag exactly as they were at
#: BEFORE_VERSIONING. Those also in OVERLAY are replaced; the rest are used as they are.
TOOLING = (
    "docs/conf.py",
    "scripts/build_site.py",
    "playground/vite.config.ts",
    "playground/scripts/fetch-assets.ts",
)

#: What makes a build versioned, copied from this checkout over the release's.
OVERLAY = (
    "docs/conf.py",
    "docs/_templates/playground-link.html",
    "docs/_static/scenet.css",
    "scripts/build_site.py",
    "scripts/site_versions.py",
    "playground/vite.config.ts",
)


def release_tag(tag: str) -> Version:
    """The release a tag names.

    Raises:
        ValueError: The tag is not `vX.Y.Z`.
    """
    if not tag.startswith("v"):
        raise ValueError(f"{tag!r} is not a release tag, such as v0.11.0")
    try:
        return Version.parse(tag)
    except ValueError:
        raise ValueError(f"{tag!r} is not a release tag, such as v0.11.0") from None


def _run(command: list[str], *, cwd: Path = ROOT) -> None:
    """Run a command, echoing it first so a CI log shows what happened.

    Raises:
        SystemExit: The command failed.
    """
    print(f"$ {' '.join(command)}", flush=True)
    # Not the virtual environment this script runs in: the release's commands run in its
    # own, which `uv` creates in the worktree.
    env = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
    result = subprocess.run(command, cwd=cwd, env=env, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def _blob(revision: str, path: str) -> str:
    result = subprocess.run(  # noqa: S603
        [GIT, "rev-parse", "--verify", "--quiet", f"{revision}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check_tooling(tag: str) -> None:
    """Refuse a release whose site tooling is not the tooling OVERLAY was written against.

    Raises:
        SystemExit: The tag is unknown, or some file in TOOLING differs at it.
    """
    if not _blob(tag, "pyproject.toml"):
        sys.exit(f"{tag}: no such tag here; fetch the tags (git fetch --tags)")
    differing = [path for path in TOOLING if _blob(tag, path) != _blob(BEFORE_VERSIONING, path)]
    if differing:
        sys.exit(
            f"{tag} builds its site differently from {BEFORE_VERSIONING} "
            f"({', '.join(differing)}), so it cannot be built versioned this way. Its "
            f"documentation is readable at https://github.com/{REPOSITORY}/tree/{tag}/docs"
        )


def backfill(tag: str, out: Path) -> Path:
    """Build a release's site, archived as `scenet-X.Y.Z-site.zip` in `out`.

    Returns:
        The archive.
    """
    version = release_tag(tag)
    check_tooling(tag)

    work = WORKTREES / tag
    if work.exists():
        _run([GIT, "worktree", "remove", "--force", str(work)])
    _run([GIT, "worktree", "add", "--detach", str(work), tag])
    try:
        for relative in OVERLAY:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

        # The wheel this release published, not a rebuild of it: that is what the
        # release's playground ran, and what `pip install` gives for this version.
        wheel = f"scenet-{version}-py3-none-any.whl"
        _run([GH, "release", "download", tag, "--repo", REPOSITORY, "--pattern", wheel,
              "--dir", str(work / "dist")])  # fmt: skip

        archive = out.resolve() / version.archive
        _run([UV, "sync", "--frozen", "--group", "docs"], cwd=work)
        _run(
            [UV, "run", "--frozen", "python", "scripts/build_site.py",
             "--release-archive", str(archive)],
            cwd=work,
        )  # fmt: skip
    finally:
        _run([GIT, "worktree", "remove", "--force", str(work)])

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"\n{archive}\nsha256 {digest}")
    return archive


def main() -> None:
    """Build one release's site."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="the release, such as v0.11.0")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "backfill")
    args = parser.parse_args()
    try:
        release_tag(args.tag)
    except ValueError as error:
        sys.exit(str(error))
    backfill(args.tag, args.out)


if __name__ == "__main__":
    main()
