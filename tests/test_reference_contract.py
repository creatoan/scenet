"""`docs/reference/cli.md` is the specification. These tests hold the code to it.

The reference has drifted before: `scenet check -o` ignored `-o` in text format although
the reference said it wrote a file (#88), and two rules `check` reported were missing
from it (#65). Every test here fails in **both** directions, when something is documented
and not implemented and when something is implemented and not documented, so neither
the page nor the code can move on its own.

What is checked:

- each command's options, their choices and their documented defaults, against the
  argument parser;
- each command's exit-status table, against a scenario that produces every code;
- every rule in the catalogue, against a document in `tests/rule_corpus/` that produces
  exactly one finding of it, and the SARIF rule objects against the catalogue;
- each behavioural sentence, against a test of it.

The `bash` examples in the reference are run too, by `tests/shell_examples.py`.
"""

import argparse
import json
import re
import shlex
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scenet import __version__
from scenet.cli import build_parser, main
from scenet.diagnostics import RULES, Diagnostic, diagnose_script, diagnose_source, to_sarif
from scenet.pipeline import FRONTENDS

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = (ROOT / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")
CORPUS = Path(__file__).resolve().parent / "rule_corpus"
#: The folder the corpus is read beside, as the playground reads every document: the
#: pictures, fonts and puppet a document names are the gallery's.
GALLERY = ROOT / "examples" / "gallery"
#: The corpus documents that give a rule, without their fixed twins in `fixed/` or the ones
#: that give a compile note: `tests/test_diagnostics_reference.py` holds those.
DOCUMENTS = sorted(
    path for path in CORPUS.iterdir() if path.is_file() and path.name.split(".")[0] in RULES
)
COMMANDS = ("build", "check", "schema", "mcp")

PANEL = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
BROKEN = "cast: {alice: {reference: alice}}\nscript: [{say: {by: bpb, text: Hello.}}]\n"
# Valid, but no layout exists: each actor in front of the other.
UNCOMPILABLE = (
    "cast: {a: {reference: alice}, b: {reference: bob}}\n"
    "staging: [a in_front_of b, b in_front_of a]\n"
)


# ---------------------------------------------------------------- reading the reference


def _section(command: str) -> str:
    """The reference's section for one command, up to the next command's."""
    start = REFERENCE.index(f"## `scenet {command}`")
    following = REFERENCE.find("\n## ", start + 1)
    return REFERENCE[start : following if following != -1 else len(REFERENCE)]


def _synopsis(command: str) -> str:
    section = _section(command)
    block = re.search(r"```\n(scenet [^\n]+)\n```", section)
    assert block, f"no synopsis for `scenet {command}`"
    return block.group(1)


def _definitions(command: str) -> list[str]:
    """The terms of the section's option definition list, as `-o`, `--output PATH`."""
    return re.findall(r"^(`-[^\n]*)\n: ", _section(command), re.MULTILINE)


_OPTION = re.compile(r"(?<![\w-])(--?[a-z][a-z-]*)")


def _documented_options(command: str) -> set[str]:
    words = " ".join([_synopsis(command), *_definitions(command)])
    return set(_OPTION.findall(words)) - {"-", "--"}


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    (group,) = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    return dict(group.choices)


def _actions(command: str) -> list[argparse.Action]:
    return [
        action
        for action in _subparsers()[command]._actions
        if not isinstance(action, argparse._HelpAction)
    ]


def _implemented_options(command: str) -> set[str]:
    return {option for action in _actions(command) for option in action.option_strings}


def _exit_codes(command: str) -> set[int]:
    section = _section(command)
    table = section[section.index("### Exit status") :]
    return {int(code) for code in re.findall(r"^\| (\d) \|", table, re.MULTILINE)}


# ---------------------------------------------------------------- options


class TestFrontends:
    def test_the_extension_table_is_what_build_reads(self):
        """`.panel.yaml` and `.scene.yaml` are read through their last suffix, `.yaml`."""
        table = _section("build")[_section("build").index("| Extension |") :]
        rows = re.findall(r"^\| (`[^|]+`) \| ([^|]+) \|$", table, re.MULTILINE)
        documented = {
            Path(f"x{extension}").suffix: reader.strip()
            for cell, reader in rows
            for extension in re.findall(r"`([^`]+)`", cell)
        }
        readers = {".yaml": "load_scene", ".yml": "load_scene", ".script": "load_script"}
        assert {key: reader.__name__ for key, reader in FRONTENDS.items()} == readers
        assert set(documented) == set(FRONTENDS)
        assert {key for key, said in documented.items() if said == "Comic script"} == {".script"}


class TestOptions:
    @pytest.mark.parametrize("command", COMMANDS)
    def test_the_options_are_the_documented_ones(self, command: str):
        """Documented but missing, or present but undocumented, fails either way."""
        assert _implemented_options(command) == _documented_options(command)

    @pytest.mark.parametrize("command", COMMANDS)
    def test_every_option_has_a_definition(self, command: str):
        """The synopsis lists an option; the definition list says what it does."""
        defined = set(_OPTION.findall(" ".join(_definitions(command))))
        long_forms = {option for option in _implemented_options(command) if option.startswith("--")}
        assert long_forms <= defined

    def test_the_top_level_has_only_version(self):
        parser = build_parser()
        options = {
            option
            for action in parser._actions
            if not isinstance(action, argparse._HelpAction | argparse._SubParsersAction)
            for option in action.option_strings
        }
        synopsis = re.search(r"scenet \[([^\]]+)\]", REFERENCE)
        assert synopsis, "the reference opens with `scenet [--version] <command>`"
        assert options == set(_OPTION.findall(synopsis.group(1)))

    @pytest.mark.parametrize(("command", "option"), [("check", "--format"), ("mcp", "--transport")])
    def test_the_choices_are_the_documented_ones(self, command: str, option: str):
        documented = re.search(rf"\[{option} \{{([^}}]+)\}}\]", _synopsis(command))
        assert documented, f"{option} has no choices in the synopsis"
        (action,) = [action for action in _actions(command) if option in action.option_strings]
        assert set(action.choices or ()) == set(documented.group(1).split(","))

    @pytest.mark.parametrize(("command", "option"), [("check", "--format"), ("mcp", "--transport")])
    def test_the_value_marked_default_is_the_default(self, command: str, option: str):
        marked = re.search(rf"^`{option} (\S+)` \(default\)$", _section(command), re.MULTILINE)
        assert marked, f"no value of {option} is marked (default)"
        (action,) = [action for action in _actions(command) if option in action.option_strings]
        assert action.default == marked.group(1)

    def test_the_server_listens_where_the_reference_says(self):
        said = re.search(r"Defaults to `([^`]+)` and `([^`]+)`", _section("mcp"))
        assert said
        defaults = {action.dest: action.default for action in _actions("mcp")}
        assert (defaults["host"], str(defaults["port"])) == said.groups()


# ---------------------------------------------------------------- exit status


def _source(tmp_path: Path, text: str, name: str = "duel.panel.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _build_scenarios(tmp_path: Path) -> dict[int, Callable[[], int]]:
    return {
        0: lambda: main(["build", str(_source(tmp_path, PANEL)), "--quiet"]),
        1: lambda: main(["build", str(_source(tmp_path, UNCOMPILABLE))]),
        2: lambda: main(["build", str(tmp_path / "missing.panel.yaml")]),
    }


def _check_scenarios(tmp_path: Path) -> dict[int, Callable[[], int]]:
    return {
        0: lambda: main(["check", "--quiet", str(_source(tmp_path, PANEL))]),
        1: lambda: main(["check", str(_source(tmp_path, BROKEN))]),
        2: lambda: main(["check", str(_source(tmp_path, PANEL, "duel.txt"))]),
    }


def _schema_scenarios(tmp_path: Path) -> dict[int, Callable[[], int]]:
    return {
        0: lambda: main(["schema", "-o", str(tmp_path / "panel.schema.json")]),
        2: lambda: main(["schema", "-o", str(tmp_path)]),
    }


def _returns_at_once(*_args: object, **_kwargs: object) -> None:
    """A server whose client disconnects as soon as it starts."""


def _mcp_scenarios(monkeypatch: pytest.MonkeyPatch) -> dict[int, Callable[[], int]]:
    def disconnected() -> int:
        import scenet.mcp  # noqa: PLC0415 -- only this scenario needs the extra

        with monkeypatch.context() as patch:
            # The client leaves at once: what `serve` returns on is a disconnect.
            patch.setattr(scenet.mcp, "serve", _returns_at_once)
            return main(["mcp"])

    def without_the_extra() -> int:
        def missing(name: str) -> object:
            raise ModuleNotFoundError(f"No module named {name!r}", name="mcp")

        with monkeypatch.context() as patch:
            patch.setattr("scenet.cli.importlib.import_module", missing)
            return main(["mcp"])

    return {0: disconnected, 2: without_the_extra}


class TestExitStatus:
    """Every code in a command's table is produced by a scenario, and every scenario
    produces a code in the table."""

    @pytest.mark.parametrize("command", COMMANDS)
    def test_each_documented_code_is_produced(
        self, command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        scenarios = {
            "build": lambda: _build_scenarios(tmp_path),
            "check": lambda: _check_scenarios(tmp_path),
            "schema": lambda: _schema_scenarios(tmp_path),
            "mcp": lambda: _mcp_scenarios(monkeypatch),
        }[command]()
        assert set(scenarios) == _exit_codes(command)
        for code, scenario in scenarios.items():
            assert scenario() == code, f"`scenet {command}` scenario for {code}"

    def test_a_bare_scenet_exits_two(self, capsys):
        assert main([]) == 2
        assert "usage: scenet" in capsys.readouterr().err

    def test_version_prints_the_version_and_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as caught:
            main(["--version"])
        assert caught.value.code == 0
        assert __version__ in capsys.readouterr().out


# ---------------------------------------------------------------- rules


def _diagnose(path: Path, *, deep: bool) -> list[Diagnostic]:
    """Check a corpus document as a file beside the gallery's pictures, fonts and puppet."""
    diagnose = diagnose_script if path.suffix == ".script" else diagnose_source
    return diagnose(path.read_text(encoding="utf-8"), source=path, base=GALLERY, deep=deep)


class TestRules:
    # The table of rules is held to the catalogue, both ways, by
    # `tests/test_diagnostics.py::TestTheReferenceListsEveryRule`.

    def test_the_table_gives_each_rule_its_level(self):
        """A note reports a house limit and never fails `check`, so the reader must be
        able to tell one from an error before running anything."""
        rows = re.findall(
            r"^\| \[`scenet/([a-z-]+)`\]\(diagnostics\.md#([a-z-]+)\) \| (\w+) \|",
            _section("check"),
            re.MULTILINE,
        )
        assert {name: level for name, _, level in rows} == {
            name: rule.level for name, rule in RULES.items()
        }
        assert [name for name, anchor, _ in rows if name != anchor] == []

    def test_every_rule_but_internal_has_a_corpus_document(self):
        covered = {path.name.split(".")[0] for path in DOCUMENTS}
        assert covered == set(RULES) - {"internal"}

    @pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
    def test_a_corpus_document_gets_exactly_its_rule(self, path: Path):
        rule = path.name.split(".")[0]
        found = _diagnose(path, deep=rule in {"layout", "balloon-placement", "sfx-placement"})
        assert [item.rule for item in found] == [rule], [item.message for item in found]

    def test_sarif_describes_each_rule_as_the_catalogue_does(self):
        found = [finding for path in DOCUMENTS for finding in _diagnose(path, deep=True)]
        driver = to_sarif(found)["runs"][0]["tool"]["driver"]
        described = {entry["id"]: entry for entry in driver["rules"]}
        assert set(described) == {f"scenet/{rule}" for rule in RULES} - {"scenet/internal"}
        for rule, entry in RULES.items():
            if rule == "internal":
                continue
            emitted = described[f"scenet/{rule}"]
            assert emitted["shortDescription"]["text"] == entry.summary
            assert emitted["fullDescription"]["text"] == entry.description
            assert emitted["help"]["text"].startswith(entry.help)

    def test_sarif_links_each_rule_to_its_entry(self):
        """`helpUri` is where code scanning and an editor send a reader, and `help` names it."""
        found = [finding for path in DOCUMENTS for finding in _diagnose(path, deep=True)]
        for emitted in to_sarif(found)["runs"][0]["tool"]["driver"]["rules"]:
            uri = f"https://creatoan.github.io/scenet/reference/diagnostics.html#{emitted['name']}"
            assert emitted["helpUri"] == uri
            assert uri in emitted["help"]["text"]
            assert f"]({uri})" in emitted["help"]["markdown"]


# ---------------------------------------------------------------- since and examples


SINCE: dict[str, Any] = tomllib.loads(
    (ROOT / "docs" / "reference" / "cli.since.toml").read_text(encoding="utf-8")
)
#: Every option of every command, by its long form when it has one: `build --output`.
OPTIONS = sorted(
    f"{command} {max(action.option_strings, key=len)}"
    for command in COMMANDS
    for action in _actions(command)
    if action.option_strings
)

_SINCE = re.compile(r"\*Since (\d+\.\d+)\.\*")


def _definition_blocks(command: str) -> list[tuple[str, str]]:
    """Each option definition of a command: its term line, and the text that defines it."""
    section = _section(command)
    found = re.findall(r"^(`-[^\n]*)\n((?:: .*\n)(?:  .*\n|\n(?=  ))*)", section, re.MULTILINE)
    return [(term, text) for term, text in found]


def _bash_lines(command: str) -> list[list[str]]:
    """Every `scenet` line of the `bash` blocks in a command's section, split as a shell would."""
    blocks = re.findall(r"```bash\n(.*?)```", _section(command), re.DOTALL)
    return [
        shlex.split(line)
        for block in blocks
        for line in block.splitlines()
        if line.strip().startswith("scenet ")
    ]


class TestEveryCommandAndOptionSaysWhenItCame:
    def test_the_versions_were_mined_for_every_command_and_option(self):
        assert sorted(SINCE["commands"]) == sorted(COMMANDS)
        assert sorted(SINCE["options"]) == OPTIONS
        assert SINCE["top-level"] == {"--version": "0.1"}

    @pytest.mark.parametrize("command", COMMANDS)
    def test_a_command_says_its_release(self, command: str):
        found = _SINCE.search(_section(command).split("```", 1)[0])
        assert found, f"`scenet {command}` says no *Since X.Y.* above its synopsis"
        assert found.group(1) == SINCE["commands"][command]

    @pytest.mark.parametrize("option", OPTIONS)
    def test_an_option_says_its_release(self, option: str):
        command, flag = option.split(" ")
        said = {
            found.group(1)
            for term, text in _definition_blocks(command)
            if re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", term)
            for found in _SINCE.finditer(text)
        }
        assert said == {SINCE["options"][option]}, f"{option}: end its definition on *Since X.Y.*"

    def test_one_added_since_the_last_release_takes_the_next(self):
        """Nothing is said to come later than the next minor release: `--pdf` is not out yet."""
        major, minor = (int(part) for part in __version__.split(".")[:2])
        for version in [*SINCE["commands"].values(), *SINCE["options"].values()]:
            assert tuple(int(part) for part in version.split(".")) <= (major, minor + 1)
        assert SINCE["options"]["build --pdf"] == f"{major}.{minor + 1}"


class TestEveryOptionHasAnExample:
    """A flag without a tested example is a gap (#315): every one is run by
    `tests/shell_examples.py`, from a `bash` block in its command's section."""

    @pytest.mark.parametrize("option", OPTIONS)
    def test_it_is_in_an_example(self, option: str):
        command, flag = option.split(" ")
        (action,) = [a for a in _actions(command) if flag in a.option_strings]
        lines = [words for words in _bash_lines(command) if words[1:2] == [command]]
        used = {word.split("=", 1)[0] for words in lines for word in words if word.startswith("-")}
        assert used & set(action.option_strings), f"add a `scenet {command} ... {flag}` example"


class TestNoIssueNumbers:
    def test_the_reference_says_what_a_thing_does_not_where_it_was_asked_for(self):
        assert re.findall(r"\(#\d+\)|(?<![\w/])#\d+\b", REFERENCE) == []


# ---------------------------------------------------------------- behaviour


def _files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if path.suffix in {".svg", ".json"})


class TestBehaviour:
    """One test per behavioural sentence in the reference. The pull request that added
    these carries the sentence-to-test table."""

    def test_duel_panel_yaml_becomes_duel_svg(self, tmp_path: Path):
        assert main(["build", str(_source(tmp_path, PANEL)), "--quiet"]) == 0
        assert _files(tmp_path) == ["duel.svg"]

    @pytest.mark.parametrize("written", [".", "out/"])
    def test_a_directory_takes_the_default_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: str
    ):
        source = _source(tmp_path, PANEL)
        monkeypatch.chdir(tmp_path)
        assert main(["build", str(source), "-o", written, "--quiet"]) == 0
        assert (tmp_path / written / "duel.svg").is_file()

    def test_a_scene_suffixes_each_panel_and_strips_on_request(self, tmp_path: Path):
        source = _source(
            tmp_path,
            "cast: {a: {reference: alice}}\npanels: {one: {}, two: {}}\n",
            "seq.scene.yaml",
        )
        assert main(["build", str(source), "--strip", "--quiet"]) == 0
        assert _files(tmp_path) == ["seq.one.svg", "seq.strip.svg", "seq.two.svg"]

    def test_pages_are_written_with_their_core_and_overlay(self, tmp_path: Path):
        source = _source(
            tmp_path,
            "cast: {a: {reference: alice}}\npanels: {one: {}}\n"
            "pages: [{tiers: [{panels: [one]}]}]\n",
            "story.scene.yaml",
        )
        assert main(["build", str(source), "--core", "--debug", "--quiet"]) == 0
        pages = [name for name in _files(tmp_path) if ".page-" in name]
        assert pages == ["story.page-1.core.json", "story.page-1.debug.svg", "story.page-1.svg"]

    def test_a_panel_named_like_a_page_is_exit_two_and_nothing_written(self, tmp_path: Path):
        source = _source(
            tmp_path,
            "cast: {a: {reference: alice}}\npanels: {page-1: {}}\n"
            "pages: [{tiers: [{panels: [page-1]}]}]\n",
            "story.scene.yaml",
        )
        assert main(["build", str(source)]) == 2
        assert _files(tmp_path) == []

    def test_quiet_hides_the_reassurance_never_the_findings(self, tmp_path: Path, capsys):
        # Four actors in a close-up: the camera retreats, and says so in a note.
        crowded = "camera: {shot: close_up}\ncast:\n" + "".join(
            f"  a{index}: {{reference: alice}}\n" for index in range(4)
        )
        main(["build", str(_source(tmp_path, crowded)), "--quiet"])
        main(["check", "--quiet", str(_source(tmp_path, PANEL, "fine.panel.yaml"))])
        assert capsys.readouterr().out == ""
        assert main(["check", "--quiet", str(_source(tmp_path, BROKEN, "bad.panel.yaml"))]) == 1
        assert "unknown-actor" in capsys.readouterr().err

    def test_check_writes_no_svg(self, tmp_path: Path):
        main(["check", "--quiet", str(_source(tmp_path, PANEL))])
        assert _files(tmp_path) == []

    def test_sarif_is_the_only_thing_on_stdout(self, tmp_path: Path, capsys):
        main(["check", "--format", "sarif", str(_source(tmp_path, BROKEN))])
        document = json.loads(capsys.readouterr().out)
        assert document["version"] == "2.1.0"

    def test_check_o_writes_one_finding_per_line_and_nothing_when_valid(self, tmp_path: Path):
        report = tmp_path / "report.txt"
        broken = _source(tmp_path, BROKEN, "bad.panel.yaml")
        assert main(["check", "-o", str(report), str(broken)]) == 1
        lines = report.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert "unknown-actor" in lines[0]
        assert main(["check", "-o", str(report), str(_source(tmp_path, PANEL))]) == 0
        assert report.read_text(encoding="utf-8") == ""

    @pytest.mark.parametrize("command", ["check", "schema"])
    def test_o_names_a_file_so_a_directory_is_refused(self, command: str, tmp_path: Path):
        argv = [command, "-o", str(tmp_path)]
        if command == "check":
            argv.append(str(_source(tmp_path, PANEL)))
        assert main(argv) == 2

    def test_schema_is_sorted_and_indented(self, capsys):
        assert main(["schema"]) == 0
        text = capsys.readouterr().out
        assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"

    def test_a_compile_error_is_one_line_not_a_traceback(self, tmp_path: Path, capsys):
        assert main(["build", str(_source(tmp_path, UNCOMPILABLE))]) == 1
        err = capsys.readouterr().err
        assert err.count("\n") == 1
        assert "Traceback" not in err

    def test_deep_is_skipped_once_the_cheap_pass_found_something(self, tmp_path: Path, capsys):
        bad_pose = "cast: {alice: {reference: alice, pose: levitating}}\n"
        assert main(["check", "--deep", str(_source(tmp_path, bad_pose))]) == 1
        err = capsys.readouterr().err
        assert err.count("unknown-pose") == 1
        assert "layout" not in err
