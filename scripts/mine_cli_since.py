"""Mine the release each command and option of the command line appeared in, from the tags.

`docs/reference/cli.md` says, for every command and every option, the minor release it came
in. Those versions come from `docs/reference/cli.since.toml`, which this writes by reading
`src/scenet/cli.py` at every release tag: the subcommands `add_parser` names, and the options
each `add_argument` gives them, the parser's own included. A command or an option the
current parser has and no tag had takes the next minor version.

`tests/test_reference_contract.py` holds the reference to the file, and the file to the
current parser.

Run from the repository root after adding a command or an option:

    uv run python scripts/mine_cli_since.py           # rewrite cli.since.toml
    uv run python scripts/mine_cli_since.py --check   # exit 1 if it is stale
"""

import argparse
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SINCE = ROOT / "docs" / "reference" / "cli.since.toml"
CLI = "src/scenet/cli.py"


def _git(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def _tags() -> list[str]:
    listed = _git("tag", "--list", "v*").split()
    return sorted(listed, key=lambda tag: tuple(int(part) for part in tag[1:].split(".")))


def interface(source: str) -> tuple[set[str], dict[str, set[str]]]:
    """The subcommands a version of `cli.py` defines, and each one's options.

    An option of the parser itself is listed under `""`. A group a subcommand makes, mutually
    exclusive or not, adds its options to that subcommand.
    """
    tree = ast.parse(source)
    owner: dict[str, str] = {"parser": ""}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        call, target = node.value, node.targets[0]
        if not (isinstance(call.func, ast.Attribute) and isinstance(target, ast.Name)):
            continue
        base = call.func.value.id if isinstance(call.func.value, ast.Name) else None
        if call.func.attr == "add_parser" and call.args and isinstance(call.args[0], ast.Constant):
            owner[target.id] = str(call.args[0].value)
        elif call.func.attr.endswith("_group") and base in owner:
            owner[target.id] = owner[base]
    options: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        base = node.func.value.id if isinstance(node.func.value, ast.Name) else None
        if node.func.attr != "add_argument" or base not in owner:
            continue
        flags = [
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
            and argument.value.startswith("-")
        ]
        if flags:
            options.setdefault(owner[base], set()).add(max(flags, key=len))
    return {name for name in owner.values() if name}, options


def mine() -> str:
    """`cli.since.toml`, from `cli.py` at every release tag and as it is now."""
    commands: dict[str, str] = {}
    options: dict[str, str] = {}
    top: dict[str, str] = {}
    tags = _tags()
    for tag in tags:
        version = ".".join(tag[1:].split(".")[:2])
        named, given = interface(_git("show", f"{tag}:{CLI}"))
        for command in named:
            commands.setdefault(command, version)
        for command, flags in given.items():
            for flag in flags:
                if command:
                    options.setdefault(f"{command} {flag}", version)
                else:
                    top.setdefault(flag, version)
    latest = tags[-1][1:].split(".")
    upcoming = f"{latest[0]}.{int(latest[1]) + 1}"
    named, given = interface((ROOT / CLI).read_text(encoding="utf-8"))
    current_options = {f"{c} {f}" for c, flags in given.items() if c for f in flags}
    current_top = given.get("", set())
    for command in named:
        commands.setdefault(command, upcoming)
    for option in current_options:
        options.setdefault(option, upcoming)
    for flag in current_top:
        top.setdefault(flag, upcoming)

    def table(name: str, entries: dict[str, str], keep: set[str]) -> list[str]:
        rows = [f'"{key}" = "{entries[key]}"' for key in sorted(entries) if key in keep]
        return [f"[{name}]", *rows, ""]

    lines = [
        "# The minor release each command and option of `scenet` appeared in: the first release",
        "# tag whose `src/scenet/cli.py` defined it. One added since the last release takes the",
        "# next minor version. An option is named by its long form, after its command.",
        "#",
        "# Mined from the tags by `uv run python scripts/mine_cli_since.py`.",
        "",
        *table("top-level", top, current_top),
        *table("commands", commands, named),
        *table("options", options, current_options),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    """Rewrite `cli.since.toml`, or with `--check` report whether it is stale."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report whether it is stale")
    args = parser.parse_args()
    expected = mine()
    current = SINCE.read_text(encoding="utf-8") if SINCE.exists() else ""
    if args.check:
        if current != expected:
            print(f"stale: {SINCE.relative_to(ROOT)}", file=sys.stderr)
            return 1
        return 0
    if current != expected:
        SINCE.write_text(expected, encoding="utf-8", newline="\n")
        print(f"wrote {SINCE.relative_to(ROOT)}")
    else:
        print("everything is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
