"""The MCP server -- the one rung that closes the loop with no human relaying text.

A model calls `validate`, reads a finding that names the rule, the line and the fix,
corrects its own document and calls `render`. These tests drive every tool through a
real MCP client, in process, and once more over stdio against the installed `scenet mcp`
command -- because the commonest way to ship a broken stdio server is for something to
print to stdout, and only the real transport shows that.
"""

import base64
import importlib
import json
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any, get_args

import anyio
import fonts.ttf
import pytest
from mcp import Client, StdioServerParameters
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)

from scenet import compile_source, render, render_conditioning
from scenet import mcp as scenet_mcp
from scenet.cli import main
from scenet.diagnostics import RULES
from scenet.mcp import (
    Section,
    build_server,
    compile_panel,
    get_spec,
    list_puppets,
    render_panel,
    validate,
)
from scenet.spec_pack import SPEC_PARTS, part
from tests.images import contract, tiny_png

TOOLS = {"get_spec", "list_puppets", "validate", "compile", "render"}

VALID = """\
panel: {size: [420, 560]}
cast:
  alice: {reference: alice, at: left_third}
  bob:   {reference: bob,   at: right_third, facing: left}
staging:
  - alice left_of bob
script:
  - say: {by: alice, text: "Hello there."}
"""

#: The same panel over a setting, drawn in colour (#244).
TINTED = (
    """\
palette: tinted
setting: {place: docks, time: dusk}
"""
    + VALID
)

UNKNOWN_ACTOR = """\
panel: {size: [420, 560]}
cast:
  alice: {reference: alice}
script:
  - say: {by: bpb, text: Hello}
"""

#: Keys alongside `panels:` are defaults every panel inherits.
SCENE = """\
panel: {size: [420, 560]}
cast:
  alice: {reference: alice}
panels:
  first:
    script:
      - say: {by: alice, text: "One."}
  second:
    over: first
    camera: {shot: close_up}
"""

SCRIPT = """\
---
panel:
  size: [600, 400]
cast:
  ALICE: {reference: alice}
---

PANEL 1
ALICE
Hello.

PANEL 2
@shot: close_up
ALICE
Goodbye.
"""

#: Prose before the first heading. No front matter, so the reported line is the file's.
BAD_SCRIPT = """\


@shot: close_up

PANEL 1
ALICE
Hello.
"""

#: Passes every cheap check, and fails only once the solver runs.
CAST_LESS = "panel: {size: [420, 560]}\n"

#: The same two panels, laid out side by side on one page.
PAGED = SCENE + "pages: [{tiers: [{panels: [first, second]}]}]\n"


def call(tool: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
    """One tool call through a real MCP client session, in process."""

    async def go() -> CallToolResult:
        async with Client(build_server()) as client:
            return await client.call_tool(tool, arguments or {})

    return anyio.run(go)


def text_of(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


@pytest.fixture(scope="module")
def listing() -> tuple[str | None, str | None, Any]:
    """The negotiated protocol version, the server's instructions, and its tool list."""

    async def go() -> tuple[str | None, str | None, Any]:
        async with Client(build_server()) as client:
            return client.protocol_version, client.instructions, await client.list_tools()

    return anyio.run(go)


class TestDiscovery:
    """What a client sees before it calls anything."""

    def test_the_five_tools_and_no_more(self, listing: Any):
        """The issue's list, deliberately small: each extra tool is surface to learn."""
        *_, tools = listing
        assert {tool.name for tool in tools.tools} == TOOLS

    def test_every_tool_is_read_only_and_closed_world(self, listing: Any):
        """Nothing here writes a file, touches the network or changes between calls."""
        *_, tools = listing
        for tool in tools.tools:
            assert tool.annotations is not None, tool.name
            assert tool.annotations.read_only_hint is True, tool.name
            assert tool.annotations.idempotent_hint is True, tool.name
            assert tool.annotations.open_world_hint is False, tool.name

    def test_descriptions_are_written_for_a_model(self, listing: Any):
        """The docstring's Args section is for Python readers; the schema carries those."""
        *_, tools = listing
        for tool in tools.tools:
            assert tool.description, tool.name
            assert "Args:" not in tool.description, tool.name
            assert "Returns:" not in tool.description, tool.name

    def test_every_parameter_is_described(self, listing: Any):
        *_, tools = listing
        for tool in tools.tools:
            for name, schema in tool.input_schema.get("properties", {}).items():
                assert schema.get("description"), f"{tool.name}.{name}"

    def test_the_protocol_is_the_one_targeted(self, listing: Any):
        version, _, _ = listing
        assert version == "2026-07-28"

    def test_instructions_send_a_model_to_the_spec_first(self, listing: Any):
        _, instructions, _ = listing
        assert "get_spec" in (instructions or "")
        assert "validate" in (instructions or "")


class TestGetSpec:
    def test_with_no_section_it_is_the_preamble_and_a_table_of_contents(self):
        result = call("get_spec")
        body = text_of(result)
        assert part("preamble").strip() in body
        for name in SPEC_PARTS:
            assert f"`{name}`" in body

    @pytest.mark.parametrize("section", list(SPEC_PARTS))
    def test_each_section_is_that_part_of_the_pack(self, section: str):
        assert text_of(call("get_spec", {"section": section})) == part(section)

    def test_the_sections_offered_are_the_parts_of_the_pack(self):
        assert get_args(Section) == tuple(SPEC_PARTS)

    def test_an_unknown_section_is_refused_by_the_schema(self):
        result = call("get_spec", {"section": "chapter-eleven"})
        assert result.is_error


class TestListPuppets:
    def test_every_shipped_puppet_with_what_it_declares(self):
        result = call("list_puppets")
        assert result.structured_content is not None
        puppets = result.structured_content["puppets"]
        assert [puppet["name"] for puppet in puppets] == ["alice", "bob"]
        alice = puppets[0]
        assert "pointing" in alice["poses"]
        assert "angry" in alice["expressions"]
        assert alice["poses"] == sorted(alice["poses"])
        assert alice["heads_tall"] == 7.5


class TestValidate:
    def test_a_valid_panel(self):
        result = call("validate", {"source": VALID})
        assert result.structured_content == {"valid": True, "findings": []}

    def test_a_finding_names_the_rule_the_place_and_the_fix(self):
        """Exactly what a model needs to repair its own output."""
        result = call("validate", {"source": UNKNOWN_ACTOR})
        assert result.structured_content is not None
        assert result.structured_content["valid"] is False
        (finding,) = result.structured_content["findings"]
        assert finding["rule"] == "scenet/unknown-actor"
        assert "bpb" in finding["message"]
        assert finding["fix"] == RULES["unknown-actor"].help
        assert finding["where"] == "script.0.say.by"
        assert (finding["line"], finding["column"]) == (5, 15)
        assert finding["end_line"] >= finding["line"]

    def test_a_finding_is_also_readable_as_text(self):
        """Many hosts show the model `content` only, never `structuredContent`."""
        assert "scenet/unknown-actor" in text_of(call("validate", {"source": UNKNOWN_ACTOR}))

    def test_a_scene(self):
        assert call("validate", {"source": SCENE}).structured_content == {
            "valid": True,
            "findings": [],
        }

    def test_a_comic_script(self):
        result = call("validate", {"source": SCRIPT, "syntax": "script"})
        assert result.structured_content == {"valid": True, "findings": []}

    def test_a_broken_comic_script(self):
        result = call("validate", {"source": BAD_SCRIPT, "syntax": "script"})
        assert result.structured_content is not None
        (finding,) = result.structured_content["findings"]
        assert finding["rule"].startswith("scenet/")
        assert "before the first PANEL" in finding["message"]
        assert finding["line"] == 3

    def test_the_cheap_pass_misses_what_only_the_solver_finds(self):
        assert call("validate", {"source": CAST_LESS}).structured_content == {
            "valid": True,
            "findings": [],
        }

    def test_deep_reaches_the_solver(self):
        result = call("validate", {"source": CAST_LESS, "deep": True})
        assert result.structured_content is not None
        (finding,) = result.structured_content["findings"]
        assert finding["rule"] == "scenet/layout"

    def test_an_unknown_syntax_is_refused_by_the_schema(self):
        assert call("validate", {"source": VALID, "syntax": "xml"}).is_error

    def test_a_document_with_only_notes_is_valid(self):
        """A note reports a house limit, not a fault: the document is still valid."""
        long = " ".join(["word"] * 26)
        source = (
            f'cast: {{bob: {{reference: bob}}}}\nscript:\n  - say: {{by: bob, text: "{long}"}}\n'
        )
        result = call("validate", {"source": source})
        assert result.structured_content is not None
        assert result.structured_content["valid"] is True
        (finding,) = result.structured_content["findings"]
        assert (finding["rule"], finding["level"]) == ("scenet/word-limit", "note")

    def test_every_finding_says_its_level(self):
        result = call("validate", {"source": UNKNOWN_ACTOR})
        assert result.structured_content is not None
        assert [item["level"] for item in result.structured_content["findings"]] == ["error"]


class TestCompile:
    def test_the_core_is_what_build_writes_with_core(self):
        result = call("compile", {"source": VALID})
        assert not result.is_error
        assert result.structured_content is not None
        (panel,) = result.structured_content["panels"]
        assert panel["name"] == "panel"
        assert panel["core"] == json.loads(compile_source(VALID).core.to_json())

    def test_notes_are_carried(self):
        crowded = (
            "{panel: {size: [600.0, 400.0]}, camera: {shot: close_up},"
            " cast: {a: {reference: alice}, b: {reference: bob}}, staging: [a left_of b]}"
        )
        result = call("compile", {"source": crowded})
        assert result.structured_content is not None
        (panel,) = result.structured_content["panels"]
        assert any("camera retreated" in note for note in panel["notes"])

    def test_a_scene_compiles_every_panel_in_order(self):
        result = call("compile", {"source": SCENE})
        assert result.structured_content is not None
        assert [panel["name"] for panel in result.structured_content["panels"]] == [
            "first",
            "second",
        ]

    def test_a_page_comes_back_with_its_frames(self):
        result = call("compile", {"source": PAGED})
        assert result.structured_content is not None
        (page,) = result.structured_content["pages"]
        assert page["number"] == 1
        assert [frame["panel"] for frame in page["core"]["frames"]] == ["first", "second"]

    def test_a_document_without_pages_has_none(self):
        result = call("compile", {"source": SCENE})
        assert result.structured_content is not None
        assert result.structured_content["pages"] == []

    def test_a_comic_script_is_named_by_its_panel_numbers(self):
        result = call("compile", {"source": SCRIPT, "syntax": "script"})
        assert result.structured_content is not None
        assert [panel["name"] for panel in result.structured_content["panels"]] == ["1", "2"]

    def test_a_broken_document_is_an_error_carrying_the_findings(self):
        result = call("compile", {"source": UNKNOWN_ACTOR})
        assert result.is_error
        assert "scenet/unknown-actor" in text_of(result)
        assert "5:15" in text_of(result)
        assert RULES["unknown-actor"].help in text_of(result)

    def test_a_solver_failure_is_located_too(self):
        result = call("compile", {"source": CAST_LESS})
        assert result.is_error
        assert "scenet/layout" in text_of(result)

    def test_a_broken_script_is_an_error(self):
        result = call("compile", {"source": BAD_SCRIPT, "syntax": "script"})
        assert result.is_error
        assert "scenet/" in text_of(result)


class TestRender:
    @staticmethod
    def resources(result: CallToolResult) -> list[TextResourceContents]:
        found = []
        for block in result.content:
            if isinstance(block, EmbeddedResource):
                assert isinstance(block.resource, TextResourceContents)
                found.append(block.resource)
        return found

    def test_the_svg_is_exactly_what_build_writes(self):
        """Byte-identical to `scenet build`, which is what makes it worth trusting."""
        result = call("render", {"source": VALID})
        assert not result.is_error
        (svg,) = self.resources(result)
        assert svg.mime_type == "image/svg+xml"
        assert svg.text == render(compile_source(VALID).core)

    def test_never_as_an_image_block(self):
        """Hosts forward image blocks to models that reject SVG, breaking the turn."""
        result = call("render", {"source": VALID})
        assert not any(isinstance(block, ImageContent) for block in result.content)

    def test_it_can_be_read_by_a_screen_reader(self):
        (svg,) = self.resources(call("render", {"source": VALID}))
        assert 'role="img"' in svg.text

    def test_without_aria_it_is_what_build_writes_with_no_aria(self):
        (svg,) = self.resources(call("render", {"source": VALID, "aria": False}))
        assert svg.text == render(compile_source(VALID).core, aria=False)
        assert "role=" not in svg.text

    def test_live_text_is_smaller(self):
        outlines = self.resources(call("render", {"source": VALID}))[0].text
        live = self.resources(call("render", {"source": VALID, "live_text": True}))[0].text
        assert "<text" in live
        assert len(live) < len(outlines)

    def test_mono_draws_a_tinted_panel_as_palette_mono_does(self):
        """The output's monochrome (#244), as `scenet build --mono` writes it."""
        tinted = TINTED
        mono = tinted.replace("palette: tinted", "palette: mono")
        (drawn,) = self.resources(call("render", {"source": tinted, "mono": True}))
        (plain,) = self.resources(call("render", {"source": mono}))
        (coloured,) = self.resources(call("render", {"source": tinted}))
        assert drawn.text == plain.text
        assert coloured.text != plain.text

    def test_one_resource_per_panel_named_after_it(self):
        result = call("render", {"source": SCENE})
        assert [svg.uri for svg in self.resources(result)] == [
            "scenet://panels/first.svg",
            "scenet://panels/second.svg",
        ]

    def test_each_page_follows_the_panels(self):
        """A page is one more SVG resource, not one more tool: the budget is five."""
        result = call("render", {"source": PAGED})
        assert [svg.uri for svg in self.resources(result)] == [
            "scenet://panels/first.svg",
            "scenet://panels/second.svg",
            "scenet://pages/1.svg",
        ]
        assert isinstance(result.content[0], TextContent)
        assert "1 page" in result.content[0].text

    def test_a_summary_comes_first_as_text(self):
        result = call("render", {"source": SCENE})
        assert isinstance(result.content[0], TextContent)
        assert "2 panels" in result.content[0].text

    def test_a_comic_script(self):
        result = call("render", {"source": SCRIPT, "syntax": "script"})
        assert len(self.resources(result)) == 2

    def test_a_broken_document_is_an_error(self):
        result = call("render", {"source": UNKNOWN_ACTOR})
        assert result.is_error
        assert "scenet/unknown-actor" in text_of(result)


class TestStdoutStaysClean:
    """On a stdio transport, stdout *is* the protocol stream. One stray `print` -- the
    `wrote` and `note:` lines `scenet build` emits, say -- and the client reads garbage."""

    def test_no_tool_writes_to_stdout(self, capsys: pytest.CaptureFixture[str]):
        get_spec()
        get_spec("gallery")
        list_puppets()
        validate(VALID)
        validate(UNKNOWN_ACTOR)
        compile_panel(VALID)
        render_panel(SCENE)
        for broken in (compile_panel, render_panel):
            with pytest.raises(Exception, match="scenet/"):
                broken(UNKNOWN_ACTOR)
        assert capsys.readouterr().out == ""

    def test_over_a_real_stdio_session(self):
        """The installed command, spoken to as a client would. Anything written to stdout
        that is not a JSON-RPC message breaks this session."""
        command = shutil.which("scenet", path=str(Path(sys.executable).parent))
        assert command, "the scenet console script should be installed beside the interpreter"

        async def go() -> list[CallToolResult]:
            parameters = StdioServerParameters(command=command, args=["mcp"])
            async with Client(parameters) as client:
                tools = await client.list_tools()
                assert {tool.name for tool in tools.tools} == TOOLS
                return [
                    await client.call_tool("get_spec", {"section": "characters"}),
                    await client.call_tool("list_puppets", {}),
                    await client.call_tool("validate", {"source": UNKNOWN_ACTOR}),
                    await client.call_tool("compile", {"source": VALID}),
                    await client.call_tool("compile", {"source": CAST_LESS}),
                    await client.call_tool("render", {"source": SCRIPT, "syntax": "script"}),
                ]

        spec, puppets, invalid, compiled, failed, rendered = anyio.run(go)
        assert "alice" in text_of(spec)
        assert puppets.structured_content is not None
        assert invalid.structured_content is not None
        assert invalid.structured_content["valid"] is False
        assert not compiled.is_error
        assert failed.is_error
        assert not rendered.is_error


class TestCommand:
    @pytest.fixture
    def runs(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
        """Capture what the server would have been started with, without starting it."""
        seen: list[tuple[str, dict[str, Any]]] = []

        def record(transport: str, **options: Any) -> None:
            seen.append((transport, options))

        monkeypatch.setattr(scenet_mcp, "serve", record)
        return seen

    def test_stdio_is_the_default(self, runs: list[tuple[str, dict[str, Any]]]):
        assert main(["mcp"]) == 0
        assert runs == [("stdio", {})]

    def test_streamable_http_takes_a_host_and_port(self, runs: list[tuple[str, dict[str, Any]]]):
        assert main(["mcp", "--transport", "streamable-http", "--port", "9123"]) == 0
        assert runs == [("streamable-http", {"host": "127.0.0.1", "port": 9123})]

    def test_sse_is_not_offered(self, capsys: pytest.CaptureFixture[str]):
        """SSE is deprecated in the protocol; Streamable HTTP replaced it."""
        with pytest.raises(SystemExit):
            main(["mcp", "--transport", "sse"])
        capsys.readouterr()

    def test_without_the_extra_it_says_how_to_get_it(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.delitem(sys.modules, "scenet.mcp", raising=False)
        monkeypatch.setitem(sys.modules, "mcp", None)
        monkeypatch.setitem(sys.modules, "mcp.server", None)
        assert main(["mcp"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "pip install 'scenet[mcp]'" in captured.err

    def test_an_unrelated_import_failure_is_not_disguised(self, monkeypatch: pytest.MonkeyPatch):
        """Only a missing `mcp` means a missing extra; anything else is a real bug."""

        def broken(name: str) -> None:
            raise ImportError("something else entirely", name="not_mcp")

        monkeypatch.setattr(importlib, "import_module", broken)
        with pytest.raises(ImportError, match="something else"):
            main(["mcp"])


class TestServeCallsTheSdk:
    def test_it_starts_the_server_with_the_transport_and_options(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        started: list[tuple[str, dict[str, Any]]] = []

        class Recorder:
            def run(self, transport: str, **options: Any) -> None:
                started.append((transport, options))

        monkeypatch.setattr(scenet_mcp, "build_server", Recorder)
        scenet_mcp.serve("streamable-http", host="127.0.0.1", port=8000)
        assert started == [("streamable-http", {"host": "127.0.0.1", "port": 8000})]


class TestRegistryManifest:
    """`server.json` points the MCP registry at the PyPI package, and must agree with it.

    Validated against the registry's own schema when written; these hold the parts that
    drift -- the version on every release, the launch command whenever the extra changes.
    """

    ROOT = Path(__file__).resolve().parents[1]

    @pytest.fixture(scope="class")
    @classmethod
    def manifest(cls) -> dict[str, Any]:
        return json.loads((cls.ROOT / "server.json").read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    @classmethod
    def project(cls) -> dict[str, Any]:
        return tomllib.loads((cls.ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    def test_the_versions_match_the_package(
        self, manifest: dict[str, Any], project: dict[str, Any]
    ):
        """Release bumps `project.version`; `server.json` has to move with it."""
        assert manifest["version"] == project["version"]
        assert {package["version"] for package in manifest["packages"]} == {project["version"]}

    def test_the_readme_proves_ownership_of_the_name(self, manifest: dict[str, Any]):
        """The registry checks for this marker in the PyPI description, which is the README."""
        readme = (self.ROOT / "README.md").read_text(encoding="utf-8")
        assert f"<!-- mcp-name: {manifest['name']} -->" in readme

    def test_the_launch_installs_the_extra(self, manifest: dict[str, Any], project: dict[str, Any]):
        (package,) = manifest["packages"]
        assert package["identifier"] == project["name"]
        (runtime,) = package["runtimeArguments"]
        assert (runtime["name"], runtime["value"]) == (
            "--with",
            *project["optional-dependencies"]["mcp"],
        )
        assert [argument["value"] for argument in package["packageArguments"]] == ["mcp"]

    def test_the_description_fits_the_registry(self, manifest: dict[str, Any]):
        assert 0 < len(manifest["description"]) <= 100


class TestFilesBesideTheDocument:
    """A server never reads a folder of its own, so the files a document names come with it.

    `files` maps the path the document writes to the file's bytes in base64. It stands in
    for the document's folder, for a picture behind the cast and for a font alike, and is
    read in memory: nothing is written to the server's disk.
    """

    PAINTED = "cast: {alice: {reference: alice}}\nsetting: {image: art/street.png}\n"

    def test_with_no_files_a_named_picture_is_a_finding(self):
        report = json.loads(text_of(call("validate", {"source": self.PAINTED})))
        assert [finding["rule"] for finding in report["findings"]] == ["scenet/image-file"]

    def test_with_its_files_it_is_valid(self):
        files = {"./art/street.png": base64.b64encode(tiny_png()).decode("ascii")}
        report = json.loads(text_of(call("validate", {"source": self.PAINTED, "files": files})))
        assert report["valid"] is True

    def test_compile_records_the_picture(self):
        files = {"art/street.png": base64.b64encode(tiny_png()).decode("ascii")}
        result = call("compile", {"source": self.PAINTED, "files": files})
        assert not result.is_error
        core = json.loads(text_of(result))["panels"][0]["core"]
        assert core["backdrop"]["image"]["href"] == "art/street.png"

    def test_render_embeds_it_as_build_does_with_embed_images(self):
        files = {"art/street.png": base64.b64encode(tiny_png()).decode("ascii")}
        result = call("render", {"source": self.PAINTED, "files": files})
        assert not result.is_error
        (svg,) = TestRender.resources(result)
        compiled = compile_source(self.PAINTED, base={"art/street.png": tiny_png()})
        assert svg.text == render(compiled.core, embed=compiled.images)
        assert "data:image/png;base64," in svg.text

    def test_a_font_comes_the_same_way(self):
        face = Path(fonts.ttf.SourceSansProSemibold).read_bytes()  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
        source = (
            "cast: {alice: {reference: alice}}\nlettering: {font: fonts/Comic.ttf}\n"
            "script: [{say: {by: alice, text: Hi}}]\n"
        )
        files = {"fonts/Comic.ttf": base64.b64encode(face).decode("ascii")}
        assert not call("render", {"source": source, "files": files}).is_error

    @pytest.mark.parametrize(
        "files",
        [
            {"art/street.png": "not base64!"},
            {"/srv/art/street.png": "AAAA"},
            {"art\\street.png": "AAAA"},
        ],
    )
    def test_a_file_that_cannot_be_taken_is_a_tool_error(self, files: dict[str, str]):
        result = call("validate", {"source": self.PAINTED, "files": files})
        assert result.is_error
        assert "files" in text_of(result)


class TestFiguresAPictureDraws:
    """A cast of figures needs its picture's artwork contract, which comes in `files` (#71)."""

    SOURCE = (
        "cast: {ana: {figure: ana}}\nsetting: {image: art/p.png}\n"
        "script: [{say: {by: ana, text: Hello.}}]\n"
    )

    def _files(self, size: tuple[int, int] = (3, 2)) -> dict[str, str]:
        ana = {"face": {"center": [1, 1], "radius": 0.5}, "mouth": [1, 1.5]}
        return {
            "art/p.png": base64.b64encode(tiny_png()).decode("ascii"),
            "art/p.art.yaml": base64.b64encode(contract(size, {"ana": ana})).decode("ascii"),
        }

    def test_with_the_contract_it_is_valid_and_compiles(self):
        files = self._files()
        report = json.loads(text_of(call("validate", {"source": self.SOURCE, "files": files})))
        assert report["valid"] is True
        result = call("compile", {"source": self.SOURCE, "files": files})
        core = json.loads(text_of(result))["panels"][0]["core"]
        assert core["figures"][0]["actor"] == "ana"

    def test_without_it_the_finding_is_at_the_line_naming_the_picture(self):
        files = self._files()
        del files["art/p.art.yaml"]
        report = json.loads(text_of(call("validate", {"source": self.SOURCE, "files": files})))
        (finding,) = report["findings"]
        assert finding["rule"] == "scenet/artwork-contract"
        assert finding["line"] == 2
        assert "art/p.art.yaml" in finding["message"]

    def test_a_fault_inside_it_names_its_line_in_the_message(self):
        files = self._files(size=(6, 4))
        report = json.loads(text_of(call("validate", {"source": self.SOURCE, "files": files})))
        (finding,) = report["findings"]
        assert finding["line"] == 2
        assert "'art/p.art.yaml', line 1" in finding["message"]

    def test_the_spec_pack_says_where_figures_come_from(self):
        characters = text_of(call("get_spec", {"section": "characters"}))
        assert "figure: <name>" in characters
        assert "art/p01.art.yaml" in characters


class TestRenderForImageModels:
    """`render` with `conditioning`: five more resources per panel, still five tools (#72)."""

    def test_none_unless_asked(self):
        uris = [svg.uri for svg in TestRender.resources(call("render", {"source": PAGED}))]
        assert not any(uri.endswith((".json", ".depth.svg", ".mask.svg")) for uri in uris)

    def test_five_per_panel_after_the_pages(self):
        result = call("render", {"source": PAGED, "conditioning": True})
        found = TestRender.resources(result)
        assert [item.uri for item in found] == [
            "scenet://panels/first.svg",
            "scenet://panels/second.svg",
            "scenet://pages/1.svg",
            *(
                f"scenet://panels/{name}{suffix}"
                for name in ("first", "second")
                for suffix in (
                    ".pose.json",
                    ".boxes.json",
                    ".depth.svg",
                    ".mask.svg",
                    ".semantics.json",
                )
            ),
        ]
        types = {item.uri.rsplit(".", 1)[-1]: item.mime_type for item in found}
        assert types == {"svg": "image/svg+xml", "json": "application/json"}

    def test_each_is_what_build_writes(self):
        found = TestRender.resources(call("render", {"source": VALID, "conditioning": True}))
        exports = render_conditioning(compile_source(VALID).core)
        texts = {item.uri.rsplit("/", 1)[-1]: item.text for item in found}
        for suffix, text in exports.files():
            assert next(value for key, value in texts.items() if key.endswith(suffix)) == text

    def test_the_summary_says_so(self):
        result = call("render", {"source": SCENE, "conditioning": True})
        assert isinstance(result.content[0], TextContent)
        assert "image models" in result.content[0].text
