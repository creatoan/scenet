"""Check the gallery as CI does: everything `scenet check` finds but the notes it declares.

Some examples give a note on purpose -- those grouped under "What Scenet tells you" (#240)
-- and their manifest entry declares it under `notes:`. `scenet check` reports them, as it
should; uploaded to code scanning as they are, they would be alerts nobody will ever fix.
So CI checks the gallery through this script instead. Each document is checked as
`scenet check` checks it, the notes its entry declares are dropped, and whatever is left
is printed, written as SARIF, and fails the run: an error, or a note nobody declared.

Run from the repository root, as CI does, so the SARIF's paths are the repository's:

    uv run python scripts/check_gallery.py -o results.sarif
"""

import argparse
import json
import sys
from collections.abc import Collection
from pathlib import Path

import yaml

from scenet.diagnostics import Diagnostic, diagnose_file, to_sarif

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "examples" / "gallery"


def undeclared(found: list[Diagnostic], declared: Collection[str]) -> list[Diagnostic]:
    """A document's findings, less the notes its manifest entry declares.

    Args:
        found: What checking the document found.
        declared: Its entry's `notes:`.

    Returns:
        Every error, and every note of a rule the entry does not declare, in order.
    """
    return [item for item in found if item.level == "error" or item.rule not in declared]


def findings() -> list[Diagnostic]:
    """What checking every document of the gallery finds that its entry does not declare."""
    manifest = yaml.safe_load((GALLERY / "manifest.yaml").read_text(encoding="utf-8"))
    found: list[Diagnostic] = []
    for entry in manifest["examples"]:
        found += undeclared(diagnose_file(GALLERY / entry["file"]), entry.get("notes", []))
    return found


def _line(item: Diagnostic) -> str:
    """A finding as `scenet check` prints it, its file relative to the repository."""
    source = item.source.relative_to(ROOT).as_posix() if item.source else "<string>"
    line = item.region.start.line if item.region else 1
    column = item.region.start.column if item.region else 1
    level = "note: " if item.level == "note" else ""
    return f"{source}:{line}:{column}: {level}{item.rule}: {item.message}"


def run(argv: list[str] | None = None) -> int:
    """Check the gallery, write SARIF if asked to, and exit 1 if anything is left."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, help="write the findings here, as SARIF")
    args = parser.parse_args(argv)

    found = findings()
    for item in found:
        print(_line(item), file=sys.stderr)
    if args.output:
        # Relative to the working directory, which code scanning matches results against,
        # and with a trailing newline, as `scenet check --format sarif` writes it.
        document = to_sarif(found, root=Path.cwd())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{json.dumps(document, indent=2, ensure_ascii=False)}\n",
            encoding="utf-8",
            newline="\n",
        )
    if not found:
        print("the gallery gives the notes its manifest declares, and nothing else")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(run())
