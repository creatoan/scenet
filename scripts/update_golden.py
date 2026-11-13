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
  overlay, its live-text variant, each strip and each page; and of every print PDF (#80),
  lettered in outlines and, in the live-text variant, in its embedded faces (#284).
  SVG is too large to review usefully as text, and its Core already says what moved.
- `docs/images/gallery/` holds the pictures the documentation shows of each gallery
  example (#243), whole: copies of goldens, compared byte for byte.
- `tests/golden/findings.json` holds every finding `scenet check` gives, with and without
  `--deep`, on every gallery example, every document of `tests/rule_corpus/` and its fixed
  twins, and `tests/finding_corpus/`: rule, level, message, path, file, region and
  fingerprint. The rule corpus pins which rule a document breaks; this pins everything else
  a finding says, which nothing held until mutation testing reached the diagnostics (#345).
  The gallery is there for what it does not say: a check that lost its document's folder
  or its puppets would find fault with it.
- `tests/golden/parsed.json` holds the SHA-256 of what the front ends read from each of the
  same documents -- every panel's IR, a script's lines, notes and page layout -- or of how
  they refused it. A Core only says what was drawn; this holds what was read on the way.

After an intended change to the output, regenerate and review the diff:

    uv run python scripts/update_golden.py           # rewrite the goldens
    uv run python scripts/update_golden.py --check   # exit 1 if any is stale
"""

import argparse
import contextlib
import dataclasses
import hashlib
import io
import json
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from scenet.cli import main
from scenet.diagnostics import Diagnostic, diagnose_file
from scenet.errors import ScenetError
from scenet.frontends.script_front import load_script, parse_script_document
from scenet.frontends.yaml_front import (
    load_panel,
    load_scene,
    load_scene_document,
    parse_scene_document,
)

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "examples" / "gallery"
GOLDEN = ROOT / "tests" / "golden"
CORES = GOLDEN / "core"
DIGESTS = GOLDEN / "digests.json"
FINDINGS = GOLDEN / "findings.json"
PARSED = GOLDEN / "parsed.json"
#: The folders whose documents' findings are kept: the gallery; one document per diagnostic,
#: and its fixed twin; and a document for each way of reaching a finding the others miss.
FINDING_CORPORA = (
    GALLERY,
    ROOT / "tests" / "rule_corpus",
    ROOT / "tests" / "rule_corpus" / "fixed",
    ROOT / "tests" / "finding_corpus",
)
#: What a document `scenet check` reads ends in.
DOCUMENT_SUFFIXES = (".panel.yaml", ".scene.yaml", ".script")
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
    "live-text/": ["--live-text", "--strip", "--pdf"],
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


def _finding(item: Diagnostic) -> dict[str, Any]:
    region = item.region
    return {
        "rule": item.rule,
        "level": item.level,
        "message": item.message,
        "path": list(item.path),
        "source": item.source.relative_to(ROOT).as_posix() if item.source else None,
        "region": None
        if region is None
        else [region.start.line, region.start.column, region.end.line, region.end.column],
        "fingerprint": item.fingerprint(root=ROOT),
    }


def finding_documents() -> list[Path]:
    """Every document whose findings are kept, in order."""
    return sorted(
        path
        for corpus in FINDING_CORPORA
        for path in corpus.iterdir()
        if path.is_file() and path.name.endswith(DOCUMENT_SUFFIXES)
    )


def findings_of(path: Path) -> dict[str, list[dict[str, Any]]]:
    """A document's findings, checked and checked `--deep`, keyed as the golden keys them."""
    name = path.relative_to(ROOT).as_posix()
    return {
        name + (" --deep" if deep else ""): [
            _finding(item) for item in diagnose_file(path, deep=deep)
        ]
        for deep in (False, True)
    }


def findings() -> bytes:
    """Every finding of every kept document, as the golden's JSON."""
    table = {key: found for path in finding_documents() for key, found in findings_of(path).items()}
    text = json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def _plain(value: object) -> object:
    """A value the front ends return, as JSON can hold it."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return value.relative_to(ROOT).as_posix() if value.is_absolute() else value.as_posix()
    return value


def _refusal(exc: ScenetError) -> dict[str, Any]:
    return {
        "refused": type(exc).__name__,
        # Without the path `str()` puts in front, which is written as the system writes it.
        "message": getattr(exc, "detail", str(exc)),
        "rule": getattr(exc, "rule", None),
        "loc": list(getattr(exc, "loc", None) or ()),
        "line": getattr(exc, "line", None),
        "source": _plain(getattr(exc, "source", None)),
    }


def _reading(read: Callable[[], object]) -> object:
    try:
        return _plain(read())
    except ScenetError as exc:
        return _refusal(exc)


def parsed_of(path: Path) -> str:
    """The SHA-256 of what the front end reads from a document, or of its refusal.

    Each document is read twice, as a caller would: by the loader for its kind of file, and
    by the parser that reads the whole document -- a script's lines and notes, a scene's
    page layout, a panel file as the one panel of a scene.
    """
    text = path.read_text(encoding="utf-8")
    if path.name.endswith(".script"):
        readings = {
            "loaded": _reading(lambda: load_script(path)),
            "document": _reading(lambda: parse_script_document(text, source=path)),
        }
    elif path.name.endswith(".scene.yaml"):
        readings = {
            "loaded": _reading(lambda: load_scene(path)),
            "document": _reading(lambda: load_scene_document(path)),
        }
    else:
        readings = {
            "loaded": _reading(lambda: load_panel(path)),
            "document": _reading(lambda: parse_scene_document(text, source=path)),
        }
    encoded = json.dumps(readings, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parsed() -> bytes:
    """What every kept document reads as, as the golden's JSON."""
    table = {path.relative_to(ROOT).as_posix(): parsed_of(path) for path in finding_documents()}
    return (json.dumps(table, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
    if not FINDINGS.is_file() or FINDINGS.read_bytes() != findings():
        names.append(FINDINGS.relative_to(ROOT).as_posix())
    if not PARSED.is_file() or PARSED.read_bytes() != parsed():
        names.append(PARSED.relative_to(ROOT).as_posix())
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
    FINDINGS.write_bytes(findings())
    PARSED.write_bytes(parsed())


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
