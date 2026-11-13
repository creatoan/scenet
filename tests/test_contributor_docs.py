"""The contributor and project documents say what the repository does.

`CONTRIBUTING.md`, the maintainer guide, `SECURITY.md`, the GitHub templates and the
CHANGELOG each make claims about something the repository holds: the gates CI runs, the
Python floor, the scripts that regenerate committed files, the project's status. Each was
written once and then drifted, because nothing read it against what it describes. These
tests do, wherever the claim can be held to a file in the repository.

What they cannot hold is GitHub's own configuration: the ruleset that names the required
checks, or the commit subjects in a history CI checks out one commit deep.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
CLAUDE = ROOT / "CLAUDE.md"
SECURITY = ROOT / "SECURITY.md"
CHANGELOG = ROOT / "CHANGELOG.md"
COPILOT = ROOT / ".github" / "copilot-instructions.md"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
BUG_TEMPLATE = ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
MAINTAINER = ROOT / "docs" / "maintainer"
GUIDE = MAINTAINER / "index.md"
RELEASING = MAINTAINER / "releasing.md"
DECISIONS = ROOT / "docs" / "explanation" / "design_decisions.md"
INSTALL = ROOT / "docs" / "howto" / "install.md"

CONTRIBUTING_URL = "https://github.com/creatoan/scenet/blob/main/CONTRIBUTING.md"
ISSUES_URL = "https://github.com/creatoan/scenet/issues/"

#: The documents that state the house rules, each in its own words.
RULE_DOCUMENTS = [CLAUDE, CONTRIBUTING, GUIDE, DECISIONS]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(_read(ROOT / "pyproject.toml"))


def _workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load(_read(WORKFLOWS / name))


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads a bare `on` as the boolean True, which is how PyYAML sees it.
    return workflow.get("on") or workflow[True]


def _bash_blocks(text: str) -> str:
    return "\n".join(re.findall(r"^```bash\n(.*?)^```", text, re.MULTILINE | re.DOTALL))


def _floor() -> str:
    found = re.fullmatch(r">=(\d+\.\d+)", _pyproject()["project"]["requires-python"])
    assert found, "requires-python is not a plain floor"
    return found.group(1)


def _slug(heading: str) -> str:
    """The anchor MyST gives a heading, as `myst_heading_anchors` makes it."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


# ---------------------------------------------------------------- the gates


#: The CI jobs whose commands a contributor runs before a pull request. Left out: the
#: licence job, which checks a runtime-only environment a contributor never makes, and the
#: jobs that run npm or a packaging tool rather than `uv run`.
GATE_JOBS = ("check", "windows", "typecheck-strict", "docs", "examples")


def _gate(command: str) -> str:
    """What names a `uv run` command: the tool, and its subcommand or script."""
    words = command.split()
    if words[0] in {"ruff", "ty", "python"}:
        return " ".join(words[:2])
    return words[0]


def _ci_gates() -> list[str]:
    jobs = _workflow("ci.yml")["jobs"]
    found: list[str] = []
    for job in GATE_JOBS:
        for step in jobs[job]["steps"]:
            for command in re.findall(r"uv run (.+)", step.get("run", "")):
                gate = _gate(command)
                if gate not in found:
                    found.append(gate)
    return found


def test_the_gates_are_found():
    """A parse that found nothing would let every test below pass."""
    assert {
        "ruff format",
        "ruff check",
        "ty check",
        "pytest",
        "basedpyright",
        "sphinx-build",
    } <= set(_ci_gates())


@pytest.mark.parametrize("path", [CONTRIBUTING, GUIDE], ids=lambda p: p.name)
@pytest.mark.parametrize("gate", _ci_gates())
def test_every_gate_ci_runs_is_listed(path: Path, gate: str):
    """`Run what CI runs` is only true if the list is CI's list."""
    assert f"uv run {gate}" in _bash_blocks(_read(path)), f"{path.name} never says `uv run {gate}`"


@pytest.mark.parametrize("path", [CONTRIBUTING, CLAUDE, GUIDE], ids=lambda p: p.name)
def test_every_install_installs_every_group(path: Path):
    """CI syncs every group; a plain `uv sync` leaves out the documentation build."""
    syncs = re.findall(r"uv sync[^\n#]*", _bash_blocks(_read(path)))
    assert syncs, f"{path.name} says nothing about installing"
    assert all("--all-groups" in sync for sync in syncs), syncs


def test_the_strict_type_check_blocks():
    """The design decisions once called it advisory; CI has made it block since."""
    job = _workflow("ci.yml")["jobs"]["typecheck-strict"]
    assert "continue-on-error" not in job
    assert any(step.get("run") == "uv run basedpyright" for step in job["steps"])


@pytest.mark.parametrize("path", [*RULE_DOCUMENTS, ROOT / "pyproject.toml"], ids=lambda p: p.name)
def test_nothing_calls_a_gate_non_blocking(path: Path):
    assert "non-blocking" not in _read(path)


def _pull_request_checks() -> list[str]:
    """Every check a pull request gets, by the name GitHub shows, with matrices expanded."""
    checks: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(_read(path))
        trigger = _triggers(workflow).get("pull_request", False)
        # A workflow filtered to its own file runs on the pull requests that edit it alone.
        if trigger is False or (isinstance(trigger, dict) and "paths" in trigger):
            continue
        for job in workflow["jobs"].values():
            # The report of a scheduled run is skipped on every pull request, so it is not
            # a check one waits for (tests/test_scheduled_runs.py).
            if job.get("uses") == "./.github/workflows/scheduled-report.yml":
                continue
            name = job["name"]
            matrix = job.get("strategy", {}).get("matrix", {})
            values = {
                key: [str(value) for value in matrix.get(key, [])]
                + [str(item[key]) for item in matrix.get("include", []) if key in item]
                for key in re.findall(r"\$\{\{ matrix\.(\w+) \}\}", name)
            }
            names = [name]
            for key, options in values.items():
                names = [
                    n.replace(f"${{{{ matrix.{key} }}}}", option)
                    for n in names
                    for option in dict.fromkeys(options)
                ]
            checks.extend(names)
    return checks


def test_the_checks_are_found():
    checks = _pull_request_checks()
    assert "Lint, types and tests (Python 3.12)" in checks
    assert "Analyze (python)" in checks
    assert "Dependency review" in checks


@pytest.mark.parametrize("check", _pull_request_checks())
def test_the_maintainer_guide_names_every_check(check: str):
    """`Seven status checks` had stopped being true without anyone noticing."""
    rows = re.findall(r"^\| `([^`]+)` \|", _read(GUIDE), re.MULTILINE)
    assert check in rows, f"the maintainer guide's table of checks has no row for {check!r}"


# ---------------------------------------------------------------- what changes with a change


def _generators() -> list[str]:
    """Every script that rewrites committed files, and can say they are stale."""
    return sorted(
        f"scripts/{path.name}"
        for path in (ROOT / "scripts").glob("*.py")
        if re.search(r"--check\s+# exit 1 if", _read(path))
    )


def test_the_generators_are_found():
    assert {"scripts/update_golden.py", "scripts/build_spec.py"} <= set(_generators())


@pytest.mark.parametrize("path", [CONTRIBUTING, PR_TEMPLATE], ids=lambda p: p.name)
@pytest.mark.parametrize("script", _generators())
def test_every_generator_is_named(path: Path, script: str):
    """A change that moves a generated file and forgets to regenerate fails CI; say so first."""
    assert f"uv run python {script}" in _read(path)


@pytest.mark.parametrize("path", [CONTRIBUTING, PR_TEMPLATE], ids=lambda p: p.name)
def test_the_editor_schemas_are_named(path: Path):
    """The JSON Schemas the editor ships are regenerated by its own script."""
    scripts = json.loads(_read(ROOT / "editor" / "package.json"))["scripts"]
    assert "scenet schema" in scripts["schemas"]
    assert "npm run schemas" in _read(path)


def test_the_pull_request_template_asks_for_a_changelog_entry():
    text = _read(PR_TEMPLATE)
    assert "CHANGELOG.md" in text
    assert "[Unreleased]" in text


# ---------------------------------------------------------------- the Python floor


def test_the_floor_is_the_one_every_tool_targets():
    floor = _floor()
    tools = _pyproject()["tool"]
    assert tools["ruff"]["target-version"] == "py" + floor.replace(".", "")
    assert tools["basedpyright"]["pythonVersion"] == floor


@pytest.mark.parametrize(
    ("path", "claim"),
    [
        (CLAUDE, "the floor is {floor}"),
        (CONTRIBUTING, "The floor is Python {floor}"),
        (GUIDE, "The floor is **{floor}**"),
        (DECISIONS, "### The floor is Python {floor}"),
        (INSTALL, "Python **{floor} or newer**"),
    ],
    ids=lambda value: value.name if isinstance(value, Path) else "",
)
def test_every_document_names_the_floor_pyproject_declares(path: Path, claim: str):
    assert claim.format(floor=_floor()) in _read(path)


def test_the_install_guide_links_the_reason_for_the_floor():
    """It once linked the design decisions, which had no such section."""
    found = re.search(
        r"\[why [\d.]+\]\(\.\./explanation/design_decisions\.md#([\w-]+)\)", _read(INSTALL)
    )
    assert found, "the install guide does not link a section of the design decisions"
    headings = re.findall(r"^#{2,3} (.+)$", _read(DECISIONS), re.MULTILINE)
    assert found.group(1) in {_slug(heading) for heading in headings}


@pytest.mark.parametrize("path", RULE_DOCUMENTS, ids=lambda p: p.name)
def test_every_document_quotes_forward_references(path: Path):
    """Unquoted, `-> Point` inside `class Point` raises NameError on the floor."""
    text = _read(path)
    assert '-> "Point"' in text
    assert "UP037" in text
    assert not re.search(r"\bworks? unquoted\b", text)


def test_copilot_is_pointed_at_the_rules_rather_than_given_a_copy():
    """A copy said Python 3.14 and lazy annotations, and never to quote."""
    text = _read(COPILOT)
    assert "CLAUDE.md" in text
    assert not re.search(r"\b3\.1\d\b", text), "it states a Python version of its own"
    assert len(text.splitlines()) <= 12


# ---------------------------------------------------------------- one guide, both ways


def test_contributing_links_the_maintainer_guide():
    assert "(docs/maintainer/index.md)" in _read(CONTRIBUTING)


def test_the_maintainer_guide_links_contributing():
    assert f"]({CONTRIBUTING_URL})" in _read(GUIDE)


def _prose(text: str) -> str:
    """The text with its code blocks and code spans taken out."""
    text = re.sub(r"^(`{3,}|~{3,}).*?^\1", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]+`", "", text)


@pytest.mark.parametrize(
    "path", [CONTRIBUTING, *sorted(MAINTAINER.glob("*.md"))], ids=lambda p: p.name
)
def test_every_issue_number_is_a_link(path: Path):
    """A bare `#71` renders as text on the site; a contributor following one needs a link."""
    text = _prose(_read(path))
    bare = re.findall(r"(?<![\w/&\[])#\d+(?!\w)", text)
    assert bare == [], f"{path.name} has bare issue numbers: {bare}"
    for number, url in re.findall(r"\[#(\d+)\]\(([^)]+)\)", text):
        if "github.com/creatoan/scenet" in url:
            assert url == f"{ISSUES_URL}{number}", url


# ---------------------------------------------------------------- the project's status


def _status() -> str:
    for classifier in _pyproject()["project"]["classifiers"]:
        if classifier.startswith("Development Status :: "):
            return classifier.rsplit(" - ", 1)[1].lower()
    raise AssertionError("no Development Status classifier")


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "README.md",
        CONTRIBUTING,
        SECURITY,
        CLAUDE,
        COPILOT,
        PR_TEMPLATE,
        *sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")),
        *sorted(path for path in (ROOT / "docs").rglob("*.md") if "_build" not in path.parts),
    ],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_nothing_says_pre_alpha(path: Path):
    """The CHANGELOG may say what the project was; nothing else may."""
    assert "pre-alpha" not in _read(path).lower()


@pytest.mark.parametrize("path", [SECURITY, BUG_TEMPLATE], ids=lambda p: p.name)
def test_the_status_is_the_classifiers(path: Path):
    assert f"is {_status()}" in _read(path).lower()


# ---------------------------------------------------------------- security


def _minor() -> str:
    major, minor, _ = _pyproject()["project"]["version"].split(".")
    return f"{major}.{minor}"


def test_security_names_the_release_that_gets_fixes():
    """`Only main receives fixes` was untrue from 0.11.1, a security release."""
    supported = re.findall(r"^\| ([^|]+?) \| Yes\b", _read(SECURITY), re.MULTILINE)
    assert supported == [f"{_minor()}.x"], (
        f"SECURITY.md supports {supported}; at a release, set it to {_minor()}.x"
    )


def test_releasing_says_to_move_the_supported_release():
    assert "SECURITY.md" in _read(RELEASING)


@pytest.mark.parametrize(
    "surface",
    [
        "scenet mcp --transport streamable-http",
        "127.0.0.1",
        "`files`",
        "font",
        "PNG",
        "JPEG",
        "puppet",
        "artwork contract",
        "PDF",
        "yaml.safe_load",
    ],
)
def test_security_scope_covers_what_scenet_reads_and_serves(surface: str):
    """It said YAML in and SVG out, with no network: the MCP server listens on one."""
    assert surface in _read(SECURITY)


def test_security_no_longer_says_scenet_has_no_network_access():
    assert "no network access" not in _read(SECURITY)


def test_the_mcp_server_binds_where_security_says():
    """The scope is written from the default; the default is the CLI's."""
    assert '"--host", default="127.0.0.1"' in _read(ROOT / "src" / "scenet" / "cli.py")


# ---------------------------------------------------------------- the bug report


def test_the_bug_report_takes_any_document_and_its_files():
    form = yaml.safe_load(_read(BUG_TEMPLATE))
    fields = {item.get("id"): item for item in form["body"] if "id" in item}
    source = fields["source"]["attributes"]
    described = source["label"] + " " + source["description"]
    for kind in (".panel.yaml", ".scene.yaml", "comic script", "font", "picture", "puppet"):
        assert kind in described, kind
    assert "render" not in source, "a comic script is not YAML"
    assert "command" in fields


# ---------------------------------------------------------------- the changelog


#: Keep a Changelog's kinds, in its order, then the two this project adds after them.
KINDS = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Upgrading",
    "Known limitations",
)


def _sections() -> list[tuple[str, str]]:
    parts = re.split(r"^## ", _read(CHANGELOG), flags=re.MULTILINE)[1:]
    return [(part.split("\n", 1)[0], part.split("\n", 1)[1]) for part in parts]


def _structured() -> list[tuple[str, str]]:
    # 0.1.0 had nothing to add to or change: its notes introduce the project, by theme.
    return [(name, body) for name, body in _sections() if not name.startswith("[0.1.0]")]


def test_the_changelog_opens_with_unreleased():
    assert _sections()[0][0] == "[Unreleased]"


@pytest.mark.parametrize(("name", "body"), _structured(), ids=[name for name, _ in _structured()])
def test_every_section_has_each_kind_once_in_order(name: str, body: str):
    headings = re.findall(r"^### (.+)$", body, re.MULTILINE)
    assert all(heading in KINDS for heading in headings), headings
    assert headings == sorted(set(headings), key=KINDS.index), f"{name}: {headings}"


@pytest.mark.parametrize(("name", "body"), _structured(), ids=[name for name, _ in _structured()])
def test_nothing_stands_between_the_kinds(name: str, body: str):
    """What a release asks of whoever upgrades opens its section, before the first kind.

    In the middle, as a bold line between two kinds, it split one `Added` from the next.
    """
    _, _, kinds = body.partition("\n### ")
    assert not re.search(r"^\*\*", kinds, re.MULTILINE), f"{name} has a bold line among its kinds"
