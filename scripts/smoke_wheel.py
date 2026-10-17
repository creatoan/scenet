"""Prove a built wheel installs and works, from outside the repository.

Run it from an empty directory, with the wheel installed and nothing else::

    cd "$(mktemp -d)"
    uv run --no-project --with dist/scenet-*.whl python /path/to/scripts/smoke_wheel.py

`import scenet` succeeding in the repository root proves nothing -- the source tree is
right there. From an empty directory, with no project on the path, it proves the wheel
carries the package, its metadata and its data files. `release.yml` runs this before
publishing and `ci.yml` on every pull request, so the two can never check different things.
"""

import importlib.resources

import scenet


def _require(condition: bool, problem: str) -> None:
    """Fail with the problem named -- an `assert` would vanish under `python -O`."""
    if not condition:
        raise SystemExit(f"wheel check failed: {problem}")


def main() -> None:
    """Check the version, the typing marker, and one panel compiled and rendered."""
    _require(scenet.__version__ != "0.0.0+unknown", "version metadata missing")
    _require(
        importlib.resources.files("scenet").joinpath("py.typed").is_file(),
        "py.typed missing from the wheel: downstream type checkers will ignore us",
    )
    result = scenet.compile_source("{cast: {a: {reference: alice}}}")
    _require(len(result.core.actors) == 1, "a one-actor panel did not compile to one actor")
    _require(scenet.render(result.core).lstrip().startswith("<?xml"), "rendering did not give SVG")
    print("wheel OK:", scenet.__version__, len(scenet.__all__), "public names")


if __name__ == "__main__":
    main()
