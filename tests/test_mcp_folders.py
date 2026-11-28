"""`scenet mcp --root` and `--output`: pictures in, artefacts out, no bytes via the model (#444).

A chat model can write a document and cannot write a 2 MB picture as base64, nor repeat a
page of SVG to hand it over. A server started over stdio may be given two folders:

- `--root DIR`, from which every document sent as text reads the files it names, under the
  containment of #379 and the size limits of #363, through a new `folder` argument;
- `--output DIR`, which lists a sixth tool, `build`, that writes what `scenet build` writes,
  never replaces a file with other contents, and returns each file's path and size, never
  its contents.

Without them the server is what it was: five read-only tools, and no file is opened.
"""

import base64
import hashlib
import json
import multiprocessing
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, EmbeddedResource, ImageContent, ResourceLink, TextContent

import scenet.mcp
from scenet.cli import main
from scenet.mcp import build_server
from tests.images import tiny_png
from tests.under_mutmut import needs_a_clean_child_process

PICTURE = (
    "cast: {alice: {reference: alice}}\n"
    "setting: {image: art/p01.png}\n"
    "script: [{say: {by: alice, text: Hello.}}]\n"
)
PLAIN = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
OTHER = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Goodbye.}}]\n"
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
pages: [{tiers: [{panels: [first, second]}]}]
"""


def text_of(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


def call(
    tool: str,
    arguments: dict[str, Any],
    *,
    root: Path | None = None,
    output: Path | None = None,
    timeout: float | None = None,
) -> CallToolResult:
    """One tool call through a real MCP client session, in process, on a server so started."""

    server = build_server(root=root, output=output, timeout=timeout)

    async def go() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    # A server with a timeout runs its calls in worker processes, each a whole interpreter
    # with the compiler loaded: left open, one outlives the test and starves the shard.
    try:
        return anyio.run(go)
    finally:
        server.close()


def listed(*, root: Path | None = None, output: Path | None = None) -> tuple[str, Any]:
    async def go() -> tuple[str, Any]:
        async with Client(build_server(root=root, output=output)) as client:
            return client.instructions or "", await client.list_tools()

    return anyio.run(go)


def report(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error, text_of(result)
    assert result.structured_content is not None
    return result.structured_content


@pytest.fixture(autouse=True)
def _served(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put back the folders a test's server was built with, which are the module's own.

    `build_server` sets them for the process, as it sets the limits: left behind, the next
    test that calls a tool as a function would read the last test's temporary folder.
    """
    for name in ("limits", "root", "output"):
        monkeypatch.setattr(scenet.mcp._SERVED, name, getattr(scenet.mcp._SERVED, name))


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    """A root with a picture in it, and an empty output folder."""
    root, output = tmp_path / "root", tmp_path / "output"
    (root / "art").mkdir(parents=True)
    output.mkdir()
    (root / "art" / "p01.png").write_bytes(tiny_png())
    return root, output


def tree(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


class TestWhichModeIsActive:
    def test_without_options_it_is_five_tools_and_no_folder(self):
        instructions, tools = listed()
        assert {tool.name for tool in tools.tools} == {
            "get_spec",
            "list_puppets",
            "validate",
            "compile",
            "render",
        }
        for tool in tools.tools:
            properties = tool.input_schema.get("properties", {})
            assert "folder" not in properties, tool.name
            assert "paths" not in properties, tool.name
        assert "folder of files" not in instructions
        assert "output folder" not in instructions

    def test_a_root_adds_folder_to_every_tool_that_reads_files(self, folders: tuple[Path, Path]):
        root, _ = folders
        instructions, tools = listed(root=root)
        by_name = {tool.name: tool for tool in tools.tools}
        assert set(by_name) == {"get_spec", "list_puppets", "validate", "compile", "render"}
        for name in ("validate", "compile", "render", "list_puppets"):
            assert "folder" in by_name[name].input_schema["properties"], name
        assert "paths" in by_name["list_puppets"].input_schema["properties"]
        assert "folder" not in by_name["get_spec"].input_schema.get("properties", {})
        assert "This server was started with a folder of files." in instructions
        assert "output folder" not in instructions
        for tool in tools.tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True, tool.name

    def test_an_output_adds_build_and_says_so(self, folders: tuple[Path, Path]):
        _, output = folders
        instructions, tools = listed(output=output)
        by_name = {tool.name: tool for tool in tools.tools}
        assert set(by_name) == {
            "get_spec",
            "list_puppets",
            "validate",
            "compile",
            "render",
            "build",
        }
        assert "folder" not in by_name["build"].input_schema["properties"]
        assert "build writes the document's SVG files" in instructions
        assert "folder of files" not in instructions
        assert "never replaces a file with other contents" in instructions

    def test_both_give_build_a_folder(self, folders: tuple[Path, Path]):
        root, output = folders
        _, tools = listed(root=root, output=output)
        build = {tool.name: tool for tool in tools.tools}["build"]
        assert "folder" in build.input_schema["properties"]
        assert set(build.input_schema["required"]) == {"source", "name"}

    def test_build_is_the_one_tool_that_writes_and_says_so(self, folders: tuple[Path, Path]):
        _, output = folders
        _, tools = listed(output=output)
        for tool in tools.tools:
            assert tool.annotations is not None
            if tool.name == "build":
                assert tool.annotations.read_only_hint is False
                assert tool.annotations.destructive_hint is False
                assert tool.annotations.idempotent_hint is True
                assert tool.annotations.open_world_hint is False
            else:
                assert tool.annotations.read_only_hint is True, tool.name

    def test_the_descriptions_say_which_mode_they_are_in(self, folders: tuple[Path, Path]):
        root, output = folders
        _, tools = listed(root=root, output=output)
        by_name = {tool.name: tool for tool in tools.tools}
        assert "folder" in by_name["render"].input_schema["properties"]
        folder = by_name["render"].input_schema["properties"]["folder"]["description"]
        assert "chapter-1/art/p01.png" in folder
        assert "never writes" in (by_name["render"].description or "")

    def test_every_new_parameter_is_described(self, folders: tuple[Path, Path]):
        root, output = folders
        _, tools = listed(root=root, output=output)
        for tool in tools.tools:
            for name, schema in tool.input_schema.get("properties", {}).items():
                assert schema.get("description"), f"{tool.name}.{name}"


class TestReadingUnderTheRoot:
    def test_a_picture_on_disk_is_read(self, folders: tuple[Path, Path]):
        root, _ = folders
        found = report(call("validate", {"source": PICTURE}, root=root))
        assert found == {"valid": True, "findings": []}

    def test_without_a_root_the_same_document_is_refused(self):
        found = report(call("validate", {"source": PICTURE}))
        assert [finding["rule"] for finding in found["findings"]] == ["scenet/image-file"]

    def test_the_picture_is_drawn_and_embedded(self, folders: tuple[Path, Path]):
        root, _ = folders
        result = call("render", {"source": PICTURE}, root=root)
        assert not result.is_error
        svg = next(b for b in result.content if isinstance(b, EmbeddedResource))
        text = getattr(svg.resource, "text", "")
        assert "data:image/png;base64," in text

    def test_compile_and_list_puppets_read_the_root(self, folders: tuple[Path, Path]):
        root, _ = folders
        document = PICTURE
        core = json.loads(text_of(call("compile", {"source": document}, root=root)))
        assert core["panels"][0]["core"]["backdrop"]["image"]["href"] == "art/p01.png"

    def test_folder_is_where_the_document_is_saved(self, folders: tuple[Path, Path]):
        root, _ = folders
        (root / "chapter-1" / "art").mkdir(parents=True)
        (root / "chapter-1" / "art" / "p01.png").write_bytes(tiny_png(5, 4))
        (root / "art" / "p01.png").unlink()
        here = report(call("validate", {"source": PICTURE}, root=root))
        assert [f["rule"] for f in here["findings"]] == ["scenet/image-file"]
        there = report(call("validate", {"source": PICTURE, "folder": "chapter-1"}, root=root))
        assert there == {"valid": True, "findings": []}

    def test_a_puppet_file_on_disk_is_listed(self, folders: tuple[Path, Path]):
        from tests.puppets import KID, KID_PATH  # noqa: PLC0415 -- only this test needs it

        root, _ = folders
        (root / "puppets").mkdir()
        (root / KID_PATH).write_text(KID, encoding="utf-8")
        names = [
            puppet["name"]
            for puppet in report(call("list_puppets", {"paths": [KID_PATH]}, root=root))["puppets"]
        ]
        assert names[-1] == KID_PATH
        assert KID_PATH not in [
            puppet["name"] for puppet in report(call("list_puppets", {}, root=root))["puppets"]
        ]

    @pytest.mark.parametrize(
        "written",
        ["../secret.png", "art/../../secret.png", "/etc/hosts", "C:/secret.png", "art\\p01.png"],
    )
    def test_a_path_that_leaves_the_root_is_refused(self, folders: tuple[Path, Path], written: str):
        root, _ = folders
        (root.parent / "secret.png").write_bytes(tiny_png())
        source = PICTURE.replace("art/p01.png", written)
        found = report(call("validate", {"source": source}, root=root))
        assert [finding["rule"] for finding in found["findings"]] == ["scenet/image-file"]
        assert str(root) not in json.dumps(found)

    def test_a_symbolic_link_out_of_the_root_is_refused(self, folders: tuple[Path, Path]):
        root, _ = folders
        secret = root.parent / "secret.png"
        secret.write_bytes(tiny_png())
        try:
            (root / "art" / "link.png").symlink_to(secret)
        except OSError:  # pragma: no cover -- no symbolic links here
            pytest.skip("no symbolic links")
        source = PICTURE.replace("art/p01.png", "art/link.png")
        found = report(call("validate", {"source": source}, root=root))
        (finding,) = found["findings"]
        assert finding["rule"] == "scenet/image-file"
        assert "outside the root" in finding["message"]
        assert str(root) not in finding["message"]

    def test_a_symbolic_link_inside_the_root_is_read(self, folders: tuple[Path, Path]):
        root, _ = folders
        try:
            (root / "art" / "link.png").symlink_to(root / "art" / "p01.png")
        except OSError:  # pragma: no cover
            pytest.skip("no symbolic links")
        source = PICTURE.replace("art/p01.png", "art/link.png")
        assert report(call("validate", {"source": source}, root=root))["valid"] is True

    def test_only_a_regular_file_is_read(self, folders: tuple[Path, Path]):
        root, _ = folders
        (root / "art" / "folder.png").mkdir()
        source = PICTURE.replace("art/p01.png", "art/folder.png")
        (finding,) = report(call("validate", {"source": source}, root=root))["findings"]
        assert "not a regular file" in finding["message"]

    @pytest.mark.parametrize(
        "folder", ["..", "../root", "/etc", "a\\b", "", "chapter-1/../..", "x"]
    )
    def test_a_folder_is_held_to_a_documents_rules_and_to_the_root(
        self, folders: tuple[Path, Path], folder: str
    ):
        root, _ = folders
        result = call("validate", {"source": PICTURE, "folder": folder}, root=root)
        assert result.is_error
        assert "folder" in text_of(result)
        assert str(root) not in text_of(result)

    def test_a_folder_that_is_a_link_out_of_the_root_is_refused(
        self, folders: tuple[Path, Path], tmp_path: Path
    ):
        root, _ = folders
        outside = tmp_path / "outside"
        (outside / "art").mkdir(parents=True)
        (outside / "art" / "p01.png").write_bytes(tiny_png())
        try:
            (root / "elsewhere").symlink_to(outside, target_is_directory=True)
        except OSError:  # pragma: no cover
            pytest.skip("no symbolic links")
        result = call("validate", {"source": PICTURE, "folder": "elsewhere"}, root=root)
        assert result.is_error
        assert str(tmp_path) not in text_of(result)

    def test_the_size_limit_of_a_file_holds(
        self, folders: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ):
        root, _ = folders
        monkeypatch.setattr("scenet.limits.IMAGE_BYTES", 10)
        (finding,) = report(call("validate", {"source": PICTURE}, root=root))["findings"]
        assert finding["rule"] == "scenet/image-file"

    def test_files_and_folder_together_are_refused_naming_both(self, folders: tuple[Path, Path]):
        root, _ = folders
        sent = {"art/p01.png": base64.b64encode(tiny_png()).decode()}
        result = call("validate", {"source": PICTURE, "files": sent, "folder": "art"}, root=root)
        assert result.is_error
        assert "files" in text_of(result)
        assert "folder" in text_of(result)

    def test_files_stand_in_for_the_disk_and_the_disk_is_not_read(self, folders: tuple[Path, Path]):
        root, _ = folders
        # The picture is on disk, and `files` is sent without it: the mapping is the root.
        found = report(call("validate", {"source": PICTURE, "files": {"x.txt": ""}}, root=root))
        assert [f["rule"] for f in found["findings"]] == ["scenet/image-file"]

    def test_files_alone_still_work_under_a_root(self, folders: tuple[Path, Path]):
        root, _ = folders
        (root / "art" / "p01.png").unlink()
        sent = {"art/p01.png": base64.b64encode(tiny_png()).decode()}
        assert report(call("validate", {"source": PICTURE, "files": sent}, root=root))["valid"]

    def test_folder_is_refused_without_a_root(self):
        result = call("validate", {"source": PLAIN, "folder": "."})
        assert result.is_error

    def test_nothing_lists_the_folder(self, folders: tuple[Path, Path]):
        root, _ = folders
        (root / "art" / "other.png").write_bytes(tiny_png())
        _, tools = listed(root=root)
        assert not [t for t in tools.tools if "list" in t.name and t.name != "list_puppets"]
        result = call("list_puppets", {}, root=root)
        assert "other.png" not in json.dumps(result.structured_content)


class TestWhatTheFixSays:
    """The `fix` of a picture finding says whether `files` or the root applies; no command."""

    def fix(self, arguments: dict[str, Any], *, root: Path | None = None) -> str:
        found = report(call("validate", {"source": PICTURE, **arguments}, root=root))
        return found["findings"][0]["fix"]

    def test_text_alone(self):
        fix = self.fix({})
        assert "`files`" in fix
        assert "scenet " not in fix

    def test_files_sent(self):
        fix = self.fix({"files": {"art/other.png": ""}})
        assert "key" in fix
        assert "scenet " not in fix

    def test_a_root(self, folders: tuple[Path, Path]):
        root, _ = folders
        (root / "art" / "p01.png").unlink()
        fix = self.fix({}, root=root)
        assert "<folder>/<path>" in fix
        assert "`files`" in fix
        assert "scenet " not in fix

    def test_an_artwork_contract_finding_names_no_command_either(self, folders: tuple[Path, Path]):
        root, _ = folders
        source = (
            "cast: {ana: {figure: ana}}\nsetting: {image: art/p01.png}\n"
            "script: [{say: {by: ana, text: Hello.}}]\n"
        )
        (finding,) = report(call("validate", {"source": source}, root=root))["findings"]
        assert finding["rule"] == "scenet/artwork-contract"
        assert "scenet " not in finding["fix"]
        assert "<folder>/<path>" in finding["fix"]


class TestBuild:
    def test_it_writes_an_svg_and_a_pdf_and_returns_links(self, folders: tuple[Path, Path]):
        """A model-sized transcript: document text only, no base64, a picture on disk."""
        root, output = folders
        arguments = {"source": PICTURE, "name": "cover", "pdf": True, "embed_images": True}
        result = call("build", arguments, root=root, output=output)
        found = report(result)
        assert [item["path"] for item in found["files"]] == ["cover.svg", "cover.pdf"]
        assert [item["mime_type"] for item in found["files"]] == [
            "image/svg+xml",
            "application/pdf",
        ]
        for item in found["files"]:
            data = (output / item["path"]).read_bytes()
            assert item["size"] == len(data)
            assert item["sha256"] == hashlib.sha256(data).hexdigest()
            assert item["uri"] == (output / item["path"]).resolve().as_uri()
        assert (output / "cover.pdf").read_bytes().startswith(b"%PDF")
        links = [block for block in result.content if isinstance(block, ResourceLink)]
        assert [str(link.uri) for link in links] == [item["uri"] for item in found["files"]]
        assert [link.size for link in links] == [item["size"] for item in found["files"]]

    def test_no_bytes_come_back(self, folders: tuple[Path, Path]):
        root, output = folders
        result = call("build", {"source": PICTURE, "name": "cover"}, root=root, output=output)
        assert not [b for b in result.content if isinstance(b, EmbeddedResource | ImageContent)]
        text = text_of(result)
        assert "cover.svg" in text
        assert "<svg" not in text
        assert "base64" not in text
        assert str(output) not in text

    def test_the_text_names_each_file_with_its_size(self, folders: tuple[Path, Path]):
        _, output = folders
        result = call("build", {"source": PLAIN, "name": "cover", "pdf": True}, output=output)
        text = text_of(result)
        for path in ("cover.svg", "cover.pdf"):
            assert f"{path} ({(output / path).stat().st_size} bytes)" in text

    def test_a_linked_picture_is_copied_beside_the_svg_and_listed(self, folders: tuple[Path, Path]):
        root, output = folders
        found = report(
            call("build", {"source": PICTURE, "name": "cover"}, root=root, output=output)
        )
        assert [item["path"] for item in found["files"]] == ["cover.svg", "art/p01.png"]
        assert found["files"][1]["mime_type"] == "image/png"
        assert (output / "art" / "p01.png").read_bytes() == tiny_png()

    def test_it_is_byte_identical_to_scenet_build(
        self, folders: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        _, output = folders
        flags = {"pdf": True, "strip": True, "core": True, "conditioning": True, "mono": True}
        found = report(
            call(
                "build",
                {"source": SCENE, "name": "book", **flags, "live_text": True},
                output=output,
            )
        )
        document = tmp_path / "doc" / "book.scene.yaml"
        document.parent.mkdir()
        document.write_text(SCENE, encoding="utf-8")
        cli_out = tmp_path / "cli"
        status = main(
            [
                "build",
                str(document),
                "-o",
                str(cli_out / "book.svg"),
                "--pdf",
                "--strip",
                "--core",
                "--conditioning",
                "--mono",
                "--live-text",
                "--quiet",
            ]
        )
        assert status == 0, capsys.readouterr().err
        assert tree(output) == tree(cli_out)
        assert {item["path"] for item in found["files"]} == set(tree(cli_out))

    def test_the_names_are_deterministic(self, folders: tuple[Path, Path]):
        _, output = folders
        found = report(call("build", {"source": SCENE, "name": "book", "pdf": True}, output=output))
        assert [item["path"] for item in found["files"]] == [
            "book.first.svg",
            "book.second.svg",
            "book.page-1.svg",
            "book.pdf",
        ]

    def test_a_second_identical_call_succeeds_and_writes_nothing(self, folders: tuple[Path, Path]):
        _, output = folders
        arguments = {"source": SCENE, "name": "book", "pdf": True}
        first = report(call("build", arguments, output=output))
        for path in output.iterdir():
            os.utime(path, (1_000_000_000, 1_000_000_000))
        second = report(call("build", arguments, output=output))
        assert second == first
        assert {path.stat().st_mtime_ns for path in output.iterdir()} == {1_000_000_000 * 10**9}

    def test_other_contents_under_the_same_name_is_output_exists_and_writes_nothing(
        self, folders: tuple[Path, Path]
    ):
        _, output = folders
        report(call("build", {"source": PLAIN, "name": "cover"}, output=output))
        before = tree(output)
        result = call("build", {"source": OTHER, "name": "cover"}, output=output)
        assert result.is_error
        text = text_of(result)
        assert "output-exists" in text
        assert "cover.svg" in text
        assert "another `name`" in text
        assert str(output) not in text
        assert tree(output) == before

    def test_every_file_is_checked_before_any_is_written(self, folders: tuple[Path, Path]):
        _, output = folders
        (output / "cover.pdf").write_bytes(b"not a pdf")
        result = call("build", {"source": PLAIN, "name": "cover", "pdf": True}, output=output)
        assert result.is_error
        assert "output-exists" in text_of(result)
        assert "cover.pdf" in text_of(result)
        assert tree(output) == {"cover.pdf": b"not a pdf"}

    def test_a_file_that_is_a_folder_is_not_replaced(self, folders: tuple[Path, Path]):
        _, output = folders
        (output / "cover.svg").mkdir()
        result = call("build", {"source": PLAIN, "name": "cover"}, output=output)
        assert result.is_error
        assert "output-exists" in text_of(result)

    @pytest.mark.parametrize(
        "name", ["", "../x", "a/b", "a.b", "a b", "con", "NUL", "Aux", "com1", "LPT9", "-x"]
    )
    def test_a_name_is_an_identifier_and_not_a_device(self, folders: tuple[Path, Path], name: str):
        _, output = folders
        result = call("build", {"source": PLAIN, "name": name}, output=output)
        assert result.is_error
        assert "name" in text_of(result)
        assert tree(output) == {}

    def test_a_document_that_does_not_compile_writes_nothing(self, folders: tuple[Path, Path]):
        _, output = folders
        broken = "cast: {alice: {reference: alice}}\nscript: [{say: {by: bpb, text: Hi}}]\n"
        result = call("build", {"source": broken, "name": "cover"}, output=output)
        assert result.is_error
        assert "scenet/unknown-actor" in text_of(result)
        assert tree(output) == {}

    def test_the_notes_are_returned(self, folders: tuple[Path, Path]):
        _, output = folders
        crowded = (
            "panel: {size: [300, 400]}\ncamera: {shot: close_up}\n"
            "cast: {a: {reference: alice, at: left_edge}, b: {reference: bob, at: right_edge}}\n"
        )
        notes = report(call("build", {"source": crowded, "name": "n"}, output=output))["notes"]
        assert notes
        assert notes[0]["level"] == "note"
        assert notes[0]["rule"] == "scenet/camera-retreated"

    def test_a_script_is_built_too(self, folders: tuple[Path, Path]):
        _, output = folders
        script = "---\ncast: {ALICE: {reference: alice}}\n---\nPANEL 1\nALICE\nHello.\n"
        found = report(
            call("build", {"source": script, "syntax": "script", "name": "s"}, output=output)
        )
        assert found["files"][0]["path"] == "s.1.svg"

    def test_files_are_a_root_for_build_too(self, folders: tuple[Path, Path]):
        _, output = folders
        sent = {"art/p01.png": base64.b64encode(tiny_png()).decode()}
        found = report(
            call(
                "build",
                {"source": PICTURE, "name": "c", "files": sent, "embed_images": True},
                output=output,
            )
        )
        assert [item["path"] for item in found["files"]] == ["c.svg"]

    def test_files_and_folder_are_refused_for_build_too(self, folders: tuple[Path, Path]):
        root, output = folders
        result = call(
            "build",
            {"source": PICTURE, "name": "c", "files": {"a.txt": ""}, "folder": "art"},
            root=root,
            output=output,
        )
        assert result.is_error
        assert tree(output) == {}

    def test_render_never_writes(self, folders: tuple[Path, Path]):
        root, output = folders
        call("render", {"source": PICTURE}, root=root, output=output)
        call("compile", {"source": PICTURE}, root=root, output=output)
        assert tree(output) == {}

    def test_build_runs_in_a_worker_too(self, folders: tuple[Path, Path]):
        root, output = folders
        before = set(multiprocessing.active_children())
        found = report(
            call(
                "build",
                {"source": PICTURE, "name": "w", "embed_images": True},
                root=root,
                output=output,
                timeout=60,
            )
        )
        assert found["files"][0]["path"] == "w.svg"
        assert (output / "w.svg").is_file()
        # The server was closed, and stopped the worker it started.
        assert set(multiprocessing.active_children()) <= before


class TestTheCommand:
    @pytest.fixture
    def started(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        seen: list[dict[str, Any]] = []

        def record(_transport: str, **options: Any) -> None:
            seen.append(options)

        monkeypatch.setattr(scenet.mcp, "serve", record)
        return seen

    def test_both_folders_are_handed_on_resolved(
        self,
        folders: tuple[Path, Path],
        started: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ):
        root, output = folders
        monkeypatch.chdir(root.parent)
        assert main(["mcp", "--root", "root", "--output", "output"]) == 0
        assert started[0]["root"] == root.resolve()
        assert started[0]["output"] == output.resolve()

    def test_neither_is_handed_on_when_not_given(self, started: list[dict[str, Any]]):
        assert main(["mcp"]) == 0
        assert "root" not in started[0]
        assert "output" not in started[0]

    @pytest.mark.parametrize("option", ["--root", "--output"])
    def test_a_folder_that_does_not_exist_is_exit_2(
        self,
        option: str,
        tmp_path: Path,
        started: list[dict[str, Any]],
        capsys: pytest.CaptureFixture[str],
    ):
        assert main(["mcp", option, str(tmp_path / "nowhere")]) == 2
        assert started == []
        assert f"{option} " in capsys.readouterr().err

    @pytest.mark.parametrize("option", ["--root", "--output"])
    def test_a_file_is_not_a_folder(
        self,
        option: str,
        tmp_path: Path,
        started: list[dict[str, Any]],
        capsys: pytest.CaptureFixture[str],
    ):
        (tmp_path / "file").write_text("x")
        assert main(["mcp", option, str(tmp_path / "file")]) == 2
        assert started == []
        assert "is not a folder" in capsys.readouterr().err

    @pytest.mark.parametrize("option", ["--root", "--output"])
    def test_the_http_transport_refuses_both(
        self,
        option: str,
        tmp_path: Path,
        started: list[dict[str, Any]],
        capsys: pytest.CaptureFixture[str],
    ):
        assert main(["mcp", "--transport", "streamable-http", option, str(tmp_path)]) == 2
        assert started == []
        assert "they are for a server on stdio" in capsys.readouterr().err

    def test_the_http_transport_refuses_a_missing_folder_as_a_transport_fault_first(
        self, tmp_path: Path, started: list[dict[str, Any]]
    ):
        argv = ["mcp", "--transport", "streamable-http", "--root", str(tmp_path / "nowhere")]
        assert main(argv) == 2
        assert started == []


@needs_a_clean_child_process
class TestOverARealStdioSession:
    """The installed command, with both folders, spoken to as a client would."""

    def test_a_model_sized_transcript_letters_a_picture_on_disk(self, folders: tuple[Path, Path]):
        root, output = folders
        command = shutil.which("scenet", path=str(Path(sys.executable).parent))
        assert command

        async def go() -> tuple[CallToolResult, CallToolResult]:
            parameters = StdioServerParameters(
                command=command, args=["mcp", "--root", str(root), "--output", str(output)]
            )
            async with Client(parameters) as client:
                checked = await client.call_tool("validate", {"source": PICTURE})
                built = await client.call_tool(
                    "build", {"source": PICTURE, "name": "cover", "pdf": True, "embed_images": True}
                )
                return checked, built

        checked, built = anyio.run(go)
        assert report(checked)["valid"] is True
        found = report(built)
        assert [item["path"] for item in found["files"]] == ["cover.svg", "cover.pdf"]
        assert len(json.dumps(PICTURE)) < 400
        assert (output / "cover.pdf").read_bytes().startswith(b"%PDF")
