"""Build the gallery through the command line, and keep what it wrote as golden files.

`docs/reference/cli.md` promises that the same input produces byte-identical output, and
that two runs on different machines produce files `cmp` calls equal. In-process tests
cannot see the second half: every output was CRLF on Windows until #89, and nothing
noticed. So `tests/test_golden.py` builds the gallery exactly as a user would, through
`scenet build`, and compares the **bytes on disk** with what is committed here, in every
CI job -- Linux on two Pythons, and Windows.

Two kinds of golden:

- `tests/golden/core/` holds every Panel Core and Page Core the gallery compiles to. Core
  is small, readable and diffable by design, so a change in layout is reviewed coordinate
  by coordinate.
- `tests/golden/digests.json` holds the SHA-256 of every SVG: each panel, its debug
  overlay, its live-text variant, each strip and each page; and of every print PDF (#80).
  SVG is too large to review usefully as text, and its Core already says what moved.
- `docs/images/gallery/` holds the pictures the documentation shows of each gallery
  example (#243), whole: copies of goldens, compared byte for byte.

After an intended change to the output, regenerate and review the diff:

    uv run python scripts/update_golden.py           # rewrite the goldens
    uv run python scripts/update_golden.py --check   # exit 1 if any is stale
"""

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from scenet.cli import main

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "examples" / "gallery"
GOLDEN = ROOT / "tests" / "golden"
CORES = GOLDEN / "core"
DIGESTS = GOLDEN / "digests.json"
COMMAND = "uv run python scripts/update_golden.py"

#: Pictures the documentation shows, each exactly as `scenet build` writes it -- so each is a
#: golden too, kept whole, and rewritten with the others. These are chosen by hand: a panel
#: beside its depth map and mask, in the how-to on exporting for image models. `pictures()`
#: adds the gallery's.
PICTURES = {
    ROOT / "docs" / "images" / "conditioning" / "panel.svg": "21-atmosphere.noon.svg",
    ROOT / "docs" / "images" / "conditioning" / "depth.svg": "21-atmosphere.noon.depth.svg",
    ROOT / "docs" / "images" / "conditioning" / "mask.svg": "21-atmosphere.noon.mask.svg",
}

#: Every gallery example drawn whole, named as the build names it (#243): what the Gallery
#: page shows, and what the home page, the language reference and the README show of it.
GALLERY_PICTURES = ROOT / "docs" / "images" / "gallery"

#: A fourth build, of the examples lettered over a picture of their own only, with the picture
#: written into the SVG. An SVG shown as an image -- on a page of the documentation, in the
#: README -- may load nothing from outside itself, so a picture it only links is missing there.
#: Every other document writes the same bytes with or without it.
EMBEDDED = "embedded/"
EMBEDDED_FLAGS = ["--embed-images", "--strip"]

#: What a file an example names ends in when it is a picture the example is lettered over.
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg")

#: The outputs drawn over a panel rather than as it, which never show a document.
OVERLAYS = (".debug.svg", ".depth.svg", ".mask.svg")

#: The exports for image models that are JSON, which are digested as the SVGs are.
EXPORTED_JSON = (".pose.json", ".boxes.json", ".semantics.json")

#: Three builds of every document: one with every output; one with live text, whose SVG
#: differs and whose Core does not; and one without accessibility markup.
VARIANTS = {
    "": ["--core", "--debug", "--strip", "--conditioning", "--pdf"],
    "live-text/": ["--live-text", "--strip"],
    # Without accessibility markup: what a post-processing pipeline gets, which must be
    # exactly what was written before there was any, file for file.
    "no-aria/": ["--no-aria", "--strip"],
}


def gallery() -> list[Path]:
    """Every document in the gallery, in a fixed order.

    Files only: a picture an example is lettered over sits in a folder of its own.
    """
    return sorted(
        path for path in GALLERY.iterdir() if path.is_file() and path.name != "manifest.yaml"
    )


def entries() -> list[dict[str, Any]]:
    """The gallery's manifest entries, in the manifest's order."""
    manifest = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))
    return manifest["examples"]


def lettered_over_a_picture(entry: dict[str, Any]) -> bool:
    """Whether a manifest entry names a picture beside itself, which it is lettered over."""
    return any(name.lower().endswith(PICTURE_SUFFIXES) for name in entry.get("files", []))


def build(sources: list[Path], directory: Path) -> dict[str, bytes]:
    """Build each source through the command line into `directory`.

    Args:
        sources: Documents to build.
        directory: Where to write; each variant gets a folder of its own.

    Returns:
        Every file written, keyed by its path under `directory`, as the bytes on disk.
    """
    written: dict[str, bytes] = {}
    for prefix, flags in VARIANTS.items():
        written |= _build_variant(sources, directory, prefix, flags)
    over_a_picture = {entry["file"] for entry in entries() if lettered_over_a_picture(entry)}
    embedded = [source for source in sources if source.name in over_a_picture]
    return written | _build_variant(embedded, directory, EMBEDDED, EMBEDDED_FLAGS)


def _build_variant(
    sources: list[Path], directory: Path, prefix: str, flags: list[str]
) -> dict[str, bytes]:
    """Build each source with `flags` into `directory / prefix`; what it wrote, by name."""
    out = directory / prefix
    out.mkdir(parents=True, exist_ok=True)
    for source in sources:
        with contextlib.redirect_stdout(io.StringIO()):
            status = main(["build", str(source), "-o", f"{out}/", "--quiet", *flags])
        if status != 0:
            message = f"scenet build {source.name} exited {status}"
            raise RuntimeError(message)
    return {
        f"{prefix}{path.name}": path.read_bytes()
        for path in sorted(out.iterdir())
        if path.is_file()
    }


def shown(stem: str, names: Iterable[str]) -> list[str]:
    """The outputs that show a document whole: its pages, or else its strip, or else its panel.

    Args:
        stem: The document's file name up to its first dot, `38-tour`.
        names: Every file one build wrote, by name; those in a variant's folder are ignored.

    Returns:
        The names of its SVGs to show, pages in their order.

    Raises:
        ValueError: The build drew no panel of the document, or several and no strip.
    """
    own = [
        name
        for name in names
        if "/" not in name
        and name.startswith(f"{stem}.")
        and name.endswith(".svg")
        and not name.endswith(OVERLAYS)
    ]
    pages = sorted(
        (name for name in own if re.fullmatch(rf"{re.escape(stem)}\.page-\d+\.svg", name)),
        key=lambda name: int(name.removesuffix(".svg").rsplit("-", 1)[1]),
    )
    if pages:
        return pages
    if f"{stem}.strip.svg" in own:
        return [f"{stem}.strip.svg"]
    if len(own) != 1:
        message = f"nothing shows {stem!r} whole: {sorted(own)}"
        raise ValueError(message)
    return own


def pictures(names: Iterable[str]) -> dict[Path, str]:
    """Every picture the documentation shows: where it is committed, and the golden it copies.

    Args:
        names: Every output of a build, or every digest, by its path under the build.

    Returns:
        The pictures chosen by hand, and each gallery example's under `GALLERY_PICTURES`.
    """
    built = set(names)
    gallery_pictures: dict[Path, str] = {}
    for entry in entries():
        prefix = EMBEDDED if lettered_over_a_picture(entry) else ""
        variant = [name.removeprefix(prefix) for name in built if name.startswith(prefix)]
        stem = entry["file"].split(".")[0]
        if not any(name.startswith(f"{stem}.") for name in variant):
            continue  # a build of part of the gallery
        for name in shown(stem, variant):
            gallery_pictures[GALLERY_PICTURES / name] = f"{prefix}{name}"
    return PICTURES | gallery_pictures


def goldens(written: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, str]]:
    """Split a build into the Core files kept whole and the digests of everything else.

    Returns:
        Core file name to bytes, and each SVG, print PDF or exported JSON path to its
        SHA-256.
    """
    cores = {name: data for name, data in written.items() if name.endswith(".core.json")}
    digests = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(written.items())
        if name.endswith((".svg", ".pdf", *EXPORTED_JSON))
    }
    return cores, digests


def committed() -> tuple[dict[str, bytes], dict[str, str]]:
    """The goldens as committed."""
    cores = {path.name: path.read_bytes() for path in sorted(CORES.glob("*.core.json"))}
    digests = json.loads(DIGESTS.read_text(encoding="utf-8")) if DIGESTS.exists() else {}
    return cores, digests


def differences(written: dict[str, bytes]) -> list[str]:
    """Every output that differs from its golden, or exists on only one side."""
    cores, digests = goldens(written)
    kept_cores, kept_digests = committed()
    names = sorted(
        name for name in {*cores, *kept_cores} if cores.get(name) != kept_cores.get(name)
    )
    names += sorted(
        name for name in {*digests, *kept_digests} if digests.get(name) != kept_digests.get(name)
    )
    shown_now = pictures(written)
    for picture, source in shown_now.items():
        if not picture.is_file() or picture.read_bytes() != written.get(source):
            names.append(str(picture.relative_to(ROOT).as_posix()))
    names += [
        str(stale.relative_to(ROOT).as_posix())
        for stale in sorted(GALLERY_PICTURES.glob("*"))
        if stale not in shown_now
    ]
    return names


def write(written: dict[str, bytes]) -> None:
    """Replace the committed goldens with these."""
    cores, digests = goldens(written)
    CORES.mkdir(parents=True, exist_ok=True)
    for stale in CORES.glob("*.core.json"):
        stale.unlink()
    for name, data in cores.items():
        (CORES / name).write_bytes(data)
    DIGESTS.write_text(
        json.dumps(digests, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    for stale in GALLERY_PICTURES.glob("*"):
        stale.unlink()
    for picture, source in pictures(written).items():
        picture.parent.mkdir(parents=True, exist_ok=True)
        picture.write_bytes(written[source])


def run(argv: list[str] | None = None) -> int:
    """Rewrite the goldens, or with `--check` report the stale ones and exit 1."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if a golden is stale")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as directory:
        written = build(gallery(), Path(directory))
    if args.check:
        stale = differences(written)
        for name in stale:
            print(f"stale: {name}", file=sys.stderr)
        return 1 if stale else 0
    write(written)
    print(f"wrote {len(goldens(written)[0])} Core files and {len(goldens(written)[1])} digests")
    return 0


if __name__ == "__main__":
    sys.exit(run())
