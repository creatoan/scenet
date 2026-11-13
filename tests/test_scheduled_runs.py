"""A scheduled workflow that fails says so, in an issue somebody is notified of.

The link check was red for eleven weeks and the mutation run for six before anyone looked:
a scheduled run's failure reaches nobody unless something tells them. So every workflow with
a `schedule:` trigger ends in one job that calls `.github/workflows/scheduled-report.yml`,
which opens an issue titled with the workflow's name on a failure, comments on that issue
on the next one, and closes it on the next success.

The script is plain shell over the `gh` CLI, so it runs here against a fake `gh` that
records what it was asked to do. Whether the real `gh` finds the issue it opened is shown
on GitHub, by the forced failures `linkcheck.yml` can be dispatched with.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
REPORT = "scheduled-report.yml"
CALL = f"./.github/workflows/{REPORT}"
RESULTS = "${{ join(needs.*.result, ' ') }}"


def _load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads a bare `on` as the boolean True, which is how PyYAML sees it.
    return workflow.get("on") or workflow[True]


def _scheduled() -> list[Path]:
    return sorted(path for path in WORKFLOWS.glob("*.yml") if "schedule" in _triggers(_load(path)))


def _reporters(workflow: dict[Any, Any]) -> dict[str, dict[Any, Any]]:
    return {name: job for name, job in workflow["jobs"].items() if job.get("uses") == CALL}


def _needs(job: dict[Any, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def test_the_scheduled_workflows_are_found():
    names = [path.name for path in _scheduled()]
    assert {"linkcheck.yml", "mutation.yml", "codeql.yml"} <= set(names)
    assert REPORT not in names


@pytest.mark.parametrize("path", _scheduled(), ids=lambda p: p.name)
class TestEveryScheduledWorkflowReports:
    """Each workflow with `schedule:`, listed by name in the test ids."""

    def test_it_calls_the_report_once(self, path: Path):
        assert len(_reporters(_load(path))) == 1, f"{path.name} does not call {CALL}"

    def test_the_report_waits_for_every_last_job(self, path: Path):
        """A job it does not wait for is a failure it cannot see.

        Waiting for the jobs nothing else waits for is enough: a job that fails before them
        leaves them skipped, and a skipped job is reported as a failure.
        """
        workflow = _load(path)
        ((name, job),) = _reporters(workflow).items()
        others = {other: body for other, body in workflow["jobs"].items() if other != name}
        needed = {need for body in others.values() for need in _needs(body)}
        assert set(_needs(job)) == set(others) - needed

    def test_it_runs_after_a_failure_but_not_after_a_cancellation(self, path: Path):
        """`always()` would also report a run somebody cancelled, or a newer push replaced."""
        ((_, job),) = _reporters(_load(path)).items()
        assert job["if"].startswith("${{ !cancelled() && ")
        assert "github.event_name == 'schedule'" in job["if"]

    def test_it_hands_over_every_result(self, path: Path):
        ((_, job),) = _reporters(_load(path)).items()
        assert job["with"] == {"results": RESULTS}

    def test_it_alone_may_write_issues(self, path: Path):
        workflow = _load(path)
        ((name, job),) = _reporters(workflow).items()
        assert job["permissions"] == {"issues": "write"}
        assert "issues" not in (workflow.get("permissions") or {})
        for other, body in workflow["jobs"].items():
            if other != name:
                assert "issues" not in (body.get("permissions") or {}), other


class TestTheReportWorkflow:
    @pytest.fixture(scope="class")
    @classmethod
    def report(cls) -> dict[Any, Any]:
        return _load(WORKFLOWS / REPORT)

    def test_it_can_only_be_called(self, report: dict[Any, Any]):
        assert set(_triggers(report)) == {"workflow_call"}
        assert set(_triggers(report)["workflow_call"]["inputs"]) == {"results"}

    def test_it_holds_nothing_but_issues_write(self, report: dict[Any, Any]):
        assert report["permissions"] == {}
        (job,) = report["jobs"].values()
        assert job["permissions"] == {"issues": "write"}

    def test_it_runs_no_action_and_checks_nothing_out(self, report: dict[Any, Any]):
        """Shell and the `gh` already on the runner: no third-party code holds the token."""
        (job,) = report["jobs"].values()
        assert [step for step in job["steps"] if "uses" in step] == []

    def test_no_expression_is_spliced_into_the_script(self, report: dict[Any, Any]):
        """Every value reaches the shell as an environment variable, never as source."""
        (job,) = report["jobs"].values()
        for step in job["steps"]:
            assert "${{" not in step["run"]


def _script() -> str:
    (job,) = _load(WORKFLOWS / REPORT)["jobs"].values()
    (step,) = job["steps"]
    assert step["shell"] == "bash"
    return step["run"]


def _bash() -> str | None:
    found = shutil.which("bash")
    # On Windows, System32's `bash.exe` starts WSL, which sees none of this environment.
    if found is None or (sys.platform == "win32" and "system32" in found.lower()):
        return None
    return found


FAKE_GH = r"""#!/usr/bin/env bash
# One line per call, so a newline inside an argument is logged as a space.
args="$*"
printf '%s\n' "${args//$'\n'/ }" >> "$GH_LOG"
if [ "$1 $2" = "issue list" ] && [ -n "${OPEN_ISSUE:-}" ]; then
  printf '%s\n' "$OPEN_ISSUE"
fi
"""


@pytest.mark.skipif(_bash() is None, reason="needs a bash that shares this environment")
class TestWhatTheReportDoes:
    """The script against a fake `gh`: which calls it makes, for which results."""

    def _run(self, tmp_path: Path, results: str, open_issue: str = "") -> list[str]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH, encoding="utf-8", newline="\n")
        (bin_dir / "gh").chmod(0o755)
        script = tmp_path / "report.sh"
        script.write_text(_script(), encoding="utf-8", newline="\n")
        log = tmp_path / "gh.log"
        log.touch()
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GH_LOG": log.as_posix(),
            "OPEN_ISSUE": open_issue,
            "RESULTS": results,
            "GH_TOKEN": "not-a-token",
            "GH_REPO": "creatoan/scenet",
            "GITHUB_WORKFLOW": "Link check",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "creatoan/scenet",
            "GITHUB_RUN_ID": "1234",
            "GITHUB_REF_NAME": "main",
            "GITHUB_SHA": "0" * 40,
            "GITHUB_EVENT_NAME": "schedule",
        }
        bash = _bash()
        assert bash is not None
        subprocess.run(  # noqa: S603 -- bash, running this repository's own workflow script
            [bash, "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()],
            env=env,
            check=True,
            capture_output=True,
        )
        return log.read_text(encoding="utf-8").splitlines()

    @staticmethod
    def _writes(calls: list[str]) -> list[str]:
        return [call for call in calls if not call.startswith("issue list")]

    def test_it_looks_for_the_open_issue_by_label_and_exact_title(self, tmp_path: Path):
        (call, *_) = self._run(tmp_path, "failure")
        assert call.startswith("issue list --state open --label scheduled-failure")
        assert "env.TITLE" in call

    def test_a_first_failure_opens_one_issue_titled_with_the_workflow(self, tmp_path: Path):
        writes = self._writes(self._run(tmp_path, "success failure"))
        assert [w.split(" --")[0] for w in writes] == [
            "label create scheduled-failure",
            "issue create",
        ]
        assert "--title Scheduled run failed: Link check" in writes[1]
        assert "--label scheduled-failure" in writes[1]
        assert "https://github.com/creatoan/scenet/actions/runs/1234" in writes[1]

    def test_a_second_failure_comments_on_the_open_issue(self, tmp_path: Path):
        writes = self._writes(self._run(tmp_path, "failure", open_issue="12"))
        assert len(writes) == 1
        assert writes[0].startswith("issue comment 12 --body ")
        assert "actions/runs/1234" in writes[0]

    def test_a_success_closes_the_open_issue(self, tmp_path: Path):
        writes = self._writes(self._run(tmp_path, "success success", open_issue="12"))
        assert len(writes) == 1
        assert writes[0].startswith("issue close 12 --comment ")
        assert "actions/runs/1234" in writes[0]

    def test_a_success_with_nothing_open_writes_nothing(self, tmp_path: Path):
        assert self._writes(self._run(tmp_path, "success")) == []

    @pytest.mark.parametrize("result", ["skipped", "cancelled"])
    def test_a_job_that_did_not_succeed_is_a_failure(self, tmp_path: Path, result: str):
        """Skipped because a job it needs failed; cancelled because it ran out of time.

        Somebody cancelling the whole run never gets here: the job runs on `!cancelled()`.
        """
        writes = self._writes(self._run(tmp_path, f"success {result}"))
        assert any(w.startswith("issue create") for w in writes)


class TestTheLinkCheckCanBeMadeToFail:
    """How the report is shown working: dispatched on a branch, forced to fail."""

    @pytest.fixture(scope="class")
    @classmethod
    def linkcheck(cls) -> dict[Any, Any]:
        return _load(WORKFLOWS / "linkcheck.yml")

    def test_it_takes_the_two_inputs(self, linkcheck: dict[Any, Any]):
        inputs = _triggers(linkcheck)["workflow_dispatch"]["inputs"]
        assert {name: spec["type"] for name, spec in inputs.items()} == {
            "force-failure": "boolean",
            "report": "boolean",
        }
        assert inputs["force-failure"]["default"] is False
        assert inputs["report"]["default"] is False

    def test_a_forced_failure_fails_before_anything_else(self, linkcheck: dict[Any, Any]):
        first = linkcheck["jobs"]["linkcheck"]["steps"][0]
        assert first["if"] == "inputs.force-failure"
        assert re.fullmatch(r"(echo .*\n)?exit 1\n?", first["run"])

    def test_a_dispatched_run_reports_only_when_asked(self, linkcheck: dict[Any, Any]):
        ((_, job),) = _reporters(linkcheck).items()
        assert job["if"] == (
            "${{ !cancelled() && (github.event_name == 'schedule' || inputs.report) }}"
        )
