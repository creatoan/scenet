"""The security model page states facts, and each fact is held by a test (#381).

`docs/explanation/security_model.md` lists what Scenet guarantees with untrusted input, each
guarantee beside the test that holds it. This file holds the ones no other test did, and holds
the page to its own rule: every guarantee names a test, and every test it names exists.
"""

import ast
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scenet.emit.pdf import printed_panels, render_pdf
from scenet.pipeline import compile_book_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "scenet"
PAGE = ROOT / "docs" / "explanation" / "security_model.md"
BLOB = "https://github.com/creatoan/scenet/blob/main/"
SVG = "{http://www.w3.org/2000/svg}"


def _modules() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        f"{node.func.value.id}.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }


#: Modules that run or rebuild what they are handed, and the XML parsers.
_FORBIDDEN_MODULES = ("pickle", "marshal", "shelve", "subprocess", "lxml", "defusedxml")
_XML_PARSERS = ("xml.etree", "xml.dom", "xml.parsers", "xml.sax.parse", "xml.sax.make_parser")
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "os.system", "os.popen", "os.execv"}


class TestNothingRunsWhatItReads:
    @pytest.mark.parametrize("path", _modules(), ids=lambda p: p.relative_to(SOURCE).as_posix())
    def test_no_module_runs_or_rebuilds_what_it_is_handed(self, path: Path):
        imported = _imports(path)
        assert not {name for name in imported if name.split(".")[0] in _FORBIDDEN_MODULES}, (
            f"{path.name} imports a module that runs or rebuilds what it reads"
        )
        assert not _calls(path) & _FORBIDDEN_CALLS

    @pytest.mark.parametrize("path", _modules(), ids=lambda p: p.relative_to(SOURCE).as_posix())
    def test_no_xml_is_parsed(self, path: Path):
        """SVG is written, never read: `xml.sax.saxutils` escapes, and nothing parses."""
        parsers = {name for name in _imports(path) if name.startswith(_XML_PARSERS)}
        assert parsers == set()

    def test_only_the_mcp_server_starts_processes_and_only_its_own(self):
        starting = {
            path.relative_to(SOURCE).as_posix()
            for path in _modules()
            if any(name.split(".")[0] == "multiprocessing" for name in _imports(path))
        }
        assert starting == {"mcp.py"}


def _svgs() -> list[Path]:
    return sorted((ROOT / "docs" / "images").rglob("*.svg"))


_REFERENCE = re.compile(r"^(#|data:image/(png|jpeg);base64,)|^(?![a-z][a-z0-9+.-]*:)(?!/)")


class TestTheOutput:
    """Every SVG the gallery builds, as committed for the documentation, and a print PDF."""

    @pytest.mark.parametrize("path", _svgs(), ids=lambda p: p.name)
    def test_no_svg_holds_a_script_a_handler_or_a_link_out(self, path: Path):
        root = ElementTree.fromstring(path.read_bytes())
        for element in root.iter():
            assert element.tag not in {f"{SVG}script", f"{SVG}foreignObject"}, path.name
            for name, value in element.attrib.items():
                local = name.rsplit("}", 1)[-1]
                assert not local.lower().startswith("on"), (path.name, name)
                if local == "href":
                    assert _REFERENCE.match(value), (path.name, value[:60])

    def test_a_print_pdf_holds_no_script_link_or_action(self):
        book = compile_book_file(ROOT / "examples" / "gallery" / "34-supplied-art.scene.yaml")
        printed = printed_panels(book.pages, {n: r.core for n, r in book.panels.items()})
        pdf = render_pdf(book.pages, printed, fonts=book.fonts, images=book.images)
        for token in (
            b"/JavaScript",
            b"/JS ",
            b"/URI",
            b"/Link",
            b"/OpenAction",
            b"/AA ",
            b"/Launch",
        ):
            assert token not in pdf, token


class TestThePlayground:
    PAGE = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")

    def _policy(self) -> dict[str, list[str]]:
        found = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', self.PAGE)
        assert found, "the playground sets its Content Security Policy in a meta tag"
        return {
            directive.split()[0]: directive.split()[1:]
            for directive in (part.strip() for part in found.group(1).split(";"))
            if directive
        }

    def test_it_runs_no_script_but_its_own_and_loads_no_plug_in(self):
        policy = self._policy()
        assert policy["default-src"] == ["'self'"]
        assert "'unsafe-inline'" not in policy["script-src"]
        assert "'unsafe-eval'" not in policy["script-src"]
        assert policy["object-src"] == ["'none'"]
        assert policy["base-uri"] == ["'self'"]
        assert policy["form-action"] == ["'none'"]

    def test_a_shared_link_holds_at_most_512_kb(self):
        persist = (ROOT / "playground" / "src" / "persist.ts").read_text(encoding="utf-8")
        assert "export const MAX_SOURCE_BYTES = 512 * 1024;" in persist


_LINK = re.compile(r"\[`(tests/[\w/]+\.py)(?:::([\w:]+))?`\]\(([^)]+)\)")


def _rows() -> list[tuple[str, str]]:
    text = PAGE.read_text(encoding="utf-8")
    table = text[text.index("## What is guaranteed") : text.index("## What is not guaranteed")]
    return [
        (guarantee.strip(), held.strip())
        for guarantee, held in re.findall(r"^\| (?!Guarantee|---)(.+?) \| (.+) \|$", table, re.M)
    ]


def _defines(path: Path, qualified: str) -> bool:
    scope: list[ast.stmt] = ast.parse(path.read_text(encoding="utf-8")).body
    for name in qualified.split("::"):
        found = next(
            (
                node
                for node in scope
                if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name == name
            ),
            None,
        )
        if found is None:
            return False
        scope = found.body
    return True


class TestThePage:
    def test_it_has_its_guarantees(self):
        assert len(_rows()) >= 12

    @pytest.mark.parametrize(("guarantee", "held"), _rows(), ids=lambda value: value[:40])
    def test_every_guarantee_names_a_test_that_exists(self, guarantee: str, held: str):
        links = _LINK.findall(held)
        assert links, f"no test holds: {guarantee}"
        for path, name, url in links:
            assert url == BLOB + path
            assert (ROOT / path).is_file(), path
            assert name, f"{path}: name the test, as {path}::TestSomething"
            assert _defines(ROOT / path, name), f"{path} defines no {name}"

    @pytest.mark.parametrize(
        "page",
        ["SECURITY.md", "README.md", "docs/reference/api/guarantees.md"],
    )
    def test_it_is_linked_from(self, page: str):
        text = (ROOT / page).read_text(encoding="utf-8")
        assert "security_model" in text, f"{page} does not link the security model"

    def test_it_is_in_the_explanations(self):
        index = (ROOT / "docs" / "explanation" / "index.md").read_text(encoding="utf-8")
        assert "\nsecurity_model\n" in index


class TestTheSecurityPolicy:
    TEXT = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    def test_it_says_how_to_report_and_promises_nothing(self):
        assert "private vulnerability reporting" in self.TEXT
        assert "makes no commitment about security" in self.TEXT
        assert not re.search(r"within \d+ (?:business )?days", self.TEXT, re.IGNORECASE)

    def test_it_names_no_supported_version(self):
        assert not re.search(r"^\|.*\| Yes \|$", self.TEXT, re.MULTILINE)
