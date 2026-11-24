"""Reading the files a document names: bounded, regular files only, optionally contained (#379).

A document names pictures, fonts, puppets and artwork contracts by relative path, and may
climb out of its folder with `..` on purpose. What it may not do any more:

- name something that is not a regular file -- a folder, a device, a pipe -- which hung or
  exhausted memory;
- name a file larger than Scenet reads (`scenet.limits`), which was read whole;
- carry a PNG whose image data inflates past what its header says, which was decompressed
  whole when building a PDF;
- under `--root` (`root=` in the API), reach any file outside that folder, through `..` or a
  symbolic link;
- have a file it names quoted back in a message, when that file was read from disk.

Each is a finding of the read's own rule, located where the document names the file, and
each is reached within a fixed time.
"""

import os
import struct
import subprocess
import sys
import time
import zlib
from collections.abc import Callable
from pathlib import Path

import fonts.ttf
import pytest

import scenet.lettering
import scenet.limits
from scenet.cli import main
from scenet.diagnostics import Diagnostic, diagnose_file, diagnose_source
from scenet.errors import PanelSyntaxError
from scenet.lettering import load_font
from scenet.paths import MARKER, OutsideRootError
from scenet.pipeline import compile_book_file, compile_file
from tests.images import PNG_SIGNATURE, chunk, tiny_png
from tests.puppets import KID, kid

CAST = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
FONT = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[missing-attribute]  # pyright: ignore[reportAttributeAccessIssue]

#: However a bound is reached, it is reached at once.
SECONDS = 10


def _document(folder: Path, line: str, name: str = "p.panel.yaml") -> Path:
    path = folder / name
    path.write_text(f"{CAST}{line}\n", encoding="utf-8")
    return path


def _only(found: list[Diagnostic]) -> Diagnostic:
    (finding,) = found
    return finding


def _can_symlink(tmp_path: Path) -> bool:
    try:
        (tmp_path / "probe").symlink_to(tmp_path)
    except OSError:
        return False
    (tmp_path / "probe").unlink()
    return True


class TestOnlyRegularFiles:
    def test_a_folder_named_as_a_picture(self, tmp_path: Path):
        (tmp_path / "art" / "street.png").mkdir(parents=True)
        finding = _only(diagnose_file(_document(tmp_path, "setting: {image: art/street.png}")))
        assert finding.rule == "image-file"
        assert finding.message == (
            "image file 'art/street.png' is not a regular file; a folder, a device or a pipe "
            "is never read"
        )

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
    def test_a_pipe_named_as_a_font_does_not_hang(self, tmp_path: Path):
        """Opening a pipe for reading waits for a writer that never comes: it is never opened.

        In a process of its own, so that a hang fails the test instead of the suite.
        """
        if sys.platform == "win32":
            pytest.skip("no named pipes here")
        (tmp_path / "fonts").mkdir()
        os.mkfifo(tmp_path / "fonts" / "pipe.ttf")
        document = _document(tmp_path, "lettering: {font: fonts/pipe.ttf}")
        run = subprocess.run(  # noqa: S603 -- our own interpreter, on a file written here
            [sys.executable, "-m", "scenet.cli", "check", str(document)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        assert run.returncode == 1
        assert "font-file: font file 'fonts/pipe.ttf' is not a regular file" in run.stderr

    def test_a_link_to_an_endless_device_named_as_a_puppet(self, tmp_path: Path):
        """`/dev/zero` never ends: read whole, it was memory until there was none."""
        if not Path("/dev/zero").exists() or not _can_symlink(tmp_path):
            pytest.skip("no endless device to link to")
        (tmp_path / "puppets").mkdir()
        (tmp_path / "puppets" / "zero.puppet.yaml").symlink_to("/dev/zero")
        document = tmp_path / "p.panel.yaml"
        document.write_text(
            "cast: {pip: {reference: puppets/zero.puppet.yaml}}\n"
            "script: [{say: {by: pip, text: Hi.}}]\n",
            encoding="utf-8",
        )
        # Within the default root, the link leads out of it; within the whole file system,
        # which `--root /` reads, it is a device. Refused, at once, either way.
        for root, said in (
            (None, "is outside the root folder"),
            (Path("/"), "is not a regular file"),
        ):
            started = time.monotonic()
            finding = _only(diagnose_file(document, root=root))
            assert time.monotonic() - started < SECONDS
            assert finding.rule == "puppet-file"
            assert said in finding.message

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows names a device in every folder")
    def test_a_device_named_as_a_font_on_windows(self, tmp_path: Path):
        document = _document(tmp_path, "lettering: {font: fonts/NUL}")
        (tmp_path / "fonts").mkdir()
        finding = _only(diagnose_file(document))
        assert finding.rule == "font-file"
        # The device is no file in the folder at all: its name leads out of it.
        assert "is outside the root folder" in finding.message

    def test_a_document_that_is_not_a_regular_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        folder = tmp_path / "p.panel.yaml"
        folder.mkdir()
        assert main(["build", str(folder)]) == 1
        assert capsys.readouterr().err == f"scenet: {folder}: not a regular file\n"


class TestABoundOnSize:
    @pytest.mark.parametrize(
        ("line", "limit", "rule", "what"),
        [
            ("setting: {image: art/big.png}", "IMAGE_BYTES", "image-file", "image"),
            ("lettering: {font: art/big.png}", "FONT_BYTES", "font-file", "font"),
        ],
    )
    def test_a_file_over_the_limit_is_refused_without_reading_it(
        self, tmp_path: Path, line: str, limit: str, rule: str, what: str
    ):
        """A sparse file far past the bound is refused by its size, before a byte is read."""
        (tmp_path / "art").mkdir()
        bound = getattr(scenet.limits, limit)
        with (tmp_path / "art" / "big.png").open("wb") as big:
            big.truncate(bound * 8)
        started = time.monotonic()
        finding = _only(diagnose_file(_document(tmp_path, line)))
        assert time.monotonic() - started < SECONDS
        assert finding.rule == rule
        assert finding.message == (
            f"{what} file 'art/big.png' is larger than {scenet.limits.describe(bound)}, the most "
            f"Scenet reads of one {what} file"
        )

    def test_one_byte_over_is_over(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scenet.limits, "IMAGE_BYTES", len(tiny_png()) - 1)
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(tiny_png())
        finding = _only(diagnose_file(_document(tmp_path, "setting: {image: art/a.png}")))
        assert "is larger than" in finding.message

    def test_at_the_limit_is_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scenet.limits, "IMAGE_BYTES", len(tiny_png()))
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(tiny_png())
        assert diagnose_file(_document(tmp_path, "setting: {image: art/a.png}")) == []

    def test_a_puppet_file_has_the_text_bound(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(scenet.limits, "DOCUMENT_BYTES", len(KID.encode()) - 1)
        (tmp_path / "puppets").mkdir()
        (tmp_path / "puppets" / "kid.puppet.yaml").write_text(KID, encoding="utf-8")
        document = tmp_path / "p.panel.yaml"
        document.write_text(
            "cast: {kid: {reference: puppets/kid.puppet.yaml}}\n"
            "script: [{say: {by: kid, text: Hi.}}]\n",
            encoding="utf-8",
        )
        finding = _only(diagnose_file(document))
        assert finding.rule == "puppet-file"
        assert "is larger than" in finding.message

    def test_files_sent_in_memory_have_the_same_bound(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(scenet.limits, "IMAGE_BYTES", 10)
        found = diagnose_source(
            f"{CAST}setting: {{image: art/a.png}}\n", base={"art/a.png": tiny_png()}
        )
        assert _only(found).message.startswith("image file 'art/a.png' is larger than 10 bytes")

    def test_a_document_over_the_bound(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(scenet.limits, "DOCUMENT_BYTES", 16)
        document = _document(tmp_path, "")
        for command in ("build", "check"):
            assert main([command, str(document)]) == 1
            assert capsys.readouterr().err == (
                f"scenet: {document}: larger than 16 bytes, the most Scenet reads of a document\n"
            )

    @pytest.mark.parametrize(
        ("size", "said"),
        [
            (1, "1 byte"),
            (10, "10 bytes"),
            (2048, "2 KiB"),
            (8 * 2**20, "8 MiB"),
            (3 * 2**30, "3 GiB"),
        ],
    )
    def test_a_bound_is_said_in_words(self, size: int, said: str):
        assert scenet.limits.describe(size) == said

    def test_every_bound_is_generous_for_a_real_comic(self):
        """A 600 dpi A4 page as a PNG, a CJK font, a long script: each fits."""
        assert scenet.limits.IMAGE_BYTES >= 100 * 2**20
        assert scenet.limits.FONT_BYTES >= 32 * 2**20
        assert scenet.limits.DOCUMENT_BYTES >= 4 * 2**20


def _png(width: int, height: int, colour: int, raw: bytes, *, depth: int = 8) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class TestADecompressionBomb:
    """A PNG with alpha is decoded for print; its data inflates to exactly what its header
    says, or the print is refused, and no more than that is ever inflated."""

    @pytest.fixture
    def comic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "art").mkdir()
        _document(tmp_path, "setting: {image: art/a.png}")
        return tmp_path

    def _build(self, comic: Path, picture: bytes) -> tuple[int, float]:
        (comic / "art" / "a.png").write_bytes(picture)
        started = time.monotonic()
        status = main(["build", "p.panel.yaml", "--pdf", "--quiet"])
        return status, time.monotonic() - started

    def test_data_that_inflates_past_its_header(
        self, comic: Path, capsys: pytest.CaptureFixture[str]
    ):
        """One RGBA pixel is five bytes; this inflates to 256 MiB of zeros."""
        bomb = _png(1, 1, 6, bytes(256 * 2**20))
        assert len(bomb) < 2**20
        status, seconds = self._build(comic, bomb)
        assert status == 1
        assert seconds < SECONDS
        assert capsys.readouterr().err == (
            "scenet: art/a.png is a PNG whose image data inflates past the 1 by 1 pixels its "
            "header gives\n"
        )
        assert not (comic / "p.pdf").exists()

    def test_data_that_falls_short_of_its_header(
        self, comic: Path, capsys: pytest.CaptureFixture[str]
    ):
        short = _png(4, 4, 6, bytes(1 + 16))
        assert self._build(comic, short)[0] == 1
        assert capsys.readouterr().err == (
            "scenet: art/a.png is a PNG whose image data falls short of the 4 by 4 pixels its "
            "header gives\n"
        )

    def test_exactly_its_header_prints(self, comic: Path):
        rows = b"".join(bytes([0]) + bytes([9, 9, 9, 255] * 3) for _ in range(2))
        assert self._build(comic, _png(3, 2, 6, rows))[0] == 0

    @pytest.mark.parametrize(("colour", "depth"), [(5, 8), (7, 8), (2, 4), (3, 16), (0, 3)])
    def test_a_colour_type_or_depth_png_has_not_is_refused(
        self, comic: Path, colour: int, depth: int, capsys: pytest.CaptureFixture[str]
    ):
        """It was a `KeyError` from inside the PDF writer: an internal error, for a bad file."""
        status, _ = self._build(comic, _png(1, 1, colour, b"\0\0", depth=depth))
        err = capsys.readouterr().err
        assert status == 1
        assert "internal error" not in err
        assert err == (
            f"scenet: art/a.png is a PNG of colour type {colour} at {depth} bits, which PNG "
            "does not define\n"
        )


@pytest.fixture
def climbing(tmp_path: Path) -> Path:
    """A document in `comic/` naming a picture in `shared/`, beside it."""
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "sky.png").write_bytes(tiny_png())
    (tmp_path / "comic").mkdir()
    return _document(tmp_path / "comic", "setting: {image: ../shared/sky.png}")


OUTSIDE = (
    "image file '../shared/sky.png' is outside the root folder, the only one this compile "
    "reads from; an empty scenet.toml in a folder that holds both, or a wider --root, lets it in"
)


class TestTheDefaultRoot:
    """With no root named, a document reads within the nearest folder at or above its own
    that holds a `scenet.toml`, or else within its own folder (#432)."""

    def test_a_document_may_not_climb_out_of_its_folder(self, climbing: Path):
        finding = _only(diagnose_file(climbing))
        assert finding.rule == "image-file"
        assert finding.message == OUTSIDE

    def test_compile_file_and_compile_book_file_refuse_it(self, climbing: Path):
        for compile_ in (compile_file, compile_book_file):
            with pytest.raises(PanelSyntaxError, match="outside the root folder"):
                compile_(climbing)

    def test_an_empty_marker_above_lets_it_in(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        assert diagnose_file(climbing) == []
        compile_file(climbing)

    def test_a_marker_of_comments_only_is_empty(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text(
            "# the top of the comic\n\n# fonts and puppets are shared below\n", encoding="utf-8"
        )
        assert diagnose_file(climbing) == []

    def test_the_nearest_marker_decides(self, climbing: Path):
        """One in the document's own folder is nearer than one above, and holds less."""
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        (climbing.parent / MARKER).write_text("", encoding="utf-8")
        assert _only(diagnose_file(climbing)).message == OUTSIDE

    def test_a_marker_that_holds_a_key_is_not_yet(self, climbing: Path):
        marker = climbing.parent.parent / MARKER
        marker.write_text("# the root\n\nfonts = 'shared'\n", encoding="utf-8")
        finding = _only(diagnose_file(climbing))
        assert finding.rule == "not-yet"
        assert finding.source == marker
        assert finding.region is not None
        assert finding.region.start.line == 3
        assert finding.message == (
            "scenet.toml holds 'fonts', and a scenet.toml holds nothing yet: it marks the root "
            "of a project, and what it may say is kept for a later version of Scenet"
        )
        with pytest.raises(PanelSyntaxError, match="holds nothing yet"):
            compile_file(climbing)

    def test_a_marker_that_is_not_toml(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text("[unclosed\n", encoding="utf-8")
        finding = _only(diagnose_file(climbing))
        assert finding.rule == "syntax"
        assert finding.message.startswith("scenet.toml is not TOML")

    def test_the_marker_is_a_dependency_and_a_refused_file_is_not(self, climbing: Path):
        read: set[Path] = set()
        with pytest.raises(PanelSyntaxError):
            compile_book_file(climbing, dependencies=read)
        assert (climbing.parent.parent / "shared" / "sky.png").resolve() not in read
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        read.clear()
        compile_book_file(climbing, dependencies=read)
        assert (climbing.parent.parent / MARKER).resolve() in read
        assert (climbing.parent.parent / "shared" / "sky.png").resolve() in read

    def test_nothing_outside_is_looked_at_by_a_path_that_says_it_leaves(
        self, climbing: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The lexical test comes first: a path that says it leaves is never resolved."""
        resolve = Path.resolve

        def watched(path: Path, strict: bool = False) -> Path:
            assert "sky.png" not in path.name, "a path outside the root was resolved"
            return resolve(path, strict=strict)

        monkeypatch.setattr(Path, "resolve", watched)
        assert _only(diagnose_file(climbing)).message == OUTSIDE

    def test_text_with_a_source_finds_the_marker_too(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        text = climbing.read_text(encoding="utf-8")
        assert diagnose_source(text, source=climbing) == []

    def test_a_base_folder_is_its_own_root_and_no_marker_is_looked_for(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        text = climbing.read_text(encoding="utf-8")
        assert _only(diagnose_source(text, base=climbing.parent)).message == OUTSIDE
        assert diagnose_source(text, base=climbing.parent, root=climbing.parent.parent) == []

    def test_a_mapping_is_its_own_root(self):
        found = diagnose_source(
            f"{CAST}setting: {{image: ../shared/sky.png}}\n",
            base={"../shared/sky.png": tiny_png()},
        )
        assert _only(found).message == OUTSIDE

    def test_a_symbolic_link_out_of_the_folder(self, tmp_path: Path):
        if not _can_symlink(tmp_path):
            pytest.skip("symbolic links need a privilege here")
        (tmp_path / "secret.png").write_bytes(tiny_png())
        (tmp_path / "comic" / "art").mkdir(parents=True)
        (tmp_path / "comic" / "art" / "a.png").symlink_to(tmp_path / "secret.png")
        document = _document(tmp_path / "comic", "setting: {image: art/a.png}")
        assert _only(diagnose_file(document)).message.startswith(
            "image file 'art/a.png' is outside the root folder"
        )
        assert diagnose_file(document, root=tmp_path) == []

    def test_a_symbolic_link_within_the_folder(self, tmp_path: Path):
        if not _can_symlink(tmp_path):
            pytest.skip("symbolic links need a privilege here")
        (tmp_path / "comic" / "art").mkdir(parents=True)
        (tmp_path / "comic" / "art" / "real.png").write_bytes(tiny_png())
        (tmp_path / "comic" / "art" / "a.png").symlink_to(tmp_path / "comic" / "art" / "real.png")
        assert diagnose_file(_document(tmp_path / "comic", "setting: {image: art/a.png}")) == []

    @pytest.mark.parametrize(
        ("line", "file", "rule"),
        [
            ("lettering: {font: ../fonts/a.ttf}", "fonts/a.ttf", "font-file"),
            ("setting: {image: ../art/a.png}", "art/a.png", "image-file"),
        ],
    )
    def test_every_kind_of_file(self, tmp_path: Path, line: str, file: str, rule: str):
        (tmp_path / file).parent.mkdir(parents=True)
        (tmp_path / file).write_bytes(FONT.read_bytes() if rule == "font-file" else tiny_png())
        (tmp_path / "comic").mkdir()
        document = _document(tmp_path / "comic", line)
        assert _only(diagnose_file(document)).rule == rule
        assert diagnose_file(document, root=tmp_path) == []

    def test_a_puppet_file(self, tmp_path: Path):
        (tmp_path / "puppets").mkdir()
        (tmp_path / "puppets" / "kid.puppet.yaml").write_text(KID, encoding="utf-8")
        (tmp_path / "comic").mkdir()
        document = tmp_path / "comic" / "p.panel.yaml"
        document.write_text(
            "cast: {kid: {reference: ../puppets/kid.puppet.yaml}}\n"
            "script: [{say: {by: kid, text: Hi.}}]\n",
            encoding="utf-8",
        )
        assert _only(diagnose_file(document)).rule == "puppet-file"
        assert diagnose_file(document, root=tmp_path) == []

    def test_the_finding_names_no_absolute_path(self, climbing: Path):
        message = _only(diagnose_file(climbing)).message
        assert str(climbing.parent) not in message
        assert climbing.parent.as_posix() not in message


class TestANamedRoot:
    def test_a_wider_root_lets_it_in(self, climbing: Path):
        assert diagnose_file(climbing, root=climbing.parent.parent) == []

    def test_the_top_of_the_file_system_reads_what_0_13_read(self, climbing: Path):
        assert diagnose_file(climbing, root=Path(climbing.anchor)) == []

    def test_a_named_root_wins_over_a_marker(self, climbing: Path):
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        assert _only(diagnose_file(climbing, root=climbing.parent)).message == OUTSIDE

    def test_a_root_that_does_not_hold_the_document_is_refused(self, climbing: Path):
        elsewhere = climbing.parent.parent / "shared"
        for call in (compile_file, compile_book_file, diagnose_file):
            with pytest.raises(OutsideRootError, match="outside its root folder"):
                call(climbing, root=elsewhere)


class TestTheCommandLineRoot:
    @pytest.mark.parametrize("command", ["build", "check"])
    def test_a_climb_is_refused_by_default(
        self, command: str, climbing: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert main([command, str(climbing)]) == 1
        assert OUTSIDE in capsys.readouterr().err

    @pytest.mark.parametrize("command", ["build", "check"])
    def test_a_wider_root_or_a_marker_lets_it_in(self, command: str, climbing: Path):
        assert main([command, str(climbing), "--root", str(climbing.parent.parent), "--quiet"]) == 0
        assert main([command, str(climbing), "--root", climbing.anchor, "--quiet"]) == 0
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        assert main([command, str(climbing), "--quiet"]) == 0

    def test_a_watch_keeps_its_root(
        self, climbing: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        def once(_dependencies: object, rebuild: Callable[[], None]) -> None:
            rebuild()

        monkeypatch.setattr("scenet.cli.watch_loop", once)
        assert main(["build", str(climbing), "--watch", "--root", str(climbing.parent)]) == 1
        assert capsys.readouterr().err.count(OUTSIDE) == 2  # the first build, and the rebuild

    def test_a_watch_watches_the_marker(self, climbing: Path, monkeypatch: pytest.MonkeyPatch):
        (climbing.parent.parent / MARKER).write_text("", encoding="utf-8")
        watched: list[set[Path]] = []

        def watch(dependencies: set[Path], _rebuild: Callable[[], None]) -> None:
            watched.append(dependencies)

        monkeypatch.setattr("scenet.cli.watch_loop", watch)
        assert main(["build", str(climbing), "--watch", "--quiet"]) == 0
        assert (climbing.parent.parent / MARKER).resolve() in watched[0]

    @pytest.mark.parametrize("command", ["build", "check"])
    def test_a_root_that_is_not_a_folder_is_a_usage_error(
        self, command: str, climbing: Path, capsys: pytest.CaptureFixture[str]
    ):
        missing = climbing.parent / "nowhere"
        assert main([command, str(climbing), "--root", str(missing)]) == 2
        assert capsys.readouterr().err == f"scenet: --root {missing} is not a folder\n"

    @pytest.mark.parametrize("command", ["build", "check"])
    def test_a_root_that_does_not_hold_the_document_is_a_usage_error(
        self, command: str, climbing: Path, capsys: pytest.CaptureFixture[str]
    ):
        elsewhere = climbing.parent.parent / "shared"
        assert main([command, str(climbing), "--root", str(elsewhere)]) == 2
        assert capsys.readouterr().err == (
            f"scenet: {climbing} is outside --root {elsewhere}, which must hold it\n"
        )


SECRET = "hunter2-the-secret"  # noqa: S105 -- what must never be quoted back, not a password


class TestNoContentQuoted:
    """A file the document names, read from disk, may be one its author never had: what is
    in it is never said back. Its line is enough to find the fault."""

    @pytest.fixture
    def named(self, tmp_path: Path) -> tuple[Path, Path]:
        (tmp_path / "puppets").mkdir()
        document = tmp_path / "p.panel.yaml"
        document.write_text(
            "cast: {kid: {reference: puppets/kid.puppet.yaml}}\n"
            "script: [{say: {by: kid, text: Hi.}}]\n",
            encoding="utf-8",
        )
        return document, tmp_path / "puppets" / "kid.puppet.yaml"

    @pytest.mark.parametrize(
        "content",
        [
            f"{SECRET}\n",
            f"password: {SECRET}\n",
            f"{SECRET}: 1\n",
            f"key: [{SECRET}\n",
            f"key: !{SECRET} x\n",
            f"scenet: {SECRET}\n",
            kid("name: kid", f"name: kid\n{SECRET}: 1"),
            kid("name: kid", f"name: {SECRET}\nscenet: 99"),
        ],
    )
    def test_a_puppet_file(self, named: tuple[Path, Path], content: str):
        document, puppet = named
        puppet.write_text(content, encoding="utf-8")
        for finding in diagnose_file(document):
            assert SECRET not in finding.message
            assert "password" not in finding.message
        with pytest.raises(PanelSyntaxError) as raised:
            compile_file(document)
        assert SECRET not in str(raised.value)

    def test_an_artwork_contract(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(tiny_png())
        (tmp_path / "art" / "a.art.yaml").write_text(
            f"size: [3, 2]\n{SECRET}: 1\n", encoding="utf-8"
        )
        document = tmp_path / "p.panel.yaml"
        document.write_text(
            "cast: {man: {figure: man}}\nsetting: {image: art/a.png}\n"
            "script: [{say: {by: man, text: Hi.}}]\n",
            encoding="utf-8",
        )
        found = diagnose_file(document)
        assert found
        assert all(SECRET not in finding.message for finding in found)

    def test_a_contract_measured_on_another_picture_says_no_size_it_holds(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(tiny_png())
        (tmp_path / "art" / "a.art.yaml").write_text("size: [7919, 7907]\n", encoding="utf-8")
        document = tmp_path / "p.panel.yaml"
        document.write_text(
            "cast: {man: {figure: man}}\nsetting: {image: art/a.png}\n"
            "script: [{say: {by: man, text: Hi.}}]\n",
            encoding="utf-8",
        )
        messages = " ".join(finding.message for finding in diagnose_file(document))
        assert "7919" not in messages
        assert "7907" not in messages
        assert "measured on a picture of another size" in messages

    def test_the_line_is_still_given(self, named: tuple[Path, Path]):
        document, puppet = named
        puppet.write_text(kid("name: kid", f"name: kid\n{SECRET}: 1"), encoding="utf-8")
        finding = _only(diagnose_file(document))
        line = KID.splitlines().index("name: kid") + 2
        assert finding.region is not None
        assert finding.region.start.line == line
        assert f", line {line}: " in finding.message

    def test_a_file_sent_with_the_document_is_its_senders_and_is_quoted(self):
        """Over MCP and in the playground the files are sent with the document: whoever
        sent them has them, and is told which key is wrong."""
        found = diagnose_source(
            "cast: {kid: {reference: puppets/kid.puppet.yaml}}\n"
            "script: [{say: {by: kid, text: Hi.}}]\n",
            base={"puppets/kid.puppet.yaml": kid("name: kid", f"name: kid\n{SECRET}: 1").encode()},
        )
        assert SECRET in _only(found).message


class TestTheFontCache:
    def test_it_holds_a_bounded_number_of_faces(self, tmp_path: Path):
        """A server compiling documents from many users no longer keeps every face it saw."""
        scenet.lettering._BY_CONTENT.clear()
        data = FONT.read_bytes()
        for index in range(scenet.lettering.FONT_CACHE_ENTRIES + 5):
            # Bytes after the last table change the digest, and nothing a reader reads.
            load_font("a.ttf", {"a.ttf": data + bytes(4 * (index + 1))}, loc=())
        assert len(scenet.lettering._BY_CONTENT) == scenet.lettering.FONT_CACHE_ENTRIES

    def test_the_face_used_last_is_kept(self):
        scenet.lettering._BY_CONTENT.clear()
        data = FONT.read_bytes()
        first = load_font("a.ttf", {"a.ttf": data}, loc=())
        for index in range(scenet.lettering.FONT_CACHE_ENTRIES - 1):
            load_font("a.ttf", {"a.ttf": data + bytes(4 * (index + 1))}, loc=())
            assert load_font("a.ttf", {"a.ttf": data}, loc=()) is first
        load_font("a.ttf", {"a.ttf": data + bytes(4096)}, loc=())
        assert load_font("a.ttf", {"a.ttf": data}, loc=()) is first
