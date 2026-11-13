"""The weekly mutation run is split into legs, and each is held to a threshold (#345).

One job mutating all of `solve/` and `emit/` stopped finishing: three weekly runs were
cancelled at the 120-minute limit, and a cancelled run saves no cache, so the next one
started from nothing again. `scripts/mutation.py` lists the legs; the workflow builds its
matrix from that list, runs each leg with its own cache, and fails a leg whose score falls
below its threshold. `docs/maintainer/testing.md` gives the same scores and thresholds.
"""

import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests import under_mutmut
from tests.under_mutmut import reads_the_source

ROOT = Path(__file__).resolve().parents[1]
TESTING = ROOT / "docs" / "maintainer" / "testing.md"


@pytest.fixture(scope="module")
def mutation() -> ModuleType:
    """Import `scripts/mutation.py`, which is a script rather than a package module."""
    path = ROOT / "scripts" / "mutation.py"
    spec = importlib.util.spec_from_file_location("mutation_legs", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutation_legs"] = module
    spec.loader.exec_module(module)
    return module


def _only_mutate() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["mutmut"]["only_mutate"]


def _sources() -> list[str]:
    return sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "src").rglob("*.py"))


def _matching(patterns: list[str] | tuple[str, ...]) -> set[str]:
    return {path for path in _sources() if any(fnmatch.fnmatch(path, p) for p in patterns)}


class TestTheLegs:
    @reads_the_source  # each leg's job narrows `only_mutate` to the leg before it runs
    def test_every_mutated_file_is_in_exactly_one_leg(self, mutation: ModuleType):
        """A new file under a mutated directory is mutated by the pull request's clean run
        at once, and fails this until it is given a leg, so no file goes unmutated weekly."""
        mutated = _matching(_only_mutate())
        seen: dict[str, str] = {}
        for leg in mutation.LEGS:
            for path in _matching(leg.paths):
                assert path not in seen, f"{path} is in {seen[path]} and {leg.name}"
                seen[path] = leg.name
        assert set(seen) == mutated

    def test_every_path_of_a_leg_names_a_file(self, mutation: ModuleType):
        for leg in mutation.LEGS:
            for path in leg.paths:
                assert (ROOT / path).is_file(), f"{leg.name}: {path}"

    @pytest.mark.parametrize(
        "module",
        [
            "src/scenet/frontends/*",
            "src/scenet/core.py",
            "src/scenet/ir.py",
            "src/scenet/diagnostics.py",
        ],
    )
    def test_the_modules_past_solve_and_emit_are_mutated_in_legs_of_their_own(
        self, mutation: ModuleType, module: str
    ):
        """The issue's four, each apart from the solver, the emitters and one another."""
        files = _matching([module])
        assert files
        holding = [leg for leg in mutation.LEGS if _matching(leg.paths) & files]
        assert holding
        for leg in holding:
            assert _matching(leg.paths) <= files, leg.name

    def test_names_and_cache_keys_are_unique(self, mutation: ModuleType):
        names = [leg.name for leg in mutation.LEGS]
        keys = [leg.key for leg in mutation.LEGS]
        assert len(set(names)) == len(names)
        assert len(set(keys)) == len(keys)
        assert all(re.fullmatch(r"[a-z0-9-]+", key) for key in keys)

    def test_every_threshold_is_a_whole_percent_at_or_under_its_score(self, mutation: ModuleType):
        for leg in mutation.LEGS:
            assert leg.threshold == int(leg.threshold), leg.name
            assert 0 < leg.threshold <= leg.score, leg.name


#: What `also_copy` leaves out: mutmut copies `src/`, `tests/` and `uv.lock` itself, and
#: `.claude/` holds agents' settings and worktrees, which no test reads.
NOT_COPIED = {"src", "tests", "uv.lock", ".claude"}


def test_the_mutants_tree_holds_everything_at_the_top_of_the_repository():
    """mutmut's clean run runs the suite in `mutants/`, which holds `also_copy` and no more.

    `tests/test_contributor_docs.py` reads `CHANGELOG.md`, which was not copied, so the
    clean run failed before a single mutant was tried.
    """
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    listed = subprocess.run(  # noqa: S603 -- git, found on PATH, with literal arguments
        [git, "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    tracked = {line.split("/", 1)[0] for line in listed.splitlines() if line}
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    copied = {entry.rstrip("/") for entry in config["tool"]["mutmut"]["also_copy"]}
    assert tracked - NOT_COPIED == copied


class TestTheMatrix:
    def test_a_scheduled_run_has_every_leg(self, mutation: ModuleType):
        matrix = json.loads(mutation.matrix())
        assert [leg["name"] for leg in matrix["include"]] == [leg.name for leg in mutation.LEGS]
        first = matrix["include"][0]
        leg = mutation.LEGS[0]
        assert first == {
            "name": leg.name,
            "key": leg.key,
            "paths": " ".join(leg.paths),
            "threshold": f"{leg.threshold:g}",
        }

    def test_named_legs_alone(self, mutation: ModuleType):
        wanted = [mutation.LEGS[-1].name, mutation.LEGS[0].name]
        matrix = json.loads(mutation.matrix(legs=",".join(wanted)))
        assert [leg["name"] for leg in matrix["include"]] == [
            mutation.LEGS[0].name,
            mutation.LEGS[-1].name,
        ]

    def test_an_unknown_leg_is_refused(self, mutation: ModuleType):
        with pytest.raises(SystemExit, match="no leg named 'nowhere'"):
            mutation.matrix(legs="nowhere")

    def test_a_path_is_one_leg_with_no_threshold(self, mutation: ModuleType):
        """A run on one file is a probe during triage, not a score to hold."""
        matrix = json.loads(mutation.matrix(path="src/scenet/solve/camera.py"))
        (leg,) = matrix["include"]
        assert leg["paths"] == "src/scenet/solve/camera.py"
        assert leg["threshold"] == ""
        assert re.fullmatch(r"path-[0-9a-f]{12}", leg["key"])

    def test_two_paths_do_not_share_a_cache(self, mutation: ModuleType):
        one = json.loads(mutation.matrix(path="src/scenet/solve/camera.py"))
        two = json.loads(mutation.matrix(path="src/scenet/solve/text.py"))
        assert one["include"][0]["key"] != two["include"][0]["key"]


class TestNarrowing:
    def test_only_mutate_becomes_the_leg_s_paths(self, mutation: ModuleType):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        narrowed = mutation.narrowed(text, ["src/scenet/core.py", "src/scenet/ir.py"])
        config = tomllib.loads(narrowed)["tool"]["mutmut"]
        assert config["only_mutate"] == ["src/scenet/core.py", "src/scenet/ir.py"]
        assert narrowed.replace(
            'only_mutate = ["src/scenet/core.py", "src/scenet/ir.py"]', ""
        ) == mutation.ONLY_MUTATE.sub("", text, count=1)

    def test_a_quote_cannot_escape_the_list(self, mutation: ModuleType):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        narrowed = mutation.narrowed(text, ['src/scenet/core.py"]\nx = ["'])
        assert tomllib.loads(narrowed)["tool"]["mutmut"]["only_mutate"] == [
            "src/scenet/core.py]\nx = ["
        ]

    def test_a_file_with_no_only_mutate_is_refused(self, mutation: ModuleType):
        with pytest.raises(SystemExit, match="only_mutate"):
            mutation.narrowed("[tool.mutmut]\n", ["src/scenet/core.py"])


def _stats(**changes: int) -> dict[str, Any]:
    stats = {
        "killed": 90,
        "survived": 8,
        "total": 100,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 2,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    stats.update(changes)
    return stats


class TestTheScore:
    def test_a_timeout_is_a_kill(self, mutation: ModuleType):
        assert mutation.Score.of(_stats()).percent == pytest.approx(92.0)

    def test_a_skipped_mutant_is_not_counted(self, mutation: ModuleType):
        score = mutation.Score.of(_stats(total=110, skipped=10))
        assert score.percent == pytest.approx(92.0)

    def test_a_mutant_no_test_reaches_is_not_a_kill(self, mutation: ModuleType):
        score = mutation.Score.of(_stats(killed=88, no_tests=2))
        assert score.percent == pytest.approx(90.0)

    def test_untried_mutants_are_counted(self, mutation: ModuleType):
        """`total` holds every mutant, tried or not, and nothing else says how many were
        left: the lesson of runs that looked clean because they stopped early."""
        score = mutation.Score.of(_stats(total=130))
        assert score.untried == 30
        assert mutation.Score.of(_stats()).untried == 0

    def test_the_summary_says_the_score_and_what_is_left(self, mutation: ModuleType):
        summary = mutation.Score.of(_stats(total=130)).markdown()
        assert "**70.8%** killed: 92 of 130 mutants" in summary
        assert "8 survived" in summary
        assert "30 never tried" in summary


class TestTheGate:
    def test_a_score_at_its_threshold_passes(self, mutation: ModuleType):
        assert mutation.failures(mutation.Score.of(_stats()), threshold="92") == []

    def test_a_score_below_its_threshold_fails(self, mutation: ModuleType):
        (failure,) = mutation.failures(mutation.Score.of(_stats()), threshold="93")
        assert "92.0% is below the threshold of 93%" in failure

    def test_a_run_that_left_mutants_untried_fails(self, mutation: ModuleType):
        (failure,) = mutation.failures(mutation.Score.of(_stats(total=101)), threshold="")
        assert "1 of 101 mutants were never tried" in failure

    def test_no_threshold_holds_only_the_finish(self, mutation: ModuleType):
        score = mutation.Score.of(_stats(killed=10, survived=88))
        assert score.untried == 0
        assert mutation.failures(score, threshold="") == []

    def test_no_stats_at_all_fails(self, mutation: ModuleType, tmp_path: Path):
        assert mutation.gate(tmp_path / "missing.json", threshold="90") == 1

    def test_the_gate_reads_the_file(self, mutation: ModuleType, tmp_path: Path):
        stats = tmp_path / "stats.json"
        stats.write_text(json.dumps(_stats()), encoding="utf-8", newline="\n")
        assert mutation.gate(stats, threshold="92") == 0
        assert mutation.gate(stats, threshold="95") == 1


class TestTheCleanRun:
    """The pull request's job runs mutmut up to its forced-fail test and stops there."""

    def test_it_stops_after_the_forced_fail_test(self, mutation: ModuleType):
        calls: list[str] = []

        class Main:
            def run_forced_fail_test(self, runner: object) -> None:
                calls.append(f"forced fail on {runner}")

            def _run(self, names: tuple[str, ...], max_children: int) -> None:
                calls.append(f"clean run, {max_children} children")
                self.run_forced_fail_test("the runner")
                calls.append("a mutant")

        with pytest.raises(SystemExit) as stopped:
            mutation.clean_run(Main(), max_children=4)
        assert stopped.value.code == 0
        assert calls == ["clean run, 4 children", "forced fail on the runner"]

    def test_a_mutmut_that_never_reaches_the_forced_fail_test_fails(self, mutation: ModuleType):
        class Main:
            def run_forced_fail_test(self, runner: object) -> None:
                pass

            def _run(self, names: tuple[str, ...], max_children: int) -> None:
                pass

        assert mutation.clean_run(Main(), max_children=4) == 1

    def test_mutmut_still_has_what_it_stops_at(self, mutation: ModuleType):
        """`_run` is mutmut's own, so a new mutmut that renamed it fails here first."""
        if sys.platform == "win32":
            pytest.skip("mutmut exits on import on Windows: it needs fork()")
        mutmut_main = pytest.importorskip("mutmut.__main__")
        assert callable(mutmut_main.run_forced_fail_test)
        assert callable(mutmut_main._run)  # pyright: ignore[reportPrivateUsage]


class TestTheDocument:
    """`docs/maintainer/testing.md` gives each leg's score and threshold, as the script has
    them, and the run they were measured on."""

    @pytest.fixture(scope="class")
    @classmethod
    def rows(cls) -> dict[str, list[str]]:
        text = TESTING.read_text(encoding="utf-8")
        table = text.split("### Scores and thresholds", 1)[1].split("\n\n", 2)[1]
        found: dict[str, list[str]] = {}
        for line in table.splitlines()[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            found[cells[0].strip("`")] = cells
        return found

    def test_every_leg_has_a_row(self, mutation: ModuleType, rows: dict[str, list[str]]):
        assert list(rows) == [leg.name for leg in mutation.LEGS]

    def test_each_row_gives_its_leg_s_score_and_threshold(
        self, mutation: ModuleType, rows: dict[str, list[str]]
    ):
        for leg in mutation.LEGS:
            _, files, mutants, survivors, score, threshold, run = rows[leg.name]
            assert files == ", ".join(f"`{path.removeprefix('src/scenet/')}`" for path in leg.paths)
            assert int(mutants.replace(",", "")) == leg.mutants, leg.name
            assert int(survivors) == leg.survivors, leg.name
            assert score == f"{leg.score:.1f}%", leg.name
            assert threshold == f"{leg.threshold:g}%", leg.name
            assert (
                run == f"[`{leg.run}`](https://github.com/creatoan/scenet/actions/runs/{leg.run})"
            )


class TestTheStatsStayInThisProcess:
    """A child of mutmut's stats run imports the mutants with nothing to record into."""

    def test_the_stats_run_s_variable_is_dropped(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "stats")
        under_mutmut.keep_the_stats_in_this_process()
        assert "MUTANT_UNDER_TEST" not in os.environ

    @pytest.mark.parametrize("value", ["", "fail", "scenet.ir.x_tag_by__mutmut_3"])
    def test_any_other_run_keeps_it(self, monkeypatch: pytest.MonkeyPatch, value: str):
        """A child of a mutant's run runs the mutant, and one of the forced-fail run fails."""
        monkeypatch.setenv("MUTANT_UNDER_TEST", value)
        under_mutmut.keep_the_stats_in_this_process()
        assert os.environ["MUTANT_UNDER_TEST"] == value

    def test_outside_mutmut_nothing_is_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MUTANT_UNDER_TEST", raising=False)
        under_mutmut.keep_the_stats_in_this_process()
        assert "MUTANT_UNDER_TEST" not in os.environ


class TestTheCleanRunIsSharded:
    """The clean run is the suite three times over -- coverage, stats, clean -- each slower
    than a plain run, and the stats run three times slower with every function behind a
    trampoline. Run whole, it took 22 minutes. A pull request runs it as four shards of the
    test files, without the coverage pass, which decides only which lines get mutants."""

    def test_the_shards_split_the_test_files_between_them(self, mutation: ModuleType):
        files = mutation.test_files()
        shards = [mutation.shard(files, number, of=4) for number in range(1, 5)]
        assert all(shards)
        assert sorted(path for one in shards for path in one) == sorted(files)

    def test_every_test_file_is_found(self, mutation: ModuleType):
        files = mutation.test_files()
        assert "tests/test_mutation_legs.py" in files
        assert any(path.startswith("tests/properties/") for path in files)
        assert all(path.startswith("tests/") and path.endswith(".py") for path in files)
        assert len(files) == len(set(files))

    def test_the_shards_are_near_one_size(self, mutation: ModuleType):
        files = mutation.test_files()
        sizes = [
            sum((ROOT / path).stat().st_size for path in mutation.shard(files, number, of=4))
            for number in range(1, 5)
        ]
        assert max(sizes) < 1.25 * min(sizes)

    def test_a_shard_number_out_of_range_is_refused(self, mutation: ModuleType):
        with pytest.raises(SystemExit, match="shard 5 of 4"):
            mutation.shard(mutation.test_files(), 5, of=4)

    def test_the_configuration_runs_the_shard_s_files_without_coverage(self, mutation: ModuleType):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        config = tomllib.loads(
            mutation.for_a_shard(text, ["tests/test_ir.py", "tests/test_page.py"])
        )
        mutmut = config["tool"]["mutmut"]
        assert mutmut["pytest_add_cli_args_test_selection"] == [
            "tests/test_ir.py",
            "tests/test_page.py",
        ]
        assert mutmut["mutate_only_covered_lines"] is False
        assert mutmut["only_mutate"] == _only_mutate()
