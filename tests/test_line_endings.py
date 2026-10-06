"""Every file Scenet writes ends its lines with LF, on every platform.

Identical input must produce byte-identical output, and a line ending is bytes.
`Path.write_text` and a text-mode stdout translate `\\n` to the platform's line separator,
so on Windows every SVG, Core, report and schema came out with CRLF and differed from the
same build on Linux. CI ran only on Linux, where the translation is a no-op, so nothing
noticed; the Windows job in CI is what runs the byte checks here where they can fail.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from scenet.cli import main

REPO = Path(__file__).resolve().parents[1]

SCENE = """\
cast: {a: {reference: alice}, b: {reference: bob, at: right_third}}
staging: [a left_of b]
pages: [{tiers: [{panels: [one, two]}]}]
panels:
  one: {script: [{say: {by: a, text: "Two lines,\\nso there is a break."}}]}
  two: {over: one}
"""


def scenet(*arguments: str) -> bytes:
    """Run the CLI in a fresh interpreter and return exactly the bytes it wrote to stdout."""
    return subprocess.run(  # noqa: S603 -- our own interpreter, running a literal in this file
        [
            sys.executable,
            "-c",
            "import sys; from scenet.cli import main; sys.exit(main())",
            *arguments,
        ],
        capture_output=True,
        check=False,
        cwd=REPO,
    ).stdout


class TestFilesAreLf:
    def test_every_build_output(self, tmp_path: Path):
        source = tmp_path / "story.scene.yaml"
        source.write_bytes(SCENE.encode("utf-8"))
        arguments = ["build", str(source), "--core", "--debug", "--strip", "--quiet"]
        assert main(arguments) == 0
        written = sorted(path for path in tmp_path.iterdir() if path != source)
        assert len(written) == 10
        for path in written:
            content = path.read_bytes()
            assert b"\n" in content, path.name
            assert b"\r" not in content, path.name

    def test_a_sarif_report(self, tmp_path: Path):
        bad = tmp_path / "bad.panel.yaml"
        bad.write_bytes(b"cast:\n  a: {reference: nobody}\n")
        report = tmp_path / "results.sarif"
        main(["check", "--format", "sarif", "-o", str(report), "--quiet", str(bad)])
        assert b"\r" not in report.read_bytes()

    def test_a_text_report(self, tmp_path: Path):
        bad = tmp_path / "bad.panel.yaml"
        bad.write_bytes(b"cast:\n  a: {reference: nobody}\n")
        report = tmp_path / "report.txt"
        main(["check", "-o", str(report), "--quiet", str(bad)])
        assert report.read_bytes().endswith(b"\n")
        assert b"\r" not in report.read_bytes()

    @pytest.mark.parametrize("scene", [False, True])
    def test_a_schema(self, tmp_path: Path, scene: bool):
        target = tmp_path / "schema.json"
        main(["schema", "-o", str(target), *(["--scene"] if scene else [])])
        assert b"\r" not in target.read_bytes()


class TestStdoutIsLf:
    """`scenet check --format sarif x > results.sarif` is documented as producing the file,
    so what reaches stdout is held to the same rule as what is written to disk."""

    def test_a_schema(self):
        out = scenet("schema")
        assert out.startswith(b"{\n")
        assert b"\r" not in out

    def test_a_sarif_report(self, tmp_path: Path):
        bad = tmp_path / "bad.panel.yaml"
        bad.write_bytes(b"cast:\n  a: {reference: nobody}\n")
        out = scenet("check", "--format", "sarif", str(bad))
        assert out.startswith(b"{\n")
        assert b"\r" not in out


def _write_text_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
    ]


WRITERS = sorted([*(REPO / "src" / "scenet").rglob("*.py"), *(REPO / "scripts").glob("*.py")])


class TestEveryWriterSaysLf:
    """The byte checks above only fail on Windows. This one fails everywhere: a new
    `write_text` that leaves the line ending to the platform is caught on Linux too."""

    @pytest.mark.parametrize("path", WRITERS, ids=lambda path: path.relative_to(REPO).as_posix())
    def test_write_text_passes_newline(self, path: Path):
        unpinned = [
            call.lineno
            for call in _write_text_calls(path)
            if not any(keyword.arg == "newline" for keyword in call.keywords)
        ]
        assert unpinned == [], f"write_text without newline= at lines {unpinned}"
