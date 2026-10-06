"""The command-line interface.

Error handling gets the most attention here. A panel that cannot be compiled is the
user's problem to fix, so it must produce a readable message and a non-zero exit --
never a traceback, which tells them nothing actionable.
"""

from pathlib import Path

import pytest

from scenet import __version__
from scenet.cli import build_parser, main

PANEL = """
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third}
staging:
  - alice left_of bob
script:
  - say: {by: alice, text: "Hello there."}
"""


@pytest.fixture
def panel_file(tmp_path: Path) -> Path:
    path = tmp_path / "scene.panel.yaml"
    path.write_text(PANEL, encoding="utf-8")
    return path


class TestBasics:
    def test_version_is_populated(self):
        assert __version__
        assert __version__ != "0.0.0+unknown", "package metadata should be installed"

    def test_version_flag_exits_zero(self, capsys: pytest.CaptureFixture[str]):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--version"])
        assert exc.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_bare_invocation_prints_help_to_stderr_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ):
        # Exit 2, not 0: a bare `scenet` did nothing, and a shell script chaining off
        # its status must not read that as success.
        assert main([]) == 2
        assert "usage: scenet" in capsys.readouterr().err

    def test_unknown_argument_is_rejected(self):
        with pytest.raises(SystemExit) as exc:
            main(["--definitely-not-a-flag"])
        assert exc.value.code != 0


class TestBuild:
    def test_builds_an_svg_next_to_the_source(self, panel_file: Path, capsys):
        assert main(["build", str(panel_file)]) == 0
        output = panel_file.with_name("scene.svg")
        assert output.exists()
        assert output.read_text(encoding="utf-8").startswith("<?xml")

    def test_panel_suffix_is_not_doubled(self, panel_file: Path, capsys):
        """`scene.panel.yaml` should yield `scene.svg`, not `scene.panel.svg`."""
        main(["build", str(panel_file)])
        assert not panel_file.with_name("scene.panel.svg").exists()
        assert panel_file.with_name("scene.svg").exists()

    @pytest.mark.parametrize(
        "name", ["scene.panel.yml", "scene.yml", "scene.scene.yml", "scene.panel.yaml"]
    )
    def test_both_yaml_extensions_name_the_output_alike(self, panel_file: Path, name: str, capsys):
        """`.yml` is read exactly as `.yaml` is, so it has to be named alike -- it used to
        come out as `scene.panel.yml.svg`."""
        source = panel_file.with_name(name)
        panel_file.rename(source)
        assert main(["build", str(source)]) == 0
        assert source.with_name("scene.svg").exists()

    def test_explicit_output_path_is_honoured(self, panel_file: Path, tmp_path: Path, capsys):
        target = tmp_path / "nested" / "out.svg"
        assert main(["build", str(panel_file), "-o", str(target)]) == 0
        assert target.exists()

    @pytest.mark.parametrize("written", [".", "out", "out/", "out\\", "./out/.."])
    def test_a_directory_takes_the_default_names(
        self, panel_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: str
    ):
        """`-o` naming a directory puts the output in it, under the name it would have
        had beside the source -- as `cp` does. `-o .` used to crash with a traceback."""
        if "\\" in written and Path("a\\b").name == "a\\b":
            pytest.skip("a backslash is not a separator here")
        (tmp_path / "out").mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        source = elsewhere / panel_file.name
        panel_file.rename(source)
        monkeypatch.chdir(tmp_path)
        assert main(["build", str(source), "-o", written, "--core", "--quiet"]) == 0
        directory = (tmp_path / written).resolve()
        assert sorted(path.name for path in directory.glob("scene.*")) == [
            "scene.core.json",
            "scene.svg",
        ]

    def test_a_trailing_separator_makes_the_directory(self, panel_file: Path, tmp_path: Path):
        """`-o new/` cannot be a file, so it is the directory to create."""
        target = tmp_path / "new"
        assert main(["build", str(panel_file), "-o", f"{target}/", "--quiet"]) == 0
        assert (target / "scene.svg").exists()

    def test_a_directory_takes_a_scene_and_its_pages(self, tmp_path: Path):
        source = tmp_path / "story.scene.yaml"
        source.write_text(
            "cast: {a: {reference: alice}}\npages: [{tiers: [{panels: [one, two]}]}]\n"
            "panels: {one: {}, two: {}}\n",
            encoding="utf-8",
        )
        out = tmp_path / "out"
        out.mkdir()
        assert main(["build", str(source), "-o", str(out), "--quiet"]) == 0
        assert sorted(path.name for path in out.iterdir()) == [
            "story.one.svg",
            "story.page-1.svg",
            "story.two.svg",
        ]

    def test_a_path_with_no_directory_is_still_a_file(self, panel_file: Path, tmp_path: Path):
        """Only an existing directory, or a trailing separator, means a directory: a
        new name without a suffix is still the file to write, as it always was."""
        target = tmp_path / "plain"
        assert main(["build", str(panel_file), "-o", str(target), "--quiet"]) == 0
        assert target.is_file()

    def test_core_flag_writes_the_intermediate_tier(self, panel_file: Path, tmp_path: Path, capsys):
        target = tmp_path / "out.svg"
        main(["build", str(panel_file), "-o", str(target), "--core"])
        core = tmp_path / "out.core.json"
        assert core.exists()
        assert '"format_version"' in core.read_text(encoding="utf-8")

    def test_debug_flag_writes_the_overlay(self, panel_file: Path, tmp_path: Path, capsys):
        target = tmp_path / "out.svg"
        main(["build", str(panel_file), "-o", str(target), "--debug"])
        assert (tmp_path / "out.debug.svg").exists()

    def test_live_text_switches_to_selectable_text(self, panel_file: Path, tmp_path: Path, capsys):
        outlined = tmp_path / "a.svg"
        live = tmp_path / "b.svg"
        main(["build", str(panel_file), "-o", str(outlined)])
        main(["build", str(panel_file), "-o", str(live), "--live-text"])
        assert "<text" not in outlined.read_text(encoding="utf-8")
        assert "<text" in live.read_text(encoding="utf-8")

    def test_quiet_suppresses_output(self, panel_file: Path, capsys):
        main(["build", str(panel_file), "--quiet"])
        assert capsys.readouterr().out == ""

    def test_notes_are_reported(self, tmp_path: Path, capsys):
        """A retreating camera changes the requested framing, so the user is told."""
        crowded = tmp_path / "crowd.panel.yaml"
        crowded.write_text(
            "camera: {shot: close_up}\ncast:\n"
            + "\n".join(f"  a{i}: {{reference: alice}}" for i in range(4)),
            encoding="utf-8",
        )
        main(["build", str(crowded)])
        assert "note:" in capsys.readouterr().out


class TestErrors:
    def test_missing_file_reports_cleanly(self, tmp_path: Path, capsys):
        assert main(["build", str(tmp_path / "nope.panel.yaml")]) == 2
        assert "no such file" in capsys.readouterr().err

    def test_an_unsupported_extension_is_a_usage_error_not_a_traceback(
        self, tmp_path: Path, capsys
    ):
        """It used to escape as a ValueError traceback, which this command promises never
        to print for anything that is the input's fault."""
        notes = tmp_path / "duel.txt"
        notes.write_text("cast: {a: {reference: alice}}\n", encoding="utf-8")
        assert main(["build", str(notes)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("scenet: ")
        assert "unsupported extension '.txt'" in err
        assert not (tmp_path / "duel.txt.svg").exists()

    @pytest.mark.parametrize("command", ["check", "schema"])
    def test_a_directory_is_no_place_for_a_report(
        self, panel_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
    ):
        """`check` and `schema` write one file of their own, which has no default name
        to take inside a directory. They used to crash writing to it."""
        arguments = [command, str(panel_file)] if command == "check" else [command]
        assert main([*arguments, "-o", str(tmp_path)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("scenet: ")
        assert "directory" in err
        assert "Traceback" not in err

    def test_check_writes_its_text_report_to_the_output_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        """`-o` is documented as writing the report to a file, and it was ignored unless
        the format was SARIF: the findings went to stderr and no file was written."""
        bad = tmp_path / "bad.panel.yaml"
        bad.write_text("cast:\n  a: {reference: nobody}\n", encoding="utf-8")
        target = tmp_path / "report.txt"
        assert main(["check", str(bad), "-o", str(target)]) == 1
        report = target.read_text(encoding="utf-8")
        assert "unknown-puppet" in report
        assert report.endswith("\n")
        captured = capsys.readouterr()
        assert "unknown-puppet" not in captured.err
        assert f"wrote {target}" in captured.out

    def test_a_clean_check_writes_an_empty_report(self, panel_file: Path, tmp_path: Path, capsys):
        target = tmp_path / "report.txt"
        assert main(["check", str(panel_file), "-o", str(target), "--quiet"]) == 0
        assert target.read_text(encoding="utf-8") == ""
        assert capsys.readouterr().out == ""

    def test_invalid_panel_reports_without_a_traceback(self, tmp_path: Path, capsys):
        bad = tmp_path / "bad.panel.yaml"
        bad.write_text("cast:\n  a: {reference: alice}\nstaging:\n  - a left_of ghost\n", "utf-8")
        assert main(["build", str(bad)]) == 1
        error = capsys.readouterr().err
        assert error.startswith("scenet:")
        assert "ghost" in error
        assert "Traceback" not in error

    def test_unknown_character_is_reported_cleanly(self, tmp_path: Path, capsys):
        """Naming a character that does not exist is a user error, so it gets a
        message listing the available cast -- not a traceback."""
        bad = tmp_path / "bad.panel.yaml"
        bad.write_text("cast:\n  a: {reference: nobody}\n", encoding="utf-8")
        assert main(["build", str(bad)]) == 1
        error = capsys.readouterr().err
        assert "nobody" in error
        assert "alice" in error
        assert "Traceback" not in error

    def test_error_messages_are_not_wrapped_in_quotes(self, tmp_path: Path, capsys):
        """KeyError stringifies via repr, which would surface the message wrapped in
        quotes. Users should see prose."""
        bad = tmp_path / "bad.panel.yaml"
        bad.write_text("cast:\n  a: {reference: nobody}\n", encoding="utf-8")
        main(["build", str(bad)])
        assert capsys.readouterr().err.startswith("scenet: unknown character")


def _scene(tmp_path: Path, panels: str, pages: str = "") -> Path:
    source = tmp_path / "story.scene.yaml"
    source.write_text(
        f"cast: {{a: {{reference: alice}}}}\npanels: {panels}\n{pages}", encoding="utf-8"
    )
    return source


def _written(tmp_path: Path) -> list[str]:
    return sorted(path.name for path in tmp_path.iterdir() if path.suffix in {".svg", ".json"})


class TestOutputsNeverReplaceEachOther:
    """`docs/reference/cli.md` refuses one output silently replacing another, but only a
    panel named like a page was caught. Found while writing the contract tests for #93."""

    @pytest.mark.parametrize(
        ("panels", "flags", "clash"),
        [
            ("{one: {}, strip: {}}", ["--strip"], "story.strip.svg"),
            ("{x: {}, x.debug: {}}", ["--debug"], "story.x.debug.svg"),
            ("{One: {}, one: {}}", [], "story.one.svg"),
        ],
        ids=["strip", "debug-overlay", "case"],
    )
    def test_a_clash_is_a_usage_error_and_nothing_is_written(
        self, tmp_path: Path, capsys, panels: str, flags: list[str], clash: str
    ):
        source = _scene(tmp_path, panels)
        assert main(["build", str(source), *flags]) == 2
        assert _written(tmp_path) == []
        assert clash.lower() in capsys.readouterr().err.lower()

    def test_a_panel_named_strip_is_fine_without_a_strip(self, tmp_path: Path):
        source = _scene(tmp_path, "{one: {}, strip: {}}")
        assert main(["build", str(source), "--quiet"]) == 0
        assert _written(tmp_path) == ["story.one.svg", "story.strip.svg"]

    @pytest.mark.parametrize("name", ["a/b", "a\\\\b"], ids=["slash", "backslash"])
    def test_a_name_that_cannot_be_a_file_is_a_usage_error_not_a_traceback(
        self, tmp_path: Path, capsys, name: str
    ):
        source = _scene(tmp_path, f'{{one: {{}}, "{name}": {{}}}}')
        assert main(["build", str(source)]) == 2
        assert _written(tmp_path) == []
        assert "cannot be part of a file name" in capsys.readouterr().err


class TestStripNeedsMoreThanOnePanel:
    """`--strip` is "ignored for a single panel", but only a document whose one panel was
    called `panel` skipped it: a one-panel scene still wrote a strip of one."""

    def test_a_one_panel_scene_writes_no_strip(self, tmp_path: Path):
        source = _scene(tmp_path, "{only: {}}")
        assert main(["build", str(source), "--strip", "--quiet"]) == 0
        assert _written(tmp_path) == ["story.only.svg"]

    def test_two_panels_still_write_one(self, tmp_path: Path):
        source = _scene(tmp_path, "{one: {}, two: {}}")
        assert main(["build", str(source), "--strip", "--quiet"]) == 0
        assert "story.strip.svg" in _written(tmp_path)
