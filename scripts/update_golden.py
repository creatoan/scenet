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
  overlay, its live-text variant, each strip and each page. SVG is too large to review
  usefully as text, and its Core already says what moved.

After an intended change to the output, regenerate and review the diff:

    uv run python scripts/update_golden.py           # rewrite the goldens
    uv run python scripts/update_golden.py --check   # exit 1 if any is stale
"""

import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

from scenet.cli import main

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "examples" / "gallery"
GOLDEN = ROOT / "tests" / "golden"
CORES = GOLDEN / "core"
DIGESTS = GOLDEN / "digests.json"
COMMAND = "uv run python scripts/update_golden.py"

#: Two builds of every document: one with every output, one with live text, whose SVG
#: differs and whose Core does not.
VARIANTS = {
    "": ["--core", "--debug", "--strip"],
    "live-text/": ["--live-text", "--strip"],
}


def gallery() -> list[Path]:
    """Every document in the gallery, in a fixed order."""
    return sorted(path for path in GALLERY.iterdir() if path.name != "manifest.yaml")


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
        out = directory / prefix
        out.mkdir(parents=True, exist_ok=True)
        for source in sources:
            with contextlib.redirect_stdout(io.StringIO()):
                status = main(["build", str(source), "-o", f"{out}/", "--quiet", *flags])
            if status != 0:
                message = f"scenet build {source.name} exited {status}"
                raise RuntimeError(message)
        written |= {
            f"{prefix}{path.name}": path.read_bytes()
            for path in sorted(out.iterdir())
            if path.is_file()
        }
    return written


def goldens(written: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, str]]:
    """Split a build into the Core files kept whole and the SVG digests.

    Returns:
        Core file name to bytes, and SVG path to its SHA-256.
    """
    cores = {name: data for name, data in written.items() if name.endswith(".core.json")}
    digests = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(written.items())
        if name.endswith(".svg")
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
