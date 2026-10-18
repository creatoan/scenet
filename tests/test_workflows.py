"""The release workflows hold credentials, so their shape is tested.

A workflow is the one place in this repository that can publish to something other
people read. Nothing here runs it -- that needs GitHub -- but the properties that keep
it safe are properties of the file, and a file can be checked: the credential is minted
by one job and no other, nothing installs an unverified binary, and every action is
pinned to a commit rather than to a tag somebody can move.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _load(name: str) -> dict[Any, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads a bare `on` as the boolean True, which is how PyYAML sees it.
    return workflow.get("on") or workflow[True]


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(path: Path):
    """A tag can be re-pointed at different code by whoever controls the repository."""
    text = path.read_text(encoding="utf-8")
    for use in re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, re.MULTILINE):
        if use.startswith("./"):
            continue
        assert re.search(r"@[0-9a-f]{40}$", use), f"{path.name}: {use} is not pinned to a SHA"


class TestRegistryWorkflow:
    """Publishing to the MCP registry, by OIDC, from the repository's own identity."""

    @pytest.fixture(scope="class")
    @classmethod
    def registry(cls) -> dict[Any, Any]:
        return _load("registry.yml")

    def test_it_can_be_run_by_hand_and_called_by_the_release(self, registry: dict[Any, Any]):
        """By hand because the first release needs listing without re-tagging it."""
        triggers = _triggers(registry)
        assert set(triggers) == {"workflow_dispatch", "workflow_call"}
        assert "tag" in triggers["workflow_dispatch"]["inputs"]
        assert "tag" in triggers["workflow_call"]["inputs"]

    def test_nothing_is_granted_workflow_wide(self, registry: dict[Any, Any]):
        assert registry["permissions"] == {"contents": "read"}

    def test_the_credential_is_minted_by_one_job_only(self, registry: dict[Any, Any]):
        minting = [
            name
            for name, job in registry["jobs"].items()
            if (job.get("permissions") or {}).get("id-token") == "write"
        ]
        assert minting == ["publish"]

    def test_the_tool_is_pinned_and_checksummed(self, registry: dict[Any, Any]):
        """The binary runs with the OIDC credential in reach, so it is not `latest`."""
        (step,) = [
            s
            for s in registry["jobs"]["publish"]["steps"]
            if "mcp-publisher" in s.get("name", "") and "Install" in s["name"]
        ]
        assert re.fullmatch(r"v\d+\.\d+\.\d+", step["env"]["VERSION"])
        assert re.fullmatch(r"[0-9a-f]{64}", step["env"]["SHA256"])
        assert "releases/download/${VERSION}/" in step["run"]
        assert "/releases/latest/" not in step["run"]
        assert "sha256sum --check" in step["run"]
        assert step["run"].index("sha256sum --check") < step["run"].index("tar ")

    def test_it_checks_before_it_publishes(self, registry: dict[Any, Any]):
        script = "\n".join(step.get("run", "") for step in registry["jobs"]["publish"]["steps"])
        order = [
            script.index(command)
            for command in (
                "./mcp-publisher validate",
                "./mcp-publisher login github-oidc",
                "./mcp-publisher publish",
            )
        ]
        assert order == sorted(order)

    def test_it_never_relies_on_a_dry_run_flag(self, registry: dict[Any, Any]):
        """`publish` has no such flag, so one would be ignored and the publish would happen."""
        script = "\n".join(step.get("run", "") for step in registry["jobs"]["publish"]["steps"])
        assert "--dry-run" not in script

    def test_it_waits_for_the_package_it_points_at(self, registry: dict[Any, Any]):
        """The registry checks the PyPI description, so the version has to be there."""
        script = "\n".join(step.get("run", "") for step in registry["jobs"]["publish"]["steps"])
        assert "pypi.org/pypi/scenet/" in script


class TestReleaseWorkflowCallsIt:
    @pytest.fixture(scope="class")
    @classmethod
    def release(cls) -> dict[Any, Any]:
        return _load("release.yml")

    def test_it_is_opt_in(self, release: dict[Any, Any]):
        """OIDC login for an org namespace is unproven until it has worked once."""
        assert "vars.MCP_REGISTRY_PUBLISH == 'true'" in release["jobs"]["registry"]["if"]

    def test_it_runs_after_everything_else_and_blocks_nothing(self, release: dict[Any, Any]):
        job = release["jobs"]["registry"]
        assert set(job["needs"]) == {"publish", "github-release"}
        for name, other in release["jobs"].items():
            assert "registry" not in (other.get("needs") or []), name

    def test_it_calls_the_reusable_workflow_with_the_tag(self, release: dict[Any, Any]):
        job = release["jobs"]["registry"]
        assert job["uses"] == "./.github/workflows/registry.yml"
        assert job["with"]["tag"] == "${{ github.ref_name }}"

    def test_the_credential_is_granted_to_that_job_only(self, release: dict[Any, Any]):
        assert release["permissions"] == {"contents": "read"}
        job = release["jobs"]["registry"]
        assert job["permissions"]["id-token"] == "write"


class TestThePackageIsCheckedOnEveryPullRequest:
    """What `release.yml` checks before publishing, CI checks on every pull request.

    A file missing from the wheel or the sdist, or a README PyPI cannot render, otherwise
    shows only when a tag is pushed -- the one moment it is too late to be cheap.
    """

    @pytest.fixture
    def steps(self) -> str:
        job = _load("ci.yml")["jobs"]["package"]
        return "\n".join(str(step.get("run", "")) for step in job["steps"])

    def test_it_runs_on_pull_requests(self):
        assert "pull_request" in _triggers(_load("ci.yml"))

    def test_it_builds_both_distributions(self, steps: str):
        assert re.search(r"^uv build\s*$", steps, re.MULTILINE)

    def test_it_checks_what_pypi_will_show_with_a_pinned_twine(self, steps: str):
        assert re.search(r"twine==\d+\.\d+\.\d+ twine check --strict", steps)

    def test_it_builds_the_wheel_again_from_the_sdist_alone(self, steps: str):
        assert re.search(r"uv build --wheel \S*\.tar\.gz", steps)

    def test_it_smoke_tests_the_wheel_as_the_release_does(self, steps: str):
        release = _load("release.yml")["jobs"]["build"]
        released = "\n".join(str(step.get("run", "")) for step in release["steps"])
        assert "scripts/smoke_wheel.py" in steps
        assert "scripts/smoke_wheel.py" in released

    def test_it_publishes_nothing(self):
        job = _load("ci.yml")["jobs"]["package"]
        assert "environment" not in job
        assert "id-token" not in str(job.get("permissions", {}))


def test_the_python_floor_is_really_tested():
    """`uv run` reads .python-version (3.14) and, finding a 3.12 environment, rebuilds it.

    The 3.12 job synced 3.12, then ran its tests on 3.14 with the default groups only, so
    the floor went untested. Every uv command in the job must name the matrix's Python.
    """
    job = _load("ci.yml")["jobs"]["check"]
    assert job["env"]["UV_PYTHON"] == "${{ matrix.python }}"
    script = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "uv run pytest" in script


def test_the_mutation_run_installs_what_the_tests_import():
    """mutmut's clean run is the whole suite, so it needs every group the suite does.

    It synced `mutation` alone, with the default `dev`. `tests/test_site.py` reads the
    documentation's configuration, which needs `docs`, so the clean run failed and no
    mutant was tried: run 39116267418. CI's test jobs sync every group; so must this.
    """
    job = _load("mutation.yml")["jobs"]["mutmut"]
    syncs = [line for line in _script(job).splitlines() if "uv sync" in line]
    assert syncs
    assert all("--all-groups" in line for line in syncs), syncs


def _script(job: dict[Any, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def _downloads(job: dict[Any, Any]) -> list[str]:
    return [
        step["with"]["name"]
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/download-artifact@")
    ]


#: Grants that publish something: a deployment, an OIDC token, a write to the repository.
PUBLISHING = {"id-token", "pages", "contents", "packages", "attestations", "deployments"}
#: Events a pull request -- possibly from a fork -- can set off.
PULL_REQUEST_EVENTS = {"pull_request", "pull_request_target", "merge_group"}


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_no_pull_request_holds_a_publishing_credential(path: Path):
    """A workflow a pull request sets off writes nothing and deploys nothing."""
    workflow = _load(path.name)
    if not PULL_REQUEST_EVENTS & set(_triggers(workflow)):
        return
    grants = [workflow.get("permissions") or {}]
    for name, job in workflow["jobs"].items():
        assert "environment" not in job, f"{path.name}: {name} deploys to an environment"
        grants.append(job.get("permissions") or {})
    for grant in grants:
        assert isinstance(grant, dict), f"{path.name}: permissions must be listed one by one"
        for scope, level in grant.items():
            assert scope not in PUBLISHING or level != "write", f"{path.name}: {scope}: write"


class TestTheReleaseBuildsItsSite:
    """Pages serves every release from the site attached to it, built by the release."""

    @pytest.fixture(scope="class")
    @classmethod
    def release(cls) -> dict[Any, Any]:
        return _load("release.yml")

    def test_it_is_built_from_the_wheel_the_release_publishes(self, release: dict[Any, Any]):
        job = release["jobs"]["site"]
        assert job["needs"] == "build"
        assert _downloads(job) == ["distributions"]
        assert "scripts/build_site.py --release-archive" in _script(job)

    def test_it_publishes_nothing_itself(self, release: dict[Any, Any]):
        job = release["jobs"]["site"]
        assert "permissions" not in job
        assert "environment" not in job
        uploads = [s for s in job["steps"] if "upload-artifact@" in str(s.get("uses", ""))]
        assert [step["with"]["name"] for step in uploads] == ["site"]

    def test_pypi_waits_for_it(self, release: dict[Any, Any]):
        """Everything that can fail runs before anything is published."""
        assert "site" in release["jobs"]["publish"]["needs"]

    def test_pypi_gets_the_distributions_only(self, release: dict[Any, Any]):
        assert _downloads(release["jobs"]["publish"]) == ["distributions"]

    def test_the_github_release_attaches_it(self, release: dict[Any, Any]):
        job = release["jobs"]["github-release"]
        assert "site" in job["needs"]
        assert "needs.site.result == 'success'" in job["if"]
        assert "site" in _downloads(job)

    def test_the_notes_link_the_releases_own_documentation(self, release: dict[Any, Any]):
        """The root moves on to the next release; the notes are forever."""
        assert "creatoan.github.io/scenet/v${MINOR}/" in _script(release["jobs"]["github-release"])


class TestPagesWorkflow:
    """The latest release at the root, main under /dev/, assembled on every deploy."""

    @pytest.fixture(scope="class")
    @classmethod
    def pages(cls) -> dict[Any, Any]:
        return _load("pages.yml")

    def test_a_push_or_a_finished_release_deploys(self, pages: dict[Any, Any]):
        triggers = _triggers(pages)
        assert set(triggers) == {"push", "workflow_run", "workflow_dispatch"}
        assert triggers["push"] == {"branches": ["main"]}
        assert triggers["workflow_run"] == {"workflows": ["Release"], "types": ["completed"]}

    def test_only_a_release_a_push_started(self, pages: dict[Any, Any]):
        """A pull request can add a workflow called Release; its runs must not deploy."""
        condition = pages["jobs"]["build"]["if"]
        assert "github.event_name != 'workflow_run'" in condition
        assert "github.event.workflow_run.event == 'push'" in condition
        assert "conclusion" not in condition  # a failed registry listing must not stop it

    def test_it_builds_main_and_nothing_the_trigger_named(self, pages: dict[Any, Any]):
        """Never the triggering run's commit or artifacts: main, and the releases."""
        build = pages["jobs"]["build"]
        (checkout,) = [s for s in build["steps"] if "checkout@" in str(s.get("uses", ""))]
        assert "ref" not in checkout.get("with", {})
        assert _downloads(build) == []
        assert "head_sha" not in str(pages)

    def test_it_reads_the_releases_with_a_read_only_token(self, pages: dict[Any, Any]):
        build = pages["jobs"]["build"]
        assert "permissions" not in build
        assert pages["permissions"] == {"contents": "read"}
        (step,) = [s for s in build["steps"] if "scripts/build_site.py" in str(s.get("run", ""))]
        assert step["env"]["GH_TOKEN"] == "${{ github.token }}"  # noqa: S105 -- not a secret
        assert "--release-archive" not in step["run"]

    def test_only_the_deploy_holds_the_credential(self, pages: dict[Any, Any]):
        holders = [
            name
            for name, job in pages["jobs"].items()
            if (job.get("permissions") or {}).get("id-token") == "write"
            or (job.get("permissions") or {}).get("pages") == "write"
        ]
        assert holders == ["deploy"]
        assert pages["jobs"]["deploy"]["environment"]["name"] == "github-pages"

    def test_deploys_queue_rather_than_cancel(self, pages: dict[Any, Any]):
        assert pages["concurrency"]["cancel-in-progress"] is False


class TestSiteBackfill:
    """Attaching a site to a release made before releases carried one."""

    @pytest.fixture(scope="class")
    @classmethod
    def backfill(cls) -> dict[Any, Any]:
        return _load("site-backfill.yml")

    def test_it_is_run_by_hand_for_one_tag(self, backfill: dict[Any, Any]):
        triggers = _triggers(backfill)
        assert set(triggers) == {"workflow_dispatch"}
        assert triggers["workflow_dispatch"]["inputs"]["tag"]["required"] is True

    def test_only_attaching_can_write(self, backfill: dict[Any, Any]):
        """The build runs an old release's npm install and build; it holds nothing."""
        assert backfill["permissions"] == {"contents": "read"}
        writers = [
            name
            for name, job in backfill["jobs"].items()
            if "write" in (job.get("permissions") or {}).values()
        ]
        assert writers == ["attach"]
        assert backfill["jobs"]["attach"]["permissions"] == {"contents": "write"}

    def test_the_tag_never_reaches_a_shell_as_code(self, backfill: dict[Any, Any]):
        """An input interpolated into `run:` is spliced into the script before it runs."""
        for job in backfill["jobs"].values():
            assert "${{" not in _script(job)
            assert "inputs.tag" not in _script(job)

    def test_it_builds_with_the_backfill_script(self, backfill: dict[Any, Any]):
        job = backfill["jobs"]["build"]
        assert "scripts/backfill_site.py" in _script(job)
        (checkout,) = [s for s in job["steps"] if "checkout@" in str(s.get("uses", ""))]
        assert checkout["with"]["fetch-depth"] == 0
        assert checkout["with"]["persist-credentials"] is False

    def test_it_never_replaces_an_attached_site(self, backfill: dict[Any, Any]):
        script = _script(backfill["jobs"]["attach"])
        assert "gh release upload" in script
        assert "--clobber" not in script
        assert backfill["jobs"]["attach"]["needs"] == "build"


def test_every_python_the_package_claims_is_tested():
    """PyPI shows the classifiers as a promise; each version in them gets a CI job."""
    pyproject = (WORKFLOWS.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    claimed = re.findall(r'"Programming Language :: Python :: (3\.\d+)"', pyproject)
    tested = _load("ci.yml")["jobs"]["check"]["strategy"]["matrix"]["python"]
    assert claimed
    assert tested == claimed


def test_every_pull_request_checks_the_docs_say_their_version():
    """The switcher, the banner and canonical links rest on settings a build carries."""
    steps = _load("ci.yml")["jobs"]["docs"]["steps"]
    script = "\n".join(str(step.get("run", "")) for step in steps)
    assert "scripts/site_versions.py check docs/_build/html" in script
    assert script.index("sphinx-build") < script.index("site_versions.py check")


def test_the_smoke_test_runs_outside_the_checkout():
    """`import scenet` succeeding in the repository root proves nothing."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "smoke_wheel.py").read_text(
        encoding="utf-8"
    )
    assert "py.typed" in text
    assert "__version__" in text


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class TestCodeQL:
    """The Python, the TypeScript and the workflows themselves, analysed by CodeQL."""

    @pytest.fixture(scope="class")
    @classmethod
    def codeql(cls) -> dict[Any, Any]:
        return _load("codeql.yml")

    def test_it_runs_on_pull_requests_on_main_and_every_week(self, codeql: dict[Any, Any]):
        """Weekly too, because new queries find old code: nothing has to change for that."""
        triggers = _triggers(codeql)
        assert "pull_request" in triggers
        assert triggers["push"] == {"branches": ["main"]}
        assert [entry["cron"] for entry in triggers["schedule"]]

    def test_it_covers_python_and_typescript(self, codeql: dict[Any, Any]):
        matrix = codeql["jobs"]["analyze"]["strategy"]["matrix"]["include"]
        assert {"python", "javascript-typescript"} <= {entry["language"] for entry in matrix}

    def test_only_the_analysis_can_write_to_code_scanning(self, codeql: dict[Any, Any]):
        assert codeql["permissions"] == {"contents": "read"}
        writers = [
            name
            for name, job in codeql["jobs"].items()
            if "write" in (job.get("permissions") or {}).values()
        ]
        assert writers == ["analyze"]
        # `actions: read` is for private repositories only; this one is public.
        assert codeql["jobs"]["analyze"]["permissions"] == {
            "contents": "read",
            "security-events": "write",
        }

    def test_it_is_the_codeql_action_the_gallery_uploads_with(self):
        """One pin for the whole action, so Dependabot moves it in one pull request."""
        pins = set(
            re.findall(
                r"github/codeql-action/[\w-]+@([0-9a-f]{40})", _text("ci.yml") + _text("codeql.yml")
            )
        )
        assert len(pins) == 1


class TestDependencyReview:
    """A pull request adding a known high or critical vulnerability fails before it merges."""

    @pytest.fixture(scope="class")
    @classmethod
    def review(cls) -> dict[Any, Any]:
        return _load("dependency-review.yml")

    @pytest.fixture(scope="class")
    @classmethod
    def step(cls, review: dict[Any, Any]) -> dict[Any, Any]:
        (step,) = [
            s
            for job in review["jobs"].values()
            for s in job["steps"]
            if str(s.get("uses", "")).startswith("actions/dependency-review-action@")
        ]
        return step

    def test_it_reviews_pull_requests_and_the_merge_queue(self, review: dict[Any, Any]):
        """The queue too, if one returns: a required check it never ran would stall it."""
        assert set(_triggers(review)) == {"pull_request", "merge_group"}

    def test_a_fork_can_run_it(self, review: dict[Any, Any]):
        """Read-only and secret-free, so a fork's pull request is reviewed like any other."""
        assert review["permissions"] == {"contents": "read"}
        for job in review["jobs"].values():
            assert "permissions" not in job
        assert "secrets." not in _text("dependency-review.yml")

    def test_high_and_critical_fail_it(self, step: dict[Any, Any]):
        assert step["with"]["fail-on-severity"] == "high"

    def test_development_dependencies_count(self, step: dict[Any, Any]):
        """They run in CI, with a token in reach; the default would ignore them."""
        scopes = {scope.strip() for scope in step["with"]["fail-on-scopes"].split(",")}
        assert {"runtime", "development", "unknown"} <= scopes

    def test_it_never_comments(self, step: dict[Any, Any]):
        """Commenting needs `pull-requests: write`, which a fork's token does not carry."""
        assert step["with"]["comment-summary-in-pr"] == "never"

    def test_the_queue_compares_the_commit_it_queued(self, step: dict[Any, Any]):
        assert "merge_group.base_sha" in step["with"]["base-ref"]
        assert "merge_group.head_sha" in step["with"]["head-ref"]
