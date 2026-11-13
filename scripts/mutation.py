"""The weekly mutation run's legs, and what `.github/workflows/mutation.yml` does with each.

One job mutating everything stopped finishing inside its time limit. The run is split
into the legs below instead. Each runs as its own job, from nothing, and fails when its
score falls below its threshold, or when it stops with mutants it never tried.
`docs/maintainer/testing.md` gives the same table, and a test holds the two together.

    python scripts/mutation.py matrix [--legs NAME,...] [--path GLOB]
    python scripts/mutation.py narrow PATH...
    python scripts/mutation.py report mutants/mutmut-cicd-stats.json
    python scripts/mutation.py gate mutants/mutmut-cicd-stats.json --threshold 90
    python scripts/mutation.py clean-run --shard 1/4 --max-children 4

`clean-run` is the pull request's check: `mutmut run` up to its forced-fail test, every
leg's files mutated, and nothing after. A test that reads a generated file or the package's
source text breaks there and nowhere else (#139, #152, #193, #345). Whole, it took 22
minutes, so it runs as shards of the test files, each in a job of its own.
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
TESTS = ROOT / "tests"
#: `[tool.mutmut]`'s list of what to mutate, over as many lines as it is written on.
ONLY_MUTATE = re.compile(r"^only_mutate = \[[^\]]*\]", re.MULTILINE)
#: The tests mutmut runs, and whether it mutates only the lines they cover.
TEST_SELECTION = re.compile(r"^pytest_add_cli_args_test_selection = \[[^\]]*\]", re.MULTILINE)
COVERED_LINES = re.compile(r"^mutate_only_covered_lines = \w+", re.MULTILINE)


@dataclass(frozen=True)
class Leg:
    """One job of the weekly run, and what its last full run measured.

    Attributes:
        name: What the job is called, and the row of the table in `testing.md`.
        paths: The files it mutates, as `only_mutate` patterns.
        threshold: The lowest score that passes, in whole percent.
        score: The share of mutants killed when it was last measured, in percent.
        mutants: How many mutants that run tried.
        survivors: How many of them survived, each killed since or accepted in `testing.md`.
        run: The Actions run it was measured on, which survivors are numbered from.
    """

    name: str
    paths: tuple[str, ...]
    threshold: float
    score: float
    mutants: int
    survivors: int
    run: int

    @property
    def key(self) -> str:
        """The leg's name as its artifact is named: lower case, letters, digits and dashes."""
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


def _in(directory: str, *names: str) -> tuple[str, ...]:
    return tuple(f"src/scenet/{directory}{name}" for name in names)


#: Every file `[tool.mutmut]` mutates, in exactly one leg each, sized to finish from nothing
#: well inside the job's 180 minutes on a four-core runner. About 17 minutes go on syncing
#: and on mutmut's coverage, stats and clean runs; then a mutant takes from under a second
#: to minutes, by how much of the suite reaches the function it changed.
LEGS: tuple[Leg, ...] = (
    Leg("solve/balloons", _in("solve/", "balloons.py"), 97, 97.9, 1371, 29, 43410981157),
    Leg("solve/backdrop", _in("solve/", "backdrop.py"), 99, 99.2, 1060, 8, 43410981157),
    Leg(
        "solve/text",
        _in(
            "solve/",
            "__init__.py",
            "camera.py",
            "figures.py",
            "speakers.py",
            "staging.py",
            "text.py",
        ),
        92,
        92.5,
        1284,
        96,
        43410981157,
    ),
    Leg(
        "solve/page",
        _in("solve/", "describe.py", "page.py", "sfx.py"),
        96,
        96.7,
        1414,
        46,
        43410981157,
    ),
    Leg("emit/pdf", _in("emit/", "pdf.py"), 97, 97.7, 1388, 32, 43410981157),
    Leg(
        "emit/pdf parts",
        _in("emit/", "pdf_fonts.py", "pdf_images.py"),
        95,
        95.2,
        979,
        47,
        43410981157,
    ),
    Leg("emit/svg", _in("emit/", "marks.py", "svg.py"), 98, 98.8, 1370, 16, 43410981157),
    Leg(
        "emit/drawing",
        _in("emit/", "debug_svg.py", "geometry.py", "page.py", "strip.py"),
        98,
        98.9,
        1093,
        12,
        43410981157,
    ),
    Leg(
        "emit/other",
        _in(
            "emit/",
            "__init__.py",
            "boxes.py",
            "cmyk.py",
            "conditioning.py",
            "depth.py",
            "export.py",
            "mask.py",
            "pose.py",
            "preview.py",
            "semantics.py",
            "turbulence.py",
        ),
        95,
        95.7,
        1006,
        43,
        43410981157,
    ),
    Leg("frontends/script", _in("frontends/", "script_front.py"), 84, 84.2, 2104, 333, 43410981157),
    Leg(
        "frontends/common",
        _in("frontends/", "__init__.py", "common.py"),
        91,
        91.2,
        500,
        44,
        43429063598,
    ),
    Leg(
        "frontends/yaml",
        _in("frontends/", "positions.py", "yaml_front.py"),
        80,
        80.2,
        359,
        71,
        43429063598,
    ),
    Leg("core", _in("", "core.py"), 91, 91.2, 351, 31, 43410981157),
    Leg("ir", _in("", "ir.py"), 86, 86.7, 165, 22, 43410981157),
    Leg("diagnostics", _in("", "diagnostics.py"), 83, 83.7, 1603, 262, 43410981157),
)


# ---------------------------------------------------------------- the matrix


def _row(name: str, key: str, paths: tuple[str, ...], threshold: str) -> dict[str, str]:
    return {"name": name, "key": key, "paths": " ".join(paths), "threshold": threshold}


def matrix(legs: str = "", path: str = "") -> str:
    """The workflow's `strategy.matrix`, as JSON.

    Args:
        legs: Comma-separated leg names to run alone; every leg when empty.
        path: One `only_mutate` pattern to run instead of any leg, with no threshold:
            a probe during triage, not a score to hold.

    Returns:
        `{"include": [...]}`, one entry per job, each a name, an artifact key, the paths
        separated by spaces, and the threshold, empty when there is none.
    """
    if path:
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        rows = [_row(path, f"path-{digest}", (path,), "")]
    else:
        wanted = {name.strip() for name in legs.split(",") if name.strip()}
        unknown = sorted(wanted - {leg.name for leg in LEGS})
        if unknown:
            sys.exit(f"no leg named {unknown[0]!r}: the legs are in scripts/mutation.py")
        rows = [
            _row(leg.name, leg.key, leg.paths, f"{leg.threshold:g}")
            for leg in LEGS
            if not wanted or leg.name in wanted
        ]
    return json.dumps({"include": rows})


# ---------------------------------------------------------------- narrowing


def narrowed(text: str, paths: list[str]) -> str:
    """`pyproject.toml` with `[tool.mutmut]`'s `only_mutate` set to these paths alone."""
    line = "only_mutate = " + json.dumps([path.replace('"', "") for path in paths])
    replaced, count = re.subn(ONLY_MUTATE, lambda _: line, text, count=1)
    if count != 1:
        sys.exit("pyproject.toml has no only_mutate line to narrow")
    return replaced


# ---------------------------------------------------------------- the pull request's shards


def test_files() -> list[str]:
    """Every test file under `tests/`, as a path from the repository's root."""
    return sorted(path.relative_to(ROOT).as_posix() for path in TESTS.rglob("test_*.py"))


def shard(files: list[str], number: int, of: int) -> list[str]:
    """One of `of` shards of the test files, numbered from 1, near one size in bytes.

    The largest file goes to the smallest shard, then the next largest, and so on: a file's
    size is a fair guess at how long it runs, and the split stays the same until the files
    change.
    """
    if not 1 <= number <= of:
        sys.exit(f"there is no shard {number} of {of}")
    shards: list[list[str]] = [[] for _ in range(of)]
    sizes = [0] * of
    for path in sorted(files, key=lambda path: (-(ROOT / path).stat().st_size, path)):
        smallest = sizes.index(min(sizes))
        shards[smallest].append(path)
        sizes[smallest] += (ROOT / path).stat().st_size
    return sorted(shards[number - 1])


def for_a_shard(text: str, tests: list[str]) -> str:
    """`pyproject.toml` with mutmut running these tests alone, and mutating every line.

    The coverage pass, which decides which lines get mutants, is a run of the suite of its
    own, and a clean run tries no mutant, so it is left out.
    """
    selection = "pytest_add_cli_args_test_selection = " + json.dumps(tests)
    text, found = TEST_SELECTION.subn(lambda _: selection, text, count=1)
    text, covered = COVERED_LINES.subn("mutate_only_covered_lines = false", text, count=1)
    if not (found and covered):
        sys.exit("pyproject.toml has no test selection, or no mutate_only_covered_lines, to set")
    return text


# ---------------------------------------------------------------- the score


@dataclass(frozen=True)
class Score:
    """What `mutmut export-cicd-stats` counted, read the way the thresholds are.

    A timeout is a kill: the mutant made the tests hang, which they noticed. A skipped
    mutant is not counted. A mutant no test reaches counts as a survivor.

    Attributes:
        killed: Mutants the tests failed on, timeouts included.
        survived: Mutants the tests passed.
        tested: Every mutant but the skipped.
        untried: Mutants the run never reached. `total` counts them and nothing else says
            how many there are, so they are what is left once every outcome is counted.
        stats: The file as mutmut wrote it.
    """

    killed: int
    survived: int
    tested: int
    untried: int
    stats: dict[str, int]

    @classmethod
    def of(cls, stats: dict[str, Any]) -> "Score":
        """Read `mutmut-cicd-stats.json`'s counts."""
        counts = {key: int(value) for key, value in stats.items()}
        outcomes = sum(value for key, value in counts.items() if key != "total")
        return cls(
            killed=counts["killed"] + counts["timeout"],
            survived=counts["survived"] + counts["no_tests"],
            tested=counts["total"] - counts["skipped"],
            untried=counts["total"] - outcomes,
            stats=counts,
        )

    @property
    def percent(self) -> float:
        """The share of tested mutants killed; 0 when none was tested."""
        return 100 * self.killed / self.tested if self.tested else 0.0

    def markdown(self) -> str:
        """The job summary's lines: the score, then every count mutmut gave."""
        lines = [
            f"**{self.percent:.1f}%** killed: {self.killed} of {self.tested} mutants "
            f"({self.survived} survived, {self.untried} never tried).",
            "",
            "| | |",
            "|---|---|",
            *(f"| {key} | {value} |" for key, value in self.stats.items()),
        ]
        return "\n".join(lines)


def failures(score: Score, threshold: str) -> list[str]:
    """Why a leg fails: mutants it never tried, or a score below its threshold."""
    found: list[str] = []
    if score.untried:
        found.append(
            f"{score.untried} of {score.stats['total']} mutants were never tried, so the "
            "score counts them as survivors and its survivors are not the whole list"
        )
    if threshold and score.percent < float(threshold):
        found.append(
            f"{score.percent:.1f}% is below the threshold of {threshold}%: a new survivor "
            "is killed by a test, or accepted in docs/maintainer/testing.md"
        )
    return found


def gate(stats: Path, threshold: str) -> int:
    """Print each failure as a workflow error; 1 if there is any, or no stats at all."""
    if not stats.is_file():
        print(f"::error::{stats} is missing: mutmut tried no mutant", file=sys.stderr)
        return 1
    found = failures(Score.of(json.loads(stats.read_text(encoding="utf-8"))), threshold)
    for failure in found:
        print(f"::error::{failure}", file=sys.stderr)
    return 1 if found else 0


# ---------------------------------------------------------------- the clean run


class _Mutmut(Protocol):
    """The two functions of `mutmut.__main__` the clean run needs."""

    def run_forced_fail_test(self, runner: object, /) -> None: ...

    def _run(self, mutant_names: tuple[str, ...], max_children: int, /) -> None: ...


class _Stop(SystemExit):
    """Raised once the forced-fail test has passed, to leave `mutmut run` there."""


def clean_run(main: _Mutmut, max_children: int) -> int:
    """Run mutmut up to and including its forced-fail test, then stop.

    `mutmut run` copies the tree into `mutants/`, rewrites every file it mutates, runs the
    suite there twice -- collecting stats, then clean -- and checks that a forced failure
    fails it. Only then does it try mutants. Every break of the weekly run so far was in
    those first steps, so a pull request runs them and nothing after.

    Args:
        main: `mutmut.__main__`, or a stand-in with the same two functions.
        max_children: Processes mutmut may fork.

    Returns:
        1 if mutmut finished without reaching the forced-fail test, which means a new
        mutmut no longer runs it there. Exits 0 once it has passed.
    """
    forced_fail = main.run_forced_fail_test

    def stop_after(runner: object) -> None:
        forced_fail(runner)
        print("The suite passes in the mutants tree, and a forced failure fails it.")
        raise _Stop(0)

    main.run_forced_fail_test = stop_after  # type: ignore[method-assign]  # the seam
    main._run((), max_children)  # pyright: ignore[reportPrivateUsage]
    print("::error::mutmut never reached its forced-fail test", file=sys.stderr)
    return 1


# ---------------------------------------------------------------- the command


def main() -> None:
    """Run one of the subcommands above."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("matrix", help="print the workflow's matrix as JSON")
    plan.add_argument("--legs", default="")
    plan.add_argument("--path", default="")
    narrow = commands.add_parser("narrow", help="set only_mutate in pyproject.toml")
    narrow.add_argument("paths", nargs="+")
    report = commands.add_parser("report", help="print the job summary's score")
    report.add_argument("stats", type=Path)
    hold = commands.add_parser("gate", help="fail below the threshold, or if unfinished")
    hold.add_argument("stats", type=Path)
    hold.add_argument("--threshold", default="")
    clean = commands.add_parser("clean-run", help="mutmut up to its forced-fail test")
    clean.add_argument("--shard", default="1/1", help="which of how many, e.g. 2/4")
    clean.add_argument("--max-children", type=int, default=4)
    args = parser.parse_args()

    if args.command == "matrix":
        print(matrix(args.legs, args.path))
    elif args.command == "narrow":
        text = PYPROJECT.read_text(encoding="utf-8")
        PYPROJECT.write_text(narrowed(text, args.paths), encoding="utf-8", newline="\n")
    elif args.command == "report":
        if args.stats.is_file():
            print(Score.of(json.loads(args.stats.read_text(encoding="utf-8"))).markdown())
        else:
            print("No mutant was tried.")
    elif args.command == "gate":
        sys.exit(gate(args.stats, args.threshold))
    else:
        number, _, of = args.shard.partition("/")
        tests = shard(test_files(), int(number), int(of))
        print(f"Shard {args.shard}: {len(tests)} test files.")
        text = PYPROJECT.read_text(encoding="utf-8")
        PYPROJECT.write_text(for_a_shard(text, tests), encoding="utf-8", newline="\n")
        import mutmut.__main__ as mutmut_main  # noqa: PLC0415  # Linux only: it forks

        sys.exit(clean_run(mutmut_main, args.max_children))  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
