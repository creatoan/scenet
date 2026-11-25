"""`scenet.paths`, function by function: each refusal compared whole (#379).

`tests/test_file_reads.py` holds what a document can and cannot make Scenet read, through
the compile and the check. This file holds the readers themselves to their contract: the
rule, the location and the words of every refusal, the region of every fault in a named file,
and the error each lower reader raises -- what a finding is built from, so that a reader that
lost one of them would be caught here rather than in a message somebody reads one day.
"""

import errno
import os
import stat
import tomllib
from pathlib import Path

import pytest

import scenet.limits
from scenet.assets.contract import PuppetFileError, PuppetSpec, load_puppet_file
from scenet.errors import FileReadError, PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.positions import Position, Region
from scenet.paths import (
    FileTooLargeError,
    Folder,
    MarkerError,
    NotRegularFileError,
    _toml_line,
    _unquoted,
    _untagged,
    _whole_line,
    check_relative,
    contained,
    marker_fault,
    read_bounded,
    read_document,
    read_file,
    read_model,
    read_relative,
    resolve_relative,
)
from tests.puppets import KID

LOC = ("cast", "pip", "reference")


def _file(tmp_path: Path, data: bytes, name: str = "f.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


class TestReadBounded:
    def test_a_file_within_its_bound_is_read_whole(self, tmp_path: Path):
        assert read_bounded(_file(tmp_path, b"0123456789"), 10) == b"0123456789"

    def test_with_no_bound_any_size_is_read(self, tmp_path: Path):
        assert read_bounded(_file(tmp_path, bytes(5000)), None) == bytes(5000)

    def test_one_byte_over_is_refused_by_its_size(self, tmp_path: Path):
        path = _file(tmp_path, b"0123456789")
        with pytest.raises(FileTooLargeError) as raised:
            read_bounded(path, 9, what="a font")
        assert raised.value.limit == 9
        assert raised.value.errno == errno.EFBIG
        assert raised.value.strerror == "larger than 9 bytes, the most Scenet reads of a font"
        assert raised.value.filename == str(path)

    def test_a_file_that_grows_after_its_size_was_read_is_refused_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Its size says it fits; what is read says otherwise, and no more than one byte
        past the bound is read to find out."""
        path = _file(tmp_path, bytes(100))
        real = Path.stat

        def small(self: Path, **kwargs: object) -> os.stat_result:
            found = real(self)
            return os.stat_result((found.st_mode, *found[1:6], 5, *found[7:]))

        monkeypatch.setattr(Path, "stat", small)
        with pytest.raises(FileTooLargeError):
            read_bounded(path, 10)
        assert read_bounded(path, 100) == bytes(100)

    def test_the_default_what_is_a_file(self, tmp_path: Path):
        with pytest.raises(FileTooLargeError) as raised:
            read_bounded(_file(tmp_path, b"xx"), 1)
        assert raised.value.strerror == "larger than 1 byte, the most Scenet reads of a file"

    def test_a_missing_file_is_said_in_the_c_librarys_words(self, tmp_path: Path):
        path = tmp_path / "nowhere"
        with pytest.raises(FileNotFoundError) as raised:
            read_bounded(path, 10)
        assert raised.value.errno == errno.ENOENT
        assert raised.value.strerror == os.strerror(errno.ENOENT)
        assert raised.value.filename == str(path)

    def test_a_failure_with_no_errno_is_raised_as_it_came(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        odd = OSError("the system says nothing more")

        def fail(self: Path, **kwargs: object) -> os.stat_result:
            raise odd

        monkeypatch.setattr(Path, "stat", fail)
        with pytest.raises(OSError, match="the system says nothing more") as raised:
            read_bounded(tmp_path / "x", 10)
        assert raised.value is odd

    def test_a_folder_is_not_a_regular_file(self, tmp_path: Path):
        with pytest.raises(NotRegularFileError) as raised:
            read_bounded(tmp_path, 10)
        assert raised.value.errno == errno.EINVAL
        assert raised.value.strerror == "not a regular file"
        assert raised.value.filename == str(tmp_path)

    def test_a_file_swapped_for_something_else_once_opened_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """What it is is asked again of the open file, which cannot be swapped."""
        path = _file(tmp_path, b"data")
        real = os.fstat

        def not_regular(descriptor: int) -> os.stat_result:
            found = real(descriptor)
            mode = (found.st_mode & ~stat.S_IFMT(found.st_mode)) | stat.S_IFIFO
            return os.stat_result((mode, *found[1:]))

        monkeypatch.setattr(os, "fstat", not_regular)
        with pytest.raises(NotRegularFileError):
            read_bounded(path, 10)


class TestReadFile:
    def test_it_takes_a_bound_and_says_what_the_file_is(self, tmp_path: Path):
        with pytest.raises(FileReadError) as raised:
            read_file(_file(tmp_path, b"xy"), limit=1, what="a font")
        assert raised.value.strerror == "larger than 1 byte, the most Scenet reads of a font"

    def test_with_no_bound_it_reads_whole(self, tmp_path: Path):
        assert read_file(_file(tmp_path, bytes(3000))) == bytes(3000)


class TestReadDocument:
    def test_every_line_ending_is_read_as_lf(self, tmp_path: Path):
        assert read_document(_file(tmp_path, b"a\r\nb\rc\n", "d.panel.yaml")) == "a\nb\nc\n"

    @pytest.mark.parametrize("error", [PanelSyntaxError, ScriptSyntaxError])
    def test_bytes_that_are_not_utf8_are_its_syntax_error(
        self, tmp_path: Path, error: type[PanelSyntaxError]
    ):
        path = _file(tmp_path, b"ok\n\xff", "d.panel.yaml")
        with pytest.raises(error) as raised:
            read_document(path, error=error)
        assert type(raised.value) is error
        assert raised.value.rule == "syntax"
        assert raised.value.source == path
        assert str(raised.value.args[0]).endswith(
            ": not UTF-8 text: byte 3 is 0xff; save the file as UTF-8"
        )


class TestCheckRelative:
    @pytest.mark.parametrize(
        ("declared", "said"),
        [
            ("a\x07.png", "the image path 'a\\x07.png' contains U+0007, a control character"),
            ("  ", "the image path is empty"),
            ("/a.png", "the image path '/a.png' is absolute"),
            ("a\\b.png", "the image path 'a\\\\b.png' has a backslash in it"),
        ],
    )
    def test_each_refusal_says_what_and_where(self, declared: str, said: str):
        with pytest.raises(PanelSyntaxError) as raised:
            check_relative(declared, what="image", rule="image-file", loc=LOC)
        assert raised.value.rule == "image-file"
        assert raised.value.loc == LOC
        assert str(raised.value.args[0]).startswith(said)


class TestResolveRelative:
    def test_with_no_folder_it_says_which_file_and_what(self):
        with pytest.raises(PanelSyntaxError) as raised:
            resolve_relative("fonts/a.ttf", None, what="font", rule="font-file", loc=LOC)
        assert raised.value.args[0] == (
            "the font 'fonts/a.ttf' is read from beside the document, and this document has "
            "no folder: it was compiled from text, not from a file"
        )
        assert (raised.value.rule, raised.value.loc) == ("font-file", LOC)

    def test_what_reaches_the_check_of_the_path(self):
        with pytest.raises(PanelSyntaxError, match=r"^the font path is empty$"):
            resolve_relative("", Path("comic"), what="font", rule="font-file")


OUTSIDE = (
    "image file '{}' is outside the root folder, the only one this compile reads from; an "
    "empty scenet.toml in a folder that holds both, or a wider --root, lets it in"
)


def _refusal(declared: str, base: Folder) -> PanelSyntaxError:
    with pytest.raises(PanelSyntaxError) as raised:
        read_relative(declared, base, what="image", rule="image-file", loc=LOC)
    return raised.value


class TestReadRelative:
    @pytest.mark.parametrize("declared", ["..", "../a.png", "art/../../a.png"])
    def test_a_path_that_climbs_out_of_the_files_sent_is_outside(self, declared: str):
        refused = _refusal(declared, {declared: b"x", "a.png": b"x"})
        assert refused.args[0] == OUTSIDE.format(declared)
        assert (refused.rule, refused.loc) == ("image-file", LOC)

    def test_one_that_climbs_out_of_its_folder_is_outside(self, tmp_path: Path):
        (tmp_path / "comic").mkdir()
        _file(tmp_path, b"x", "a.png")
        refused = _refusal("../a.png", tmp_path / "comic")
        assert refused.args[0] == OUTSIDE.format("../a.png")
        assert (refused.rule, refused.loc) == ("image-file", LOC)

    def test_a_named_root_is_the_one_held_to(self, tmp_path: Path):
        (tmp_path / "comic").mkdir()
        _file(tmp_path, b"x", "a.png")
        assert (
            read_relative("../a.png", tmp_path / "comic", what="image", rule="r", root=tmp_path)
            == b"x"
        )
        with contained(tmp_path):
            assert read_relative("../a.png", tmp_path / "comic", what="image", rule="r") == b"x"

    def test_a_file_too_large_on_disk_and_in_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(scenet.limits, "DOCUMENT_BYTES", 2)
        _file(tmp_path, b"xyz", "a.png")
        said = "image file 'a.png' is larger than 2 bytes, the most Scenet reads of one image file"
        for base in (tmp_path, {"a.png": b"xyz"}):
            refused = _refusal("a.png", base)
            assert refused.args[0] == said
            assert (refused.rule, refused.loc) == ("image-file", LOC)

    def test_a_file_not_there_on_disk_and_in_memory(self, tmp_path: Path):
        for base in (tmp_path, {"b.png": b"x"}):
            refused = _refusal("a.png", base)
            assert refused.args[0] == "image file 'a.png' was not found beside the document"
            assert (refused.rule, refused.loc) == ("image-file", LOC)

    def test_a_folder_is_said_as_such(self, tmp_path: Path):
        (tmp_path / "a.png").mkdir()
        refused = _refusal("a.png", tmp_path)
        assert refused.args[0] == (
            "image file 'a.png' is not a regular file; a folder, a device or a pipe is never read"
        )

    def test_what_reaches_the_path_checks(self, tmp_path: Path):
        assert _refusal("", tmp_path).args[0] == "the image path is empty"
        assert _refusal("", {"a": b""}).args[0] == "the image path is empty"


class TestMarkerFault:
    def _marker(self, tmp_path: Path, data: bytes) -> Path:
        return _file(tmp_path, data, "scenet.toml")

    @pytest.mark.parametrize("text", [b"", b"# a comment\n\n   # another, indented\n"])
    def test_nothing_or_comments_is_no_fault(self, tmp_path: Path, text: bytes):
        assert marker_fault(self._marker(tmp_path, text)) is None

    def test_a_key_is_not_yet_on_its_line(self, tmp_path: Path):
        marker = self._marker(tmp_path, b"  # the root\n\nfonts = 'shared'\n")
        fault = marker_fault(marker)
        assert isinstance(fault, MarkerError)
        assert (fault.rule, fault.line, fault.marker, fault.source) == (
            "not-yet",
            3,
            marker,
            marker,
        )
        assert fault.reason == (
            "scenet.toml holds 'fonts', and a scenet.toml holds nothing yet: it marks the root "
            "of a project, and what it may say is kept for a later version of Scenet"
        )

    def test_a_key_on_the_first_line(self, tmp_path: Path):
        fault = marker_fault(self._marker(tmp_path, b"a = 1\n"))
        assert fault is not None
        assert fault.line == 1

    def test_not_toml_is_syntax_on_the_line_it_is_on(self, tmp_path: Path):
        marker = self._marker(tmp_path, b"a = 1\nb = = 2\n")
        fault = marker_fault(marker)
        assert fault is not None
        assert (fault.rule, fault.line, fault.marker) == ("syntax", 2, marker)
        assert fault.reason.startswith("scenet.toml is not TOML: ")
        assert fault.reason.endswith("; it holds nothing yet, so it can be empty")

    def test_not_utf8(self, tmp_path: Path):
        fault = marker_fault(self._marker(tmp_path, b"\xff"))
        assert fault is not None
        assert (fault.rule, fault.line) == ("syntax", 1)
        assert fault.reason == (
            "scenet.toml is not UTF-8 text; it holds nothing yet, so it can be empty"
        )

    def test_one_that_cannot_be_read(self, tmp_path: Path):
        (tmp_path / "scenet.toml").mkdir()
        fault = marker_fault(tmp_path / "scenet.toml")
        assert fault is not None
        assert (fault.rule, fault.line) == ("syntax", 1)
        assert fault.reason == "scenet.toml cannot be read: not a regular file"

    def test_it_has_the_document_bound(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scenet.limits, "DOCUMENT_BYTES", 3)
        fault = marker_fault(self._marker(tmp_path, b"# long\n"))
        assert fault is not None
        assert fault.reason == (
            "scenet.toml cannot be read: larger than 3 bytes, the most Scenet reads of a "
            "scenet.toml"
        )

    def test_the_line_of_a_toml_fault(self):
        for text, line in (("a = 1\nb = = 2\n", 2), ("x = [\n", 1)):
            with pytest.raises(tomllib.TOMLDecodeError) as raised:
                tomllib.loads(text)
            assert _toml_line(raised.value) == line


def _puppet_fault(text: str, base: Folder) -> PuppetFileError:
    with pytest.raises(PuppetFileError) as raised:
        load_puppet_file("p.puppet.yaml", base, loc=LOC)
    return raised.value


@pytest.fixture(params=["sent", "on disk"])
def where(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    return str(request.param)


def _base(where: str, tmp_path: Path, text: str) -> Folder:
    if where == "sent":
        return {"p.puppet.yaml": text.encode("utf-8")}
    (tmp_path / "p.puppet.yaml").write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


class TestReadModel:
    """A fault in a named file: the same file, place and region sent or on disk; quoted only
    when it was sent."""

    def test_not_utf8(self, tmp_path: Path):
        for base in ({"p.puppet.yaml": b"\xff"}, _file(tmp_path, b"\xff", "p.puppet.yaml").parent):
            fault = _puppet_fault("", base)
            assert fault.args[0] == "puppet file 'p.puppet.yaml': it is not UTF-8 text"
            assert (fault.file, fault.inner, fault.region, fault.loc) == (
                "p.puppet.yaml",
                (),
                None,
                LOC,
            )

    def test_a_tag(self, where: str, tmp_path: Path):
        fault = _puppet_fault(
            "", _base(where, tmp_path, KID.replace("name: kid", "name: !!str kid"))
        )
        assert fault.region == Region(
            start=Position(line=2, column=7), end=Position(line=2, column=12)
        )
        if where == "sent":
            assert "'!!str' is a YAML tag" in fault.args[0]
        else:
            assert fault.args[0] == (
                "puppet file 'p.puppet.yaml', line 2: it holds a YAML tag, which Scenet YAML "
                "refuses"
            )

    def test_a_tab_is_not_scenet_yaml(self, where: str, tmp_path: Path):
        fault = _puppet_fault("", _base(where, tmp_path, "name: kid\n\tx: 1\n"))
        assert fault.region == Region(
            start=Position(line=2, column=1), end=Position(line=2, column=2)
        )
        if where == "on disk":
            assert fault.args[0] == "puppet file 'p.puppet.yaml', line 2: it is not Scenet YAML"
        else:
            assert "indented with a tab" in fault.args[0]

    def test_not_yaml_is_its_whole_line(self, where: str, tmp_path: Path):
        fault = _puppet_fault("", _base(where, tmp_path, "name: [kid\n"))
        assert fault.region == _whole_line(2)
        said = "puppet file 'p.puppet.yaml', line 2: it is not valid YAML"
        if where == "sent":
            assert fault.args[0] == f"{said}: expected ',' or ']', but got '<stream end>'"
        else:
            assert fault.args[0] == said

    def test_a_fault_yaml_gives_no_place_of(self):
        """The reader's own errors carry no problem and no mark: described whole."""
        fault = _puppet_fault("", {"p.puppet.yaml": b"name: kid\x07\n"})
        assert fault.region is None
        assert fault.args[0].startswith(
            "puppet file 'p.puppet.yaml': it is not valid YAML: unacceptable character #x0007"
        )

    def test_a_later_language(self, where: str, tmp_path: Path):
        fault = _puppet_fault(
            "", _base(where, tmp_path, KID.replace("name: kid", "scenet: 2\nname: kid"))
        )
        assert (fault.inner, fault.loc) == (("scenet",), LOC)
        assert fault.region == Region(
            start=Position(line=2, column=9), end=Position(line=2, column=10)
        )
        if where == "sent":
            assert "written for Scenet language 2" in fault.args[0]
        else:
            assert fault.args[0] == (
                "puppet file 'p.puppet.yaml', line 2: its `scenet:` is not a language this "
                "Scenet reads"
            )

    def test_an_unknown_key(self, where: str, tmp_path: Path):
        fault = _puppet_fault(
            "", _base(where, tmp_path, KID.replace("name: kid", "name: kid\nsecret: 1"))
        )
        assert fault.inner == ("secret",)
        said = "puppet file 'p.puppet.yaml', line 3: "
        if where == "sent":
            assert fault.args[0] == f"{said}secret: not a key a puppet has here"
        else:
            assert fault.args[0] == f"{said}not a key a puppet has here"

    def test_a_nested_place_is_joined_with_dots(self, tmp_path: Path):
        fault = _puppet_fault("", _base("sent", tmp_path, KID.replace("  eyes: 50", "  eyes: x")))
        assert fault.inner == ("landmarks", "eyes")
        assert fault.args[0].startswith("puppet file 'p.puppet.yaml', line 7: landmarks.eyes: ")

    def test_a_missing_key_is_named(self, tmp_path: Path):
        text = "\n".join(line for line in KID.splitlines() if not line.startswith("units_per_head"))
        fault = _puppet_fault("", _base("on disk", tmp_path, text + "\n"))
        assert fault.args[0].endswith("`units_per_head` is missing here")

    def test_the_root_reaches_the_read(self, tmp_path: Path):
        (tmp_path / "comic").mkdir()
        (tmp_path / "p.puppet.yaml").write_text(KID, encoding="utf-8")
        with pytest.raises(PanelSyntaxError, match="outside the root folder"):
            read_model(
                "../p.puppet.yaml",
                tmp_path / "comic",
                PuppetSpec,
                what="puppet",
                error=PuppetFileError,
                holds="a puppet",
                unknown_key="no",
            )
        puppet, _, _ = read_model(
            "../p.puppet.yaml",
            tmp_path / "comic",
            PuppetSpec,
            what="puppet",
            error=PuppetFileError,
            holds="a puppet",
            unknown_key="no",
            root=tmp_path,
        )
        assert puppet.name == "kid"


class TestUnquoted:
    @pytest.mark.parametrize(
        ("kind", "inner", "said"),
        [
            ("missing", ("units_per_head",), "`units_per_head` is missing here"),
            ("missing", ("poses", 0), "a key is missing here"),
            ("missing", (), "a key is missing here"),
            ("extra_forbidden", ("x",), "UNKNOWN"),
            ("int_type", ("x",), "a value it does not allow here"),
        ],
    )
    def test_what_each_kind_says(self, kind: str, inner: tuple[str | int, ...], said: str):
        assert _unquoted(kind, "UNKNOWN", inner) == said

    def test_a_rule_the_validators_broke(self, tmp_path: Path):
        """A validator's rule is pydantic's `value_error`: a value it does not allow."""
        text = KID.replace("parent: neck, offset: [0, -70]", "parent: nowhere, offset: [0, -70]")
        fault = _puppet_fault("", _base("on disk", tmp_path, text))
        assert fault.args[0].endswith(": a value it does not allow here")


class TestUntagged:
    @pytest.mark.parametrize(
        ("loc", "kept"),
        [
            (("joints", 0, "bone", "x"), ("joints", 0, "x")),
            ((0, "bone"), (0,)),
            (("bone", "x"), ("bone", "x")),
            (("joints", "bone"), ("joints", "bone")),
            (("x", 0, "y"), ("x", 0, "y")),
        ],
    )
    def test_a_tag_after_an_index_is_left_out(
        self, loc: tuple[str | int, ...], kept: tuple[str | int, ...]
    ):
        assert _untagged(loc, frozenset({"bone"})) == kept


def test_a_whole_line_is_a_region():
    assert _whole_line(3) == Region(
        start=Position(line=3, column=1), end=Position(line=4, column=1)
    )


class TestTheRestOfEachReader:
    def test_a_marker_fault_names_its_file(self, tmp_path: Path):
        for data in (b"\xff", b"a = = 1\n"):
            marker = _file(tmp_path, data, "scenet.toml")
            fault = marker_fault(marker)
            assert fault is not None
            assert fault.marker == marker

    def test_a_marker_the_system_will_not_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        marker = _file(tmp_path, b"", "scenet.toml")

        def odd(*_args: object, **_kwargs: object) -> bytes:
            raise OSError("odd")

        monkeypatch.setattr("scenet.paths.read_bounded", odd)
        fault = marker_fault(marker)
        assert fault is not None
        assert fault.marker == marker
        assert fault.reason == "scenet.toml cannot be read: OSError"

    def test_a_file_swapped_once_opened_is_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        path = _file(tmp_path, b"data")
        real = os.fstat

        def not_regular(descriptor: int) -> os.stat_result:
            found = real(descriptor)
            mode = (found.st_mode & ~stat.S_IFMT(found.st_mode)) | stat.S_IFIFO
            return os.stat_result((mode, *found[1:]))

        monkeypatch.setattr(os, "fstat", not_regular)
        with pytest.raises(NotRegularFileError) as raised:
            read_bounded(path, 10)
        assert raised.value.filename == str(path)

    def test_a_file_that_grew_is_named_and_said(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        path = _file(tmp_path, bytes(100))
        real = Path.stat

        def small(self: Path, **kwargs: object) -> os.stat_result:
            found = real(self)
            return os.stat_result((found.st_mode, *found[1:6], 5, *found[7:]))

        monkeypatch.setattr(Path, "stat", small)
        with pytest.raises(FileTooLargeError) as raised:
            read_bounded(path, 10, what="a font")
        assert raised.value.filename == str(path)
        assert raised.value.strerror == "larger than 10 bytes, the most Scenet reads of a font"

    def test_read_file_s_what_is_a_file_by_default(self, tmp_path: Path):
        with pytest.raises(FileReadError) as raised:
            read_file(_file(tmp_path, b"xy"), limit=1)
        assert raised.value.strerror == "larger than 1 byte, the most Scenet reads of a file"

    def test_a_file_sent_at_its_bound_is_read(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scenet.limits, "DOCUMENT_BYTES", 3)
        assert read_relative("a", {"a": b"xyz"}, what="image", rule="r") == b"xyz"
